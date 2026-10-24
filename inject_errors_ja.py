#!/usr/bin/env python3
"""
Plant deliberate mistakes in 7 of the 25 Japanese files; the other 18 stay exactly as the clean alignment.

Input  : output/answer_key/ja_JP_clean.json      correct alignment (from make_japanese.py)
Output : output/json/ja_JP.json                  the test file to ingest. Every item has a segment "start"/"end"
                                                 (the playing area of the audio); no "synthetic" field.
         output/answer_key/ja_JP_answer_key.json decoy-corpus style: gold vs decoy text, segment and words per
                                                 file, and every injection (family, rule, detect, word, context,
                                                 offset, gold vs decoy timing, fingerprint)
         output/answer_key/ja_JP_answer_key.pdf  the same, to read
         output/answer_key/ja_JP_answer_key.csv  one row per injection

Clean files: the segment runs exactly from the first word's start to the last word's end.
The aligner re-aligns words on ingest, so boundary mismatches are planted at two levels:
  SB-START / SB-END  segment start or end moved earlier/later (200 ms, 500 ms, 1 s): words cut or extra audio
  WB-SHIFT / WB-CUT  a word's start or end moved (200 ms, 500 ms, 1 s), or its end placed inside the word
and transcript mistakes:
  WS-SUB  the word is spoken, but the transcript says a different word
  WD      the word is spoken, but there is no segment and it is not in the transcript
  WH      a word and segment for something never spoken (placed in a pause)

Run    : python inject_errors_ja.py
"""
import csv, glob, hashlib, html, json, os, pathlib, shutil, subprocess, tempfile
from tts_to_wav import write_locale

HERE = pathlib.Path(__file__).parent
LOCALE = "ja_JP"
KEY_DIR = HERE / "output" / "answer_key"
CTX = 8                                              # characters of context on each side, as in the decoy corpus

# Per file: segment edges moved by (seconds), and word injections
#   (family, clean word index, expected clean word - or the invented word, inserted before that index -, change)
PLAN = {
    "ja_0002": {"segment": {"start": +0.2, "end": -0.5}, "words": [
        ("WB-SHIFT", 3, "会議", {"start": +0.2}),
        ("WB-SHIFT", 9, "皆さん", {"start": -1.0}),
        ("WB-SHIFT", 15, "ください", {"end": +0.2}),
        ("WB-CUT", 7, "始まります", {"end": 4.48}),
    ]},
    "ja_0006": {"segment": {"start": -0.5, "end": -1.0}, "words": [
        ("WS-SUB", 1, "玉ねぎ", {"word": "にんじん"}),
        ("WS-SUB", 26, "五分", {"word": "三分"}),
        ("WB-SHIFT", 5, "フライパン", {"start": -0.2}),
        ("WB-SHIFT", 12, "あめ色", {"start": -1.0}),
        ("WB-SHIFT", 20, "塩", {"start": +0.2}),
    ]},
    "ja_0010": {"segment": {"start": +0.5, "end": +0.2}, "words": [
        ("WD", 7, "新しい", None),
        ("WH", 13, "なお", {"start": 6.10, "end": 6.42}),
        ("WB-SHIFT", 5, "会議室", {"start": +0.2}),
        ("WB-SHIFT", 12, "行います", {"end": +0.2}),
    ]},
    "ja_0012": {"segment": {"start": -0.2, "end": -0.5}, "words": [
        ("WS-SUB", 7, "十四号", {"word": "十七号"}),
        ("WS-SUB", 12, "九州", {"word": "四国"}),
        ("WS-SUB", 31, "朝", {"word": "夜"}),
        ("WD", 37, "大きな", None),
        ("WB-SHIFT", 19, "沿岸部", {"start": -1.0}),
        ("WB-SHIFT", 9, "今夜", {"start": -0.2}),
    ]},
    "ja_0017": {"segment": {"start": +1.0, "end": +0.2}, "words": [
        ("WB-CUT", 10, "動かなくて", {"end": 5.28}),
        ("WB-CUT", 13, "できます", {"end": 8.36}),
        ("WB-SHIFT", 11, "交換", {"start": -1.0}),
        ("WB-SHIFT", 4, "けど", {"end": +0.5}),
    ]},
    "ja_0021": {"segment": {"start": -0.5, "end": -0.2}, "words": [
        ("WH", 9, "まず", {"start": 4.30, "end": 4.62}),
        ("WH", 31, "実は", {"start": 13.42, "end": 13.76}),
        ("WS-SUB", 26, "酸素", {"word": "窒素"}),
        ("WB-SHIFT", 9, "植物", {"start": +0.5}),
        ("WB-SHIFT", 22, "作ります", {"end": +0.5}),
    ]},
    "ja_0025": {"segment": {"start": +0.2, "end": -1.0}, "words": [
        ("WD", 2, "先ほど", None),
        ("WD", 12, "もう", None),
        ("WB-CUT", 21, "いただけます", {"end": 10.74}),
        ("WB-SHIFT", 7, "まだ", {"start": -0.2}),
        ("WB-SHIFT", 13, "二十分", {"start": +0.2}),
        ("WB-SHIFT", 1, "すみません", {"end": +0.5}),
    ]},
}

