#!/usr/bin/env python3
"""
Rebuild the Spanish decoy file: all 297 items, same ids, order and format; only timing-type planted errors.

Input  : spanish_fix/Updated_spanish_original.json
Output : spanish_fix/Updated_spanish_rebuilt.json      the file to upload (same format as the original)
         spanish_fix/spanish_rebuilt_answer_key.json   every planted error, band and weight

1. Text errors removed: capitals -> lowercase, punctuation stripped, digits -> Spanish words
   (a spelled letter keeps its optional period; tags such as (()) are never touched).
2. Existing missing segments are kept. Two-word chips are NOT errors here: each is split back into one chip per word
   (the split point is placed in proportion to the words' lengths). The transcript always says exactly what the
   chips say, so a missing word is simply missing (nothing for the platform to flag).
3. New errors to 3-6 per item where its length allows, at least 3 words apart, never on a tag:
   boundary mismatch (minor 40-80 ms = A3, major 100-300 ms = A2, critical over 300 ms = A1), missing segment,
   hallucinated chip
   (in a pause of at least 0.35 s, repeating the word before).
Weights: boundary 50 points, missing 25, hallucinated 25; A1 3 : A2 2 : A3 1.

Run    : python spanish_fix/rebuild_spanish.py
"""
import collections, copy, difflib, json, pathlib, random, re, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "alignment_decoys"))
import build_pack as bp                                              # noqa: E402

bp.is_tag = lambda w: w["w"].startswith(("[", "<", "(("))            # Spanish tags: (()), ((word))
bp.MIN_MS = 40                                                       # boundary sizes as agreed for these decoys
bp.MOVE_CLASSES = [("minor", 40, 80), ("major", 100, 300), ("critical", 310, 700)]
BAND_OF = {"minor": "A3", "major": "A2", "critical": "A1"}
SEED = 20261107
DIGITS = {"1": "uno", "2": "dos", "4": "cuatro", "5": "cinco", "6": "seis", "7": "siete", "12": "doce", "30": "treinta",
          "50": "cincuenta", "70": "setenta", "90": "noventa"}
FUNC = set("el la los las un una y o que de del al en con por para se lo le me te mi su es no si ya muy pero yo tú".split())
GROUP_POINTS = {"BOUNDARY": 50.0, "MISSING": 25.0, "HALLUCINATED": 25.0}
BAND_FACTOR = {"A1": 3, "A2": 2, "A3": 1}
NEW_SHARE = [("move", 0.60), ("remove", 0.20), ("add", 0.20)]


def clean_text(w):
    if w.startswith(("[", "<", "((")):
        return w
    if re.fullmatch(r"\d+", w.strip(".,;:!?¿¡\"")):
        return DIGITS[w.strip(".,;:!?¿¡\"")]
    t = w.lower()
    if re.fullmatch(r"[^\W\d_]\.", t):                               # spelled letter: optional period stays
        return t
    return re.sub(r"[.,;:!?¿¡\"]", "", t).strip()


