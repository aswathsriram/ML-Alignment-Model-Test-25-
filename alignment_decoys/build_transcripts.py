"""Turn decoy_spec.txt into <locale>/transcripts.jsonl: spoken-form words per the guidelines, decoy hints, voices."""
import json, re, pathlib, collections, sys
ROOT = pathlib.Path(__file__).resolve().parent      # decoy_spec.txt and voice_pick.json live here
SP = ROOT
voices = json.load(open(SP / "voice_pick.json", encoding="utf-8"))
CODE = {"de_DE": "de", "es_ES": "es", "it_IT": "it", "pt_BR": "pt", "fr_FR": "fr"}

def derive(tts):
    """Spoken-form words per the guidelines: lowercase, no punctuation (apostrophes inside words stay, a period after
    a spelled letter stays), hyphens removed with each part its own word. Returns words and hyphen groups."""
    bare = re.sub(r"\[[^\]]*\]", " ", tts).replace("’", "'")
    words, groups = [], []
    for tok in bare.split():
        t = tok.lower().strip('„“"«»()¿¡,!?…:;–—')
        if re.fullmatch(r"[^\W\d_]\.", t):
            words.append(t); continue
        t = t.rstrip(".")
        if not t:
            continue
        parts = [p for p in t.split("-") if p]
        if len(parts) > 1:
            groups.append([len(words), len(words) + len(parts) - 1])
        words += parts
    return words, groups

out = collections.defaultdict(list); loc = None
for line in (SP / "decoy_spec.txt").read_text(encoding="utf-8").splitlines():
    if not line.strip() or line.startswith("#"): continue
    if line.startswith("== "): loc = line[3:].strip(); continue
    i, style, gender, tts, hints = line.split("|")
    words, groups = derive(tts)
    bad = [w for w in words if not re.fullmatch(r"[a-zàâäáãçéèêëíìîïñóòôöõœúùûüÿß']+|[a-zäöüß]\.", w)]
    assert not bad, (loc, i, bad)
    if style == "synthetic": assert "[" not in tts, i
    h = {"ws": [], "num": [], "cap": [], "cmp": []}
    for part in filter(None, hints.split(";")):
        kind, val = part.split(":", 1)
        if kind == "ws":
            a, rest = val.split(">"); b, band = rest.rsplit(":", 1)
            assert a in words and b != a and band in ("A1", "A2", "A3"), (loc, i, part); h["ws"].append([a, b, band])
        elif kind == "num":
            a, b = val.split(">"); assert a in words and b.isdigit(), (loc, i, part); h["num"].append([a, b])
        elif kind == "cap":
            assert val in words, (loc, i, part); h["cap"].append(val)
        elif kind == "cmp":
            a, b = val.split(">"); p1, p2 = b.split("+"); assert a in words and p1 + p2 == a, (loc, i, part); h["cmp"].append([a, p1, p2])
    out[loc].append({"id": i, "style": style, "gender": "female" if gender == "F" else "male", "tts_text": tts,
                     "words": words, "hyphen_groups": groups, "hints": h})

for loc, rows in out.items():
    code = CODE[loc]; pool = {g: list(v) for g, v in voices[code].items()}
    assert len(rows) == 20 and sum(r["style"] == "synthetic" for r in rows) == 3, loc
    for r in rows:
        v = pool[r["gender"]].pop(0)
        r["voice_id"] = v["voice_id"]; r["language"] = code
    (ROOT / loc).mkdir(parents=True, exist_ok=True)
    keep = ["id", "language", "words", "style", "voice_id", "tts_text", "hyphen_groups", "hints"]
    (ROOT / loc / "transcripts.jsonl").write_text("".join(json.dumps({k: r[k] for k in keep}, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    n = [len(r["words"]) for r in rows]
    print(f"{loc}: 20 rows, 3 synthetic, words/clip {min(n)}-{max(n)} (avg {sum(n)/20:.0f}), ws hints {sum(len(r['hints']['ws']) for r in rows)}, "
          f"num {sum(len(r['hints']['num']) for r in rows)}, cmp {sum(len(r['hints']['cmp']) for r in rows)}, hyphen groups {sum(len(r['hyphen_groups']) for r in rows)}, "
          f"letters {sum(w.endswith('.') for r in rows for w in r['words'])}")
print(json.dumps([r["words"] for r in out["fr_FR"] if r["id"] in ("f07", "f10", "f14")], ensure_ascii=False))
print(json.dumps([r["words"] for r in out["de_DE"] if r["id"] in ("d05", "d12")], ensure_ascii=False))
