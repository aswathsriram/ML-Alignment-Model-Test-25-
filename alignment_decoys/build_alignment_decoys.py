#!/usr/bin/env python3
"""
Build the forced-alignment decoy corpus for one or more locales (de_DE es_ES it_IT pt_BR fr_FR).

Input  : alignment_decoys/<locale>/transcripts.jsonl                 the 20 transcripts and decoy hints
         alignment_decoys/build/<locale>/answer_key/<locale>_clean.json  gold alignment  (make_japanese.py --lang decoy-<locale>)
         alignment_decoys/build/<locale>/wav/*.wav                     the audio
Output : alignment_decoys/build/<locale>/package/   everything that goes into the zip
         alignment_decoys/alignment_decoys_<locale>.zip

Every one of the 20 files carries decoys (3-5 alignment decoys; the 3 synthetic files also carry CB-WHOLE).
Mix per locale, by count and by score share: boundary 50 % (minor / major / overlap / zero length), missing
segment 10 %, hallucinated segment 10 %, wrong word 10 %, segmentation 10 %, guideline 10 %.
Bands: A1 obvious (missing it costs most), A2 medium, A3 subtle. Seeded: rebuilds byte-identically.

Run    : python alignment_decoys/build_alignment_decoys.py [locale ...]
"""
import array, csv, hashlib, json, math, pathlib, random, re, shutil, subprocess, sys, unicodedata, wave, zipfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from make_japanese import frames_db                                      # noqa: E402

SEED = 20261027
LOCALES = ["de_DE", "es_ES", "it_IT", "pt_BR", "fr_FR"]
PREFIX = {"de_DE": "DE", "es_ES": "ES", "it_IT": "IT", "pt_BR": "PT", "fr_FR": "FR"}
GROUP_POINTS = {"BOUNDARY": 50, "MISSING": 10, "HALLUCINATED": 10, "WRONG-WORD": 10, "SEGMENTATION": 10, "GUIDELINE": 10}
BAND_FACTOR = {"A1": 3, "A2": 2, "A3": 1}
CB_WEIGHT = 5.0                                                          # synthetic gate, outside the 100 points
BND_SLOTS = ["MINOR"] * 10 + ["MAJOR-A2"] * 12 + ["MAJOR-A1"] * 8 + ["OVERLAP"] * 5 + ["ZERO"] * 5
OTHER_SLOTS = {"WD": 8, "WH": 8, "WS": 8, "SEG": 8, "GUIDE": 8}
PER_FILE = [(3, 2)] * 4 + [(1, 2)] * 4 + [(2, 2)] * 12                  # (boundary, other) per file: 3-5 decoys
CTX = 6                                                                  # anchor words each side

FAMILY = {   # family: (score group, detect, name)
    "BND-MINOR": ("BOUNDARY", "EDGE_AT_SLOT", "Boundary mismatch, minor (40-80 ms)"),
    "BND-MAJOR": ("BOUNDARY", "EDGE_AT_SLOT", "Boundary mismatch, major (100-300 ms A2, >300 ms A1)"),
    "BND-OVERLAP": ("BOUNDARY", "EDGE_AT_SLOT", "Segment runs into the neighbouring word (same-speaker overlap)"),
    "BND-ZERO": ("BOUNDARY", "ZERO_LENGTH", "Zero-length segment"),
    "WD": ("MISSING", "WORD_AT_SLOT_PRESENT", "Missing segment: spoken word has no segment"),
    "WH": ("HALLUCINATED", "SEGMENT_AT_SLOT_ABSENT", "Hallucinated segment over silence / breath"),
    "WS": ("WRONG-WORD", "WORD_AT_SLOT_SUBSTITUTED", "Wrong word / homophone"),
    "SEG-MERGE": ("SEGMENTATION", "WORDS_SPLIT", "Two words in one segment"),
    "SEG-SPLIT": ("SEGMENTATION", "WORD_MERGED", "One word spread over two segments (compound / elision)"),
    "SEG-LETTERS": ("SEGMENTATION", "WORDS_SPLIT", "Spelled letters joined into one segment"),
    "SEG-FILLER": ("SEGMENTATION", "FILLER_PRESENT", "Filler hidden inside the next word's segment"),
    "G-NUM": ("GUIDELINE", "WORD_AT_SLOT_SUBSTITUTED", "Number written as digits"),
    "G-CASE": ("GUIDELINE", "WORD_AT_SLOT_SUBSTITUTED", "Capital letter"),
    "G-HYPHEN": ("GUIDELINE", "WORDS_SPLIT", "Hyphenated word kept as one segment"),
    "G-ACCENT": ("GUIDELINE", "WORD_AT_SLOT_SUBSTITUTED", "Accent / umlaut / cedilla dropped"),
    "G-CONTRACT": ("GUIDELINE", "WORD_MERGED", "Mandatory contraction written out"),
    "G-BACKCH": ("GUIDELINE", "WORD_AT_SLOT_SUBSTITUTED", "Filler / backchannel spelling"),
    "G-PUNCT": ("GUIDELINE", "WORD_AT_SLOT_SUBSTITUTED", "Punctuation in a segment"),
    "CB-WHOLE": ("CHECKBOX", "CHECKBOX_WHOLE_AUDIO", "Entirely synthetic speech not marked"),
}

