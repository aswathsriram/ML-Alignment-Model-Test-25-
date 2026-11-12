#!/usr/bin/env python3
"""
spec/batch_*.txt -> transcripts.jsonl: the 1000 French clips, guideline words, voices.

Words follow Forced_Alignment_Guidelines_fr_FR: lowercase, no punctuation (apostrophes inside a word stay, elided
forms are one word), hyphens removed with each part its own word (vingt-deux -> vingt deux), numbers as words.
Each line is checked (characters, length, no digits / abbreviations, gender) and duplicates are dropped.
Voices: 25 female + 25 male (voices_fr.json), each voice used for an equal share of its gender's clips.

Run    : python french_1000/build_transcripts.py
"""
import collections, json, pathlib, random, re, sys

HERE = pathlib.Path(__file__).resolve().parent
SEED = 20261112
TAGS = {"[breathes]", "[sighs]", "[inhales]", "[exhales]"}
WORD = re.compile(r"[a-zàâäçéèêëîïôöùûüÿœæ']+")


def derive(tts):
    bare = re.sub(r"\[[^\]]*\]", " ", tts).replace("’", "'")
    words, groups = [], []
    for tok in bare.split():
        t = tok.lower().strip('„“"«»()¿¡,!?…:;–—.')
        if not t:
            continue
        parts = [p for p in t.split("-") if p]
        if len(parts) > 1:
            groups.append([len(words), len(words) + len(parts) - 1])
        words += parts
    return words, groups


def problems(g, tts, words):
    out = []
    if g not in ("F", "M"):
        out.append("gender")
    tags = re.findall(r"\[[^\]]*\]", tts)
    if any(t not in TAGS for t in tags) or len(tags) > 1 or (tags and not tts.startswith(tags[0])):
        out.append("tag")
    if re.search(r"[\d%€$&@+/°«»()]|\.\.\.|…", tts):
        out.append("digit/symbol")
    if re.search(r"\b[A-Z]{2,}\b|\b(?:M|Mme|km|kg|etc)\b\.?", tts):
        out.append("abbreviation")
    bad = [w for w in words if not WORD.fullmatch(w) or w.startswith("'") or w.endswith("'") and w not in ("presqu'",)]
    if bad:
        out.append(f"chars {bad}")
    if not 10 <= len(words) <= 40:
        out.append(f"{len(words)} words")
    return out


def main():
    rows, bad, seen = [], [], set()
    for f in sorted((HERE / "spec").glob("batch_*.txt")):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            parts = line.split("|")
            if len(parts) != 3:
                bad.append((f.name, n, "format", line)); continue
            sid, g, tts = (p.strip() for p in parts)
            words, groups = derive(tts)
            pr = problems(g, tts, words)
            key = " ".join(words)
            if key in seen:
                pr.append("duplicate")
            if pr:
                bad.append((f.name, n, pr, line)); continue
            seen.add(key)
            rows.append({"src": sid, "gender": "female" if g == "F" else "male", "tts_text": tts, "words": words,
                         "hyphen_groups": groups})
    for b in bad:
        print("REJECT", b)
    print(f"{len(rows)} good lines, {len(bad)} rejected")
    if "--check" in sys.argv:
        return
    rng = random.Random(SEED)
    rng.shuffle(rows)
    rows = rows[:1000]
    assert len(rows) == 1000, f"need 1000 good lines, have {len(rows)}"
    voices = json.loads((HERE / "voices_fr.json").read_text(encoding="utf-8"))
    by_g = collections.defaultdict(list)
    for r in rows:
        by_g[r["gender"]].append(r)
    for g, rs in by_g.items():
        pool = voices[g]
        for k, r in enumerate(rs):
            v = pool[k % len(pool)]
            r["voice_id"], r["voice_name"] = v["voice_id"], v["name"]
    for k, r in enumerate(rows, 1):
        r["id"] = f"fr{k:04d}"
    keep = ["id", "src", "gender", "voice_id", "voice_name", "tts_text", "words", "hyphen_groups"]
    (HERE / "transcripts.jsonl").write_text("".join(json.dumps({k: r[k] for k in keep}, ensure_ascii=False) + "\n"
                                                    for r in rows), encoding="utf-8")
    n = [len(r["words"]) for r in rows]
    vc = collections.Counter(r["voice_id"] for r in rows)
    print(f"1000 clips: {dict(collections.Counter(r['gender'] for r in rows))}, words {min(n)}-{max(n)} "
          f"(avg {sum(n) / len(n):.1f}), {len(vc)} voices, {min(vc.values())}-{max(vc.values())} clips per voice")


if __name__ == "__main__":
    main()
