#!/usr/bin/env python3
"""
The two downloads for the 1000 French files, from the 10 package parts (same file names, same errors):

1. fr_FR_1000_audio.zip — the clean set: audio/<file_name>.wav (1000, 16 kHz mono) + fr_FR.json (the correct
   transcription and word timings, ingest format: fileMetadata + items with id, name, transcript, source.voice /
   sample_rate_hz / duration_seconds / words) + fr_FR_voice_key.csv / .json (all human, none synthetic) + README.md.
   Also written without the audio as fr_FR_1000_transcripts.json.
2. fr_FR_1000_decoy_plants.json — the decoys in the align-decoys/v1 format (as the Hindi / Spanish / German /
   Portuguese / French plants files): {format, instructions, decoys: [{decoy_ref, file_id, file_name, words, plants}]},
   `words` = the correct alignment (i, w, s, e), `plants` = every planted error of the package as a typed action:
     BND-MINOR / BND-MAJOR -> move · BND-OVERLAP -> overlap · BND-ZERO -> zero · WD -> delete
     WH -> add (over silence) / add_noise with start / end (over a breath) · WS, G-ACCENT, G-BACKCH -> replace
   1-2 "critical": true per file (the heaviest A1). Applying the plants to `words` gives the package's pre-fill exactly
   (checked below; an `add` chip is placed by the platform inside the same pause).

Run    : python french_1000/export_deliverables.py
"""
import collections, csv, glob, io, json, pathlib, zipfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
TOUCH = 0.0005


def load_corpus():
    C = []
    for z in sorted(HERE.glob("alignment_decoys_fr_FR_1000_part*of10.zip")):
        Z = zipfile.ZipFile(z)
        top = Z.namelist()[0].split("/")[0]
        part = json.loads(Z.read(f"{top}/decoy_corpus.json"))
        for e in part:
            e["_zip"], e["_top"] = z, top
        C += part
    assert len(C) == 1000 and len({e["file_name"] for e in C}) == 1000
    return sorted(C, key=lambda e: e["decoy_id"])


def plant(x, G):
    f, m, band = x["family"], x["meta"], x["band"]
    head = f"{f} · {band} · {m.get('rule')}"
    if f in ("BND-MINOR", "BND-MAJOR", "BND-OVERLAP"):
        ms = m["shift_ms"]
        return {"action": "overlap" if f == "BND-OVERLAP" else "move", "word": m["plain_offset"], "edge": m["edge"],
                "shift_ms": ms, "note": f"{head} · {m['word']} {m['edge']} {abs(ms)} ms {'later' if ms > 0 else 'earlier'}"}
    if f == "BND-ZERO":
        return {"action": "zero", "word": m["plain_offset"], "note": f"{head} · {m['word']} collapses to zero length"}
    if f == "WD":
        return {"action": "delete", "word": m["plain_offset"], "note": f"{head} · '{m['word']}' gone"}
    if f == "WH":
        k = m["inserted_before_index"] - 1
        d = m["decoy"]
        if m["rule"].endswith("breath"):
            return {"action": "add_noise", "after_word": k, "text": m["word"], "start": d["start"], "end": d["end"],
                    "note": f"{head} · extra '{m['word']}' over the breath between {G[k]['word']} and {G[k + 1]['word']}"}
        return {"action": "add", "after_word": k, "text": m["word"],
                "note": f"{head} · extra '{m['word']}' in the {G[k + 1]['start'] - G[k]['end']:.2f} s pause "
                        f"(pre-fill chip {d['start']}-{d['end']})"}
    if f in ("WS", "G-ACCENT", "G-BACKCH"):
        return {"action": "replace", "word": m["plain_offset"], "text": m["to"], "note": f"{head} · {m['from']} -> {m['to']}"}
    raise ValueError(f)


