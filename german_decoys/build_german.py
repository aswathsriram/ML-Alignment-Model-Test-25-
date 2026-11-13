#!/usr/bin/env python3
"""
German decoys from the platform's forced-alignment deliveries (671 work items), in the align-decoys/v1 format laid out
like hindi_decoys/hindi_decoys_plants.json: {format, instructions, decoys: [{decoy_ref, work_item_id, file_name, plants}]},
each plant with a note "<error type> · <severity> · <detail>".

Correct alignment per work item: the ADJUDICATION answer when there is one, else the blind-pass answer (the two blind
passes of a non-adjudicated item have the same words; every timing rule is checked against both versions).
Work items with no segments (entirely synthetic) are skipped -> german_skipped.json.

Error types — the Hindi set, plus German ones from Forced_Alignment_Guidelines_de_DE (Part 4 / Part 5):
  boundary_start / boundary_end  move   minor 40-80 ms, major 100-300 ms, critical 310-700 ms
  boundary_overlap               overlap (same-speaker overlap, 2.2)
  zero_length                    zero   (2.2: start = end is an error)
  word_deletion / filler_deleted delete
  missing_segment                remove (word stays in the transcript, no chip)
  word_hallucination             add    (extra chip in a pause of at least 0.35 s, repeating the word before)
  filler_absorbed                absorb (2.3: a filler inside another word's segment)
  word_substitution              replace: homophone / near word (4.6, Part 5: das/dass, seite/saite, mehr/meer ...)
  spelling_slip                  replace: consonant / vowel slip in a long word
  umlaut_replaced                replace: ä ö ü ß written ae oe ue ss (Part 5)
  spoken_form                    replace: reduction written in full or the full word written reduced (Part 5)
  truncation_introduced          replace: a complete word written as cut off (4.3)
  truncation_completed           replace: a cut-off word written in full (4.3)
  unintelligible_invented        replace_unintelligible: a word invented over (()) / ((guess)) (2.5)
  multiple_speakers_off          set_flag multi_speaker = false on files with several speakers
No capitalisation, punctuation, digit, split or join errors (the split / join candidates below are kept but
not used: they are not in SHARE). 1-6 mistakes per file as its length allows, at least 3 words apart,
never on a tag ([...] / <...>); timings never touched on (( )) words; 1-2 "critical": true per file.

Run    : python german_decoys/build_german.py [deliveries.zip|folder] [template.json]
Output : german_decoys/german_decoy_plants.json, german_decoys/german_skipped.json
"""
import collections, glob, json, math, pathlib, random, re, sys, tempfile, zipfile

HERE = pathlib.Path(__file__).resolve().parent
SEED = 20261110
SIZES = [("minor", 40, 80), ("major", 100, 300), ("critical", 310, 700)]
TOUCH, KEEP, MIN_PAUSE, GAP_WORDS = 0.0005, 0.03, 0.35, 3
SHARE = {"move": 0.40, "overlap": 0.04, "zero": 0.03, "delete": 0.08, "remove": 0.08, "add": 0.08, "absorb": 0.01,
         "word_substitution": 0.08, "spelling_slip": 0.04, "umlaut_replaced": 0.07, "spoken_form": 0.02,
         "truncation_introduced": 0.03, "truncation_completed": 0.01, "unintelligible": 0.01}
ACCENT_LABEL, REDUCE_LABEL = "umlaut_replaced", "spoken_form"     # language modules (build_portuguese.py) relabel these
MIN_WORD_LEN = 2          # shortest word that may be deleted / lose its chip (Chinese: 1, one character per segment)
TARGET_FN = None          # mistakes per file from the word count (default below: 1-6 as the file's length allows)
SPEAKER_FLAG = True       # also plant multiple_speakers_off on files with several speakers
RETRIES = 1               # other placements to try when a file gets fewer mistakes than its target
FILLERS = {"äh", "ähm", "öh", "hm", "hmm", "mm", "mhm"}
HOMOPHONES = [("das", "dass"), ("den", "denn"), ("wen", "wenn"), ("man", "mann"), ("im", "ihm"), ("in", "ihn"),
              ("seit", "seid"), ("war", "wahr"), ("mehr", "meer"), ("viel", "fiel"), ("ist", "isst"), ("wieder", "wider"),
              ("dem", "den"), ("einen", "einem"), ("wird", "wirt"), ("statt", "stadt"), ("seite", "saite"),
              ("weise", "waise"), ("leib", "laib"), ("mal", "mahl"), ("leere", "lehre"), ("wahl", "wal"), ("rat", "rad"),
              ("tot", "tod"), ("fast", "fasst"), ("ende", "ente"), ("lied", "lid"), ("hat", "hatt"), ("weg", "weck"),
              ("sie", "die"), ("ihr", "ihre"), ("seine", "seiner"), ("dieser", "dieses"), ("kann", "kam")]
