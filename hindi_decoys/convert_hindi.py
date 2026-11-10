#!/usr/bin/env python3
"""
Hindi decoys (hi_alignment_decoys.json, 125 files) in the align-decoys/v1 upload format, written two ways:

  hindi_decoys_plants.json        typed: one `plants` action per answer-key error
  hindi_decoys_decoy_words.json   exact: the Hindi decoy alignment as `decoy_words` (the platform derives each mistake)

Both keep every file and every error; files are identified by file_id and file_name (= audio_id), decoy_ref = decoy_id.
Word numbers are the answer key's gold_index (0-based into ground_truth.segments).

Error type -> action (typed file):
  boundary_start / boundary_end   move (edge, shift_ms = decoy - truth); overlap when the new edge lands inside the
                                  neighbour (the Hindi decoy never moves the neighbour, overlap keeps it in place)
  word_deletion, filler_deleted   delete
  word_substitution, entity_spelling, script_swap_*, truncation_introduced, truncation_completed
                                  replace (text = the decoy's word)
  word_split                      split (parts and the split time `at` from the decoy)
  words_merged, acronym_collapsed join (count = words in gold_span)
  word_hallucination              add_noise (text and start / end of the decoy's extra chip)
  multiple_speakers_off           set_flag multi_speaker = false (the file's own answer is true)
Each file's 1-2 most obvious mistakes are "critical": true (2 when it has 5 or more).

A simulation applies the typed plants to the correct alignment and compares the result with the Hindi decoy; every
place where the template cannot reproduce the decoy exactly is counted and written to hindi_conversion_report.json.

Run    : python hindi_decoys/convert_hindi.py
"""
import collections, json, pathlib

HERE = pathlib.Path(__file__).resolve().parent
TOUCH = 0.0005
REPLACE = {"word_substitution", "entity_spelling", "script_swap_latin_to_devanagari", "script_swap_devanagari_to_latin",
           "truncation_introduced", "truncation_completed"}
DELETE = {"word_deletion", "filler_deleted"}
JOIN = {"words_merged", "acronym_collapsed"}
WORD_RANK = {"word_hallucination": 990, "word_deletion": 980, "word_substitution": 970, "script_swap_latin_to_devanagari": 960,
             "script_swap_devanagari_to_latin": 960, "entity_spelling": 950, "words_merged": 940, "acronym_collapsed": 940,
             "word_split": 930, "truncation_introduced": 920, "truncation_completed": 920, "filler_deleted": 900}


def secs(x):
    h, m, s = x.split(":")
    return round(int(h) * 3600 + int(m) * 60 + float(s), 3)


def segs(side):
    return [{"w": s["transcription"], "s": secs(s["startTime"]), "e": secs(s["endTime"])} for s in side["segments"]]


def obviousness(a):
    if a["error_type"].startswith("boundary"):
        return abs(a["delta_ms"]) + {"critical": 300, "major": 100, "minor": 0}[a["severity"]]
    return WORD_RANK.get(a["error_type"], 900) + (100 if a["severity"] == "critical" else 0)


def plant(a, G, inexact):
    """One typed action for one answer-key error (None for multiple_speakers_off, handled as set_flag)."""
    t, k = a["error_type"], a["gold_index"]
    note = f"{t} · {a['severity']}"
    if t.startswith("boundary"):
        edge, new = a["edge"], secs(a["decoy_value"])
        old = G[k]["s"] if edge == "start" else G[k]["e"]
        ms = round((new - old) * 1000)
        nb = (G[k - 1] if k > 0 else None) if edge == "start" else (G[k + 1] if k + 1 < len(G) else None)
        near = None if nb is None else (nb["e"] if edge == "start" else nb["s"])
        into = near is not None and ((edge == "start" and new < near - TOUCH) or (edge == "end" and new > near + TOUCH))
        touching = near is not None and abs(near - old) < TOUCH
        p = {"action": "overlap" if into else "move", "word": k, "edge": edge, "shift_ms": ms}
        note += f" · {edge} {abs(ms)} ms {'later' if ms > 0 else 'earlier'}"
        if abs(ms) < 150:
            inexact["move under 150 ms (template range 150-700)"] += 1
        if touching and not into:
            inexact["move away from a touching neighbour: the platform moves the neighbour too, the Hindi decoy leaves a gap"] += 1
            note += " · Hindi decoy leaves a gap here; the platform moves the touching neighbour with it"
        if into:
            note += f" · overlaps {nb['w']}"
        return dict(p, note=note)
    if t in DELETE:
        return {"action": "delete", "word": k, "note": f"{note} · '{G[k]['w']}' gone"}
    if t in REPLACE:
        return {"action": "replace", "word": k, "text": a["decoy_value"], "note": f"{note} · {a['truth_value']} -> {a['decoy_value']}"}
    if t == "word_split":
        parts = [x.strip() for x in a["decoy_value"].split("+")]
        return {"action": "split", "word": k, "parts": parts, "at": a["_at"], "note": f"{note} · {G[k]['w']} -> {' + '.join(parts)}"}
    if t in JOIN:
        lo, hi = a["gold_span"]
        mid = (G[lo]["s"] + G[hi]["e"]) / 2
        if min(abs(G[j]["e"] - mid) for j in range(lo, hi)) < 0.2:
            inexact["join where a true boundary is under 0.2 s from the chip's middle (template asks for 0.2 s)"] += 1
        return {"action": "join", "word": lo, "count": hi - lo + 1,
                "note": f"{note} · {a['truth_value']} in one chip (Hindi decoy writes '{a['decoy_value']}')"}
    if t == "word_hallucination":
        inexact["extra word cut out of the word before it, not in a pause (add needs 0.35 s): sent as add_noise"] += 1
        c = a["_chip"]
        return {"action": "add_noise", "after_word": k, "text": a["decoy_value"], "start": c["s"], "end": c["e"],
                "note": f"{note} · extra '{a['decoy_value']}' over {c['s']}-{c['e']}; the Hindi decoy also shortens "
                        f"'{G[k]['w']}' to end at {c['s']}"}
    raise ValueError(t)