FILLERS = {   # hesitation fillers / backchannels per guideline Part 5 (used for SEG-FILLER and G-BACKCH)
    "de_DE": {"äh", "ähm", "tja", "naja", "mm", "hm", "ach", "genau"},
    "es_ES": {"eh", "mmm", "pues", "este", "bueno", "claro", "hombre", "ah"},
    "it_IT": {"ehm", "beh", "cioè", "mah", "boh", "mm", "hm", "ah", "hmm", "dai"},
    "pt_BR": {"é", "né", "tipo", "ah", "ué", "mm", "hm", "hmm", "eita"},
    "fr_FR": {"euh", "ben", "bah", "hein", "bof", "ouais", "mm", "hm", "ah", "hmm"},
}
HESITATION = {"de_DE": {"äh", "ähm", "tja", "naja"}, "es_ES": {"eh", "mmm", "pues", "este", "bueno"},
              "it_IT": {"ehm", "beh", "mah", "boh", "cioè", "hmm"}, "pt_BR": {"é", "tipo", "ué", "eita", "hmm"},
              "fr_FR": {"euh", "ben", "bah", "bof", "hmm"}}
MISSPELL = {   # plausible wrong spellings of fillers / backchannels (G-BACKCH)
    "de_DE": {"ähm": "ähhm", "äh": "ähh", "tja": "tjaa", "naja": "najaa", "genau": "genao", "ach": "achh"},
    "es_ES": {"eh": "ehh", "mmm": "mmmm", "pues": "pue", "bueno": "bueeno", "claro": "claaro", "hombre": "ombre", "este": "estee"},
    "it_IT": {"ehm": "emm", "beh": "bè", "mah": "maah", "boh": "bo", "hmm": "hm", "dai": "daai"},
    "pt_BR": {"é": "eh", "né": "ne", "ué": "ue", "eita": "eitaa", "hmm": "hm", "tipo": "tipoo"},
    "fr_FR": {"euh": "heu", "ben": "bin", "bah": "ba", "bof": "boff", "hmm": "hm", "ouais": "ouai", "hein": "hin"},
}
HALLU = {   # short words that could plausibly have been said, inserted over pauses (WH)
    "de_DE": ["und", "also", "dann", "ja", "noch", "so"], "es_ES": ["y", "pues", "entonces", "ya", "muy"],
    "it_IT": ["e", "poi", "allora", "già", "proprio"], "pt_BR": ["e", "então", "aí", "já", "muito"],
    "fr_FR": ["et", "alors", "donc", "déjà", "très"],
}
FUNC = {   # function words: a missing function word is band A2, a missing content word A1
    "de_DE": "der die das den dem des ein eine einen einem und oder aber ich du er sie es wir ihr mit von zu im am in an auf für ist bin hat hab so da dann mal noch nur ja nicht wie was wo als bei zum zur",
    "es_ES": "el la los las un una y o que de del al en con por para se lo le me te mi su es no si ya muy pero yo tú",
    "it_IT": "il lo la i gli le un una e o che di del della al alla in con per si mi ti ci non ma io è a da sul",
    "pt_BR": "o a os as um uma e ou que de do da dos das no na em com por pra pelo pela se me te eu é não mas ao",
    "fr_FR": "le la les un une et ou que de du des au à en dans avec pour par se je tu il elle on est pas ne mais sur",
}
CONTRACT = {   # mandatory contractions written out (G-CONTRACT)
    "es_ES": {"al": ["a", "el"], "del": ["de", "el"]},
    "pt_BR": {"do": ["de", "o"], "da": ["de", "a"], "dos": ["de", "os"], "das": ["de", "as"], "no": ["em", "o"],
              "na": ["em", "a"], "ao": ["a", "o"], "pelo": ["por", "o"], "pela": ["por", "a"]},
}
UMLAUT = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
GUIDE_ORDER = ["G-NUM", "G-HYPHEN", "G-CONTRACT", "G-ACCENT", "G-CASE", "G-BACKCH", "G-PUNCT"]
SEG_ORDER = ["SEG-LETTERS", "SEG-SPLIT", "SEG-FILLER", "SEG-MERGE"]


def r3(x):
    return round(x + 0.0, 3)


def strip_accents(w):
    """Drop accents, tilde and cedilla (keep ñ: it is a letter, not an accent)."""
    out = []
    for ch in w:
        if ch == "ñ":
            out.append(ch); continue
        d = unicodedata.normalize("NFD", ch)
        out.append("".join(c for c in d if not unicodedata.combining(c)))
    return "".join(out)


def is_letter(w):
    return bool(re.fullmatch(r"[^\W\d_]\.", w))


