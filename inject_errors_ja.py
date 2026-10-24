#!/usr/bin/env python3
"""
Plant deliberate mistakes in 7 of the 25 Japanese files; the other 18 stay exactly as the clean alignment.

Input  : output/answer_key/ja_JP_clean.json      correct alignment (from make_japanese.py)
Output : output/json/ja_JP.json                  the test file: 18 clean items + 7 items with planted mistakes;
                                                 no "synthetic" field, so it does not give anything away
         output/answer_key/ja_JP_answer_key.json per file: human or synthetic voice, clean or not, and every
                                                 planted mistake (type, word, correct vs given)
         output/answer_key/ja_JP_answer_key.pdf  the same, to read
         output/answer_key/ja_JP_answer_key.csv  the same, one row per mistake

Mistake types (word indices refer to the clean alignment):
  boundary_shift          start/end moved before the word starts, into its middle, or past its end
  cut_off                 end placed in the middle of the word, so the word is cut off
  incorrect_transcription the word is spoken, but the transcript says a different word
  missing_segment         the word is spoken, but there is no segment and it is not in the transcript
  hallucinated_segment    a segment and transcript word for something never spoken (placed in a pause)

Run    : python inject_errors_ja.py
"""
import csv, glob, html, json, os, pathlib, shutil, subprocess, tempfile
from tts_to_wav import write_locale

HERE = pathlib.Path(__file__).parent
LOCALE = "ja_JP"
KEY_DIR = HERE / "output" / "answer_key"

# (type, clean word index, expected clean word - or the invented word, inserted before that index -, change)
PLAN = {
    "ja_0002": [
        ("boundary_shift", 3, "会議", {"start": +0.18}),            # starts in the middle of the word
        ("boundary_shift", 9, "皆さん", {"start": -0.30}),          # starts in the pause before the word
        ("boundary_shift", 15, "ください", {"end": +0.25}),         # ends in the silence after the word
        ("cut_off", 7, "始まります", {"end": 4.48}),
    ],
    "ja_0006": [
        ("incorrect_transcription", 1, "玉ねぎ", {"word": "にんじん"}),
        ("incorrect_transcription", 26, "五分", {"word": "三分"}),
        ("boundary_shift", 5, "フライパン", {"start": -0.20}),
        ("boundary_shift", 20, "塩", {"start": +0.15}),
    ],
    "ja_0010": [
        ("missing_segment", 7, "新しい", None),
        ("hallucinated_segment", 13, "なお", {"start": 6.10, "end": 6.42}),   # inserted before 参加
        ("boundary_shift", 5, "会議室", {"start": +0.20}),
    ],
    "ja_0012": [
        ("incorrect_transcription", 7, "十四号", {"word": "十七号"}),
        ("incorrect_transcription", 12, "九州", {"word": "四国"}),
        ("incorrect_transcription", 31, "朝", {"word": "夜"}),
        ("missing_segment", 37, "大きな", None),
        ("boundary_shift", 19, "沿岸部", {"start": -0.35}),
    ],
    "ja_0017": [
        ("cut_off", 10, "動かなくて", {"end": 5.28}),
        ("cut_off", 13, "できます", {"end": 8.36}),
        ("boundary_shift", 11, "交換", {"start": -0.40}),
        ("boundary_shift", 4, "けど", {"end": +0.30}),
    ],
    "ja_0021": [
        ("hallucinated_segment", 9, "まず", {"start": 4.30, "end": 4.62}),     # inserted before 植物
        ("hallucinated_segment", 31, "実は", {"start": 13.42, "end": 13.76}),  # inserted before これ
        ("incorrect_transcription", 26, "酸素", {"word": "窒素"}),
        ("boundary_shift", 9, "植物", {"start": +0.25}),
        ("boundary_shift", 22, "作ります", {"end": +0.35}),
    ],
    "ja_0025": [
        ("missing_segment", 2, "先ほど", None),
        ("missing_segment", 12, "もう", None),
        ("cut_off", 21, "いただけます", {"end": 10.74}),
        ("boundary_shift", 7, "まだ", {"start": -0.20}),
        ("boundary_shift", 13, "二十分", {"start": +0.18}),
    ],
}


def describe(kind, clean, given, change):
    if kind == "boundary_shift":
        parts = []
        for edge in ("start", "end"):
            d = round(given[edge] - clean[edge], 3)
            if d:
                where = ("before the word starts" if d < 0 else "in the middle of the word") if edge == "start" \
                    else ("in the middle of the word" if d < 0 else "after the word ends")
                parts.append(f"{edge} moved {d:+.2f}s ({where})")
        return "; ".join(parts)
    if kind == "cut_off":
        return f"end set to {given['end']:.2f}s, the word really ends at {clean['end']:.2f}s, so it is cut off"
    if kind == "incorrect_transcription":
        return f"audio says {clean['word']}, transcript says {given['word']}"
    if kind == "missing_segment":
        return f"{clean['word']} is spoken ({clean['start']:.2f}-{clean['end']:.2f}s) but has no segment"
    return f"{given['word']} is never spoken; segment {given['start']:.2f}-{given['end']:.2f}s is a pause"


