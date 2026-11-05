#!/usr/bin/env python3
"""
Build align-decoy-kit/v1 zips: decoy_corpus.json + the audio, one zip per locale, importable with our own audio.

The kit keeps four mistake families (BND-MAJOR >= 150 ms, WD, WH, SEG-MERGE); text changes, zero-length chips,
split words and moves under 150 ms are dropped on import. So the mistakes come from the same plan as the
align-decoys/v1 pack (build_pack.plan: decoys from the package that fit are carried over, the rest re-planned),
converted to kit records:
  move   -> BND-MAJOR  (decoy = the word's planted timings)   obvious >= 450 ms A1 · moderate A2 · subtle A3
  remove -> WD         content word A1 · short / function word A2
  add    -> WH         chip inside the pause; over silence A1 · over a breath A2 (measured in the audio)
  join   -> SEG-MERGE  A2
Every clip gets at least one A1 (the platform makes each clip's 1-2 heaviest A1 mistakes must-catch).
Weights: BND-MAJOR 50 points per locale, WD / WH / SEG-MERGE 50/3 each, spread A1 3 : A2 2 : A3 1.
The platform skips clips tagged synthetic_speech, so every clip is written with gold_whole_audio_tag "none" and
all 20 import; which clips really are synthetic is listed in kits/synthetic_files_<locale>.json (not in the zip).

Input  : alignment_decoys/alignment_decoys_<locale>.zip
Output : alignment_decoys/kits/alignment_decoy_kit_<locale>.zip   (decoy_corpus.json + audio/<file_name>)
         alignment_decoys/kits/synthetic_files_<locale>.json     (the clips that are entirely synthetic speech)

Run    : python alignment_decoys/build_kit.py [locale ...]
"""
import json, pathlib, sys, wave, zipfile, io

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
from build_pack import plan, MOVE_CLASSES                       # noqa: E402
from build_alignment_decoys import FUNC, LOCALES               # noqa: E402
from make_japanese import frames_db                             # noqa: E402

KIT_FORMAT = "align-decoy-kit/v1"
KIT_INSTRUCTIONS = [   # verbatim from decoy_corpus.template.json
    "Put this file (named decoy_corpus.json) and the audio files in one .zip. Any folder layout works; each decoy's `file_name` must match one audio file's name (wav, flac, mp3, m4a, ogg, opus, webm).",
    "One record per clip in `decoys` (a bare list of records works too). Clips must be at most 6 minutes long. Only records with status \"ACTIVE\" are imported.",
    "`decoy_id` must be unique and stable: importing the same decoy_id with the same correct alignment again adds nothing.",
    "`locale` is the language key: en, es_ES, de_DE, fr_FR, it_IT, pt_BR, ja_JP, zh_CN, hi_IN or kr_KR. The language must have an aligner.",
    "`gold_segments` is the CORRECT alignment, one entry per word in spoken order: word, start, end in seconds. No zero-length words, no overlaps, at least 8 words. Words starting with [ or < are tags and are never touched.",
    "`injections` are the planted mistakes. `plain_offset` is the index of a word in gold_segments (the first word is 0). Put mistakes on different words, ideally at least 3 words apart.",
    "BND-MAJOR — a moved word edge: plain_offset, edge (\"start\" | \"end\"), decoy {start, end} = that word's planted timings. The edge must move at least 150 ms (aligners get 100 ms tolerance). A neighbour it runs into gives way.",
    "WD — a missing chip: plain_offset of the word that loses its timing (it stays in the transcript).",
    "WH — an extra chip: word (its text), decoy {start, end} inside a pause, inserted_before_index = index of the word right after it (1 or more).",
    "SEG-MERGE — two words in one chip: plain_offset of the first word; it is joined with the next. Space-separated languages only (not ja_JP or zh_CN).",
    "band (A1 obvious, A2 medium, A3 subtle) and weight are yours; each clip's one or two heaviest A1 mistakes become must-catch.",
    "Dropped on import, because aligners here only fix timings: word text changes (WS, G-ACCENT, G-CASE, G-NUM, G-PUNCT), zero-length chips (BND-ZERO), one word split over two chips (SEG-SPLIT), and edges moved under 150 ms. Clips with gold_whole_audio_tag \"synthetic_speech\" are skipped.",
]
GROUP_POINTS = {"BND-MAJOR": 50.0, "WD": 50 / 3, "WH": 50 / 3, "SEG-MERGE": 50 / 3}
BAND_FACTOR = {"A1": 3, "A2": 2, "A3": 1}


def r3(x):
    return round(x + 0.0, 3)


