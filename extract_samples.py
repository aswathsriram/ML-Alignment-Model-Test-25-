#!/usr/bin/env python3
"""
Step 1: pull clean style samples out of the platform exports (<language>_segments.json).

Reads   : exports/*.json        (the files as exported, e.g. french_segments.json)
Writes  : samples/<lang>.txt    one spoken-form transcription per line (real speech only)
          samples/stats.json    per-language counts + length targets for generation

Keeps only files whose whole-audio tag is "none" (real, transcribable speech) and that were not
dumped. Skips synthetic_speech / sensitive_content / non-target / no_speech files.
Annotator names/emails and file paths are NOT copied, so they never reach the prompt.

Usage: python extract_samples.py
"""
import glob, json, pathlib, statistics as st

HERE = pathlib.Path(__file__).parent
LANG = {"French": "fr", "German": "de", "Italian": "it", "Portuguese": "pt", "Spanish": "es",
        "Japanese": "ja", "Korean": "ko", "Chinese": "zh", "Hindi": "hi"}


def lang_code(label):
    for name, code in LANG.items():
        if label and label.startswith(name):
            return code
    return None


def main():
    (HERE / "samples").mkdir(exist_ok=True)
    stats = {}
    for f in sorted(glob.glob(str(HERE / "exports" / "*.json"))):
        data = json.load(open(f, encoding="utf-8"))
        by_lang = {}
        for item in data:
            code = lang_code(item.get("Language"))
            seg = (item.get("SegmentsJson") or [{}])[0]
            tags = seg.get("mlTags") or {}
            text = (tags.get("spoken-form-transcription") or "").strip()
            if not code or not text or item.get("DumpAlignment"):
                continue
            if tags.get("select-whole-audio-tag") != "none" or item.get("SyntheticSpeaker"):
                continue
            by_lang.setdefault(code, []).append((text, item.get("DurationSeconds") or 0))
        for code, rows in by_lang.items():
            (HERE / "samples" / f"{code}.txt").write_text("\n".join(t for t, _ in rows) + "\n", encoding="utf-8")
            wc = sorted(len(t.split()) for t, _ in rows)
            du = sorted(d for _, d in rows)
            q = lambda xs, p: xs[min(len(xs) - 1, int(p * len(xs)))]
            stats[code] = {"source_file": pathlib.Path(f).name, "samples": len(rows),
                           "words_p10_median_p90": [q(wc, .1), st.median(wc), q(wc, .9)],
                           "seconds_p10_median_p90": [round(q(du, .1), 1), round(st.median(du), 1), round(q(du, .9), 1)],
                           "max_seconds": round(max(du), 1)}
            print(code, stats[code])
    (HERE / "samples" / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