FAMILY = {
    "SB-START": ("SEGMENT_BOUNDARY_MISMATCH", "Segment start moved", "the segment (playing area) starts earlier or later than the speech"),
    "SB-END": ("SEGMENT_BOUNDARY_MISMATCH", "Segment end moved", "the segment (playing area) ends earlier or later than the speech"),
    "WB-SHIFT": ("WORD_BOUNDARY_MISMATCH", "Word boundary moved", "a word's start or end is before the word starts, inside it, or past its end"),
    "WB-CUT": ("WORD_CUT_OFF", "Word cut off", "a word's end is placed in the middle of the word"),
    "WS-SUB": ("WORD_AT_SLOT_SUBSTITUTED", "Incorrect transcription", "the word is spoken, but the transcript says a different word"),
    "WD": ("WORD_AT_SLOT_PRESENT", "Missing segment", "the word is spoken, but has no segment and is not in the transcript"),
    "WH": ("WORD_AT_SLOT_ABSENT", "Hallucinated segment", "a word and segment for something never spoken"),
}


def fingerprint(inj):
    body = {k: v for k, v in inj.items() if k not in ("injection_id", "fingerprint")}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def ms(x):
    return int(round(x * 1000))


def context(words, i, insertion=False):
    """Left/right context and character offset of word i (or of an insertion before word i) in the gold text."""
    text = "".join(w["word"] for w in words)
    off = sum(len(w["word"]) for w in words[:i])
    end = off if insertion else off + len(words[i]["word"])
    return {"left": text[max(0, off - CTX):off], "right": text[end:end + CTX], "plain_offset": off}


def segment_effect(words, edge, gold, decoy):
    """Which words the moved segment edge cuts or leaves outside, or how much non-speech audio it adds."""
    if edge == "start" and decoy > gold:
        out = [w["word"] for w in words if w["end"] <= decoy]
        cut = [w["word"] for w in words if w["start"] < decoy < w["end"]]
    elif edge == "end" and decoy < gold:
        out = [w["word"] for w in words if w["start"] >= decoy]
        cut = [w["word"] for w in words if w["start"] < decoy < w["end"]]
    else:
        return {"words_outside_segment": [], "words_cut": [], "extra_non_speech_ms": abs(ms(decoy - gold))}
    return {"words_outside_segment": out, "words_cut": cut, "extra_non_speech_ms": 0}