SUBST = {}
for a, b in HOMOPHONES:
    SUBST.setdefault(a, b); SUBST.setdefault(b, a)
REDUCE = {"habe": "hab", "nicht": "nich", "ist": "is", "eine": "'ne", "einen": "'n", "gerade": "grad", "einmal": "mal",
          "hab": "habe", "nich": "nicht", "is": "ist", "'ne": "eine", "ne": "eine", "'n": "einen", "n": "ein",
          "grad": "gerade", "'s": "es"}
UMLAUT = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
NUM = ("null ein eins zwei drei vier fünf sechs sieben acht neun zehn elf zwölf dreizehn vierzehn fünfzehn sechzehn "
       "siebzehn achtzehn neunzehn zwanzig dreißig vierzig fünfzig sechzig siebzig achtzig neunzig hundert tausend und").split()
NOT_MODIFIER = set(("über unter hinter durch gegen wider wieder jeden jedes jeder jedem eben ober außer inner hinein "
                    "herein zusammen alle allen aller eine einer eines dies diese dieser denn dann wenn auch noch ganz "
                    "immer nach vorbei voraus heraus herum hinaus hier dort dazu davon darum warum").split())
NUM_RE = re.compile("(" + "|".join(sorted(NUM, key=len, reverse=True)) + ")")


def secs(x):
    h, m, s = x.split(":")
    return round(int(h) * 3600 + int(m) * 60 + float(s), 3)


def is_tag(w):
    return w.startswith(("[", "<"))


def fixed(w):                     # never retimed, split, joined or deleted: tags and (( )) words
    return w.startswith(("[", "<", "(("))


def load(src):
    if str(src).endswith(".zip"):
        tmp = tempfile.mkdtemp()
        zipfile.ZipFile(src).extractall(tmp)
        src = tmp
    for f in sorted(glob.glob(str(pathlib.Path(src) / "*.json"))):
        for w in json.loads(pathlib.Path(f).read_text(encoding="utf-8"))["workitems"]:
            runs = sorted([r for k, v in w.items() if isinstance(v, list) for r in v],
                          key=lambda r: r["metadata"]["labelledTimestamp"])
            yield w["workItemId"], [(r["metadata"]["operationType"], r["data"]["taskAnswers"][0], r["metadata"]["taskId"]) for r in runs]


def to_words(ans):
    return [{"i": i, "w": s["final_transcription"], "s": secs(s["final_startTime"]), "e": secs(s["final_endTime"])}
            for i, s in enumerate(ans["segments"])]


# ------------------------------------------------------------------ timing checks (all versions)
def move_ok(W, dur, k, edge, ms):
    n, d = len(W), ms / 1000
    if fixed(W[k]["w"]):
        return None
    if edge == "start":
        new = W[k]["s"] + d
        if new < 0 or new > W[k]["e"] - KEEP:
            return None
        if k > 0:
            p = W[k - 1]
            if abs(W[k]["s"] - p["e"]) < TOUCH:
                return None if (fixed(p["w"]) or new < p["s"] + KEEP) else {k - 1, k}
            if new < p["e"] + 0.01:
                return None
        return {k}
    new = W[k]["e"] + d
    if new > dur or new < W[k]["s"] + KEEP:
        return None
    if k + 1 < n:
        x = W[k + 1]
        if abs(x["s"] - W[k]["e"]) < TOUCH:
            return None if (fixed(x["w"]) or new > x["e"] - KEEP) else {k, k + 1}
        if new > x["s"] - 0.01:
            return None
    return {k}


