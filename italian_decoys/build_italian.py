#!/usr/bin/env python3
"""
Italian decoys from the platform's forced-alignment deliveries, in the align-decoys/v1 upload format keyed on
work_item_id.

Correct alignment per work item: the ADJUDICATION answer when there is one, else the blind-pass answer (the two
blind passes of every non-adjudicated item have identical words, so word numbers match either one; every mistake
is checked against both versions' timings). Synthetic items with no segments are skipped.

Mistakes (2-3 per file, 3 where the file is long enough; at least 3 words apart; tags such as (()) never touched;
the most obvious one "critical": true):
  move    boundary mismatch: minor 40-80 ms, major 100-300 ms, critical over 300 ms
  remove  missing word: keeps its text, loses its timing
  add     hallucinated word: an extra chip in a pause of at least 0.35 s, repeating the word before

Run    : python italian_decoys/build_italian.py <deliveries.zip|folder> <template.json>
Output : italian_decoys/italian_decoys_plants.json
"""
import collections, glob, json, pathlib, random, sys, tempfile, zipfile

HERE = pathlib.Path(__file__).resolve().parent
SEED = 20261109
SIZES = [("minor", 40, 80), ("major", 100, 300), ("critical", 310, 700)]
SHARE = {"move": 0.60, "remove": 0.20, "add": 0.20}
TOUCH, KEEP, MIN_PAUSE, GAP_WORDS = 0.0005, 0.03, 0.35, 3


def secs(x):
    h, m, s = x.split(":")
    return round(int(h) * 3600 + int(m) * 60 + float(s), 3)


def is_tag(w):
    return w.startswith(("[", "<", "(("))


def load(src):
    if str(src).endswith(".zip"):
        tmp = tempfile.mkdtemp()
        zipfile.ZipFile(src).extractall(tmp)
        src = tmp
    for f in sorted(glob.glob(str(pathlib.Path(src) / "*.json"))):
        for w in json.loads(pathlib.Path(f).read_text(encoding="utf-8"))["workitems"]:
            runs = sorted([r for k, v in w.items() if isinstance(v, list) for r in v], key=lambda r: r["metadata"]["labelledTimestamp"])
            answers = [(r["metadata"]["operationType"], r["data"]["taskAnswers"][0], r["metadata"]["taskId"]) for r in runs]
            yield w["workItemId"], answers


def to_words(ans):
    return [{"i": i, "w": s["final_transcription"], "s": secs(s["final_startTime"]), "e": secs(s["final_endTime"])}
            for i, s in enumerate(ans["segments"])]


def move_ok(W, dur, k, edge, ms):
    n, d = len(W), ms / 1000
    if is_tag(W[k]["w"]):
        return None
    if edge == "start":
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


def candidates(versions, dur, action, rng, size=None):
    W, n, out = versions[0], len(versions[0]), []
    if action == "move":
        _, lo, hi = next(s for s in SIZES if s[0] == size)
        for k in range(n):
            for edge in ("start", "end"):
                for sign in (-1, 1):
                    ms = sign * rng.randrange(lo, hi + 1, 10)
                    affs = [move_ok(V, dur, k, edge, ms) for V in versions]
                    if all(affs):
                        out.append(({"action": "move", "word": k, "edge": edge, "shift_ms": ms}, set().union(*affs),
                                    f"{W[k]['w']} {edge} {abs(ms)} ms {'early' if ms < 0 else 'late'} ({size} boundary mismatch)"))
    elif action == "remove":
        for k in range(n):
            if not is_tag(W[k]["w"]) and all(V[k]["e"] - V[k]["s"] >= 0.12 for V in versions) and len(W[k]["w"]) >= 2:
                out.append(({"action": "remove", "word": k}, {k}, f"missing word: {W[k]['w']} loses its timing"))
    else:
        for k in range(n - 1):
            if not is_tag(W[k]["w"]) and not is_tag(W[k + 1]["w"]) and all(V[k + 1]["s"] - V[k]["e"] >= MIN_PAUSE for V in versions):
                gap = min(V[k + 1]["s"] - V[k]["e"] for V in versions)
                out.append(({"action": "add", "after_word": k, "text": W[k]["w"]}, {k, k + 1},
                            f"hallucinated word: extra '{W[k]['w']}' in the {gap:.2f} s pause after it"))
    return out


def obviousness(p, W):
    if p["action"] == "move":
        return abs(p["shift_ms"])
    if p["action"] == "remove":
        return 300 + 1000 * (W[p["word"]]["e"] - W[p["word"]]["s"])
    return 400


def main(src, template):
    tpl = json.loads(pathlib.Path(template).read_text(encoding="utf-8"))
    have, sizes, decoys, skipped = collections.Counter(), collections.Counter(), [], []
    for n, (wid, answers) in enumerate(load(src), 1):
        adj = [a for o, a, _ in answers if o == "ADJUDICATION"]
        chosen = adj[-1] if adj else answers[-1][1]
        if not chosen["segments"]:
            skipped.append({"work_item_id": wid, "reason": "synthetic, no segments" if chosen["audio_synthetic"] else "no segments"})
            continue
        versions = [to_words(chosen)] if adj else [to_words(a) for o, a, _ in answers]
        assert all([w["w"] for w in V] == [w["w"] for w in versions[0]] for V in versions), wid
        W = versions[0]
        dur = max(V[-1]["e"] for V in versions)          # no audio length in the export: never move past the last word's end
        rng = random.Random(f"{SEED}-{wid}")
        target = 3 if len(W) >= 7 else 2
        plants, taken = [], []
        while len(plants) < target:
            total = sum(have.values()) + 1
            placed = False
            for action in sorted(SHARE, key=lambda a: (have[a] / total - SHARE[a], rng.random())):
                order = sorted([s for s, _, _ in SIZES], key=lambda s: (sizes[s], rng.random())) if action == "move" else [None]
                for size in order:
                    cands = [c for c in candidates(versions, dur, action, rng, size)
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
            top = max(range(len(plants)), key=lambda i: obviousness(plants[i], W))
            plants[top]["critical"] = True
            plants = [{**{k: v for k, v in p.items() if k != "note"}, "note": p["note"]} for p in plants]
            plants.sort(key=lambda p: p.get("word", p.get("after_word")))
        decoys.append({"decoy_ref": f"it_{n:03d}_{answers[-1][2]}", "work_item_id": wid, "plants": plants})
    out = {"format": tpl["format"], "instructions": tpl["instructions"], "decoys": decoys}
    (HERE / "italian_decoys_plants.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (HERE / "italian_skipped.json").write_text(json.dumps(skipped, indent=2) + "\n", encoding="utf-8")
    per = collections.Counter(len(d["plants"]) for d in decoys)
    print(f"{len(decoys)} decoys ({len(skipped)} skipped) | {sum(have.values())} mistakes {dict(have)} | "
          f"boundary {dict(sizes)} | per file {dict(sorted(per.items()))}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
