#!/usr/bin/env python3
"""
Spanish decoys in the platform's upload format: {"decoys": [{decoy_ref, file_id, file_name, plants}]}.

Plants are applied by the platform to its own reviewer-approved alignment, so words are numbered as in each item's
full original transcript (every spoken word, including the ones that had no chip in Updated_spanish.json).
Timings for the rule checks come from the chips in that file; a word with no chip has no known timing and nothing
is planted on it or next to it.

Error types (move / remove / add only — no joins):
  move    boundary mismatch: minor 40-80 ms, major 100-300 ms, critical over 300 ms; a touching neighbour moves with it,
          never past the neighbour's far edge, before 0 or past the audio end
  remove  missing segment: the word keeps its text but loses its timing
  add     hallucinated segment: an extra chip in a pause of at least 0.35 s, repeating the word before
1-6 per file as its length allows, at least 3 words apart, never on a tag; the 1-2 most obvious are "critical": true.

Input  : spanish_fix/Updated_spanish_original.json
Output : spanish_fix/spanish_decoy_plants.json
Run    : python spanish_fix/build_spanish_plants.py
"""
import collections, difflib, json, pathlib, random, re

HERE = pathlib.Path(__file__).resolve().parent
SEED = 20261107
SIZES = [("minor", 40, 80), ("major", 100, 300), ("critical", 310, 700)]
SHARE = {"move": 0.60, "remove": 0.20, "add": 0.20}
DIGITS = {"1": "uno", "2": "dos", "4": "cuatro", "5": "cinco", "6": "seis", "7": "siete", "12": "doce", "30": "treinta",
          "50": "cincuenta", "70": "setenta", "90": "noventa"}
TOUCH, KEEP, MIN_PAUSE, GAP_WORDS = 0.0005, 0.03, 0.35, 3


def is_tag(w):
    return w.startswith(("[", "<", "(("))


def clean(w):
    if is_tag(w):
        return w
    s = w.strip(".,;:!?¿¡\"")
    if s.isdigit():
        return DIGITS.get(s, s)
    t = w.lower()
    return t if re.fullmatch(r"[^\W\d_]\.", t) else re.sub(r"[.,;:!?¿¡\"]", "", t)


def gold_words(item):
    """The transcript's words, each with the timing of its chip (joined chips shared by length) or None."""
    T = [clean(t) for t in item["transcript"].split()]
    flat = []
    for c in item["source"]["words"]:
        parts = [clean(p) for p in c["word"].split()]
        tot, t = sum(len(p) for p in parts) or 1, c["start"]
        for j, p in enumerate(parts):
            e = c["end"] if j == len(parts) - 1 else t + (c["end"] - c["start"]) * len(p) / tot
            flat.append((p, t, e)); t = e
    W = [{"i": i, "w": w, "s": None, "e": None} for i, w in enumerate(T)]
    for op, a1, a2, b1, b2 in difflib.SequenceMatcher(None, T, [f[0] for f in flat], autojunk=False).get_opcodes():
        if op == "equal":
            for k in range(a2 - a1):
                W[a1 + k]["s"], W[a1 + k]["e"] = round(flat[b1 + k][1], 3), round(flat[b1 + k][2], 3)
    for a, b in zip(W, W[1:]):                       # a chip that ran over its neighbour: trust the neighbour's start
        if a["e"] is not None and b["s"] is not None and a["e"] > b["s"]:
            a["e"] = b["s"]
    return W


def known(W, *ks):
    return all(0 <= k < len(W) and W[k]["s"] is not None for k in ks)


def move_ok(W, dur, k, edge, ms):
    if is_tag(W[k]["w"]) or not known(W, k):
        return None
    d, n = ms / 1000, len(W)
    if edge == "start":
        if k > 0 and not known(W, k - 1):
            return None
        new = W[k]["s"] + d
        if new < 0 or new > W[k]["e"] - KEEP:
            return None
        if k > 0:
            p = W[k - 1]
            if abs(W[k]["s"] - p["e"]) < TOUCH:
                return None if (is_tag(p["w"]) or new < p["s"] + KEEP) else {k - 1, k}
            if new < p["e"] + 0.01:
                return None
        return {k}
    if k + 1 < n and not known(W, k + 1):
        return None
    new = W[k]["e"] + d
    if new > dur or new < W[k]["s"] + KEEP:
        return None
    if k + 1 < n:
        x = W[k + 1]
        if abs(x["s"] - W[k]["e"]) < TOUCH:
            return None if (is_tag(x["w"]) or new > x["e"] - KEEP) else {k, k + 1}
        if new > x["s"] - 0.01:
            return None
    return {k}