def simulate(G, plants, extra_times):
    W = [{"w": g["word"], "s": g["start"], "e": g["end"]} for g in G]
    gone, extra = set(), collections.defaultdict(list)
    for p in plants:
        a, k = p["action"], p.get("word", p.get("after_word"))
        if a in ("move", "overlap"):
            d = p["shift_ms"] / 1000
            if p["edge"] == "start":
                if a == "move" and k > 0 and abs(W[k - 1]["e"] - W[k]["s"]) < TOUCH:
                    W[k - 1]["e"] = round(W[k]["s"] + d, 3)
                W[k]["s"] = round(W[k]["s"] + d, 3)
            else:
                if a == "move" and k + 1 < len(W) and abs(W[k + 1]["s"] - W[k]["e"]) < TOUCH:
                    W[k + 1]["s"] = round(W[k]["e"] + d, 3)
                W[k]["e"] = round(W[k]["e"] + d, 3)
        elif a == "zero":
            W[k]["e"] = W[k]["s"]
        elif a == "delete":
            gone.add(k)
        elif a == "replace":
            W[k]["w"] = p["text"]
        elif a == "add_noise":
            extra[k].append({"w": p["text"], "s": p["start"], "e": p["end"]})
        elif a == "add":
            s, e = extra_times[k]                                  # where the pre-fill put it, inside the same pause
            assert W[k]["e"] < s < e < W[k + 1]["s"]
            extra[k].append({"w": p["text"], "s": s, "e": e})
    out = []
    for i, w in enumerate(W):
        if i not in gone:
            out.append(w)
        out += extra[i]
    return out