def inject(item, plan, seq):
    gold = item["source"]["words"]
    words = [dict(w) for w in gold]
    keep, extra, inj = [True] * len(words), [], []
    dur = item["source"]["duration_seconds"]
    gseg = {"start": gold[0]["start"], "end": gold[-1]["end"]}
    dseg = dict(gseg)
    for edge, d in plan.get("segment", {}).items():                      # segment edges
        dseg[edge] = round(gseg[edge] + d, 3)
        assert 0 <= dseg[edge] <= dur, (item["id"], edge)
        eff = segment_effect(gold, edge, gseg[edge], dseg[edge])
        direction = "early" if d < 0 else "late"
        if eff["extra_non_speech_ms"]:
            what = (f"segment {edge} {abs(ms(d))} ms {'before the speech starts' if edge == 'start' else 'after the speech ends'}"
                    f" ({eff['extra_non_speech_ms']} ms of non-speech audio inside the segment)")
        else:
            parts = []
            if eff["words_outside_segment"]:
                parts.append("not played at all: " + "".join(eff["words_outside_segment"]))
            if eff["words_cut"]:
                parts.append("cut in the middle: " + "".join(eff["words_cut"]))
            what = f"segment {edge} {abs(ms(d))} ms {'into the speech' if edge == 'start' else 'before the speech ends'}; " + "; ".join(parts)
        fam = "SB-START" if edge == "start" else "SB-END"
        inj.append({"family": fam, "meta": {"edge": edge, "gold": gseg[edge], "decoy": dseg[edge], "shift_ms": ms(d), **eff},
                    "rule": f"segment_{edge}_{direction}", "description": what})
    for fam, i, expect, change in plan.get("words", []):                 # word injections
        assert fam == "WH" or gold[i]["word"] == expect, (item["id"], i, gold[i]["word"], expect)
        ctx = context(gold, i, insertion=fam == "WH")
        if fam == "WD":
            keep[i] = False
            meta = {"word": expect, "word_index": i, "audio_start": gold[i]["start"], "audio_end": gold[i]["end"], **ctx}
            rule, what = "word_deleted", f"{expect} is spoken at {gold[i]['start']:.2f}-{gold[i]['end']:.2f}s but has no segment and is not in the transcript"
        elif fam == "WH":
            assert gold[i - 1]["end"] < change["start"] < change["end"] < gold[i]["start"], (item["id"], expect)
            extra.append({"word": expect, "start": change["start"], "end": change["end"]})
            meta = {"word": expect, "inserted_before_index": i, "decoy_start": change["start"], "decoy_end": change["end"],
                    "audio_at_slot": "pause (no speech)", **ctx}
            rule, what = "hallucinated_segment", (f"{expect} is never spoken; its segment {change['start']:.2f}-{change['end']:.2f}s "
                                                  f"is a pause between {gold[i - 1]['word']} and {gold[i]['word']}")
        elif fam == "WS-SUB":
            words[i]["word"] = change["word"]
            meta = {"from": expect, "to": change["word"], "word_index": i, "start": gold[i]["start"], "end": gold[i]["end"], **ctx}
            rule, what = "word_substituted", f"audio says {expect}, transcript says {change['word']} ({gold[i]['start']:.2f}-{gold[i]['end']:.2f}s)"
        else:
            w = words[i]
            if fam == "WB-CUT":
                w["end"] = change["end"]
                kept = (w["end"] - w["start"]) / (gold[i]["end"] - gold[i]["start"])
                meta = {"word": expect, "word_index": i, "gold": {"start": gold[i]["start"], "end": gold[i]["end"]},
                        "decoy": {"start": w["start"], "end": w["end"]}, "cut_ms": ms(gold[i]["end"] - w["end"]),
                        "kept_percent": round(100 * kept), **ctx}
                rule = "word_end_inside_word"
                what = (f"{expect} really ends at {gold[i]['end']:.2f}s; its segment ends at {w['end']:.2f}s, "
                        f"so the last {ms(gold[i]['end'] - w['end'])} ms of the word are cut off")
            else:
                (edge, d), = change.items()
                w[edge] = round(w[edge] + d, 3)
                where = ({"start": "before the word starts", "end": "inside the word"} if d < 0 else
                         {"start": "inside the word", "end": "after the word ends"})[edge]
                meta = {"word": expect, "word_index": i, "edge": edge, "gold": {"start": gold[i]["start"], "end": gold[i]["end"]},
                        "decoy": {"start": w["start"], "end": w["end"]}, "shift_ms": ms(d), **ctx}
                rule = f"word_{edge}_{'early' if d < 0 else 'late'}"
                what = (f"{expect} {edge} moved {abs(ms(d))} ms {'earlier' if d < 0 else 'later'}: "
                        f"{gold[i][edge]:.2f}s -> {w[edge]:.2f}s ({where})")
        inj.append({"family": fam, "meta": meta, "rule": rule, "description": what})
    final = sorted([w for w, k in zip(words, keep) if k] + extra, key=lambda w: w["start"])
    for a, b in zip(final, final[1:]):                     # mistakes must still give a well-formed file
        assert a["start"] < a["end"] <= b["start"] < b["end"], (item["id"], a, b)
    assert final[-1]["end"] <= dur
    for n, x in enumerate(inj, 1):
        x["detect"] = FAMILY[x["family"]][0]
        x["meta"]["detect"], x["meta"]["rule"] = x["detect"], x["rule"]
        x["injection_id"] = f"JA-AL-{seq:04d}-{n}"
        x["fingerprint"] = fingerprint(x)
    return final, gseg, dseg, inj


