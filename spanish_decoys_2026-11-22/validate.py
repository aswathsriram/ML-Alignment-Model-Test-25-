#!/usr/bin/env python3
"""
Independent check of es_ES_decoy_plants.json against the template's rules (numbers in brackets) and this build's own
stricter conditions. It shares no code with the builder: it reads the delivery again, applies every plant to EVERY
annotator pass of the file the way the template describes, and fails on the first thing that is not exactly right.

Run    : python spanish_decoys_2026-11-22/validate.py [deliveries folder|zip]
"""
import collections, glob, json, pathlib, re, sys, tempfile, zipfile

HERE = pathlib.Path(__file__).resolve().parent
ALLOWED = {"move", "delete", "add", "replace"}
TAG = ("[", "<")
EPS = 1e-6                      # times are milliseconds held as floats


def t(x):
    h, m, s = x.split(":")
    return round(int(h) * 3600 + int(m) * 60 + float(s), 3)


def passes(src):
    if str(src).endswith(".zip"):
        tmp = tempfile.mkdtemp(); zipfile.ZipFile(src).extractall(tmp); src = tmp
    out = {}
    for f in sorted(glob.glob(str(pathlib.Path(src) / "*.json"))):
        for w in json.loads(pathlib.Path(f).read_text(encoding="utf-8"))["workitems"]:
            runs = [r for k, v in w.items() if isinstance(v, list) for r in v]
            out[w["workItemId"]] = {
                "task": {r["metadata"]["taskId"] for r in runs},
                "flags": [r["data"]["taskAnswers"][0] for r in runs],
                "V": [[(s["final_transcription"], t(s["final_startTime"]), t(s["final_endTime"]))
                       for s in r["data"]["taskAnswers"][0]["segments"]] for r in runs]}
    return out


def apply(words, plants):
    """The served (wrong) alignment: the template's meaning of each action."""
    W = [list(x) for x in words]
    gone, extra = set(), {}
    for p in plants:
        a = p["action"]
        if a == "move":
            k, d = p["word"], p["shift_ms"] / 1000
            if p["edge"] == "start":
                if k > 0 and abs(W[k - 1][2] - W[k][1]) < 0.0005:      # a touching neighbour moves with it (3)
                    W[k - 1][2] = round(W[k][1] + d, 3)
                W[k][1] = round(W[k][1] + d, 3)
            else:
                if k + 1 < len(W) and abs(W[k + 1][1] - W[k][2]) < 0.0005:
                    W[k + 1][1] = round(W[k][2] + d, 3)
                W[k][2] = round(W[k][2] + d, 3)
        elif a == "delete":
            gone.add(p["word"])
        elif a == "replace":
            W[p["word"]][0] = p["text"]
        elif a == "add":
            k = p["after_word"]
            lo, hi = W[k][2], W[k + 1][1]
            L = min(0.30, hi - lo - 0.16)
            extra[k] = [p["text"], round((lo + hi) / 2 - L / 2, 3), round((lo + hi) / 2 + L / 2, 3)]
    out = []
    for i, w in enumerate(W):
        if i not in gone:
            out.append(w)
        if i in extra:
            out.append(extra[i])
    return out