def find(Dc, w=None, s=None, e=None, inside=None):
    """Index of the one decoy chip with this text / start / end (or starting inside the span `inside`)."""
    hits = [n for n, c in enumerate(Dc) if (w is None or c["w"] == w) and (s is None or abs(c["s"] - s) < TOUCH)
            and (e is None or abs(c["e"] - e) < TOUCH) and (inside is None or inside[0] < c["s"] < inside[1])]
    assert len(hits) == 1, (w, s, e, hits)
    return hits[0]


def decoy_chip_info(r, G, Dc):
    """Where each mistake sits in the decoy (decoy_segment_id is not a reliable position, so chips are matched)."""
    for a in r["answer_key"]:
        t, k = a["error_type"], a["gold_index"]
        if t == "word_split":
            a["_dw"] = find(Dc, w=a["decoy_value"].split("+")[0].strip(), s=G[k]["s"])
            a["_at"] = Dc[a["_dw"]]["e"]
            assert abs(Dc[a["_dw"] + 1]["e"] - G[k]["e"]) < TOUCH, r["decoy_id"]
        elif t == "word_hallucination":
            a["_dw"] = find(Dc, w=a["decoy_value"], inside=(G[k]["s"], G[k]["e"] + TOUCH))
            a["_chip"] = Dc[a["_dw"]]
        elif t in REPLACE:
            a["_dw"] = find(Dc, w=a["decoy_value"], s=G[k]["s"], e=G[k]["e"])
        elif t.startswith("boundary"):
            v = secs(a["decoy_value"])
            a["_dw"] = find(Dc, w=G[k]["w"], **({"s": v, "e": G[k]["e"]} if a["edge"] == "start" else {"s": G[k]["s"], "e": v}))
        elif t in JOIN:
            lo, hi = a["gold_span"]
            a["_dw"] = find(Dc, w=a["decoy_value"], s=G[lo]["s"], e=G[hi]["e"])


def simulate(G, plants):
    """Apply typed plants to the correct alignment the way the template describes them."""
    W = [dict(w, k=i) for i, w in enumerate(G)]
    by = {i: w for i, w in enumerate(W)}
    extra, gone, out = [], set(), []
    for p in plants:
        a = p["action"]
        if a == "set_flag":
            continue
        k = p.get("word", p.get("after_word"))
        if a in ("move", "overlap"):
            d = p["shift_ms"] / 1000
            if p["edge"] == "start":
                if a == "move" and k > 0 and abs(by[k - 1]["e"] - by[k]["s"]) < TOUCH:
                    by[k - 1]["e"] = round(by[k]["s"] + d, 3)
                by[k]["s"] = round(by[k]["s"] + d, 3)
            else:
                if a == "move" and k + 1 < len(W) and abs(by[k + 1]["s"] - by[k]["e"]) < TOUCH:
                    by[k + 1]["s"] = round(by[k]["e"] + d, 3)
                by[k]["e"] = round(by[k]["e"] + d, 3)
        elif a == "delete":
            gone.add(k)
        elif a == "replace":
            by[k]["w"] = p["text"]
        elif a == "split":
            by[k]["split"] = (p["parts"], p["at"])
        elif a == "join":
            by[k]["join"] = p["count"]
        elif a == "add_noise":
            extra.append((k, {"w": p["text"], "s": p["start"], "e": p["end"]}))
    i = 0
    while i < len(W):
        w = W[i]
        if i in gone:
            i += 1; continue
        if "split" in w:
            (a, b), at = w["split"]
            out += [{"w": a, "s": w["s"], "e": at}, {"w": b, "s": at, "e": w["e"]}]
        elif "join" in w:
            span = W[i:i + w["join"]]
            out.append({"w": " ".join(x["w"] for x in span), "s": span[0]["s"], "e": span[-1]["e"]})
            for x in span:
                out += [c for kk, c in extra if kk == x["k"]]
            i += w["join"]; continue
        else:
            out.append({"w": w["w"], "s": w["s"], "e": w["e"]})
        out += [c for kk, c in extra if kk == i]
        i += 1
    return out