# ------------------------------------------------------------------ candidates
class FileCtx:
    def __init__(self, loc, row, item, frames):
        self.loc, self.row, self.item, self.f = loc, row, item, frames
        self.w = item["source"]["words"]
        self.n = len(self.w)
        self.dur = item["source"]["duration_seconds"]
        self.synthetic = item["synthetic"]
        v = sorted(x for t in self.w for x in frames[self.i(t["start"]):self.i(t["end"])])
        self.speech = v[len(v) // 2]
        self.blocked = set()
        self.hyphen = {i: g for g in row["hyphen_groups"] for i in range(g[0], g[1] + 1)}

    def i(self, t):
        return min(len(self.f), max(0, int(round(t / 0.01))))

    def gap_before(self, k):
        return self.w[k]["start"] - (self.w[k - 1]["end"] if k > 0 else 0.0)

    def gap_after(self, k):
        return (self.w[k + 1]["start"] if k + 1 < self.n else self.dur) - self.w[k]["end"]

    def wdur(self, k):
        return self.w[k]["end"] - self.w[k]["start"]

    def free(self, *ks):
        return all(0 <= k < self.n and k not in self.blocked for k in ks)

    def take(self, *ks):
        for k in ks:
            for j in (k - 1, k, k + 1):
                self.blocked.add(j)

    def special(self, k):
        w = self.w[k]["word"]
        return is_letter(w) or k in self.hyphen or w in FILLERS[self.loc]

    def context(self, k, insertion=False, span=1):
        words = [x["word"] for x in self.w]
        right_from = k if insertion else k + span
        return {"left": " ".join(words[max(0, k - CTX):k]), "right": " ".join(words[right_from:right_from + CTX]),
                "plain_offset": k}

    def gold(self, k):
        return {"start": self.w[k]["start"], "end": self.w[k]["end"]}


def ws_cands(c):
    out = []
    for a, b, band in c.row["hints"]["ws"]:
        for k, x in enumerate(c.w):
            if x["word"] == a and c.free(k):
                out.append(("WS", k, {"to": b, "band": band})); break
    return out


def wd_cands(c):
    out = []
    for k in range(1, c.n - 1):
        x = c.w[k]["word"]
        if c.free(k) and not c.special(k) and c.wdur(k) >= 0.12:
            band = "A2" if (x in FUNC[c.loc].split() or len(x) <= 3) else "A1"
            out.append(("WD", k, {"band": band}))
    return out


def wh_cands(c, rng):
    out = []
    if c.synthetic:
        return out
    # pauses between words, and the silence / breath before the first word and after the last
    spans = [(k + 1, c.w[k]["end"], c.w[k + 1]["start"]) for k in range(c.n - 1)]
    spans += [(0, 0.0, c.w[0]["start"]), (c.n, c.w[-1]["end"], c.dur)]
    for k, lo, hi in spans:
        gap = hi - lo
        L = min(0.30, gap - 0.16)
        if gap < 0.40 or L < 0.15 or not c.free(*[j for j in (k - 1, k) if 0 <= j < c.n]):
            continue
        mid = (lo + hi) / 2
        a, b = r3(mid - L / 2), r3(mid + L / 2)
        peak = max(c.f[c.i(a):c.i(b)] or [-120])
        over_breath = peak >= c.speech - 30
        nb = [c.w[j]["word"] for j in (k - 1, k) if 0 <= j < c.n]
        words = [h for h in HALLU[c.loc] if h not in nb]
        out.append(("WH", k, {"word": rng.choice(words), "start": a, "end": b,
                              "band": "A2" if over_breath else "A1",
                              "rule": "hallucinated_over_breath" if over_breath else "hallucinated_over_silence"}))
    return out


def seg_cands(c):
    out = {"SEG-LETTERS": [], "SEG-SPLIT": [], "SEG-FILLER": [], "SEG-MERGE": []}
    k = 0
    while k < c.n:                                                       # spelled letters
        if is_letter(c.w[k]["word"]):
            j = k
            while j + 1 < c.n and is_letter(c.w[j + 1]["word"]):
                j += 1
            if j > k and c.free(*range(k, j + 1)):
                out["SEG-LETTERS"].append(("SEG-LETTERS", k, {"last": j}))
            k = j + 1
        else:
            k += 1
    for word, p1, p2 in c.row["hints"]["cmp"]:                          # German compounds
        for k, x in enumerate(c.w):
            if x["word"] == word and c.free(k):
                out["SEG-SPLIT"].append(("SEG-SPLIT", k, {"pieces": [p1, p2], "rule": "compound_split"})); break
    if c.loc in ("fr_FR", "it_IT"):                                      # elided forms
        for k, x in enumerate(c.w):
            m = re.fullmatch(r"([^\W\d_]+')([^\W\d_].*)", x["word"])
            if m and c.free(k) and c.wdur(k) >= 0.15:
                out["SEG-SPLIT"].append(("SEG-SPLIT", k, {"pieces": [m.group(1), m.group(2)], "rule": "elision_split"}))
    for k in range(c.n - 1):                                             # filler hidden in next word
        if c.w[k]["word"] in HESITATION[c.loc] and c.free(k, k + 1) and c.w[k + 1]["start"] - c.w[k]["end"] <= 0.30 \
                and not c.special(k + 1):
            out["SEG-FILLER"].append(("SEG-FILLER", k, {}))
    for k in range(c.n - 1):                                             # two words, one segment
        a, b = c.w[k]["word"], c.w[k + 1]["word"]
        if c.free(k, k + 1) and not c.special(k) and not c.special(k + 1) and len(a) <= 6 and len(b) <= 6 \
                and c.w[k + 1]["start"] - c.w[k]["end"] <= 0.03:
            out["SEG-MERGE"].append(("SEG-MERGE", k, {}))
    return out


def guide_cands(c):
    out = {g: [] for g in GUIDE_ORDER}
    for word, digits in c.row["hints"]["num"]:
        for k, x in enumerate(c.w):
            if x["word"] == word and c.free(k):
                out["G-NUM"].append(("G-NUM", k, {"to": digits})); break
    for g in c.row["hyphen_groups"]:
        if c.free(*range(g[0], g[1] + 1)):
            out["G-HYPHEN"].append(("G-HYPHEN", g[0], {"last": g[1]}))
    for k, x in enumerate(c.w):
        if c.loc in CONTRACT and x["word"] in CONTRACT[c.loc] and c.free(k) and c.wdur(k) >= 0.10:
            out["G-CONTRACT"].append(("G-CONTRACT", k, {"pieces": CONTRACT[c.loc][x["word"]]}))
        if c.free(k) and not is_letter(x["word"]):
            if c.loc == "de_DE":
                to = "".join(UMLAUT.get(ch, ch) for ch in x["word"])
                if to != x["word"]:
                    out["G-ACCENT"].append(("G-ACCENT", k, {"to": to, "band": "A2", "rule": "umlaut_replaced"}))
            else:
                to = strip_accents(x["word"])
                if to != x["word"]:
                    out["G-ACCENT"].append(("G-ACCENT", k, {"to": to, "band": "A3", "rule": "accent_dropped"}))
        if x["word"] in MISSPELL[c.loc] and c.free(k):
            out["G-BACKCH"].append(("G-BACKCH", k, {"to": MISSPELL[c.loc][x["word"]], "rule": "backchannel_misspelt"}))
        if c.free(k) and k + 1 < c.n and c.gap_after(k) >= 0.30 and not is_letter(x["word"]):
            out["G-PUNCT"].append(("G-PUNCT", k, {"to": x["word"] + ",", "rule": "punctuation_in_segment"}))
    for k in range(c.n - 1):                                             # "mm hm" joined into one segment
        if c.w[k]["word"] == "mm" and c.w[k + 1]["word"] == "hm" and c.free(k, k + 1):
            out["G-BACKCH"].append(("G-BACKCH", k, {"last": k + 1, "rule": "backchannel_joined"}))
    caps = set(c.row["hints"]["cap"])
    for k, x in enumerate(c.w):
        if (x["word"] in caps or k == 0) and c.free(k) and not is_letter(x["word"]) and x["word"][0].isalpha():
            out["G-CASE"].append(("G-CASE", k, {"to": x["word"][0].upper() + x["word"][1:],
                                                 "rule": "proper_noun_capitalised" if x["word"] in caps else "sentence_start_capitalised"}))
    return out


def bnd_cands(c, kind, rng):
    out = []
    for k in range(c.n):
        if not c.free(k):
            continue
        d, gb, ga = c.wdur(k), c.gap_before(k), c.gap_after(k)
        opts = []
        if kind == "MINOR":
            s = rng.choice([0.04, 0.05, 0.06, 0.07, 0.08])
            if d >= s + 0.08: opts += [("start", +s), ("end", -s)]
            if gb >= s + 0.02: opts.append(("start", -s))
            if ga >= s + 0.02: opts.append(("end", +s))
        elif kind == "MAJOR-A2":
            s = rng.choice([0.10, 0.12, 0.15, 0.18, 0.20, 0.25, 0.30])
            if d >= s + 0.10: opts += [("start", +s), ("end", -s)]
            if gb >= s + 0.03: opts.append(("start", -s))
            if ga >= s + 0.03: opts.append(("end", +s))
        elif kind == "MAJOR-A1":
            s = rng.choice([0.35, 0.40, 0.50, 0.60, 0.80])
            if gb >= s + 0.03: opts.append(("start", -s))
            if ga >= s + 0.03: opts.append(("end", +s))
            if d >= s + 0.10: opts += [("start", +s), ("end", -s)]
        elif kind == "OVERLAP":
            if k + 1 < c.n and ga <= 0.05 and c.free(k + 1) and c.wdur(k + 1) >= 0.22:
                amt = rng.choice([0.10, 0.12, 0.15, 0.18])
                opts.append(("end", r3(c.w[k + 1]["start"] + amt - c.w[k]["end"])))
            if k > 0 and gb <= 0.05 and c.free(k - 1) and c.wdur(k - 1) >= 0.22:
                amt = rng.choice([0.10, 0.12, 0.15, 0.18])
                opts.append(("start", r3(c.w[k - 1]["end"] - amt - c.w[k]["start"])))
        elif kind == "ZERO":
            if d >= 0.15: opts.append(("zero", 0.0))
        for edge, shift in opts:
            out.append(("BND-" + ("ZERO" if kind == "ZERO" else "OVERLAP" if kind == "OVERLAP" else
                                  "MINOR" if kind == "MINOR" else "MAJOR"), k,
                        {"edge": edge, "shift": shift, "kind": kind}))
    return out


# ------------------------------------------------------------------ apply
def apply(c, plan):
    """plan: list of (family, k, info) -> (decoy segments, injections)."""
    segs = [dict(x, _k=k) for k, x in enumerate(c.w)]
    drop, extra, inj = set(), [], []
    for fam, k, info in plan:
        g = c.gold(k) if k < c.n else None
        word = c.w[k]["word"] if k < c.n else None
        meta = {}
        if fam.startswith("BND-"):
            s = segs[k]
            if info["edge"] == "zero":
                s["end"] = s["start"]
                meta = {"word": word, "gold": g, "decoy": {"start": s["start"], "end": s["end"]}, "edge": "end",
                        "shift_ms": int(round((s["end"] - g["end"]) * 1000)), "rule": "zero_length"}
                band = "A1"
            else:
                s[info["edge"]] = r3(s[info["edge"]] + info["shift"])
                shift = info["shift"]
                into = ("before the word starts" if shift < 0 else "inside the word") if info["edge"] == "start" else \
                       ("inside the word" if shift < 0 else "after the word ends")
                if fam == "BND-OVERLAP":
                    into = "into the " + ("previous" if info["edge"] == "start" else "next") + " word"
                    band = "A1"
                elif fam == "BND-MINOR":
                    band = "A3"
                else:
                    band = "A1" if abs(shift) > 0.30 else "A2"
                meta = {"word": word, "gold": g, "decoy": {"start": s["start"], "end": s["end"]}, "edge": info["edge"],
                        "shift_ms": int(round(shift * 1000)), "direction": "early" if shift < 0 else "late", "lands": into,
                        "rule": f"{info['edge']}_{'early' if shift < 0 else 'late'}"}
            meta.update(c.context(k))
        elif fam == "WD":
            drop.add(k); band = info["band"]
            meta = {"word": word, "gold": g, "rule": "word_deleted", **c.context(k)}
        elif fam == "WH":
            h = {"word": info["word"], "start": info["start"], "end": info["end"], "_k": k - 0.5}
            extra.append(h); band = info["band"]
            meta = {"word": info["word"], "decoy": {"start": info["start"], "end": info["end"]}, "inserted_before_index": k,
                    "between": [c.w[k - 1]["word"] if k > 0 else None, c.w[k]["word"] if k < c.n else None],
                    "rule": info["rule"], **c.context(k, insertion=True)}
        elif fam in ("WS", "G-NUM", "G-CASE", "G-ACCENT", "G-PUNCT") or (fam == "G-BACKCH" and "last" not in info):
            segs[k]["word"] = info["to"]
            band = info.get("band") or {"G-NUM": "A1", "G-CASE": "A2", "G-PUNCT": "A2", "G-BACKCH": "A3"}[fam]
            rule = info.get("rule") or {"WS": "homophone" if band == "A2" else "word_substituted",
                                        "G-NUM": "digits_for_number_word"}.get(fam, "word_substituted")
            meta = {"from": word, "to": info["to"], "gold": g, "rule": rule, **c.context(k)}
        elif fam in ("SEG-MERGE", "SEG-LETTERS", "G-HYPHEN") or fam == "G-BACKCH":
            last = info.get("last", k + 1)
            parts = [dict(word=c.w[j]["word"], **c.gold(j)) for j in range(k, last + 1)]
            joined = {"SEG-MERGE": " ".join, "SEG-LETTERS": lambda ws: "".join(x.rstrip(".") for x in ws),
                      "G-HYPHEN": "-".join, "G-BACKCH": "".join}[fam]([p["word"] for p in parts])
            segs[k].update(word=joined, end=c.w[last]["end"])
            for j in range(k + 1, last + 1):
                drop.add(j)
            band = "A3" if fam == "G-BACKCH" else "A2"
            meta = {"joined": joined, "parts": parts, "gold": {"start": parts[0]["start"], "end": parts[-1]["end"]},
                    "rule": {"SEG-MERGE": "two_words_one_segment", "SEG-LETTERS": "letters_joined",
                             "G-HYPHEN": "hyphen_kept", "G-BACKCH": "backchannel_joined"}[fam],
                    **c.context(k, span=last - k + 1)}
        elif fam in ("SEG-SPLIT", "G-CONTRACT"):
            p1, p2 = info["pieces"]
            t = r3(g["start"] + (g["end"] - g["start"]) * len(p1) / (len(p1) + len(p2)))
            segs[k].update(word=p1, end=t)
            extra.append({"word": p2, "start": t, "end": g["end"], "_k": k + 0.5})
            band = "A2"
            meta = {"word": word, "gold": g, "pieces": [{"word": p1, "start": g["start"], "end": t},
                                                        {"word": p2, "start": t, "end": g["end"]}],
                    "rule": info.get("rule", "contraction_written_out"), **c.context(k)}
        elif fam == "SEG-FILLER":
            drop.add(k)
            segs[k + 1]["start"] = g["start"]
            band = "A2"
            meta = {"word": word, "gold": g, "next_word": c.w[k + 1]["word"], "next_gold": c.gold(k + 1),
                    "decoy_next": {"start": g["start"], "end": c.w[k + 1]["end"]}, "rule": "filler_inside_next_word",
                    **c.context(k)}
        else:
            raise ValueError(fam)
        meta["detect"] = "WORDS_SPLIT" if "parts" in meta else FAMILY[fam][1]   # "mm hm" joined is a split check
        inj.append({"family": fam, "band": band, "meta": meta})
    out = [s for s in segs if s["_k"] not in drop] + extra
    out.sort(key=lambda s: (s["_k"], s["start"]))
    clean = [{"word": s["word"], "start": r3(s["start"]), "end": r3(s["end"])} for s in out]
    fams = {x["family"] for x in inj}
    for a, b in zip(clean, clean[1:]):                                   # only planted overlaps / zero lengths
        assert a["start"] <= a["end"], (c.row["id"], a)
        if a["end"] > b["start"] + 1e-9:
            assert "BND-OVERLAP" in fams, (c.row["id"], a, b)
    for s in clean:
        assert s["end"] > s["start"] or "BND-ZERO" in fams, (c.row["id"], s)
        assert 0 <= s["start"] and s["end"] <= c.dur + 1e-9, (c.row["id"], s)
    return clean, inj


# ------------------------------------------------------------------ plan one locale
def plan_locale(loc, rows, clean, wav_dir, rng):
    ctxs = []
    for row in rows:
        item = clean[row["id"]]
        with wave.open(str(wav_dir / f"{row['id']}.wav")) as w:
            frames = frames_db(w.readframes(w.getnframes()))
        ctxs.append(FileCtx(loc, row, item, frames))
    order = list(range(len(ctxs)))
    rng.shuffle(order)
    per_file = PER_FILE[:]
    rng.shuffle(per_file)
    quota = {i: {"bnd": per_file[n][0], "other": per_file[n][1]} for n, i in enumerate(order)}

    # other-slot categories: spread so each file gets its quota and each category hits its count
    cats = []
    for cat, n in OTHER_SLOTS.items():
        cats += [cat] * n
    plans = {i: [] for i in range(len(ctxs))}
    seg_used, guide_used = {}, {}

    def pick_other(i, cat):
        c = ctxs[i]
        if cat == "WS":
            cs = ws_cands(c)
        elif cat == "WD":
            cs = wd_cands(c)
        elif cat == "WH":
            cs = wh_cands(c, rng)
        elif cat == "SEG":
            d = seg_cands(c)
            cs = []
            for s in sorted(SEG_ORDER, key=lambda s: (seg_used.get(s, 0), SEG_ORDER.index(s))):
                if d[s]:
                    cs = d[s]; break
        else:
            d = guide_cands(c)
            cs = []
            for g in sorted(GUIDE_ORDER, key=lambda g: (guide_used.get(g, 0), GUIDE_ORDER.index(g))):
                if d[g]:
                    cs = d[g]; break
        if not cs:
            return False
        fam, k, info = rng.choice(cs)
        if fam.startswith("SEG-"):
            seg_used[fam] = seg_used.get(fam, 0) + 1
        if fam.startswith("G-"):
            guide_used[fam] = guide_used.get(fam, 0) + 1
        last = info.get("last", k + 1 if fam in ("SEG-MERGE", "SEG-FILLER") else k)
        ks = list(range(k, last + 1)) if fam != "WH" else [k - 1, k]
        c.take(*ks)
        plans[i].append((fam, k, info))
        return True

    rng.shuffle(cats)
    cats.sort(key=lambda x: ["WH", "SEG", "GUIDE", "WS", "WD"].index(x))   # scarcest first
    for cat in cats:
        files = sorted(range(len(ctxs)), key=lambda i: (len(plans[i]) - quota[i]["other"], rng.random()))
        for i in files:
            if len(plans[i]) < quota[i]["other"] + 1 and pick_other(i, cat):
                break
        else:
            raise RuntimeError(f"{loc}: no file can take a {cat} decoy")
    # boundary slots
    slots = BND_SLOTS[:]
    rng.shuffle(slots)
    slots.sort(key=lambda s: ["ZERO", "OVERLAP", "MAJOR-A1", "MAJOR-A2", "MINOR"].index(s))
    nb = {i: 0 for i in range(len(ctxs))}
    for kind in slots:
        files = sorted(range(len(ctxs)), key=lambda i: (nb[i] - quota[i]["bnd"], rng.random()))
        for i in files:
            if len(plans[i]) + ctxs[i].synthetic >= 5:                  # at most 5 decoys per file, CB-WHOLE included
                continue
            cs = bnd_cands(ctxs[i], kind, rng)
            if cs and nb[i] < quota[i]["bnd"] + 1:
                fam, k, info = rng.choice(cs)
                ctxs[i].take(k)
                if fam == "BND-OVERLAP":
                    ctxs[i].take(k + (1 if info["edge"] == "end" else -1))
                plans[i].append((fam, k, info)); nb[i] += 1
                break
        else:
            raise RuntimeError(f"{loc}: no file can take a {kind} decoy")
    return ctxs, plans


def fingerprint(inj):
    body = {k: v for k, v in inj.items() if k not in ("injection_id", "fingerprint", "weight")}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def rand_ids(rng):
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    fid = "cm" + "".join(rng.choice(alphabet) for _ in range(23))
    hx = lambda n: "".join(rng.choice("0123456789abcdef") for _ in range(n))
    name = f"{hx(8)}-{hx(4)}-4{hx(3)}-{rng.choice('89ab')}{hx(3)}-{hx(12)}_{rng.randint(1, 40):03d}.wav"
    return fid, name


def build_locale(loc):
    rng = random.Random(f"{SEED}-{loc}")
    src = HERE / loc
    build = HERE / "build" / loc
    rows = [json.loads(l) for l in (src / "transcripts.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    clean = {it["id"]: it for it in json.loads((build / "answer_key" / f"{loc}_clean.json").read_text(encoding="utf-8"))["items"]}
    assert sorted(clean) == sorted(r["id"] for r in rows), "make the audio first"
    ctxs, plans = plan_locale(loc, rows, clean, build / "wav", rng)

    ids = list(range(1, len(ctxs) + 1))
    rng.shuffle(ids)
    records = []
    for n, c in enumerate(ctxs):
        decoy_segs, inj = apply(c, plans[n])
        did = f"ALN-{PREFIX[loc]}-{ids[n]:04d}"
        fid, fname = rand_ids(rng)
        if c.synthetic:
            inj.append({"family": "CB-WHOLE", "band": "A1", "field": "whole_audio_tag", "gold": "synthetic_speech",
                        "decoy": "none", "detect": "CHECKBOX_WHOLE_AUDIO", "rule": "entirely_synthetic_not_marked",
                        "audio_required": True})
        records.append({"c": c, "decoy_id": did, "file_id": fid, "file_name": fname, "decoy_segments": decoy_segs, "inj": inj})

    # weights: each score group's points spread over its injections in proportion to band (A1 3 : A2 2 : A3 1)
    group_factor = {}
    for r in records:
        for x in r["inj"]:
            g = FAMILY[x["family"]][0]
            if g != "CHECKBOX":
                group_factor[g] = group_factor.get(g, 0) + BAND_FACTOR[x["band"]]
    corpus = []
    for r in sorted(records, key=lambda r: r["decoy_id"]):
        c = r["c"]
        for m, x in enumerate(r["inj"], 1):
            g = FAMILY[x["family"]][0]
            x["weight"] = CB_WEIGHT if g == "CHECKBOX" else r3(GROUP_POINTS[g] * BAND_FACTOR[x["band"]] / group_factor[g])
            x["injection_id"] = f"{r['decoy_id']}-{m}"
            x["fingerprint"] = fingerprint(x)
        voice = c.item["source"]["voice"]
        corpus.append({
            "decoy_id": r["decoy_id"], "group": "AL-SYNTH" if c.synthetic else "AL-HUMAN", "locale": loc,
            "script": "latin", "file_id": r["file_id"], "file_name": r["file_name"], "internal_id": c.row["id"],
            "duration_seconds": c.dur,
            "gold_text": " ".join(x["word"] for x in c.w), "decoy_text": " ".join(x["word"] for x in r["decoy_segments"]),
            "gold_token_count": c.n, "decoy_token_count": len(r["decoy_segments"]),
            "gold_segments": c.w, "decoy_segments": r["decoy_segments"],
            "gold_whole_audio_tag": "synthetic_speech" if c.synthetic else "none", "decoy_whole_audio_tag": "none",
            "voice": {"name": voice["name"], "gender": voice["gender"], "type": "synthetic" if c.synthetic else "human",
                      "voice_id": c.row["voice_id"]},
            "injection_count": len(r["inj"]),
            "bands": sorted({x["band"] for x in r["inj"]}),
            "families": sorted({x["family"] for x in r["inj"]}, key=list(FAMILY).index),
            "total_weight": r3(sum(x["weight"] for x in r["inj"])),
            "injections": r["inj"],
            "status": "ACTIVE", "cat1b_flag": False, "cat2_fixes": [], "reinjected": False,
        })
    return corpus


# ------------------------------------------------------------------ package
CSV_COLS = ["decoy_id", "batch", "group", "status", "locale", "file_id", "file_name", "voice_type", "injection_id", "family",
            "score_group", "band", "weight", "detect_rule", "rule", "target", "plain_offset", "left_anchor", "right_anchor",
            "gold_start", "gold_end", "decoy_start", "decoy_end", "shift_ms", "fingerprint", "cat1b_flag",
            "cat2_fixes_applied", "reinjected", "text_changed", "gold_text", "decoy_text"]


def csv_rows(corpus):
    for e in corpus:
        for x in e["injections"]:
            m = x.get("meta", {})
            gold = m.get("gold") or {}
            dec = m.get("decoy") or m.get("decoy_next") or (m["pieces"][0] if "pieces" in m else {}) or {}
            if "parts" in m:
                target = " + ".join(p["word"] for p in m["parts"]) + " -> " + m["joined"]
            elif "pieces" in m:
                target = m["word"] + " -> " + " + ".join(p["word"] for p in m["pieces"])
            elif "from" in m:
                target = f"{m['from']} -> {m['to']}"
            elif x["family"] == "CB-WHOLE":
                target = f"{x['gold']} -> {x['decoy']}"
            else:
                target = m.get("word", "")
            yield {"decoy_id": e["decoy_id"], "batch": "B1", "group": e["group"], "status": e["status"], "locale": e["locale"],
                   "file_id": e["file_id"], "file_name": e["file_name"], "voice_type": e["voice"]["type"],
                   "injection_id": x["injection_id"], "family": x["family"], "score_group": FAMILY[x["family"]][0],
                   "band": x["band"], "weight": x["weight"], "detect_rule": m.get("detect") or x.get("detect"),
                   "rule": m.get("rule") or x.get("rule"), "target": target, "plain_offset": m.get("plain_offset", ""),
                   "left_anchor": m.get("left", ""), "right_anchor": m.get("right", ""),
                   "gold_start": gold.get("start", ""), "gold_end": gold.get("end", ""),
                   "decoy_start": dec.get("start", ""), "decoy_end": dec.get("end", ""), "shift_ms": m.get("shift_ms", ""),
                   "fingerprint": x["fingerprint"], "cat1b_flag": "FALSE", "cat2_fixes_applied": "", "reinjected": "FALSE",
                   "text_changed": "FALSE", "gold_text": e["gold_text"], "decoy_text": e["decoy_text"]}


def write_package(loc, corpus):
    build = HERE / "build" / loc
    pkg = build / "package"
    if pkg.exists():
        shutil.rmtree(pkg)
    (pkg / "audio").mkdir(parents=True)
    for e in corpus:
        shutil.copyfile(build / "wav" / f"{e['internal_id']}.wav", pkg / "audio" / e["file_name"])
    serve = sorted(corpus, key=lambda e: e["file_id"])                    # serve order unrelated to decoy_id or type
    prefill = {"fileMetadata": {"locale": loc, "workitemsCount": len(serve)},
               "items": [{"id": e["file_id"], "name": e["file_name"], "transcript": e["decoy_text"],
                          "source": {"sample_rate_hz": 16000, "duration_seconds": e["duration_seconds"],
                                     "words": e["decoy_segments"]}} for e in serve]}
    (pkg / f"alignment_prefill_{loc}.json").write_text(json.dumps(prefill, ensure_ascii=False, indent=2), encoding="utf-8")
    (pkg / "decoy_corpus.json").write_text(json.dumps(corpus, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, rows in (("decoy_corpus_ALL.csv", list(csv_rows(corpus))), ("decoy_corpus_CHANGED.csv", [])):
        with open(pkg / name, "w", newline="", encoding="utf-8-sig") as fh:
            wr = csv.DictWriter(fh, fieldnames=CSV_COLS)
            wr.writeheader(); wr.writerows(rows)
    (pkg / "decoy_change_manifest.json").write_text(json.dumps(
        {"cat2_fixed": [], "reinjected": [], "pulled": [], "flagged_cat1b": []}, indent=1), encoding="utf-8")
    shutil.copyfile(HERE / "alignmentDecoyScorer.js", pkg / "alignmentDecoyScorer.js")
    shutil.copyfile(HERE / "run_selftest.js", pkg / "run_selftest.js")
    pdf = HERE / loc / f"Forced_Alignment_Guidelines_{loc}.pdf"
    if pdf.exists():
        shutil.copyfile(pdf, pkg / pdf.name)
    return pkg


def selftest(pkg):
    node = shutil.which("node") or "/opt/node22/bin/node"
    res = subprocess.run([node, "run_selftest.js", "decoy_corpus.json"], cwd=pkg, capture_output=True, text=True)
    (pkg / "selftest_report.txt").write_text(res.stdout + res.stderr, encoding="utf-8")
    if res.returncode:
        raise SystemExit(f"self-test failed in {pkg}:\n{res.stdout}{res.stderr}")
    return json.loads(res.stdout.strip().splitlines()[-1])


def md5(p):
    return hashlib.md5(p.read_bytes()).hexdigest()


def main(locales):
    sys.path.insert(0, str(HERE))
    from package_docs import write_docs, write_xlsx                      # noqa: E402
    for loc in locales:
        corpus = build_locale(loc)
        pkg = write_package(loc, corpus)
        st = selftest(pkg)
        write_xlsx(pkg / "decoy_summary.xlsx", loc, corpus, FAMILY, GROUP_POINTS, BAND_FACTOR, CB_WEIGHT)
        write_docs(pkg, loc, corpus, st, md5(pkg / "alignmentDecoyScorer.js"), FAMILY, GROUP_POINTS, CB_WEIGHT, SEED)
        z = HERE / f"alignment_decoys_{loc}.zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(pkg.rglob("*")):
                if p.is_file():
                    info = zipfile.ZipInfo(f"alignment_decoys_{loc}/{p.relative_to(pkg).as_posix()}", (2026, 10, 27, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    zf.writestr(info, p.read_bytes())
        n = sum(e["injection_count"] for e in corpus)
        print(f"{loc}: {len(corpus)} files, {n} injections, self-test {st['decoy_missed']}/{st['scored']} MISSED on decoy, "
              f"{st['gold_caught']}/{st['scored']} CAUGHT on gold -> {z.name} ({z.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1:] or LOCALES)
