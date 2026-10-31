#!/usr/bin/env python3
"""
Write an align-decoys/v1 pack for one locale from its decoy package:

  words  = the correct (gold) alignment of each file           (i, w, s, e)
  plants = 3-6 planted mistakes per file, in the pack's four actions (move / remove / add / join)

Mistakes from the existing package are carried over wherever the pack rules allow them (boundary moves
>= 150 ms, missing words -> remove, hallucinated words -> add, two-word chips -> join), adapted to the rules
where needed; each file is then filled up to 3-6 plants with new ones. Every pack rule is checked and the
plants are applied the way the pack describes, to prove the result is a valid alignment.

Input  : alignment_decoys/alignment_decoys_<locale>.zip   (decoy_corpus.json: gold alignment + existing decoys)
Output : alignment_decoys/packs/our-files_not-in-platform_<locale>-<date>.json  (our files; the platform only
         accepts decoys on its own reviewer-finalized files, so these need uploading and reviewing there first)
         --fill <exported.json> <out.json>: fill the plants of a pack exported by the platform (imports as is)

Run    : python alignment_decoys/build_pack.py de_DE 2026-10-29
"""
import hashlib, json, pathlib, random, re, sys, zipfile

HERE = pathlib.Path(__file__).resolve().parent
SEED = 20261029
FORMAT = "align-decoys/v1"
INSTRUCTIONS = [   # verbatim from the align-decoys/v1 template
    "`words` is the CORRECT alignment, approved by a reviewer: i = index, w = word, s / e = start / end in seconds. Never change it.",
    "Fill each decoy's `plants` with 3–6 deliberate mistakes an aligner can only find by listening.",
    "move — {\"action\":\"move\",\"word\":12,\"edge\":\"start\"|\"end\",\"shift_ms\":-300}: moves one edge of word 12. Positive = later. A neighbour touching that edge moves with it. Use 150–700 ms (150–250 subtle, 250–450 moderate, 450+ obvious). Never push an edge past the far edge of the neighbouring word, before 0 or past the audio end.",
    "remove — {\"action\":\"remove\",\"word\":40}: the word keeps its text in the transcript but loses its timing (an aligner must add it back).",
    "add — {\"action\":\"add\",\"after_word\":20,\"text\":\"the\"}: an extra chip in the pause after word 20 (the pause must be at least 0.35 s). Use a word from the same sentence, e.g. a repeat of the word before.",
    "join — {\"action\":\"join\",\"word\":7}: words 7 and 8 become one chip. Only where words are separated by spaces (NOT ja_JP or zh_CN), and only when the true boundary is at least 0.2 s away from the middle of the joined chip.",
    "Keep mistakes at least 3 words apart. Never touch a tag word (text starting with [ or <).",
    "Mark the 1–2 most obvious mistakes \"critical\": true (must-catch). Optional \"note\" is for you only.",
    "Return the SAME JSON with only the `plants` arrays filled. Do not add, remove or edit any other field.",
]
MIN_MS, MAX_MS = 150, 700
MIN_PAUSE, MIN_JOIN_OFFSET, MIN_GAP_WORDS = 0.35, 0.2, 3
KEEP = 0.06                 # a word (or a touching neighbour) keeps at least 60 ms after a move
TOUCH = 0.0005              # edges closer than this touch, so they move together
MOVE_CLASSES = [("subtle", 150, 250), ("moderate", 260, 450), ("obvious", 460, 700)]
ACTION_SHARE = {"move": 0.50, "remove": 0.17, "add": 0.17, "join": 0.16}


def is_tag(w):
    return w["w"].startswith(("[", "<"))


def touching(a_end, b_start):
    return abs(b_start - a_end) < TOUCH


def move_check(W, dur, k, edge, ms):
    """None if the move breaks a pack rule, else the set of word indices it changes."""
    if is_tag(W[k]) or not MIN_MS <= abs(ms) <= MAX_MS:
        return None
    d = ms / 1000
    if edge == "start":
        new = W[k]["s"] + d
        if new < 0 or new > W[k]["e"] - KEEP:
            return None
        if k > 0:
            p = W[k - 1]
            if touching(p["e"], W[k]["s"]):                       # neighbour moves with it
                return None if (is_tag(p) or new < p["s"] + KEEP) else {k - 1, k}
            if new < p["e"] + 0.01:                                # would run into a neighbour that does not move
                return None
        return {k}
    new = W[k]["e"] + d
    if new > dur or new < W[k]["s"] + KEEP:
        return None
    if k + 1 < len(W):
        n = W[k + 1]
        if touching(W[k]["e"], n["s"]):
            return None if (is_tag(n) or new > n["e"] - KEEP) else {k, k + 1}
        if new > n["s"] - 0.01:
            return None
    return {k}