def main():
    src = json.loads((HERE / "Updated_spanish_original.json").read_text(encoding="utf-8"))
    out = copy.deepcopy(src)
    key = []
    have = collections.Counter()
    for item in out["items"]:
        rng = random.Random(f"{SEED}-{item['id']}")
        words = item["source"]["words"]
        rec = {"id": item["id"], "name": item["name"], "errors": [], "text_fixes": []}
        key.append(rec)
        if not words:
            rec["note"] = "no words in the source item: kept as is, nothing planted"
            continue
        # 1. text errors out
        for w in words:
            new = " ".join(clean_text(t) for t in w["word"].split())
            if new != w["word"]:
                rec["text_fixes"].append(f"{w['word']} -> {new}"); w["word"] = new
        # no two-word chips: split each into one chip per word, time shared by word length
        split = []
        for w in words:
            parts = w["word"].split()
            if len(parts) > 1 and not w["word"].startswith("(("):
                total, t = sum(len(x) for x in parts), w["start"]
                for j, x in enumerate(parts):
                    e = w["end"] if j == len(parts) - 1 else round(t + (w["end"] - w["start"]) * len(x) / total, 3)
                    split.append({"word": x, "start": round(t, 3), "end": e}); t = e
                rec["text_fixes"].append(f"split '{w['word']}' into {len(parts)} chips")
            else:
                split.append(w)
        words[:] = split
        item["source"]["words"] = words
        # repair the two broken overlaps (a chip over its neighbour / into a tag)
        for a, b in zip(words, words[1:]):
            if a["end"] > b["start"] + 1e-9:
                if a["word"].startswith("(("):
                    rec["text_fixes"].append(f"overlap repaired: {b['word']} start {b['start']} -> {a['end']}"); b["start"] = a["end"]
                else:
                    rec["text_fixes"].append(f"overlap repaired: {a['word']} end {a['end']} -> {b['start']}"); a["end"] = b["start"]
        # 2. existing errors: missing words (in the old transcript, no chip) and two-word chips
        T = [clean_text(t) for t in item["transcript"].split()]
        flat, owner = [], []
        for ci, w in enumerate(words):
            for tok in w["word"].split():
                flat.append(tok); owner.append(ci)
        taken = []
        for op, a1, a2, b1, b2 in difflib.SequenceMatcher(None, T, flat, autojunk=False).get_opcodes():
            if op == "delete":
                nxt = owner[b1] if b1 < len(owner) else len(words)
                for k in range(a1, a2):
                    band = "A2" if (T[k] in FUNC or len(T[k]) <= 3) else "A1"
                    rec["errors"].append({"family": "WD", "group": "MISSING", "band": band, "word": T[k], "kept_from_source": True,
                                          "note": f"'{T[k]}' is spoken before chip {nxt} but has no chip"})
                taken.append({nxt - 1, nxt})
        # 3. new errors, on the chips as they are (W uses the pack builder's i/w/s/e shape)
        W = [{"i": i, "w": w["word"], "s": w["start"], "e": w["end"]} for i, w in enumerate(words)]
        dur = item["source"]["duration_seconds"]
        target = min(6, max(3, len(W) // 4))
        plants = []
        while len(rec["errors"]) + len(plants) < target:
            total_new = sum(have.values()) + 1
            order = sorted(NEW_SHARE, key=lambda a: (have[a[0]] / total_new - a[1], rng.random()))
            placed = False
            for action, _ in order:
                classes = [rng.choice(["minor", "major", "critical"])] if action == "move" else [None]
                if action == "move":
                    classes += [c for c, _, _ in bp.MOVE_CLASSES if c not in classes]
                for cls in classes:
                    cands = [c for c in bp.fresh(W, dur, action, rng, cls) if bp.spaced(taken, c[1])
                             and not any(" " in W[i]["w"] for i in c[1])]
                    if cands:
                        p, aff, note = rng.choice(cands)
                        plants.append(p); taken.append(aff); have[action] += 1; placed = True
                        break
                if placed:
                    break
            if not placed:
                break
        # apply the new errors
        removed, extra = set(), []
        for p in plants:
            if p["action"] == "move":
                k, d = p["word"], p["shift_ms"] / 1000
                g = dict(start=words[k]["start"], end=words[k]["end"])
                if p["edge"] == "start":
                    if k > 0 and bp.touching(words[k - 1]["end"], words[k]["start"]):
                        words[k - 1]["end"] = round(words[k]["start"] + d, 3)
                    words[k]["start"] = round(words[k]["start"] + d, 3)
                else:
                    if k + 1 < len(words) and bp.touching(words[k]["end"], words[k + 1]["start"]):
                        words[k + 1]["start"] = round(words[k]["end"] + d, 3)
                    words[k]["end"] = round(words[k]["end"] + d, 3)
                cls = next(c for c, lo, hi in bp.MOVE_CLASSES if abs(p["shift_ms"]) <= hi)
                rec["errors"].append({"family": "BND-MAJOR", "group": "BOUNDARY",
                                      "band": BAND_OF[cls], "severity": cls, "word": words[k]["word"],
                                      "edge": p["edge"], "shift_ms": p["shift_ms"], "before": g,
                                      "after": {"start": words[k]["start"], "end": words[k]["end"]},
                                      "note": f"{p['edge']} {abs(p['shift_ms'])} ms {'early' if p['shift_ms'] < 0 else 'late'} ({cls})"})
            elif p["action"] == "remove":
                k = p["word"]; removed.add(k)
                band = "A2" if (W[k]["w"] in FUNC or len(W[k]["w"]) <= 3) else "A1"
                rec["errors"].append({"family": "WD", "group": "MISSING", "band": band, "word": W[k]["w"],
                                      "spoken": {"start": W[k]["s"], "end": W[k]["e"]}, "note": f"'{W[k]['w']}' has no chip"})
            else:
                k = p["after_word"]; lo, hi = W[k]["e"], W[k + 1]["s"]
                L = min(0.30, hi - lo - 0.16); mid = (lo + hi) / 2
                chip = {"word": p["text"], "start": round(mid - L / 2, 3), "end": round(mid + L / 2, 3)}
                extra.append((k, chip))
                rec["errors"].append({"family": "WH", "group": "HALLUCINATED", "band": "A1" if hi - lo >= 0.6 else "A2",
                                      "word": p["text"], "chip": chip,
                                      "note": f"extra '{p['text']}' over the {hi - lo:.2f} s pause after it; never spoken"})
        new_words = []
        for i, w in enumerate(words):
            if i not in removed:
                new_words.append(w)
            for k, chip in extra:
                if k == i:
                    new_words.append(chip)
        item["source"]["words"] = new_words
        item["transcript"] = " ".join(w["word"] for w in new_words)
    # weights
    fac = collections.Counter()
    for r in key:
        for x in r["errors"]:
            fac[x["group"]] += BAND_FACTOR[x["band"]]
    for r in key:
        for n, x in enumerate(r["errors"], 1):
            x["error_id"] = f"ES-{r['name'][:8]}-{n}"
            x["weight"] = round(GROUP_POINTS[x["group"]] * BAND_FACTOR[x["band"]] / fac[x["group"]], 3)
    (HERE / "Updated_spanish_rebuilt.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    fam = collections.Counter(x["family"] for r in key for x in r["errors"])
    (HERE / "spanish_rebuilt_answer_key.json").write_text(json.dumps(
        {"locale": "es_ES", "items": len(key), "errors_by_family": dict(fam),
         "weights": {"BOUNDARY": 50, "MISSING": 25, "HALLUCINATED": 25, "band_factor": BAND_FACTOR},
         "note": "Boundary mismatches already in the source file cannot be listed: the correct timings were not supplied.",
         "items_detail": key}, ensure_ascii=False, indent=2), encoding="utf-8")
    per = collections.Counter(len(r["errors"]) for r in key)
    print(f"{len(key)} items | errors {dict(fam)} | per item {dict(sorted(per.items()))}")


if __name__ == "__main__":
    main()