def main():
    src = json.loads((HERE / "hi_alignment_decoys.json").read_text(encoding="utf-8"))
    tpl = json.loads((HERE / "alignment-decoys-template.json").read_text(encoding="utf-8"))
    typed, exact, report = [], [], []
    inexact, actions = collections.Counter(), collections.Counter()
    for r in src:
        G, Dc = segs(r["ground_truth"]), segs(r["decoy"])
        assert all(not w["w"].startswith(("[", "<")) for w in G)
        decoy_chip_info(r, G, Dc)
        keyed = [a for a in r["answer_key"] if a["error_type"] != "multiple_speakers_off"]
        flags = []
        for a in r["answer_key"]:
            if a["error_type"] == "multiple_speakers_off":
                assert r["ground_truth"]["multiple_speakers"] is True and r["decoy"]["multiple_speakers"] is False
                flags.append({"action": "set_flag", "flag": "multi_speaker", "value": False,
                              "note": "multiple_speakers_off · the file has several speakers; served as single-speaker"})
        assert len(flags) == (1 if r["ground_truth"]["multiple_speakers"] != r["decoy"]["multiple_speakers"] else 0)
        # word positions stay 3 words apart (no [ / < tags in Hindi; (( )) words are not tags in this template)
        spans = sorted(tuple(a.get("gold_span", [a["gold_index"]] * 2)) for a in keyed)
        assert all(b[0] - a[1] >= 3 for a, b in zip(spans, spans[1:])), r["decoy_id"]
        file_inexact = collections.Counter()
        plants = [plant(a, G, file_inexact) for a in keyed]
        n_crit = 2 if len(plants) >= 5 else 1
        ranked = sorted(range(len(keyed)), key=lambda i: -obviousness(keyed[i]))
        crit = set(ranked[:n_crit])
        for i in crit:
            plants[i]["critical"] = True
        plants = [{**{k: v for k, v in p.items() if k != "note"}, "note": p["note"]} for p in plants]
        order = sorted(range(len(plants)), key=lambda i: plants[i].get("word", plants[i].get("after_word")))
        base = {"decoy_ref": r["decoy_id"], "file_id": r["file_id"], "file_name": r["audio_id"]}
        typed.append({**base, "plants": [plants[i] for i in order] + flags})
        for a in keyed:
            actions[a["error_type"]] += 1
        actions["multiple_speakers_off"] += len(flags)
        inexact.update(file_inexact)

        # exact form: the decoy itself; joined chips spelled with spaces so the platform reads a join, not a retyped word
        dw = [dict(w) for w in Dc]
        for a in keyed:
            if a["error_type"] in JOIN:
                lo, hi = a["gold_span"]
                dw[a["_dw"]]["w"] = " ".join(G[x]["w"] for x in range(lo, hi + 1))
        need = n_crit
        for a in sorted(keyed, key=lambda a: -obviousness(a)):           # deletions have no entry to mark: next one down
            if need and "_dw" in a:
                dw[a["_dw"]]["critical"] = True; need -= 1
        exact.append({**base, "decoy_words": [{"w": w["w"], "s": w["s"], "e": w["e"], **({"critical": True} if w.get("critical") else {})}
                                              for w in dw], "plants": [{k: v for k, v in f.items() if k != "note"} for f in flags]})

        # fidelity: typed plants applied to gold vs the Hindi decoy (joined chips compared with spaces)
        sim = simulate(G, plants)
        same = len(sim) == len(dw) and all(a["w"] == b["w"] and abs(a["s"] - b["s"]) < TOUCH and abs(a["e"] - b["e"]) < TOUCH
                                           for a, b in zip(sim, dw))
        report.append({"decoy_ref": r["decoy_id"], "file_id": r["file_id"], "errors": len(r["answer_key"]),
                       "typed_reproduces_decoy_exactly": same, "not_exact": dict(file_inexact)})
    head = {"format": tpl["format"], "instructions": tpl["instructions"]}
    (HERE / "hindi_decoys_plants.json").write_text(json.dumps({**head, "decoys": typed}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (HERE / "hindi_decoys_decoy_words.json").write_text(json.dumps({**head, "decoys": exact}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    exact_n = sum(x["typed_reproduces_decoy_exactly"] for x in report)
    (HERE / "hindi_conversion_report.json").write_text(json.dumps(
        {"files": len(report), "errors": sum(actions.values()), "by_error_type": dict(actions.most_common()),
         "typed_file_reproduces_decoy_exactly": exact_n, "not_exact_in_typed_form": dict(inexact.most_common()),
         "files_detail": report}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    acts = collections.Counter(p["action"] for d in typed for p in d["plants"])
    crit = sum(p.get("critical", False) for d in typed for p in d["plants"])
    print(f"{len(typed)} files | {sum(acts.values())} plants {dict(acts.most_common())} | critical {crit}")
    print(f"typed plants reproduce the Hindi decoy exactly in {exact_n}/{len(report)} files")
    for k, v in inexact.most_common():
        print(f"  {v:4d}  {k}")


if __name__ == "__main__":
    main()
