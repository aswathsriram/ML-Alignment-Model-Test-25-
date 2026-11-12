#!/usr/bin/env python3
"""
The 1000-file French alignment decoy set, in the same package as alignment_decoys/alignment_decoys_fr_FR.zip, split
into 10 self-contained parts of 100 files (one zip of 1000 wav files would be about 300 MB).

Every file is natural, human-sounding speech (no synthetic files) and carries 3-5 planted errors:
  BOUNDARY 50 %      BND-MINOR (40-80 ms, A3), BND-MAJOR (100-300 ms A2, over 300 ms A1), BND-OVERLAP (A1), BND-ZERO (A1)
  MISSING 12.5 %     WD: a spoken word has no segment
  HALLUCINATED 12.5% WH: an invented word over a pause or a breath
  WRONG-WORD 12.5 %  WS: homophone (vert -> verre, A2), small form change (le -> les, A3), different word (A1),
                     complete word written cut off (gestion -> gest-, A1), spelling slip (A3), spoken form (ça -> cela, A2)
  GUIDELINE 12.5 %   G-ACCENT: accent / cedilla dropped (A3) · G-BACKCH: filler misspelt (euh -> heu, A3)
No split, join, capital-letter, punctuation or digit errors. Errors uses the injector, scorer and self-test of
alignment_decoys/build_alignment_decoys.py; weights: each part's 100 points spread A1 3 : A2 2 : A3 1 within a group.

Input  : french_1000/transcripts.jsonl, french_1000/build/items/*.json, french_1000/build/wav/*.wav
Output : french_1000/alignment_decoys_fr_FR_1000_partNNof10.zip, french_1000/fr_FR_1000_index.csv
Run    : python french_1000/build_package.py
"""
import collections, csv, json, pathlib, random, re, shutil, sys, wave, zipfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "alignment_decoys")); sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
import build_alignment_decoys as bad                                     # noqa: E402
from make_japanese import frames_db                                      # noqa: E402
from package_docs_1000 import write_docs, write_xlsx                     # noqa: E402

LOC, SEED, PARTS = "fr_FR", 20261112, 10
GROUP_POINTS = {"BOUNDARY": 50, "MISSING": 12.5, "HALLUCINATED": 12.5, "WRONG-WORD": 12.5, "GUIDELINE": 12.5}
BND_SHARE = {"MINOR": 10, "MAJOR-A2": 12, "MAJOR-A1": 8, "OVERLAP": 5, "ZERO": 5}
OTHER = ["WD", "WH", "WS", "GUIDE"]
WS_SHARE = {"homophone": 30, "form": 15, "different": 20, "cutoff": 15, "slip": 10, "spoken": 10}
HOMOPHONES = [("ver", "verre", "vers", "vert"), ("mère", "mer", "maire"), ("sain", "saint", "sein"), ("peut", "peu"),
              ("a", "à"), ("et", "est"), ("ou", "où"), ("son", "sont"), ("ces", "ses"), ("ce", "se"), ("on", "ont"),
              ("la", "là"), ("c'est", "s'est"), ("sa", "ça"), ("quand", "quant"), ("mais", "mes"), ("près", "prêt"),
              ("vingt", "vin"), ("cent", "sans", "sang"), ("fois", "foi", "foie"), ("conte", "compte"),
              ("cour", "cours", "court"), ("voix", "voie", "voit"), ("pain", "pin"), ("du", "dû"), ("sur", "sûr"),
              ("faim", "fin"), ("mot", "maux"), ("pois", "poids"), ("coup", "coût", "cou"), ("temps", "tant"),
              ("vers", "verre"), ("chair", "cher"), ("mai", "mais"), ("été", "était")]
FORMS = [("le", "les"), ("un", "une"), ("de", "des"), ("au", "aux"), ("ma", "mon"), ("il", "ils"), ("elle", "elles"),
         ("cet", "cette"), ("tout", "tous"), ("leur", "leurs"), ("du", "des"), ("notre", "nos"), ("votre", "vos")]
SPOKEN = {"ça": "cela", "cela": "ça", "ouais": "oui", "y'a": "il"}


def table(groups):
    t = {}
    for g in groups:
        for i, w in enumerate(g):
            t.setdefault(w, g[(i + 1) % len(g)])
    return t


HOMO, FORM = table(HOMOPHONES), table(FORMS)


def slip(w, rng):
    if "'" in w or len(w) < 5:
        return None
    opts = [w[:m.start()] + w[m.start() + 1:] for m in re.finditer(r"([lmnprst])\1", w)]
    for a, b in (("ph", "f"), ("eau", "au"), ("qu", "k"), ("ai", "è")):
        if a in w:
            opts.append(w.replace(a, b, 1))
    if re.search(r"[aeiouéèê][tsdx]$", w):
        opts.append(w[:-1])
    opts = sorted(set(o for o in opts if o != w and len(o) >= 4))
    return rng.choice(opts) if opts else None