def inject(item, plan):
    words = [dict(w) for w in item["source"]["words"]]
    keep, extra, errors = [True] * len(words), [], []
    for kind, i, expect, change in plan:
        clean = item["source"]["words"][i]
        assert kind == "hallucinated_segment" or clean["word"] == expect, (item["id"], i, clean["word"], expect)
        if kind == "missing_segment":
            keep[i] = False; given = None
        elif kind == "hallucinated_segment":
            prev_end = item["source"]["words"][i - 1]["end"]
            assert prev_end < change["start"] < change["end"] < clean["start"], (item["id"], expect)
            given = {"word": expect, "start": change["start"], "end": change["end"]}; extra.append(given)
            clean = None
        else:
            w = words[i]
            if "word" in change:
                w["word"] = change["word"]
            for edge in ("start", "end"):
                if edge in change:
                    v = change[edge]
                    w[edge] = round(v if kind == "cut_off" else w[edge] + v, 3)
            given = dict(w)
        errors.append({"type": kind, "word_index_in_clean": i,
                       "correct": clean, "given": given,
                       "description": describe(kind, clean, given, change)})
    final = sorted([w for w, k in zip(words, keep) if k] + extra, key=lambda w: w["start"])
    for a, b in zip(final, final[1:]):                     # mistakes must still give a well-formed file
        assert a["start"] < a["end"] <= b["start"] < b["end"], (item["id"], a, b)
    out = json.loads(json.dumps(item))
    out["transcript"] = "".join(w["word"] for w in final)
    out["source"]["words"] = final
    return out, errors


LABEL = {"boundary_shift": "Boundary shift", "cut_off": "Cut-off word", "incorrect_transcription": "Incorrect transcription",
         "missing_segment": "Missing segment", "hallucinated_segment": "Hallucinated segment"}
MEANING = {"boundary_shift": "start or end moved before the word starts, into its middle, or past its end",
           "cut_off": "end placed in the middle of the word, so the word is cut off",
           "incorrect_transcription": "the word is spoken, but the transcript says a different word",
           "missing_segment": "the word is spoken, but there is no segment and it is not in the transcript",
           "hallucinated_segment": "a segment and transcript word for something never spoken (placed in a pause)"}


def for_test(item):
    """The test file carries nothing that gives the answer away."""
    out = json.loads(json.dumps(item))
    out.pop("synthetic", None)
    return out


def chromium():
    found = [os.environ.get("CHROME", "")] + sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    found += [shutil.which(n) or "" for n in ("chromium", "chromium-browser", "google-chrome")]
    return next((c for c in found if c and os.path.exists(c)), None)