def main():
    tpl = json.loads((ROOT / "hindi_decoys" / "alignment-decoys-template.json").read_text(encoding="utf-8"))
    C = load_corpus()

    # ---------------------------------------------------------------- decoy plants
    decoys, problems, acts = [], [], collections.Counter()
    for e in C:
        G = e["gold_segments"]
        inj = sorted(e["injections"], key=lambda x: x["meta"].get("plain_offset", x["meta"].get("inserted_before_index", 0)))
        plants = [plant(x, G) for x in inj]
        ranked = sorted(range(len(inj)), key=lambda i: (inj[i]["band"] != "A1", -inj[i]["weight"]))
        for i in ranked[:2 if len(plants) >= 5 else 1]:
            plants[i]["critical"] = True
        plants = [{**{k: v for k, v in p.items() if k != "note"}, "note": p["note"]} for p in plants]
        # template rules
        pos = []
        for p in plants:
            pos += [p["after_word"], p["after_word"] + 1] if "after_word" in p else \
                   [p["word"], p["word"] + (1 if p.get("edge") == "end" else -1)] if p["action"] == "overlap" else [p["word"]]
        spans = sorted({(p.get("word", p.get("after_word"))) for p in plants})
        if any(b - a < 3 for a, b in zip(spans, spans[1:])):
            problems.append((e["decoy_id"], "closer than 3 words"))
        for p in plants:
            if p["action"] == "add" and G[p["after_word"] + 1]["start"] - G[p["after_word"]]["end"] < 0.35:
                problems.append((e["decoy_id"], "add in a pause under 0.35 s"))
            if p["action"] == "zero" and G[p["word"]]["end"] - G[p["word"]]["start"] < 0.15:
                problems.append((e["decoy_id"], "zero on a word under 0.15 s"))
        extra_times = {x["meta"]["inserted_before_index"] - 1: (x["meta"]["decoy"]["start"], x["meta"]["decoy"]["end"])
                       for x in inj if x["family"] == "WH"}
        sim = simulate(G, plants, extra_times)
        D = e["decoy_segments"]
        if len(sim) != len(D) or any(a["w"] != b["word"] or abs(a["s"] - b["start"]) > TOUCH or abs(a["e"] - b["end"]) > TOUCH
                                     for a, b in zip(sim, D)):
            problems.append((e["decoy_id"], "plants do not give the pre-fill"))
        acts.update(p["action"] for p in plants)
        decoys.append({"decoy_ref": e["decoy_id"], "file_id": e["file_id"], "file_name": e["file_name"],
                       "words": [{"i": i, "w": g["word"], "s": g["start"], "e": g["end"]} for i, g in enumerate(G)],
                       "plants": plants})
    assert not problems, problems[:10]
    (HERE / "fr_FR_1000_decoy_plants.json").write_text(json.dumps(
        {"format": tpl["format"], "instructions": tpl["instructions"], "decoys": decoys}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")

    # ---------------------------------------------------------------- clean audio set
    items = [{"id": e["file_id"], "name": e["file_name"], "transcript": e["gold_text"],
              "source": {"voice": {"name": e["voice"]["name"], "gender": e["voice"]["gender"]}, "sample_rate_hz": 16000,
                         "duration_seconds": e["duration_seconds"], "words": e["gold_segments"]}} for e in C]
    ingest = {"fileMetadata": {"locale": "fr_FR", "workitemsCount": len(items)}, "items": sorted(items, key=lambda i: i["name"])}
    key = [{"file": e["file_name"], "file_id": e["file_id"], "voice_type": "human", "whole_audio_tag": "none",
            "voice": e["voice"]["name"], "gender": e["voice"]["gender"], "duration_seconds": e["duration_seconds"],
            "words": e["gold_token_count"]} for e in sorted(C, key=lambda e: e["file_name"])]
    meta = {"locale": "fr_FR", "files": len(key), "synthetic": 0, "human": len(key), "planted_errors": 0}
    buf = io.StringIO()
    wr = csv.DictWriter(buf, fieldnames=list(key[0])); wr.writeheader(); wr.writerows(key)
    readme = f"""# French (fr_FR) — 1000 clean audio files

- `audio/` — 1000 wav files, 16 kHz mono 16-bit, {sum(e['duration_seconds'] for e in C) / 3600:.2f} hours in total (4.8-10.4 s each).
- `fr_FR.json` — the CORRECT transcription and word alignment of every file (no planted errors): `fileMetadata` +
  `items[]` with `id`, `name` (= the wav name), `transcript`, `source.voice`, `sample_rate_hz`, `duration_seconds`,
  `words[]` (`word`, `start`, `end` in seconds). Transcripts follow Forced_Alignment_Guidelines_fr_FR (lowercase, no
  punctuation, numbers as words, hyphens split, elided forms one word).
- `fr_FR_voice_key.csv` / `.json` — voice and gender per file. Every file is natural, human-sounding speech: none is synthetic.

Voices: 50 native French ElevenLabs voices (25 female, 25 male; young, middle-aged and older). Each clip was checked by
speech-to-text against its transcript and made again until it matched. Gold alignment: ElevenLabs forced alignment plus
loudness-based correction at pauses (about ±20-30 ms).
The decoys (planted errors) for the same 1000 files are in fr_FR_1000_decoy_plants.json and in the 10 package parts
alignment_decoys_fr_FR_1000_partNNof10.zip; file names match.
"""
    (HERE / "fr_FR_1000_transcripts.json").write_text(json.dumps(ingest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    out = HERE / "fr_FR_1000_audio.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        def put(name, data):
            info = zipfile.ZipInfo(f"fr_FR_1000_audio/{name}", (2026, 11, 12, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data)
        put("README.md", readme.encode("utf-8"))
        put("fr_FR.json", json.dumps(ingest, ensure_ascii=False, indent=1).encode("utf-8"))
        put("fr_FR_voice_key.json", json.dumps({"fileMetadata": meta, "files": key}, ensure_ascii=False, indent=1).encode("utf-8"))
        put("fr_FR_voice_key.csv", ("﻿" + buf.getvalue()).encode("utf-8"))
        for e in sorted(C, key=lambda e: e["file_name"]):
            put(f"audio/{e['file_name']}", zipfile.ZipFile(e["_zip"]).read(f"{e['_top']}/audio/{e['file_name']}"))
    crit = collections.Counter(sum(p.get("critical", False) for p in d["plants"]) for d in decoys)
    print(f"fr_FR_1000_decoy_plants.json: {len(decoys)} files, {sum(acts.values())} plants {dict(acts.most_common())}, "
          f"critical per file {dict(crit)}; plants reproduce every pre-fill exactly")
    print(f"{out.name}: {len(items)} wav + fr_FR.json, {out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