def overlap_ok(W, k, edge, ms):
    """The edge must end up inside the neighbour (not past its far edge); the neighbour stays where it is."""
    d = ms / 1000
    if fixed(W[k]["w"]):
        return False
    if edge == "end":
        if k + 1 >= len(W) or fixed(W[k + 1]["w"]):
            return False
        x, new = W[k + 1], W[k]["e"] + d
        return x["s"] + 0.04 < new < x["e"] - 0.05
    if k == 0 or fixed(W[k - 1]["w"]):
        return False
    p, new = W[k - 1], W[k]["s"] + d
    return p["s"] + 0.05 < new < p["e"] - 0.04


def join_ok(V, k, count):
    for W in V:
        span = W[k:k + count]
        if len(span) < count or any(fixed(w["w"]) for w in span):
            return False
        mid = (span[0]["s"] + span[-1]["e"]) / 2
        if min(abs(w["e"] - mid) for w in span[:-1]) < 0.2:
            return False
    return True


# ------------------------------------------------------------------ text helpers
def spelling_slip(w, rng):
    opts = []
    for m in re.finditer(r"([bdfgklmnprst])\1", w):
        opts.append(w[:m.start()] + w[m.start() + 1:])
    if "ie" in w:
        opts.append(w.replace("ie", "i", 1))
    if "ei" in w:
        opts.append(w.replace("ei", "ie", 1))
    for m in re.finditer(r"([aeiouäöü])h", w):
        opts.append(w[:m.start() + 1] + w[m.start() + 2:])
    if w.endswith("dt"):
        opts.append(w[:-2] + "tt")
    for m in re.finditer(r"(?<=[^aeiouäöü])e(?=[^aeiouäöü])", w[1:-1]):
        opts.append(w[:m.start() + 1] + "a" + w[m.start() + 2:])
    opts = sorted(set(o for o in opts if o != w and len(o) >= 4))
    return rng.choice(opts) if opts else None


def umlaut(w):
    return re.sub("[äöüß]", lambda m: UMLAUT[m.group()], w) if re.search("[äöüß]", w) else None


def number_parts(w):
    toks = NUM_RE.findall(w)
    if "".join(toks) != w or len(toks) < 2:
        return None
    parts, cur = [], ""
    for t in toks:
        if t == "und":
            if cur:
                parts.append(cur)
            parts.append("und"); cur = ""
        else:
            cur += t
            if t in ("hundert", "tausend"):
                parts.append(cur); cur = ""
    if cur:
        parts.append(cur)
    # glue a lone "tausend"/"hundert" multiplier chain like "zwei"+"hundert" already joined above
    return parts if len(parts) >= 2 and "".join(parts) == w else None


def compound_parts(w, vocab):
    if len(w) < 9 or fixed(w) or not w.isalpha() or "".join(NUM_RE.findall(w)) == w:
        return None
    best = None
    for i in range(4, len(w) - 3):
        mod, head = w[:i], w[i:]
        if head not in vocab or len(head) < 4:
            continue
        cores = [mod] + [mod[:-len(x)] for x in ("s", "es", "n", "en", "e") if mod.endswith(x) and len(mod) - len(x) >= 4]
        if any(c in vocab and c not in NOT_MODIFIER for c in cores):
            score = min(len(mod), len(head))
            if not best or score > best[0]:
                best = (score, [mod, head])
    return best[1] if best else None


def at_split(V, k, parts):
    """Split time of two parts, in proportion to their letters, valid in every version."""
    ts = []
    for W in V:
        s, e = W[k]["s"], W[k]["e"]
        t = round(s + (e - s) * len(parts[0]) / len("".join(parts)), 3)
        if not (s + KEEP <= t <= e - KEEP):
            return None
        ts.append(t)
    lo = max(W[k]["s"] for W in V) + KEEP
    hi = min(W[k]["e"] for W in V) - KEEP
    t = round(sum(ts) / len(ts), 3)
    return t if lo <= t <= hi else None