def ws_cands(c, vocab, rng):
    """Wrong-word candidates by kind."""
    out = collections.defaultdict(list)
    func = set(bad.FUNC[LOC].split())
    for k, x in enumerate(c.w):
        w = x["word"]
        if not c.free(k) or bad.is_letter(w) or w in bad.FILLERS[LOC]:
            continue
        if w in HOMO:
            out["homophone"].append(("WS", k, {"to": HOMO[w], "band": "A2", "rule": "homophone"}))
        if w in FORM:
            out["form"].append(("WS", k, {"to": FORM[w], "band": "A3", "rule": "form_changed"}))
        if w in SPOKEN and w != "y'a":
            out["spoken"].append(("WS", k, {"to": SPOKEN[w], "band": "A2", "rule": "spoken_form_changed"}))
        if len(w) >= 5 and w not in func and "'" not in w:
            near = [v for v in vocab.get(w[:2], []) if v != w and abs(len(v) - len(w)) <= 2 and v not in func]
            if near:
                out["different"].append(("WS", k, {"to": rng.choice(near), "band": "A1", "rule": "word_substituted"}))
            t = slip(w, rng)
            if t:
                out["slip"].append(("WS", k, {"to": t, "band": "A3", "rule": "spelling_slip"}))
        if len(w) >= 6 and "'" not in w and c.wdur(k) >= 0.25 and k not in c.hyphen:
            out["cutoff"].append(("WS", k, {"to": w[:max(3, round(len(w) * 0.55))] + "-", "band": "A1",
                                            "rule": "complete_word_written_cut_off"}))
    return out


def guide_cands(c):
    out = {"G-ACCENT": [], "G-BACKCH": []}
    for k, x in enumerate(c.w):
        w = x["word"]
        if not c.free(k) or bad.is_letter(w):
            continue
        to = bad.strip_accents(w)
        if to != w:
            out["G-ACCENT"].append(("G-ACCENT", k, {"to": to, "band": "A3", "rule": "accent_dropped"}))
        if w in bad.MISSPELL[LOC]:
            out["G-BACKCH"].append(("G-BACKCH", k, {"to": bad.MISSPELL[LOC][w], "rule": "backchannel_misspelt"}))
    return out