def speech_frames(wav_bytes, W):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        f = frames_db(w.readframes(w.getnframes()))
    v = sorted(x for t in W for x in f[int(round(t["s"] / 0.01)):int(round(t["e"] / 0.01))])
    return f, v[len(v) // 2]


def to_kit(loc, f, wav_bytes):
    """One kit record (without weights / ids) from a planned file."""
    e, W, plants = f["e"], f["W"], f["plants"]
    frames, speech = speech_frames(wav_bytes, W)
    inj = []
    for p in plants:
        src = p["note"].split(" · from ")[1] if " · from " in p["note"] else None
        carried = f"; carried over from {src}" if src else ""
        if p["action"] == "move":
            k, edge, ms = p["word"], p["edge"], p["shift_ms"]
            decoy = {"start": W[k]["s"], "end": W[k]["e"]}
            decoy[edge] = r3(decoy[edge] + ms / 1000)
            cls = next(c for c, lo, hi in MOVE_CLASSES if abs(ms) <= hi)
            band = {"obvious": "A1", "moderate": "A2", "subtle": "A3"}[cls]
            inj.append({"family": "BND-MAJOR", "band": band, "_crit": p.get("critical", False), "_pos": k,
                        "meta": {"plain_offset": k, "word": W[k]["w"], "edge": edge, "decoy": decoy,
                                 "note": f"{edge} {abs(ms)} ms {'early' if ms < 0 else 'late'} ({cls}){carried}"}})
        elif p["action"] == "remove":
            k = p["word"]; w = W[k]["w"]
            band = "A2" if (w in FUNC[loc].split() or len(w) <= 3) else "A1"
            inj.append({"family": "WD", "band": band, "_crit": p.get("critical", False), "_pos": k,
                        "meta": {"plain_offset": k, "word": w, "note": f"{w} has no chip{carried}"}})
        elif p["action"] == "add":
            k = p["after_word"]
            lo, hi = W[k]["e"], W[k + 1]["s"]
            L = min(0.30, hi - lo - 0.16)
            mid = (lo + hi) / 2
            a, b = r3(mid - L / 2), r3(mid + L / 2)
            peak = max(frames[int(round(a / 0.01)):int(round(b / 0.01))] or [-120])
            breath = peak >= speech - 30
            inj.append({"family": "WH", "band": "A2" if breath else "A1", "_crit": p.get("critical", False), "_pos": k + 1,
                        "meta": {"inserted_before_index": k + 1, "word": p["text"], "decoy": {"start": a, "end": b},
                                 "note": f"extra '{p['text']}' over the {hi - lo:.2f} s pause "
                                         f"({'a breath' if breath else 'silence'}) between {W[k]['w']} and {W[k + 1]['w']}{carried}"}})
        else:
            k = p["word"]
            inj.append({"family": "SEG-MERGE", "band": "A2", "_crit": p.get("critical", False), "_pos": k,
                        "meta": {"plain_offset": k, "note": f"{W[k]['w']} + {W[k + 1]['w']} in one chip{carried}"}})
    if not any(x["band"] == "A1" for x in inj):                 # the platform's must-catch needs an A1
        top = next(x for x in inj if x["_crit"])
        top["band"] = "A1"; top["meta"]["note"] += "; band raised to A1 (most obvious in this clip)"
    inj.sort(key=lambda x: x["_pos"])
    return {"decoy_id": e["decoy_id"], "locale": loc, "file_name": e["file_name"],
            "duration_seconds": e["duration_seconds"], "status": "ACTIVE",
            "gold_whole_audio_tag": "none",                       # synthetic clips must import too (see top)
            "gold_segments": [{"word": w["w"], "start": w["s"], "end": w["e"]} for w in W],
            "injections": inj}


def build(loc):
    src = zipfile.ZipFile(HERE / f"alignment_decoys_{loc}.zip")
    prefix = f"alignment_decoys_{loc}/"
    records, audio = [], {}
    for f in plan(loc):
        name = f["e"]["file_name"]
        audio[name] = src.read(prefix + "audio/" + name)
        records.append(to_kit(loc, f, audio[name]))
    factor = {}
    for r in records:
        for x in r["injections"]:
            factor[x["family"]] = factor.get(x["family"], 0) + BAND_FACTOR[x["band"]]
    for r in sorted(records, key=lambda r: r["decoy_id"]):
        for n, x in enumerate(r["injections"], 1):
            x["weight"] = r3(GROUP_POINTS[x["family"]] * BAND_FACTOR[x["band"]] / factor[x["family"]])
            x["injection_id"] = f"{r['decoy_id']}-{n}"
    for r in records:
        r["injections"] = [{"injection_id": x["injection_id"], "family": x["family"], "band": x["band"],
                            "weight": x["weight"], "meta": x["meta"]} for x in r["injections"]]
    corpus = {"format": KIT_FORMAT, "instructions": KIT_INSTRUCTIONS,
              "decoys": sorted(records, key=lambda r: r["decoy_id"])}
    out = HERE / "kits" / f"alignment_decoy_kit_{loc}.zip"
    out.parent.mkdir(exist_ok=True)
    syn = [{"decoy_id": f["e"]["decoy_id"], "file_name": f["e"]["file_name"]} for f in plan(loc)
           if f["e"]["gold_whole_audio_tag"] == "synthetic_speech"]
    (HERE / "kits" / f"synthetic_files_{loc}.json").write_text(json.dumps(
        {"locale": loc, "note": "Entirely synthetic speech. In the kit they are tagged \"none\" so they import.",
         "files": sorted(syn, key=lambda x: x["decoy_id"])}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        def put(name, data):
            info = zipfile.ZipInfo(name, (2026, 10, 31, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data)
        put("decoy_corpus.json", json.dumps(corpus, ensure_ascii=False, indent=2).encode("utf-8"))
        for name in sorted(audio):
            put(f"audio/{name}", audio[name])
    return out, corpus


if __name__ == "__main__":
    for loc in sys.argv[1:] or LOCALES:
        out, corpus = build(loc)
        recs = corpus["decoys"]
        fam, band = {}, {}
        for r in recs:
            for x in r["injections"]:
                fam[x["family"]] = fam.get(x["family"], 0) + 1; band[x["band"]] = band.get(x["band"], 0) + 1
        syn = len(json.loads((HERE / "kits" / f"synthetic_files_{loc}.json").read_text(encoding="utf-8"))["files"])
        print(f"{out.name}: {len(recs)} clips, all import ({syn} of them synthetic), "
              f"{sum(fam.values())} mistakes {dict(sorted(fam.items()))} bands {dict(sorted(band.items()))}, "
              f"{out.stat().st_size // 1024} KB")