def add_check(W, dur, k):
    if is_tag(W[k]) or k + 1 >= len(W):
        return None
    return {k, k + 1} if W[k + 1]["s"] - W[k]["e"] >= MIN_PAUSE else None


def join_check(W, k):
    if k + 1 >= len(W) or is_tag(W[k]) or is_tag(W[k + 1]):
        return None
    mid = (W[k]["s"] + W[k + 1]["e"]) / 2
    boundary = (W[k]["e"] + W[k + 1]["s"]) / 2
    return {k, k + 1} if abs(boundary - mid) >= MIN_JOIN_OFFSET else None


def spaced(taken, new):
    return all(abs(a - b) >= MIN_GAP_WORDS for t in taken for a in t for b in new)


def obviousness(p, W):
    if p["action"] == "move":
        return abs(p["shift_ms"])
    if p["action"] == "remove":
        w = W[p["word"]]
        return 350 + 1000 * (w["e"] - w["s"])
    if p["action"] == "add":
        return 420
    k = p["word"]
    mid = (W[k]["s"] + W[k + 1]["e"]) / 2
    return 250 + 1000 * abs((W[k]["e"] + W[k + 1]["s"]) / 2 - mid)


def describe_move(W, k, edge, ms):
    side = "previous" if edge == "start" else "next"
    near = (k > 0 and touching(W[k - 1]["e"], W[k]["s"])) if edge == "start" else \
           (k + 1 < len(W) and touching(W[k]["e"], W[k + 1]["s"]))
    cls = next(c for c, lo, hi in MOVE_CLASSES if abs(ms) <= hi) if abs(ms) <= MAX_MS else "obvious"
    return (f"{W[k]['w']} {edge} {abs(ms)} ms {'earlier' if ms < 0 else 'later'} ({cls})"
            + (f"; touching {side} word moves with it" if near else ""))


def carried(e, W, dur):
    """Existing decoys that fit the pack rules, adapted where needed: [(plant, affected, note)]."""
    out = []
    for x in e["injections"]:
        f, m = x["family"], x.get("meta", {})
        if f in ("BND-MAJOR", "BND-OVERLAP") and abs(m["shift_ms"]) >= MIN_MS:   # smaller ones are re-planned
            k, edge, ms = m["plain_offset"], m["edge"], m["shift_ms"]
            want = min(MAX_MS, abs(ms))
            for mag in range(want, MIN_MS - 1, -10):                # shrink until the rules allow it
                aff = move_check(W, dur, k, edge, mag if ms > 0 else -mag)
                if aff:
                    s = mag if ms > 0 else -mag
                    how = "as is" if s == ms else f"{ms:+d} ms -> {s:+d} ms"
                    out.append(({"action": "move", "word": k, "edge": edge, "shift_ms": s}, aff,
                                f"{describe_move(W, k, edge, s)} · from {x['injection_id']} ({f}, {how})"))
                    break
        elif f == "WD":
            k = m["plain_offset"]
            if not is_tag(W[k]):
                out.append(({"action": "remove", "word": k}, {k},
                            f"{W[k]['w']} loses its timing · from {x['injection_id']} (missing segment)"))
        elif f == "WH" and m["inserted_before_index"] > 0:
            k = m["inserted_before_index"] - 1
            aff = add_check(W, dur, k)
            if aff:
                out.append(({"action": "add", "after_word": k, "text": W[k]["w"]}, aff,
                            f"extra '{W[k]['w']}' in the {W[k + 1]['s'] - W[k]['e']:.2f} s pause after it · from "
                            f"{x['injection_id']} (hallucinated '{m['word']}', now a repeat of the word before)"))
        elif f == "SEG-MERGE":
            k = m["plain_offset"]
            aff = join_check(W, k)
            if aff:
                out.append(({"action": "join", "word": k}, aff,
                            f"{W[k]['w']} + {W[k + 1]['w']} as one chip · from {x['injection_id']}"))
    return out