def main(src):
    doc = json.loads((HERE / "es_ES_decoy_plants.json").read_text(encoding="utf-8"))
    tpl = json.loads((HERE / "alignment-decoys-template.json").read_text(encoding="utf-8"))
    assert doc["format"] == tpl["format"] == "align-decoys/v1" and doc["instructions"] == tpl["instructions"]
    assert set(doc) == {"format", "instructions", "decoys"}
    P = passes(src)
    decoys = doc["decoys"]
    assert len(decoys) <= 1000, "more than 1000 decoys in one upload"
    assert (HERE / "es_ES_decoy_plants.json").stat().st_size < 50 * 1024 * 1024
    assert len({d["work_item_id"] for d in decoys}) == len(decoys) == len({d["decoy_ref"] for d in decoys})
    n_plants, checks = 0, collections.Counter()
    for d in decoys:
        assert set(d) == {"decoy_ref", "work_item_id", "file_name", "plants"}, d.keys()
        f = P[d["work_item_id"]]
        assert d["file_name"] in f["task"] and d["decoy_ref"] == d["file_name"]
        V, plants = f["V"], d["plants"]
        assert all(V), "a pass has no segments"
        assert not any(a.get("overlapping_speech") or a.get("audio_synthetic") for a in f["flags"])
        for v in V:                                                 # the delivered alignment itself is sound
            assert all(e > s for _, s, e in v) and all(a[2] <= b[1] + 0.001 for a, b in zip(v, v[1:]))
        assert 1 <= len(plants) <= 2, "more than two mistakes"
        assert sum(bool(p.get("critical")) for p in plants) == 1, "exactly one must-catch (18)"
        touched = []
        for p in plants:
            n_plants += 1
            a = p["action"]
            assert a in ALLOWED, a
            assert set(p) <= {"action", "word", "after_word", "edge", "shift_ms", "text", "critical", "note"}
            k = p["after_word"] if a == "add" else p["word"]
            assert isinstance(k, int)
            idx = [k, k + 1] if a == "add" else [k]
            for v in V:                                             # same word at that number in every pass
                for j in range(max(0, k - 2), k + 3):
                    if j < len(V[0]) or j < len(v):
                        assert j < len(v) and j < len(V[0]) and v[j][0] == V[0][j][0], ("passes differ near the plant", d["decoy_ref"], k)
                for j in (k - 1, k, k + 1):
                    if 0 <= j < len(v):
                        assert re.fullmatch(r"[a-zñáéíóúü]+", v[j][0]), ("tag / (( )) / cut-off next to a plant (17)", v[j][0])
                        assert not v[j][0].startswith(TAG)
            word = V[0][k][0]
            assert f"'{word}'" in p["note"], ("note names another word", word, p["note"])
            if a == "move":
                ms, edge = p["shift_ms"], p["edge"]
                assert edge in ("start", "end") and isinstance(ms, int) and ms % 10 == 0
                assert 150 <= abs(ms) <= 700, ("shift outside 150-700 ms (3)", ms)
                e = 1 if edge == "start" else 2
                times = [v[k][e] for v in V]
                assert max(times) - min(times) <= 0.03 + 1e-9, ("passes disagree on this edge", times)
                for v in V:
                    w, s, en = v[k]
                    new = v[k][e] + ms / 1000
                    if edge == "start":
                        prev_end = v[k - 1][2] if k > 0 else 0.0
                        assert new >= 0, "before 0 (3)"
                        assert new <= en - 0.12 + EPS, "past the word's own end (3)"
                        if ms < 0:
                            assert new >= prev_end + 0.05 - EPS, "reaches the previous word (3)"
                        else:
                            assert k == 0 or s - prev_end >= 0.10 - EPS, "a touching neighbour would move too"
                    else:
                        assert new >= s + 0.12 - EPS, "past the word's own start (3)"
                        if ms > 0:
                            assert k + 1 < len(v), "the last word's end may not move later: audio end unknown (3)"
                            assert new <= v[k + 1][1] - 0.05 + EPS, "reaches the next word (3)"
                        else:
                            assert k + 1 == len(v) or v[k + 1][1] - en >= 0.10 - EPS, "a touching neighbour would move too"
                checks["move: 150-700 ms, never past its own other edge, a neighbour, 0 or the audio end"] += 1
            elif a == "delete":
                assert re.fullmatch(r"[a-zñ]{4,}", word) and sum(x[0] == word for x in V[0]) == 1
                for v in V:
                    assert 0 < k < len(v) - 1 and v[k][2] - v[k][1] >= 0.25 - EPS
                    left, right = v[k][1] - v[k - 1][2], v[k + 1][1] - v[k][2]
                    assert left <= 0.02 + EPS and right <= 0.02 + EPS, "the hole is not pinned by both neighbours"
                checks["delete: a plain word said once, 0.25 s or longer, touching both neighbours"] += 1
            elif a == "add":
                for v in V:
                    assert k + 1 < len(v) and v[k + 1][1] - v[k][2] >= 0.40 - EPS, ("pause under 0.35 s (13)", v[k + 1][1] - v[k][2])
                assert p["text"] in [x[0] for x in V[0]], "not a word of the same clip (13)"
                assert re.fullmatch(r"[a-zñáéíóúü]+", p["text"])
                checks["add: a word of the clip in a pause of 0.40 s or more"] += 1
            else:
                assert p["text"] != word and re.fullmatch(r"[a-zñáéíóúü]+", p["text"]), "replace text must differ (6)"
                assert len(p["text"]) == len(word) and sum(x != y for x, y in zip(p["text"], word)) == 1, "one letter only"
                checks["replace: exactly one letter differs"] += 1
            touched.append(idx)
        for i, a in enumerate(touched):
            for b in touched[i + 1:]:
                assert min(abs(x - y) for x in a for y in b) >= 3, ("mistakes closer than 3 words (17)", d["decoy_ref"])
        for v in V:                                                 # the served alignment is well-formed in every pass
            served = apply(v, plants)
            assert all(e > s for _, s, e in served), "zero-length chip"
            assert all(a[2] <= b[1] + 0.001 for a, b in zip(served, served[1:])), ("chips overlap after planting", d["decoy_ref"])
            adds = sum(p["action"] == "add" for p in plants)
            dels = sum(p["action"] == "delete" for p in plants)
            assert len(served) == len(v) + adds - dels
            if not adds and not dels:                               # timing / text plants change exactly their own chip
                assert sum(1 for x, y in zip(served, v) if tuple(x) != y) == len(plants), ("a plant changed another chip", d["decoy_ref"])
            kept = [tuple(x) for x in served]
            assert sum(1 for y in v if y in kept) >= len(v) - len(plants), ("a plant changed another chip", d["decoy_ref"])
    print(f"OK: {len(decoys)} decoys, {n_plants} mistakes, every one checked on every pass of its file")
    for k, v in checks.items():
        print(f"  {v:5d}  {k}")
    print(f"  spacing: every pair at least 3 words apart; one must-catch per file; no tag or (( )) word touched")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else HERE / "deliveries")