# ------------------------------------------------------------------ candidates
def candidates(V, dur, kind, rng, ctx, size=None):
    W, n, out = V[0], len(V[0]), []
    words = [w["w"] for w in W]
    dmin = lambda k: min(X[k]["e"] - X[k]["s"] for X in V)

    def add(p, aff, etype, sev, detail):
        out.append((p, set(aff), f"{etype} · {sev} · {detail}", sev))

    if kind == "move":
        _, lo, hi = next(s for s in SIZES if s[0] == size)
        for k in range(n):
            for edge in ("start", "end"):
                for sign in (-1, 1):
                    ms = sign * rng.randrange(lo, hi + 1, 10)
                    affs = [move_ok(X, dur, k, edge, ms) for X in V]
                    if all(affs):
                        add({"action": "move", "word": k, "edge": edge, "shift_ms": ms}, set().union(*affs),
                            f"boundary_{edge}", size, f"{words[k]} {edge} {abs(ms)} ms {'later' if ms > 0 else 'earlier'}")
    elif kind == "overlap" and not ctx["overlap_speech"]:
        for k in range(n):
            for edge, sign in (("end", 1), ("start", -1)):
                ms = sign * rng.randrange(150, 451, 10)
                if all(overlap_ok(X, k, edge, ms) for X in V):
                    nb = k + 1 if edge == "end" else k - 1
                    add({"action": "overlap", "word": k, "edge": edge, "shift_ms": ms}, {k, nb}, "boundary_overlap",
                        "major", f"{words[k]} {edge} {abs(ms)} ms {'later' if ms > 0 else 'earlier'}, into {words[nb]}")
    elif kind == "zero":
        for k in range(n):
            if not fixed(words[k]) and dmin(k) >= 0.15:
                edge = rng.choice(["start", "end"])
                add({"action": "zero", "word": k, **({"edge": "end"} if edge == "end" else {})}, {k}, "zero_length",
                    "critical" if dmin(k) >= 0.3 else "major", f"{words[k]} collapses to zero length at its {edge}")
    elif kind == "delete":
        for k in range(n):
            if not fixed(words[k]) and dmin(k) >= 0.12 and len(words[k]) >= MIN_WORD_LEN:
                filler = words[k] in FILLERS
                add({"action": "delete", "word": k}, {k}, "filler_deleted" if filler else "word_deletion",
                    "major" if filler else "critical", f"'{words[k]}' gone from transcript and chips")
    elif kind == "remove":
        for k in range(n):
            if not fixed(words[k]) and dmin(k) >= 0.12 and len(words[k]) >= MIN_WORD_LEN:
                add({"action": "remove", "word": k}, {k}, "missing_segment", "critical" if dmin(k) >= 0.3 else "major",
                    f"{words[k]} keeps its text but has no chip")
    elif kind == "add":
        for k in range(n - 1):
            if not fixed(words[k]) and not fixed(words[k + 1]) and all(X[k + 1]["s"] - X[k]["e"] >= MIN_PAUSE for X in V):
                gap = min(X[k + 1]["s"] - X[k]["e"] for X in V)
                add({"action": "add", "after_word": k, "text": words[k]}, {k, k + 1}, "word_hallucination",
                    "critical" if gap >= 0.6 else "major", f"extra '{words[k]}' in the {gap:.2f} s pause after it")
    elif kind == "absorb":
        for k in range(n):
            if words[k] in FILLERS:
                into = "next" if k + 1 < n and not fixed(words[k + 1]) else ("previous" if k > 0 and not fixed(words[k - 1]) else None)
                if into:
                    nb = k + 1 if into == "next" else k - 1
                    add({"action": "absorb", "word": k, "into": into}, {k, nb}, "filler_absorbed", "major",
                        f"'{words[k]}' gone, {words[nb]} stretched over it")
    elif kind == "word_substitution":
        for k in range(n):
            if words[k] in SUBST:
                add({"action": "replace", "word": k, "text": SUBST[words[k]]}, {k}, "word_substitution", "critical",
                    f"{words[k]} -> {SUBST[words[k]]}")
    elif kind == "spelling_slip":
        for k in range(n):
            if len(words[k]) >= 6 and words[k].isalpha():
                t = spelling_slip(words[k], rng)
                if t:
                    add({"action": "replace", "word": k, "text": t}, {k}, "spelling_slip", "major", f"{words[k]} -> {t}")
    elif kind == "umlaut_replaced":
        for k in range(n):
            t = None if fixed(words[k]) else umlaut(words[k])
            if t:
                add({"action": "replace", "word": k, "text": t}, {k}, ACCENT_LABEL, "major", f"{words[k]} -> {t}")
    elif kind == "spoken_form":
        for k in range(n):
            if words[k] in REDUCE:
                t = REDUCE[words[k]]
                add({"action": "replace", "word": k, "text": t}, {k}, REDUCE_LABEL, "major",
                    f"said '{words[k]}', written '{t}'")
    elif kind == "truncation_introduced":
        for k in range(n):
            w = words[k]
            if len(w) >= 6 and w.isalpha() and dmin(k) >= 0.25:
                t = w[:math.ceil(len(w) * 0.55)] + "-"
                add({"action": "replace", "word": k, "text": t}, {k}, "truncation_introduced", "critical",
                    f"complete word {w} written cut off as {t}")
    elif kind == "truncation_completed":
        for k in range(n):
            w = words[k]
            if w.endswith("-") and len(w) >= 3 and not fixed(w):
                full = sorted(v for v in ctx["vocab"] if v.startswith(w[:-1]) and len(v) > len(w) - 1 and v.isalpha())
                if full:
                    add({"action": "replace", "word": k, "text": full[0]}, {k}, "truncation_completed", "critical",
                        f"cut-off {w} written in full as {full[0]}")
    elif kind == "compound_split":
        for k in range(n):
            parts = compound_parts(words[k], ctx["vocab"])
            at = parts and at_split(V, k, parts)
            if at:
                add({"action": "split", "word": k, "parts": parts, "at": at}, {k}, "compound_split", "major",
                    f"{words[k]} -> {' + '.join(parts)}")
    elif kind == "number_split":
        for k in range(n):
            parts = None if fixed(words[k]) else number_parts(words[k])
            if parts:
                p = {"action": "split", "word": k, "parts": parts}
                if len(parts) == 2:
                    at = at_split(V, k, parts)
                    if not at:
                        continue
                    p["at"] = at
                add(p, {k}, "number_split", "major", f"{words[k]} -> {' + '.join(parts)}")
    elif kind == "words_merged":
        for k in range(n - 1):
            if words[k].isalpha() and words[k + 1].isalpha() and join_ok(V, k, 2):
                add({"action": "join", "word": k, "count": 2}, {k, k + 1}, "words_merged", "major",
                    f"{words[k]} {words[k + 1]} in one chip")
    elif kind == "acronym_collapsed":
        k = 0
        while k < n:
            j = k
            while j < n and re.fullmatch(r"[a-zäöü]\.?", words[j]):
                j += 1
            if j - k >= 2:
                for c in range(j - k, 1, -1):
                    if join_ok(V, k, c):
                        add({"action": "join", "word": k, "count": c}, range(k, k + c), "acronym_collapsed", "major",
                            f"spelled letters {' '.join(words[k:k + c])} in one chip")
                        break
            k = max(j, k + 1)
    elif kind == "unintelligible":
        content = [w for w in words if w.isalpha() and len(w) >= 4]
        for k in range(n):
            w = words[k]
            if w == "(())" and content:
                t = rng.choice(content)
                add({"action": "replace_unintelligible", "word": k, "text": t}, {k}, "unintelligible_invented",
                    "critical", f"(()) written as an invented '{t}'")
            elif re.fullmatch(r"\(\(.+\)\)", w) and content:
                t = rng.choice([c for c in content if c != w[2:-2]] or content)
                add({"action": "replace_unintelligible", "word": k, "text": t}, {k}, "unintelligible_invented",
                    "critical", f"{w} written as an invented '{t}'")
    return out