def fresh(W, dur, action, rng, cls=None):
    """New candidates for one action: [(plant, affected, note)]."""
    n, out = len(W), []
    if action == "move":
        lo, hi = next((a, b) for c, a, b in MOVE_CLASSES if c == cls)
        for k in range(n):
            for edge in ("start", "end"):
                for sign in (-1, 1):
                    ms = sign * rng.randrange(lo, hi + 1, 10)
                    aff = move_check(W, dur, k, edge, ms)
                    if aff:
                        out.append(({"action": "move", "word": k, "edge": edge, "shift_ms": ms}, aff,
                                    describe_move(W, k, edge, ms) + " · new"))
    elif action == "remove":
        for k in range(1, n - 1):
            if not is_tag(W[k]) and W[k]["e"] - W[k]["s"] >= 0.12 and len(W[k]["w"]) >= 3:
                out.append(({"action": "remove", "word": k}, {k}, f"{W[k]['w']} loses its timing · new"))
    elif action == "add":
        for k in range(n - 1):
            aff = add_check(W, dur, k)
            if aff:
                out.append(({"action": "add", "after_word": k, "text": W[k]["w"]}, aff,
                            f"extra '{W[k]['w']}' in the {W[k + 1]['s'] - W[k]['e']:.2f} s pause after it · new"))
    else:
        for k in range(n - 1):
            aff = join_check(W, k)
            if aff:
                out.append(({"action": "join", "word": k}, aff, f"{W[k]['w']} + {W[k + 1]['w']} as one chip · new"))
    return out


def apply(W, dur, plants):
    """Apply the plants as the pack describes and check the result is a valid alignment."""
    chips = [dict(w=x["w"], s=x["s"], e=x["e"], i=x["i"]) for x in W]
    moved = set()
    for p in plants:
        if p["action"] == "move":
            k, d = p["word"], p["shift_ms"] / 1000
            moved.add(k)
            if p["edge"] == "start":
                if k > 0 and touching(chips[k - 1]["e"], chips[k]["s"]):
                    chips[k - 1]["e"] = round(chips[k]["s"] + d, 3); moved.add(k - 1)
                chips[k]["s"] = round(chips[k]["s"] + d, 3)
            else:
                if k + 1 < len(chips) and touching(chips[k]["e"], chips[k + 1]["s"]):
                    chips[k + 1]["s"] = round(chips[k]["e"] + d, 3); moved.add(k + 1)
                chips[k]["e"] = round(chips[k]["e"] + d, 3)
    for p in plants:
        if p["action"] == "remove":
            chips[p["word"]]["s"] = chips[p["word"]]["e"] = None
        elif p["action"] == "join":
            a, b = chips[p["word"]], chips[p["word"] + 1]
            a.update(w=f"{a['w']} {b['w']}", e=b["e"]); b["s"] = b["e"] = "joined"
    timed = [c for c in chips if isinstance(c["s"], float) or isinstance(c["s"], int)]
    for p in plants:
        if p["action"] == "add":
            a, b = W[p["after_word"]], W[p["after_word"] + 1]
            mid = (a["e"] + b["s"]) / 2
            timed.append(dict(w=p["text"], s=round(mid - 0.12, 3), e=round(mid + 0.12, 3), i=None))
    timed.sort(key=lambda c: c["s"])
    for c in timed:
        assert 0 <= c["s"] < c["e"] <= dur + 1e-9, c
        if c["i"] in moved:                                  # a moved word keeps >= 60 ms (gold may be shorter)
            assert c["e"] - c["s"] >= KEEP - 1e-9, c
    for a, b in zip(timed, timed[1:]):
        assert a["e"] <= b["s"] + 1e-9, (a, b)
    return timed