def test_item(item, words, seg):
    """Item for the file to ingest: sample format plus the segment playing area; nothing gives the answer away."""
    src = json.loads(json.dumps(item["source"]))
    src["words"] = words
    return {"id": item["id"], "name": item["name"], "start": seg["start"], "end": seg["end"],
            "transcript": "".join(w["word"] for w in words), "source": src}


def chromium():
    found = [os.environ.get("CHROME", "")] + sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    found += [shutil.which(n) or "" for n in ("chromium", "chromium-browser", "google-chrome")]
    return next((c for c in found if c and os.path.exists(c)), None)


def marked_texts(rec):
    """Gold and decoy text as HTML, with every injected word marked."""
    e = html.escape
    gold, decoy = rec["gold_words"], rec["decoy_words"]
    sub = {x["meta"]["word_index"] for x in rec["injections"] if x["family"] == "WS-SUB"}
    dele = {x["meta"]["word_index"] for x in rec["injections"] if x["family"] == "WD"}
    bnd = {x["meta"]["word_index"] for x in rec["injections"] if x["family"] in ("WB-SHIFT", "WB-CUT")}
    g = []
    for k, w in enumerate(gold):
        t = e(w["word"])
        g.append(f"<del>{t}</del>" if k in dele else f"<mark>{t}</mark>" if k in sub else f"<u>{t}</u>" if k in bnd else t)
    hall = {(x["meta"]["word"], x["meta"]["decoy_start"]) for x in rec["injections"] if x["family"] == "WH"}
    to = {(x["meta"]["to"], x["meta"]["start"]) for x in rec["injections"] if x["family"] == "WS-SUB"}
    dd = []
    for w in decoy:
        t = e(w["word"])
        dd.append(f"<ins>{t}</ins>" if (w["word"], w["start"]) in hall else f"<mark>{t}</mark>" if (w["word"], w["start"]) in to else t)
    return "".join(g), "".join(dd)