def plan(ctxs, rng, vocab):
    n = len(ctxs)
    per_file = [(3, 2)] * (n // 5) + [(1, 2)] * (n // 5) + [(2, 2)] * (n - 2 * (n // 5))
    rng.shuffle(per_file)
    plans = {i: [] for i in range(n)}
    have = collections.Counter()
    ws_have, g_have = collections.Counter(), collections.Counter()
    bnd_have = collections.Counter()
    order = list(range(n)); rng.shuffle(order)
    total_other = sum(q[1] for q in per_file)
    total_bnd = sum(q[0] for q in per_file)
    for i in order:                                                       # other errors
        c = ctxs[i]
        for _ in range(per_file[i][1]):
            done = False
            for cat in sorted(OTHER, key=lambda x: (have[x] - total_other / len(OTHER) * (sum(have.values()) + 1) / total_other,
                                                    rng.random())):
                if cat == "WD":
                    cs = bad.wd_cands(c)
                elif cat == "WH":
                    cs = bad.wh_cands(c, rng)
                elif cat == "WS":
                    d = ws_cands(c, vocab, rng)
                    tot = sum(ws_have.values()) + 1
                    kinds = sorted((k for k in WS_SHARE if d[k]), key=lambda k: (ws_have[k] / tot - WS_SHARE[k] / 100, rng.random()))
                    cs = d[kinds[0]] if kinds else []
                    if kinds:
                        kind = kinds[0]
                else:
                    d = guide_cands(c)
                    gs = [g for g in ("G-BACKCH", "G-ACCENT") if d[g]]
                    gs.sort(key=lambda g: (g_have[g] / (sum(g_have.values()) + 1) - (0.3 if g == "G-BACKCH" else 0.7), rng.random()))
                    cs = d[gs[0]] if gs else []
                if not cs:
                    continue
                fam, k, info = rng.choice(cs)
                c.take(*([k - 1, k] if fam == "WH" else [k]))
                plans[i].append((fam, k, info)); have[cat] += 1
                if cat == "WS":
                    ws_have[kind] += 1
                if cat == "GUIDE":
                    g_have[fam] += 1
                done = True
                break
            if not done:
                break
    for i in order:                                                       # boundary errors
        c = ctxs[i]
        want = per_file[i][0] + (per_file[i][1] - len(plans[i]))           # make up for other errors that did not fit
        for _ in range(want):
            if len(plans[i]) >= 5:
                break
            tot = sum(bnd_have.values()) + 1
            for kind in sorted(BND_SHARE, key=lambda k: (bnd_have[k] / tot - BND_SHARE[k] / 40, rng.random())):
                cs = bad.bnd_cands(c, kind, rng)
                if cs:
                    fam, k, info = rng.choice(cs)
                    c.take(k)
                    if fam == "BND-OVERLAP":
                        c.take(k + (1 if info["edge"] == "end" else -1))
                    plans[i].append((fam, k, info)); bnd_have[kind] += 1
                    break
    return plans, have, ws_have, g_have, bnd_have


def records_for(ctxs, plans, rng):
    ids = list(range(1, len(ctxs) + 1)); rng.shuffle(ids)
    recs, used = [], set()
    for n, c in enumerate(ctxs):
        segs, inj = bad.apply(c, plans[n])
        while True:
            fid, fname = bad.rand_ids(rng)
            if fid not in used and fname not in used:
                used |= {fid, fname}; break
        recs.append({"c": c, "decoy_id": f"ALN-FR-{ids[n]:04d}", "file_id": fid, "file_name": fname,
                     "decoy_segments": segs, "inj": inj})
    return recs


def corpus_for(recs):
    factor = collections.Counter()
    for r in recs:
        for x in r["inj"]:
            factor[bad.FAMILY[x["family"]][0]] += bad.BAND_FACTOR[x["band"]]
    out = []
    for r in sorted(recs, key=lambda r: r["decoy_id"]):
        c = r["c"]
        inj = [dict(x) for x in r["inj"]]
        for m, x in enumerate(inj, 1):
            g = bad.FAMILY[x["family"]][0]
            x["weight"] = bad.r3(GROUP_POINTS[g] * bad.BAND_FACTOR[x["band"]] / factor[g])
            x["injection_id"] = f"{r['decoy_id']}-{m}"
            x["fingerprint"] = bad.fingerprint(x)
        v = c.item["source"]["voice"]
        out.append({
            "decoy_id": r["decoy_id"], "group": "AL-HUMAN", "locale": LOC, "script": "latin", "file_id": r["file_id"],
            "file_name": r["file_name"], "internal_id": c.row["id"], "duration_seconds": c.dur,
            "gold_text": " ".join(x["word"] for x in c.w), "decoy_text": " ".join(x["word"] for x in r["decoy_segments"]),
            "gold_token_count": c.n, "decoy_token_count": len(r["decoy_segments"]),
            "gold_segments": c.w, "decoy_segments": r["decoy_segments"],
            "gold_whole_audio_tag": "none", "decoy_whole_audio_tag": "none",
            "voice": {"name": v["name"], "gender": v["gender"], "type": "human", "voice_id": v["voice_id"]},
            "injection_count": len(inj), "bands": sorted({x["band"] for x in inj}),
            "families": sorted({x["family"] for x in inj}, key=list(bad.FAMILY).index),
            "total_weight": bad.r3(sum(x["weight"] for x in inj)), "injections": inj,
            "status": "ACTIVE", "cat1b_flag": False, "cat2_fixes": [], "reinjected": False,
        })
    return out


def write_part(k, corpus):
    label = f"part{k:02d}of{PARTS:02d}"
    pkg = HERE / "build" / "package" / label
    if pkg.exists():
        shutil.rmtree(pkg)
    (pkg / "audio").mkdir(parents=True)
    for e in corpus:
        shutil.copyfile(HERE / "build" / "wav" / f"{e['internal_id']}.wav", pkg / "audio" / e["file_name"])
    serve = sorted(corpus, key=lambda e: e["file_id"])
    prefill = {"fileMetadata": {"locale": LOC, "workitemsCount": len(serve)},
               "items": [{"id": e["file_id"], "name": e["file_name"], "transcript": e["decoy_text"],
                          "source": {"sample_rate_hz": 16000, "duration_seconds": e["duration_seconds"],
                                     "words": e["decoy_segments"]}} for e in serve]}
    (pkg / f"alignment_prefill_{LOC}.json").write_text(json.dumps(prefill, ensure_ascii=False, indent=2), encoding="utf-8")
    (pkg / "decoy_corpus.json").write_text(json.dumps(corpus, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, rows in (("decoy_corpus_ALL.csv", list(bad.csv_rows(corpus))), ("decoy_corpus_CHANGED.csv", [])):
        with open(pkg / name, "w", newline="", encoding="utf-8-sig") as fh:
            wr = csv.DictWriter(fh, fieldnames=bad.CSV_COLS); wr.writeheader(); wr.writerows(rows)
    (pkg / "decoy_change_manifest.json").write_text(json.dumps(
        {"cat2_fixed": [], "reinjected": [], "pulled": [], "flagged_cat1b": []}, indent=1), encoding="utf-8")
    shutil.copyfile(ROOT / "alignment_decoys" / "alignmentDecoyScorer.js", pkg / "alignmentDecoyScorer.js")
    shutil.copyfile(ROOT / "alignment_decoys" / "run_selftest.js", pkg / "run_selftest.js")
    shutil.copyfile(ROOT / "alignment_decoys" / LOC / f"Forced_Alignment_Guidelines_{LOC}.pdf",
                    pkg / f"Forced_Alignment_Guidelines_{LOC}.pdf")
    st = bad.selftest(pkg)
    part = f"part {k} of {PARTS}"
    write_xlsx(pkg / "decoy_summary.xlsx", LOC, corpus, bad.FAMILY, GROUP_POINTS, bad.BAND_FACTOR, 0, part=part)
    write_docs(pkg, LOC, corpus, st, bad.md5(pkg / "alignmentDecoyScorer.js"), bad.FAMILY, GROUP_POINTS, 0, SEED,
               part=part, total=PARTS * len(corpus))
    z = HERE / f"alignment_decoys_{LOC}_1000_{label}.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(pkg.rglob("*")):
            if p.is_file():
                info = zipfile.ZipInfo(f"alignment_decoys_{LOC}_{label}/{p.relative_to(pkg).as_posix()}", (2026, 11, 12, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, p.read_bytes())
    return z, st


def main():
    rng = random.Random(f"{SEED}-{LOC}-1000")
    rows = [json.loads(l) for l in (HERE / "transcripts.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    items = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (HERE / "build" / "items").glob("*.json")}
    missing = [r["id"] for r in rows if r["id"] not in items]
    assert not missing, f"{len(missing)} clips not made yet: {missing[:10]}"
    vocab = collections.defaultdict(set)
    for r in rows:
        for w in r["words"]:
            if len(w) >= 5 and "'" not in w:
                vocab[w[:2]].add(w)
    vocab = {k: sorted(v) for k, v in vocab.items()}
    ctxs = []
    for r in rows:
        r = dict(r, hints={"ws": [], "num": [], "cap": [], "cmp": []})
        with wave.open(str(HERE / "build" / "wav" / f"{r['id']}.wav")) as w:
            frames = frames_db(w.readframes(w.getnframes()))
        ctxs.append(bad.FileCtx(LOC, r, items[r["id"]], frames))
    plans, have, ws_have, g_have, bnd_have = plan(ctxs, rng, vocab)
    recs = records_for(ctxs, plans, rng)
    rng.shuffle(recs)
    size = len(recs) // PARTS
    index = []
    for k in range(1, PARTS + 1):
        corpus = corpus_for(recs[(k - 1) * size:k * size])
        z, st = write_part(k, corpus)
        print(f"{z.name}: {len(corpus)} files, {st['alignment']} injections, self-test {st['decoy_missed']}/{st['scored']} "
              f"MISSED on decoy, {st['gold_caught']}/{st['scored']} CAUGHT on gold, {st['jitter_caught']}/{st['alignment']} "
              f"with ±20 ms jitter, {z.stat().st_size / 1e6:.1f} MB", flush=True)
        for e in corpus:
            index.append({"part": k, "zip": z.name, "decoy_id": e["decoy_id"], "file_id": e["file_id"], "file_name": e["file_name"],
                          "internal_id": e["internal_id"], "voice": e["voice"]["name"], "gender": e["voice"]["gender"],
                          "voice_type": "human", "duration_seconds": e["duration_seconds"], "words": e["gold_token_count"],
                          "injections": e["injection_count"], "families": ", ".join(e["families"]), "gold_text": e["gold_text"]})
    with open(HERE / "fr_FR_1000_index.csv", "w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(index[0])); wr.writeheader(); wr.writerows(sorted(index, key=lambda x: x["decoy_id"]))
    fam = collections.Counter(x["family"] for r in recs for x in r["inj"])
    band = collections.Counter(x["band"] for r in recs for x in r["inj"])
    per = collections.Counter(len(r["inj"]) for r in recs)
    print(f"{len(recs)} files | {sum(fam.values())} injections {dict(fam.most_common())} | bands {dict(sorted(band.items()))} | "
          f"per file {dict(sorted(per.items()))}")
    print(f"other {dict(have)} | wrong-word kinds {dict(ws_have)} | guideline {dict(g_have)} | boundary {dict(bnd_have)}")


if __name__ == "__main__":
    main()