def candidates(W, dur, action, rng, size=None):
    out, n = [], len(W)
    if action == "move":
        _, lo, hi = next(s for s in SIZES if s[0] == size)
        for k in range(n):
            for edge in ("start", "end"):
                for sign in (-1, 1):
                    ms = sign * rng.randrange(lo, hi + 1, 10)
                    aff = move_ok(W, dur, k, edge, ms)
                    if aff:
                        out.append(({"action": "move", "word": k, "edge": edge, "shift_ms": ms}, aff,
                                    f"{W[k]['w']} {edge} {abs(ms)} ms {'early' if ms < 0 else 'late'} ({size})"))
    elif action == "remove":
        for k in range(n):
            if not is_tag(W[k]["w"]) and known(W, k) and W[k]["e"] - W[k]["s"] >= 0.12 and len(W[k]["w"]) >= 2:
                out.append(({"action": "remove", "word": k}, {k}, f"{W[k]['w']} loses its timing"))
    else:
        for k in range(n - 1):
            if not is_tag(W[k]["w"]) and not is_tag(W[k + 1]["w"]) and known(W, k, k + 1) and W[k + 1]["s"] - W[k]["e"] >= MIN_PAUSE:
                out.append(({"action": "add", "after_word": k, "text": W[k]["w"]}, {k, k + 1},
                            f"extra '{W[k]['w']}' in the {W[k + 1]['s'] - W[k]['e']:.2f} s pause after it"))
    return out


def obviousness(p, W):
    if p["action"] == "move":
        return abs(p["shift_ms"])
    if p["action"] == "remove":
        return 300 + 1000 * (W[p["word"]]["e"] - W[p["word"]]["s"])
    return 400


def main():
    src = json.loads((HERE / "Updated_spanish_original.json").read_text(encoding="utf-8"))
    have, sizes, decoys = collections.Counter(), collections.Counter(), []
    for item in src["items"]:
        rng = random.Random(f"{SEED}-{item['id']}")
        W = gold_words(item) if item["transcript"].strip() else []
        dur = item["source"]["duration_seconds"]
        target = min(6, max(3, len(W) // 4))
        plants, taken = [], []
        while len(plants) < target:
            total = sum(have.values()) + 1
            placed = False
            for action in sorted(SHARE, key=lambda a: (have[a] / total - SHARE[a], rng.random())):
                order = sorted([s for s, _, _ in SIZES], key=lambda s: (sizes[s], rng.random())) if action == "move" else [None]
                for size in order:
                    cands = [c for c in candidates(W, dur, action, rng, size)
                             if all(abs(a - b) >= GAP_WORDS for t in taken for a in t for b in c[1])]
                    if cands:
                        p, aff, note = rng.choice(cands)
                        plants.append(dict(p, note=note)); taken.append(aff); have[action] += 1
                        if size:
                            sizes[size] += 1
                        placed = True
                        break
                if placed:
                    break
            if not placed:
                break
        if plants:
            ranked = sorted(range(len(plants)), key=lambda i: -obviousness(plants[i], W))
            for i in ranked[:2 if len(plants) >= 5 else 1]:
                plants[i]["critical"] = True
            plants = [{**{k: v for k, v in p.items() if k != "note"}, "note": p["note"]} for p in plants]
            plants.sort(key=lambda p: p.get("word", p.get("after_word")))
        decoys.append({"decoy_ref": item["name"], "file_id": item["id"], "file_name": item["name"], "plants": plants})
    (HERE / "spanish_decoy_plants.json").write_text(json.dumps({"decoys": decoys}, ensure_ascii=False, indent=2) + "\n",
                                                   encoding="utf-8")
    per = collections.Counter(len(d["plants"]) for d in decoys)
    print(f"{len(decoys)} decoys | plants {dict(have)} | boundary sizes {dict(sizes)} | per file {dict(sorted(per.items()))}")


if __name__ == "__main__":
    main()