def answer_key_html(recs, meta):
    e = html.escape
    t2 = lambda s, en: f"{s:.2f}–{en:.2f}"
    rows = "".join(
        f"<tr><td>{e(r['file_name'])}</td><td>{r['voice_type']}</td><td class='{r['status']}'>{r['status']}</td>"
        f"<td>{t2(r['gold_segment']['start'], r['gold_segment']['end'])}</td>"
        f"<td>{t2(r['decoy_segment']['start'], r['decoy_segment']['end']) if r['injections'] else '= gold'}</td>"
        f"<td>{r['injection_count'] or '—'}</td><td>{e(', '.join(r['families'])) or '—'}</td></tr>" for r in recs)
    detail = ""
    for r in recs:
        if not r["injections"]:
            continue
        g, d = marked_texts(r)
        def cell_word(x):
            m = x["meta"]
            w = m.get("word") or m.get("from") or ""
            if x["family"] in ("SB-START", "SB-END"):
                return f"segment {m['edge']} {m['gold']:.2f}→{m['decoy']:.2f}s"
            return f"{e(m['left'])}【{e(w)}】{e(m['right'])}"
        lines = "".join(
            f"<tr><td>{x['injection_id'].split('-')[-1]}</td><td><b>{x['family']}</b><br><span>{x['rule']}</span></td>"
            f"<td class='w'>{cell_word(x)}</td><td>{e(x['description'])}</td></tr>" for x in r["injections"])
        detail += (f"<section><h3>{e(r['file_name'])} <span>· {r['decoy_id']} · {r['voice_type']} voice · "
                   f"segment {t2(r['gold_segment']['start'], r['gold_segment']['end'])}s → "
                   f"{t2(r['decoy_segment']['start'], r['decoy_segment']['end'])}s · {r['injection_count']} injections</span></h3>"
                   f"<p class='tx'><b>Gold:</b> {g}<br><b>Decoy:</b> {d}</p>"
                   f"<table class='inj'><tr><th>#</th><th>Family / rule</th><th>Where (left【word】right)</th><th>What is wrong</th></tr>{lines}</table></section>")
    fam_rows = "".join(f"<tr><td><b>{f}</b></td><td>{FAMILY[f][1]}</td><td>{FAMILY[f][0]}</td><td>{e(FAMILY[f][2])}</td>"
                       f"<td>{meta['injections_by_family'].get(f, 0)}</td></tr>" for f in FAMILY)
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>{LOCALE} alignment answer key</title><style>
@page {{ size: A4; margin: 9mm 9mm; }}
body {{ font-family: "IPAPGothic", "IPAGothic", sans-serif; font-size: 7.6pt; color: #1a1a1a; line-height: 1.3; }}
h1 {{ font-size: 13pt; margin: 0 0 1mm; }} h2 {{ font-size: 10pt; margin: 3mm 0 1mm; }}
h3 {{ font-size: 8.6pt; margin: 2.8mm 0 0.8mm; break-after: avoid; }} h3 span, td span {{ font-weight: normal; color: #555; }}
p {{ margin: 0.6mm 0 1.2mm; }} table {{ border-collapse: collapse; width: 100%; }} tr {{ break-inside: avoid; }}
th, td {{ border: 0.25mm solid #c8c8c8; padding: 0.45mm 1.2mm; text-align: left; vertical-align: top; }}
th {{ background: #efefef; }} td.CLEAN {{ color: #1d6b32; font-weight: bold; }} td.ACTIVE {{ color: #a3261b; font-weight: bold; }}
td.w {{ white-space: nowrap; }} table.inj td:first-child {{ width: 4mm; }} table.inj td:nth-child(2) {{ width: 30mm; }}
mark {{ background: #ffe28a; }} ins {{ background: #c9ecd0; text-decoration: none; }} del {{ color: #b3261e; }}
u {{ text-decoration-color: #2a6fdb; text-decoration-thickness: 0.4mm; }} .tx {{ font-size: 8pt; break-after: avoid; }}
</style></head><body>
<h1>Japanese alignment decoy set ({LOCALE}) — answer key</h1>
<p>Ingest file: <code>output/json/{LOCALE}.json</code> · audio: <code>output/wav/ja_0001.wav … ja_0025.wav</code>. Keep this away from the inspectors.
<b>{meta['files']}</b> files: <b>{meta['clean']}</b> clean, <b>{meta['active']}</b> with <b>{meta['injections']}</b> injections ·
<b>{meta['synthetic']}</b> synthetic voice (whole-audio tag <code>synthetic_speech</code>), <b>{meta['human']}</b> human-sounding.</p>
<p>Every item in the ingest file has a segment <code>start</code>/<code>end</code> (the playing area). In clean files it runs exactly from the
first word's start to the last word's end. Because the aligner re-aligns words on ingest, boundary mismatches are also planted on the
segment edges (SB-START / SB-END), which it cannot re-align.</p>
<h2>Injection families</h2>
<table><tr><th>Family</th><th>Name</th><th>detect</th><th>Meaning</th><th>Count</th></tr>{fam_rows}</table>
<h2>All files</h2>
<table><tr><th>File</th><th>Voice type</th><th>Status</th><th>Gold segment (s)</th><th>Decoy segment (s)</th><th>Injections</th><th>Families</th></tr>{rows}</table>
<h2>Injections, file by file</h2>
<p>Gold text marks: <mark>substituted</mark>, <del>missing (deleted)</del>, <u>boundary changed</u>. Decoy text marks: <mark>substituted</mark>, <ins>hallucinated</ins>.
Times in seconds.</p>
{detail}
</body></html>"""


if __name__ == "__main__":
    clean = json.loads((KEY_DIR / f"{LOCALE}_clean.json").read_text(encoding="utf-8"))["items"]
    test, recs = {}, []
    for item in clean:
        seq = int(item["id"].split("_")[1])
        plan = PLAN.get(item["id"], {})
        words, gseg, dseg, inj = inject(item, plan, seq)
        test[item["id"]] = test_item(item, words, dseg)
        voice = item["source"]["voice"]
        recs.append({"locale": "ja-JP", "lang_code": "JA", "script": "cjk", "group": "JA-ALIGN",
                     "file_id": item["id"], "file_name": item["name"],
                     "gold_text": item["transcript"], "decoy_text": "".join(w["word"] for w in words),
                     "gold_token_count": len(item["source"]["words"]),
                     "gold_whole_audio_tag": "synthetic_speech" if item["synthetic"] else "none",
                     "voice_type": "synthetic" if item["synthetic"] else "human",
                     "voice": voice["name"], "voice_gender": voice["gender"], "num_speakers": "1",
                     "duration_seconds": item["source"]["duration_seconds"],
                     "gold_segment": gseg, "decoy_segment": dseg,
                     "gold_words": item["source"]["words"], "decoy_words": words,
                     "decoy_id": f"JA-AL-{seq:04d}" if inj else None, "injections": inj, "injection_count": len(inj),
                     "families": sorted({x["family"] for x in inj}, key=list(FAMILY).index),
                     "status": "ACTIVE" if inj else "CLEAN"})
    write_locale(HERE / "output" / "json" / f"{LOCALE}.json", LOCALE, test)
    by_fam = {}
    for r in recs:
        for x in r["injections"]:
            by_fam[x["family"]] = by_fam.get(x["family"], 0) + 1
    meta = {"locale": LOCALE, "files": len(recs), "clean": sum(r["status"] == "CLEAN" for r in recs),
            "active": sum(r["status"] == "ACTIVE" for r in recs), "injections": sum(r["injection_count"] for r in recs),
            "injections_by_family": by_fam, "synthetic": sum(r["voice_type"] == "synthetic" for r in recs),
            "human": sum(r["voice_type"] == "human" for r in recs),
            "families": {f: {"detect": v[0], "name": v[1], "meaning": v[2]} for f, v in FAMILY.items()}}
    (KEY_DIR / f"{LOCALE}_answer_key.json").write_text(json.dumps({"fileMetadata": meta, "files": recs},
                                                                  ensure_ascii=False, indent=2), encoding="utf-8")
    with open(KEY_DIR / f"{LOCALE}_answer_key.csv", "w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.writer(fh)
        wr.writerow(["file", "voice_type", "status", "gold_segment", "decoy_segment", "injection_id", "family", "rule",
                     "detect", "word", "left", "right", "plain_offset", "description", "fingerprint"])
        for r in recs:
            gs = f"{r['gold_segment']['start']:.3f}-{r['gold_segment']['end']:.3f}"
            ds = f"{r['decoy_segment']['start']:.3f}-{r['decoy_segment']['end']:.3f}"
            if not r["injections"]:
                wr.writerow([r["file_name"], r["voice_type"], r["status"], gs, ds] + [""] * 8 + ["no injections", ""])
            for x in r["injections"]:
                m = x["meta"]
                wr.writerow([r["file_name"], r["voice_type"], r["status"], gs, ds, x["injection_id"], x["family"], x["rule"],
                             x["detect"], m.get("word") or (f"{m['from']}->{m['to']}" if "from" in m else ""),
                             m.get("left", ""), m.get("right", ""), m.get("plain_offset", ""), x["description"], x["fingerprint"]])
    browser = chromium()
    if browser:
        with tempfile.TemporaryDirectory() as tmp:
            page = pathlib.Path(tmp) / "key.html"
            page.write_text(answer_key_html(recs, meta), encoding="utf-8")
            pdf = KEY_DIR / f"{LOCALE}_answer_key.pdf"
            subprocess.run([browser, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                            f"--print-to-pdf={pdf}", page.as_uri()], check=True, capture_output=True)
    else:
        print("No Chromium found: answer key PDF not written (JSON and CSV are).")
    print(f"{len(recs)} files: {meta['clean']} clean, {meta['active']} with {meta['injections']} injections {by_fam}")