def plan(loc):
    """Plant 3-6 pack-rule mistakes per file of a locale's decoy package (carry over what fits, re-plan the rest).
    Returns, in the pre-fill's order: [{"e": corpus record, "W": gold words, "dur": seconds, "plants": [...]}]."""
    rng = random.Random(f"{SEED}-{loc}")
    z = zipfile.ZipFile(HERE / f"alignment_decoys_{loc}.zip")
    corpus = {e["file_id"]: e for e in json.loads(z.read(f"alignment_decoys_{loc}/decoy_corpus.json"))}
    prefill = json.loads(z.read(f"alignment_decoys_{loc}/alignment_prefill_{loc}.json"))
    order = [it["id"] for it in prefill["items"]]                       # same (random) order as the pre-fill
    files = []
    for fid in order:
        e = corpus[fid]
        W = [{"i": i, "w": x["word"], "s": x["start"], "e": x["end"]} for i, x in enumerate(e["gold_segments"])]
        dur = e["duration_seconds"]
        target = min(6, max(3, len(W) // 4))
        files.append({"e": e, "W": W, "dur": dur, "target": target, "plants": [], "taken": []})

    # 1. carry over existing decoys that fit
    for f in files:
        for plant, aff, note in sorted(carried(f["e"], f["W"], f["dur"]), key=lambda t: -obviousness(t[0], f["W"])):
            if len(f["plants"]) < f["target"] and spaced(f["taken"], aff):
                f["plants"].append(dict(plant, note=note)); f["taken"].append(aff)

    # 2. fill up to the target with new plants, keeping the action mix (moves split subtle / moderate / obvious)
    total = sum(f["target"] for f in files)
    want = {a: round(s * total) for a, s in ACTION_SHARE.items()}
    have = {a: sum(p["action"] == a for f in files for p in f["plants"]) for a in ACTION_SHARE}
    cls_n = {c: sum(1 for f in files for p in f["plants"] if p["action"] == "move"
                    and next(c2 for c2, lo, hi in MOVE_CLASSES if abs(p["shift_ms"]) <= hi) == c) for c, _, _ in MOVE_CLASSES}
    for f in sorted(files, key=lambda f: rng.random()):
        while len(f["plants"]) < f["target"]:
            placed = False
            for action in sorted(ACTION_SHARE, key=lambda a: (have[a] - want[a], rng.random())):
                cls = min(cls_n, key=lambda c: (cls_n[c], rng.random())) if action == "move" else None
                cands = [c for c in fresh(f["W"], f["dur"], action, rng, cls) if spaced(f["taken"], c[1])]
                if not cands and action == "move":
                    for c2 in cls_n:
                        cands = [c for c in fresh(f["W"], f["dur"], action, rng, c2) if spaced(f["taken"], c[1])]
                        if cands:
                            cls = c2; break
                if cands:
                    plant, aff, note = rng.choice(cands)
                    f["plants"].append(dict(plant, note=note)); f["taken"].append(aff)
                    have[action] += 1
                    if action == "move":
                        cls_n[next(c for c, lo, hi in MOVE_CLASSES if abs(plant["shift_ms"]) <= hi)] += 1
                    placed = True
                    break
            if not placed:
                break

    # 2b. a short file that ended with fewer than 3: search other combinations until 3 fit the spacing rule
    for f in files:
        if len(f["plants"]) >= 3:
            continue
        best = (f["plants"], f["taken"])
        for attempt in range(300):
            r2 = random.Random(f"{SEED}-{f['e']['file_id']}-{attempt}")
            cands = [c for a in ACTION_SHARE for cls in ([m for m, _, _ in MOVE_CLASSES] if a == "move" else [None])
                     for c in fresh(f["W"], f["dur"], a, r2, cls)]
            r2.shuffle(cands)
            plants, taken = [], []
            for plant, aff, note in cands:
                if len(plants) < f["target"] and spaced(taken, aff):
                    plants.append(dict(plant, note=note)); taken.append(aff)
            if len(plants) > len(best[0]):
                best = (plants, taken)
            if len(best[0]) >= 3:
                break
        f["plants"], f["taken"] = best

    # 3. critical: the 1-2 most obvious per file
    out = []
    for f in files:
        W, plants = f["W"], f["plants"]
        assert 3 <= len(plants) <= 6, (f["e"]["file_name"], len(plants))
        ranked = sorted(range(len(plants)), key=lambda i: -obviousness(plants[i], W))
        crit = set(ranked[:2 if len(plants) >= 5 else 1])
        final = []
        for i, p in enumerate(plants):
            q = {k: v for k, v in p.items() if k != "note"}
            if i in crit:
                q["critical"] = True
            q["note"] = p["note"]
            final.append(q)
        final.sort(key=lambda p: p.get("word", p.get("after_word")))
        apply(W, f["dur"], final)
        out.append({"e": f["e"], "W": W, "dur": f["dur"], "plants": final})
    return out


def build(loc, date):
    out = []
    for f in plan(loc):
        W, e = f["W"], f["e"]
        fp = hashlib.sha256(json.dumps([[w["w"], w["s"], w["e"]] for w in W]).encode()).hexdigest()[:8]
        out.append({"decoy_ref": e["file_name"], "file_id": e["file_id"], "file_name": e["file_name"], "locale": loc,
                    "duration_s": f["dur"], "gold_fingerprint": fp, "words": W, "plants": f["plants"]})
    pack = {"format": FORMAT, "instructions": INSTRUCTIONS, "decoys": out}
    path = HERE / "packs" / f"our-files_not-in-platform_{loc}-{date}.json"     # needs the files in the platform first
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, pack


FILL_ORDER = [("move", "obvious"), ("add", None), ("join", None), ("remove", None), ("move", "moderate"),
              ("move", "subtle")]


def fill(template_path, out_path):
    """Fill the empty `plants` of a pack exported by the platform (reviewer-finalized files) and change
    nothing else: the platform only accepts decoys on its own finalized alignments."""
    pack = json.loads(pathlib.Path(template_path).read_text(encoding="utf-8"))
    for d in pack["decoys"]:
        W, dur = d["words"], d["duration_s"]
        rng = random.Random(f"{SEED}-{d['file_id']}")
        target = min(6, max(3, len(W) // 4))
        plants, taken = [], []
        for action, cls in FILL_ORDER:
            if len(plants) >= target:
                break
            cands = [c for c in fresh(W, dur, action, rng, cls) if spaced(taken, c[1])]
            if action == "move" and not cands:
                for c2, _, _ in MOVE_CLASSES:
                    cands = [c for c in fresh(W, dur, action, rng, c2) if spaced(taken, c[1])]
                    if cands:
                        break
            if not cands:
                continue
            # spread the mistakes over the file: prefer the candidate farthest from those already placed
            far = max(min((abs(min(c[1]) - min(t)) for t in taken), default=0) for c in cands)
            plant, aff, note = rng.choice([c for c in cands if min((abs(min(c[1]) - min(t)) for t in taken), default=0) >= far * 0.6])
            plants.append(dict(plant, note=note.replace(" · new", ""))); taken.append(aff)
        while len(plants) < 3:                                   # short file: top up with any valid action
            cands = [c for a in ("move", "remove", "add", "join") for c in fresh(W, dur, a, rng, "moderate")
                     if spaced(taken, c[1])]
            if not cands:
                raise SystemExit(f"{d['file_name']}: cannot place 3 mistakes under the pack rules")
            plant, aff, note = rng.choice(cands)
            plants.append(dict(plant, note=note.replace(" · new", ""))); taken.append(aff)
        ranked = sorted(range(len(plants)), key=lambda i: -obviousness(plants[i], W))
        crit = set(ranked[:2 if len(plants) >= 5 else 1])
        final = []
        for i, p in enumerate(plants):
            q = {k: v for k, v in p.items() if k != "note"}
            if i in crit:
                q["critical"] = True
            q["note"] = p["note"]
            final.append(q)
        final.sort(key=lambda p: p.get("word", p.get("after_word")))
        apply(W, dur, final)
        d["plants"] = final
    pathlib.Path(out_path).write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return pack


if __name__ == "__main__":
    if sys.argv[1:2] == ["--fill"]:                             # python build_pack.py --fill exported.json filled.json
        pack = fill(sys.argv[2], sys.argv[3])
        for d in pack["decoys"]:
            print(d["file_name"], len(d["plants"]), "plants:", [p["action"] for p in d["plants"]])
        sys.exit(0)
    loc = sys.argv[1] if len(sys.argv) > 1 else "de_DE"
    date = sys.argv[2] if len(sys.argv) > 2 else "2026-10-29"
    path, pack = build(loc, date)
    n = [len(d["plants"]) for d in pack["decoys"]]
    acts = {}
    for d in pack["decoys"]:
        for p in d["plants"]:
            acts[p["action"]] = acts.get(p["action"], 0) + 1
    print(f"{path.name}: {len(n)} decoys, {sum(n)} plants (per file {min(n)}-{max(n)}), {acts}, "
          f"carried over {sum('· from' in p['note'] for d in pack['decoys'] for p in d['plants'])}")