def answer_key_html(key, meta):
    e = html.escape
    t = lambda w: f"{w['start']:.2f}–{w['end']:.2f}" if w else "—"
    rows = "".join(
        f"<tr><td>{e(k['name'])}</td><td>{k['voice_type']}</td>"
        f"<td class='{k['status']}'>{'Clean' if k['status'] == 'clean' else 'Has errors'}</td>"
        f"<td>{e(', '.join(f'{n}× {LABEL[x]}' for x, n in k['error_summary'].items()) or '—')}</td>"
        f"<td>{k['duration_seconds']:.2f}</td><td>{e(k['voice'])}</td></tr>" for k in key)
    detail = ""
    for k in key:
        if not k["errors"]:
            continue
        er = "".join(
            f"<tr><td>{LABEL[x['type']]}</td><td>{e((x['correct'] or x['given'])['word'])}</td>"
            f"<td>{t(x['correct'])}</td><td>{e(x['given']['word']) if x['given'] else '—'}</td><td>{t(x['given'])}</td>"
            f"<td>{e(x['description'])}</td></tr>" for x in k["errors"])
        detail += (f"<section><h3>{e(k['name'])} <span>{k['voice_type']} voice · {len(k['errors'])} errors</span></h3>"
                   f"<p><b>Correct transcript:</b> {e(k['correct_transcript'])}<br>"
                   f"<b>Transcript in the test file:</b> {e(k['given_transcript'])}</p>"
                   f"<table><tr><th>Type</th><th>Word</th><th>Correct (s)</th><th>Given word</th><th>Given (s)</th>"
                   f"<th>What is wrong</th></tr>{er}</table></section>")
    legend = "".join(f"<li><b>{LABEL[x]}</b>: {MEANING[x]} ({meta['errors_by_type'].get(x, 0)})</li>" for x in LABEL)
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>{LOCALE} answer key</title><style>
@page {{ size: A4; margin: 14mm 12mm; }}
body {{ font-family: "IPAGothic", "IPAPGothic", "Noto Sans CJK JP", sans-serif; font-size: 9.5pt; color: #1a1a1a; }}
h1 {{ font-size: 17pt; margin: 0 0 2mm; }} h2 {{ font-size: 12.5pt; margin: 7mm 0 2mm; }}
h3 {{ font-size: 10.5pt; margin: 5mm 0 1.5mm; }} h3 span {{ font-weight: normal; color: #555; font-size: 9pt; }}
p {{ margin: 1mm 0 2mm; line-height: 1.5; }} ul {{ margin: 1mm 0; padding-left: 5mm; }} li {{ margin: 0.8mm 0; }}
table {{ border-collapse: collapse; width: 100%; }} th, td {{ border: 0.3mm solid #c8c8c8; padding: 1.1mm 1.6mm; text-align: left; vertical-align: top; }}
th {{ background: #f0f0f0; }} td.clean {{ color: #1d6b32; font-weight: bold; }} td.has_errors {{ color: #a3261b; font-weight: bold; }}
section {{ break-inside: avoid; }} .summary b {{ font-size: 11pt; }}
</style></head><body>
<h1>Japanese alignment test set ({LOCALE}) — answer key</h1>
<p>Test file: <code>output/json/{LOCALE}.json</code> · audio: <code>output/wav/ja_0001.wav … ja_0025.wav</code> (16 kHz mono).
Keep this document away from whoever inspects the files.</p>
<p class="summary"><b>{meta['files']}</b> files · <b>{meta['clean']}</b> clean · <b>{meta['with_errors']}</b> with planted errors
({meta['errors']} errors in total) · <b>{meta['synthetic']}</b> synthetic voice · <b>{meta['human']}</b> human-sounding voice</p>
<ul><li><b>Human-sounding</b>: breathing, sighs and uneven pauses, like a person speaking.</li>
<li><b>Synthetic</b>: robotic — no breathing or sighs, exactly the same 0.16 s silence between every word.</li></ul>
<h2>Error types</h2><ul>{legend}</ul>
<h2>All files</h2>
<table><tr><th>File</th><th>Voice type</th><th>Status</th><th>Planted errors</th><th>Duration (s)</th><th>Voice</th></tr>{rows}</table>
<h2>Errors, file by file</h2>
<p>Times are in seconds. "Correct" is the true alignment; "Given" is what the test file says.</p>
{detail}
</body></html>"""


if __name__ == "__main__":
    clean = json.loads((KEY_DIR / f"{LOCALE}_clean.json").read_text(encoding="utf-8"))["items"]
    test, key = {}, []
    for item in clean:
        plan = PLAN.get(item["id"])
        out, errors = inject(item, plan) if plan else (item, [])
        test[item["id"]] = for_test(out)
        summary = {}
        for x in errors:
            summary[x["type"]] = summary.get(x["type"], 0) + 1
        key.append({"id": item["id"], "name": item["name"],
                    "voice_type": "synthetic" if item["synthetic"] else "human",
                    "status": "has_errors" if errors else "clean", "error_count": len(errors),
                    "error_summary": summary, "voice": item["source"]["voice"]["name"],
                    "duration_seconds": item["source"]["duration_seconds"],
                    "correct_transcript": item["transcript"], "given_transcript": out["transcript"],
                    "errors": errors})
    write_locale(HERE / "output" / "json" / f"{LOCALE}.json", LOCALE, test)
    by_type = {}
    for k in key:
        for x, n in k["error_summary"].items():
            by_type[x] = by_type.get(x, 0) + n
    meta = {"locale": LOCALE, "files": len(key), "clean": sum(k["status"] == "clean" for k in key),
            "with_errors": sum(k["status"] != "clean" for k in key), "errors": sum(k["error_count"] for k in key),
            "errors_by_type": by_type, "synthetic": sum(k["voice_type"] == "synthetic" for k in key),
            "human": sum(k["voice_type"] == "human" for k in key),
            "error_types": MEANING}
    (KEY_DIR / f"{LOCALE}_answer_key.json").write_text(json.dumps({"fileMetadata": meta, "files": key},
                                                                  ensure_ascii=False, indent=2), encoding="utf-8")
    with open(KEY_DIR / f"{LOCALE}_answer_key.csv", "w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.writer(fh)
        wr.writerow(["file", "voice_type", "status", "error_type", "word", "correct_start", "correct_end",
                     "given_word", "given_start", "given_end", "description"])
        for k in key:
            if not k["errors"]:
                wr.writerow([k["name"], k["voice_type"], k["status"], "", "", "", "", "", "", "", "no planted errors"])
            for x in k["errors"]:
                c, g = x["correct"] or {}, x["given"] or {}
                wr.writerow([k["name"], k["voice_type"], k["status"], x["type"], c.get("word", ""), c.get("start", ""),
                             c.get("end", ""), g.get("word", ""), g.get("start", ""), g.get("end", ""), x["description"]])
    browser = chromium()
    if browser:
        with tempfile.TemporaryDirectory() as tmp:
            page = pathlib.Path(tmp) / "key.html"
            page.write_text(answer_key_html(key, meta), encoding="utf-8")
            pdf = KEY_DIR / f"{LOCALE}_answer_key.pdf"
            subprocess.run([browser, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                            f"--print-to-pdf={pdf}", page.as_uri()], check=True, capture_output=True)
    else:
        print("No Chromium found: answer key PDF not written (JSON and CSV are).")
    print(f"{len(key)} files: {meta['clean']} clean, {meta['with_errors']} with {meta['errors']} planted errors")
