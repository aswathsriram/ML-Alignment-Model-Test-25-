#!/usr/bin/env python3
"""
Plant deliberate mistakes in 7 of the 25 Japanese files; the other 18 stay exactly as the clean alignment.

Input  : output/answer_key/ja_JP_clean.json      correct alignment (from make_japanese.py)
Output : output/json/ja_JP.json                  the test file: 18 clean items + 7 items with planted mistakes
         output/answer_key/ja_JP_answer_key.json every planted mistake: file, type, word, correct vs given
         output/answer_key/ja_JP_answer_key.csv  the same as a table

Mistake types (word indices refer to the clean alignment):
  boundary_shift          start/end moved before the word starts, into its middle, or past its end
  cut_off                 end placed in the middle of the word, so the word is cut off
  incorrect_transcription the word is spoken, but the transcript says a different word
  missing_segment         the word is spoken, but there is no segment and it is not in the transcript
  hallucinated_segment    a segment and transcript word for something never spoken (placed in a pause)

Run    : python inject_errors_ja.py
"""
import csv, json, pathlib
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


if __name__ == "__main__":
    clean = json.loads((KEY_DIR / f"{LOCALE}_clean.json").read_text(encoding="utf-8"))["items"]
    test, key = {}, []
    for item in clean:
        plan = PLAN.get(item["id"])
        out, errors = inject(item, plan) if plan else (item, [])
        test[item["id"]] = out
        key.append({"id": item["id"], "name": item["name"], "synthetic": item["synthetic"],
                    "voice": item["source"]["voice"]["name"],
                    "category": "planted_errors" if errors else "clean",
                    "correct_transcript": item["transcript"], "given_transcript": out["transcript"],
                    "errors": errors})
    write_locale(HERE / "output" / "json" / f"{LOCALE}.json", LOCALE, test)
    (KEY_DIR / f"{LOCALE}_answer_key.json").write_text(json.dumps(
        {"fileMetadata": {"locale": LOCALE, "files": len(key),
                          "clean": sum(k["category"] == "clean" for k in key),
                          "with_planted_errors": sum(k["category"] != "clean" for k in key),
                          "synthetic": sum(k["synthetic"] for k in key)},
         "files": key}, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(KEY_DIR / f"{LOCALE}_answer_key.csv", "w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.writer(fh)
        wr.writerow(["id", "synthetic", "category", "error_type", "word", "correct_start", "correct_end",
                     "given_word", "given_start", "given_end", "description"])
        for k in key:
            if not k["errors"]:
                wr.writerow([k["id"], k["synthetic"], k["category"], "", "", "", "", "", "", "", "no planted errors"])
            for e in k["errors"]:
                c, g = e["correct"] or {}, e["given"] or {}
                wr.writerow([k["id"], k["synthetic"], k["category"], e["type"], c.get("word", ""), c.get("start", ""),
                             c.get("end", ""), g.get("word", ""), g.get("start", ""), g.get("end", ""), e["description"]])
    n = sum(len(k["errors"]) for k in key)
    print(f"{len(key)} files: {sum(k['category'] == 'clean' for k in key)} clean, "
          f"{sum(k['category'] != 'clean' for k in key)} with {n} planted errors")