def obviousness(p, sev):
    if p["action"] == "move":
        return abs(p["shift_ms"])
    return {"critical": 600, "major": 350, "minor": 100}[sev] + (50 if p["action"] in ("delete", "add", "replace") else 0)


def main(src, template, out_dir=HERE, name="german"):
    tpl = json.loads(pathlib.Path(template).read_text(encoding="utf-8"))
    items = list(load(src))
    vocab = set()
    for _, answers in items:
        for _, a, _ in answers:
            vocab.update(s["final_transcription"] for s in a["segments"])
    have, sizes, decoys, skipped = collections.Counter(), collections.Counter(), [], []
    etypes = collections.Counter()
    for wid, answers in items:
        adj = [a for o, a, _ in answers if o == "ADJUDICATION"]
        chosen = adj[-1] if adj else answers[-1][1]
        task = answers[-1][2]
        if not chosen["segments"]:
            skipped.append({"work_item_id": wid, "file_name": task,
                            "reason": "entirely synthetic, no segments" if chosen["audio_synthetic"] else "no segments"})
            continue
        V = [to_words(chosen)] if adj else [to_words(a) for o, a, _ in answers]
        assert all([w["w"] for w in X] == [w["w"] for w in V[0]] for X in V), wid
        W = V[0]
        dur = max(X[-1]["e"] for X in V)
        n = len(W)
        target = TARGET_FN(n) if TARGET_FN else 1 if n < 8 else 2 if n < 16 else 3 if n < 30 else 4 if n < 45 else 5 if n < 60 else 6
        ctx = {"vocab": vocab, "overlap_speech": chosen["overlapping_speech"]}
        best = None
        for attempt in range(RETRIES):                    # attempt 0 = the original plan; others only if it falls short
            rng = random.Random(f"{SEED}-{wid}" + (f"-{attempt}" if attempt else ""))
            h, sz, et = collections.Counter(have), collections.Counter(sizes), collections.Counter(etypes)
            plants, taken = [], []
            while len(plants) < target:
                total = sum(h.values()) + 1
                placed = False
                key = (lambda a: (h[a] / total - SHARE[a], rng.random())) if attempt == 0 else (lambda a: rng.random())
                for kind in sorted(SHARE, key=key):
                    order = sorted([s for s, _, _ in SIZES], key=lambda s: (sz[s], rng.random())) if kind == "move" else [None]
                    for size in order:
                        cands = [c for c in candidates(V, dur, kind, rng, ctx, size)
                                 if all(abs(a - b) >= GAP_WORDS for t in taken for a in t for b in c[1])]
                        if cands:
                            p, aff, note, sev = rng.choice(cands)
                            plants.append((dict(p, note=note), sev)); taken.append(aff); h[kind] += 1
                            et[note.split(" · ")[0]] += 1
                            if size:
                                sz[size] += 1
                            placed = True
                            break
                    if placed:
                        break
                if not placed:
                    break
            if best is None or len(plants) > len(best[0]):
                best = (plants, h, sz, et)
            if len(plants) >= target:
                break
        plants, have, sizes, etypes = best
        if plants:
            ranked = sorted(range(len(plants)), key=lambda i: -obviousness(*plants[i]))
            for i in ranked[:2 if len(plants) >= 5 else 1]:
                plants[i][0]["critical"] = True
        out = [{**{k: v for k, v in p.items() if k != "note"}, "note": p["note"]} for p, _ in plants]
        out.sort(key=lambda p: p.get("word", p.get("after_word")))
        if SPEAKER_FLAG and chosen["multiple_speakers"]:
            out.append({"action": "set_flag", "flag": "multi_speaker", "value": False,
                        "note": "multiple_speakers_off · critical · the file has several speakers; served as single-speaker"})
            etypes["multiple_speakers_off"] += 1
        decoys.append({"decoy_ref": task, "work_item_id": wid, "file_name": task, "plants": out})
    res = {"format": tpl["format"], "instructions": tpl["instructions"], "decoys": decoys}
    (pathlib.Path(out_dir) / f"{name}_decoy_plants.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (pathlib.Path(out_dir) / f"{name}_skipped.json").write_text(json.dumps(skipped, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    per = collections.Counter(len(d["plants"]) for d in decoys)
    acts = collections.Counter(p["action"] for d in decoys for p in d["plants"])
    print(f"{len(items)} work items -> {len(decoys)} decoys, {len(skipped)} skipped | {sum(acts.values())} plants")
    print(f"actions {dict(acts.most_common())}")
    print(f"error types {dict(etypes.most_common())}")
    print(f"boundary sizes {dict(sizes)} | per file {dict(sorted(per.items()))}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else HERE / "forced-alignment-deliveries-de_DE-2026-11-10.zip",
         sys.argv[2] if len(sys.argv) > 2 else HERE.parent / "hindi_decoys" / "alignment-decoys-template.json")
