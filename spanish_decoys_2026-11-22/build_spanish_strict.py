#!/usr/bin/env python3
"""
Spanish (es_ES) decoys, strict build — align-decoys/v1 plants keyed on work_item_id, at most 2 mistakes per file.

Why "strict": annotators reported that some fixes were not recognised by the platform. A fix can only be recognised
when the correct answer is unambiguous, so every mistake here is planted only where the delivery itself proves it:

  * the delivery holds 2 independent blind passes per file (+ an adjudication on a third of them) and the machine
    pre-fill. A word is used only where ALL passes have the same word at the same index, with the same words two
    places either side (so the word number is right whichever pass the platform holds as its finalized alignment);
  * a timing mistake is planted only on an edge where the passes agree within 30 ms, and only on an edge that faces
    a real pause (a speech / silence transition), never on a boundary inside running speech;
  * every timing rule of the template is checked against every pass, with margins.

Mistakes (rule numbers = the template's instructions):
  boundary mismatch   move (3)     150-700 ms: minor 150-250, major 260-440, critical 450-700 (the platform's subtle /
                                   moderate / obvious bands). Four shapes, none moves a neighbour:
                                     start too early / end too late  -> the chip runs into the silence of a pause
                                     start too late / end too early  -> the chip cuts off part of the word, pause side
  missing word        delete (8)   a common, unaccented, unambiguous word that occurs once in the file, at least 0.25 s
                                   long, touching both neighbours: the hole it leaves is exactly its own span, so the
                                   chip an annotator adds back lands on the correct times. (delete, not remove: with
                                   remove the word stays in the transcript, and an annotator who adds a new word
                                   instead of timing the old one leaves the old one unfixed)
  hallucinated word   add (13)     an extra chip in a pause of at least 0.40 s (rule: 0.35 s) between two agreed words;
                                   text = a short function word of the same sentence (what the machine really
                                   hallucinates in this data), else a repeat of the word before; never in a
                                   pause where the machine pre-fill had a chip (there may be a noise there)
  accent error        replace (6)  accent dropped where the result is only a misspelling (también -> tambien), or a
                                   classic wrong accent added (fue -> fué); never the pairs told apart by grammar
                                   alone (que / qué, mas / más, el / él, si / sí, solo / sólo ...)
  wrong word          replace (6)  one letter changed inside a common word, giving another real word that sounds
                                   different (the client's "Incorrect Transcription" finding); the machine pre-fill and
                                   both passes agree on the correct word
Not used: remove, zero, overlap, absorb, join, split, add_noise, replace_unintelligible, set_flag, capitals,
punctuation, digits. Mistakes are at least 4 words apart (rule: 3) and never on or next to a tag / (( )) / cut-off word.
Exactly one mistake per file is "critical": true (the more obvious one).

Files are dropped when: no segments, overlapping speech, an overlap / zero-length chip in any pass, or no place
meets the conditions above. Clips too short for two mistakes 4 words apart get one.

Run    : pip install wordfreq ; python spanish_decoys_2026-11-22/build_spanish_strict.py [deliveries.zip|folder] [template.json]
Output : es_ES_decoy_plants.json, es_ES_decoy_review.csv, es_ES_dropped.csv (next to this script)
"""
import collections, csv, difflib, glob, json, pathlib, random, re, sys, tempfile, zipfile
from wordfreq import zipf_frequency

HERE = pathlib.Path(__file__).resolve().parent
SEED = 20261122
LANG = "es"                # wordfreq language; the tables below are the Spanish ones (build_portuguese_strict.py swaps them)
PLAIN = re.compile(r"[a-zñáéíóúü]+")
TARGET = re.compile(r"[a-zñ]{4,}")          # a word that may be deleted / swapped: plain letters, no accent mark
LETTERS = "abcdefgijlmnñoprstuv"            # letters a wrong word may get (none that only change the spelling)
FILLERS = set("eh em ehm mmm mm m ah oh mjm ajá aja hmm hm uh um uf uy ay bah ey ejem".split())
FUNC = "y de a en que la el los las un una con por para del se lo es no".split()
AGREE_EDGE = 0.03          # passes must agree on a moved edge within this (s)
PAUSE_MARGIN = 0.06        # a chip moved into a pause stays this far from the next chip (s)
NOT_TOUCHING = 0.10        # an edge with at least this gap has no touching neighbour (s)
TOUCHING = 0.02            # a deleted word's neighbours are at most this far (s)
MIN_SPACING = 4            # words between two mistakes (rule 17 asks for 3)
MIN_ADD_PAUSE = 0.40       # rule 13 asks for 0.35
BANDS = [("minor", 150, 250), ("major", 260, 440), ("critical", 450, 700)]
OTHER_SHARE = {"MISS": 0.40, "HALL": 0.22, "ACC": 0.26, "WORD": 0.12}     # of the mistakes that are not boundary ones
NAMES = {"BND": "boundary mismatch", "MISS": "missing word", "HALL": "hallucinated word", "ACC": "accent error",
         "WORD": "wrong word"}
OBVIOUS = {"MISS": 5, "HALL": 4, "WORD": 2, "ACC": 1}            # BND: 3 critical band, 2.5 major, 0.5 minor

# accents told apart by grammar only (same sound): never used
DIACRITIC = set("""mas más si sí se sé te té de dé el él tu tú mi mí que qué como cómo cuando cuándo donde dónde adonde adónde
quien quién quienes quiénes cual cuál cuales cuáles cuanto cuánto cuanta cuánta cuantos cuántos cuantas cuántas aun aún
solo sólo este éste esta ésta estos éstos estas éstas ese ése esa ésa esos ésos esas ésas aquel aquél aquella aquélla
porque porqué o ó""".split())
ADDED_ACCENT = {"fue": "fué", "fui": "fuí", "dio": "dió", "vio": "vió", "ti": "tí", "esto": "ésto", "eso": "éso",
                "joven": "jóven", "examen": "exámen", "imagen": "imágen", "origen": "orígen", "volumen": "volúmen",
                "resumen": "resúmen", "margen": "márgen", "orden": "órden", "feliz": "felíz", "incluido": "incluído",
                "construido": "construído", "ruido": "ruído"}
NUMBERS = set("""cero uno una dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince veinte treinta
cuarenta cincuenta sesenta setenta ochenta noventa cien ciento mil millón millones primero primera segundo segunda""".split())
STRIP = str.maketrans("áéíóú", "aeiou")
ACCENT_MARKS = "áéíóú"                      # accent marks an accent error may drop
ACCENT_MIN_LEN = 4                          # shortest word an accent is dropped from
ACCENT_GAP = 0.75                           # how much rarer (zipf) the bare form must be: then it is only a misspelling
ACCENT_HOW = "accent dropped"               # how the review sheet names it
VOWEL_SWAPS = True                          # a wrong word may change a vowel (German: no — finden / fanden is one verb)
EXTRA_TARGET_CHECK = None                   # language hook: False for a word that must not be deleted / swapped
HOMOPHONE_ZIPF = 3.8                        # a same-sounding spelling this common is another word (French: 3.0)
MISS_RISK = None                            # language hook (F, k) -> True when the word at k could be spelled another way
WORD_RISK = None                            # language hook (word) -> True when a swapped word could be spelled another way
REPEAT_PENALTY = 0.0                        # lowers a text mistake's rank each time its word was already used
USED = collections.Counter()
PAIR_AVOID = set()                          # (word, replacement) pairs a wrong-word mistake never uses
UNIQUE_IN_EVERY_PASS = False                # a deleted word is said once in every pass (off: once in the reference
                                            # pass, which reproduces the delivered Spanish file; 1 of its 218 deletes differs)
ACCENTED = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú"}      # letter -> its accented forms
FINAL_ACCENT_OK = set("aquí allí allá ahí así café perú josé bogotá panamá sofá menú".split())
# never deleted / swapped: proper names and brands (spelling and capitals vary), words with two accepted spellings,
# and words that sound like another word or like two words (every candidate word of this delivery was read through)
AVOID = set("""alberto alejandro alfredo argentina arturo barcelona burgos carlos castro china españa europa facebook
florida francisco gabriel google guatemala guerrero gustavo jack james javier jorge kevin lima luis madrid maldonado
manuel mario marta mauricio miranda molina monterrey morena oaxaca pablo pedro quito rodrigo rosario rusia salvador
santiago santos sergio sevilla texas veracruz vicente walter whatsapp youtube zaragoza venezuela julio cruz rojas reyes
center online plus campus extra juan com benito esteban peter grecia polonia macho
haber hacia sino aparte enfrente alrededor periodo vaya haya halla valla hecho hechos echo tuvo tubo hola ola hay casa
casas caza cien ciento cientos siento sede cede bello vello grabar gravar hora horas vez ves voz vos has haz rosa mate""".split())


def secs(x):
    h, m, s = x.split(":")
    return round(int(h) * 3600 + int(m) * 60 + float(s), 3)


def zipf(w):
    return zipf_frequency(w, LANG)


def drop_accent(w):
    """The word with its accent mark dropped (Spanish words carry one at most)."""
    return w.translate(STRIP)


def special(w):
    return not PLAIN.fullmatch(w)


def sound_alikes(w):
    """Spellings that sound the same (b/v, h, ll/y, s/z/c, g/j): another real word among them = a homophone risk."""
    out = set()
    for a, b in (("b", "v"), ("v", "b"), ("ll", "y"), ("y", "ll"), ("s", "z"), ("z", "s"), ("ce", "se"), ("ci", "si"),
                 ("se", "ce"), ("si", "ci"), ("ze", "ce"), ("zi", "ci"), ("ge", "je"), ("gi", "ji"), ("je", "ge"),
                 ("ji", "gi"), ("x", "s"), ("s", "x")):
        for m in re.finditer(a, w):
            out.add(w[:m.start()] + b + w[m.end():])
    out.add(w[1:] if w.startswith("h") else "h" + w)
    out.discard(w)
    return out


def homophone_risk(w):
    return any(zipf(v) >= HOMOPHONE_ZIPF for v in sound_alikes(w))


def load(src):
    if str(src).endswith(".zip"):
        tmp = tempfile.mkdtemp()
        zipfile.ZipFile(src).extractall(tmp)
        src = tmp
    for f in sorted(glob.glob(str(pathlib.Path(src) / "*.json"))):
        doc = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
        batch = pathlib.Path(f).name[:8]
        for w in doc["workitems"]:
            runs = sorted([r for k, v in w.items() if isinstance(v, list) for r in v],
                          key=lambda r: r["metadata"]["labelledTimestamp"])
            yield {"wid": w["workItemId"], "batch": batch, "task": runs[-1]["metadata"]["taskId"],
                   "runs": [(r["metadata"]["operationType"], r["data"]["taskAnswers"][0]) for r in runs],
                   "machine": [(s["refTranscript"], secs(s["startTime"]), secs(s["endTime"]))
                               for s in (w.get("inputData") or {}).get("segments", [])]}


def to_words(ans):
    return [{"w": s["final_transcription"], "s": secs(s["final_startTime"]), "e": secs(s["final_endTime"])}
            for s in ans["segments"]]


class File:
    """One work item: every pass of its alignment, and what all passes agree on."""

    def __init__(self, item):
        self.item = item
        self.V = [to_words(a) for _, a in item["runs"]]
        adj = [to_words(a) for o, a in item["runs"] if o == "ADJUDICATION"]
        self.ref = adj[-1] if adj else self.V[-1]
        self.n = len(self.ref)
        self.words = [x["w"] for x in self.ref]
        self.same_len = all(len(v) == self.n for v in self.V)
        self.count = collections.Counter(self.words)
        self.machine_ok = {}                                    # word index -> the machine pre-fill's (start, end)
        sm = difflib.SequenceMatcher(None, [m[0] for m in item["machine"]], self.words, autojunk=False)
        for op, a1, a2, b1, b2 in sm.get_opcodes():
            if op == "equal":
                for j in range(b2 - b1):
                    self.machine_ok[b1 + j] = item["machine"][a1 + j][1:]

    def reason_to_drop(self):
        answers = [a for _, a in self.item["runs"]]
        if not all(self.V):
            return "no segments (entirely synthetic / discarded)"
        if any(a.get("audio_synthetic") for a in answers):
            return "marked synthetic in one pass"
        if any(a.get("overlapping_speech") for a in answers):
            return "overlapping speech"
        for v in self.V:
            if any(x["e"] <= x["s"] for x in v) or any(a["e"] > b["s"] + 0.001 for a, b in zip(v, v[1:])):
                return "an overlap or zero-length chip in the delivered alignment"
        return None

    def agree(self, k):
        return all(len(v) > k and v[k]["w"] == self.ref[k]["w"] for v in self.V)

    def stable(self, k):
        """Same word at index k and two places either side in every pass (and the same end, near the end)."""
        if not 0 <= k < self.n:
            return False
        lo, hi = max(0, k - 2), min(self.n - 1, k + 2)
        if not all(self.agree(j) for j in range(lo, hi + 1)):
            return False
        return self.same_len or hi < self.n - 1

    def lo(self, f):
        return min(f(v) for v in self.V)

    def hi(self, f):
        return max(f(v) for v in self.V)

    def spread(self, k, edge):
        return self.hi(lambda v: v[k][edge]) - self.lo(lambda v: v[k][edge])

    def dur(self, k):
        return self.lo(lambda v: v[k]["e"] - v[k]["s"])

    def gap_before(self, k, worst=min):
        f = lambda v: v[k]["s"] - (v[k - 1]["e"] if k > 0 else 0.0)
        return self.lo(f) if worst is min else self.hi(f)

    def gap_after(self, k, worst=min):
        if k >= self.n - 1:
            return None
        f = lambda v: v[k + 1]["s"] - v[k]["e"]
        return self.lo(f) if worst is min else self.hi(f)

    def confirmed(self, k, edge):
        """Every pass moved this edge away from the machine's value (30 ms or more) and they still agree."""
        if k not in self.machine_ok:
            return False
        m = self.machine_ok[k][0 if edge == "s" else 1]
        return all(abs(v[k][edge] - m) >= 0.03 for v in self.V)

    def clean(self, k):
        """A plain word whose neighbours are plain words too (no tag, (( )), cut-off word, letter, digit)."""
        return all(not special(self.words[j]) for j in (k - 1, k, k + 1) if 0 <= j < self.n)


# ------------------------------------------------------------------ candidates
def boundary_candidates(F):
    out = []
    for k in range(F.n):
        w = F.words[k]
        if not F.stable(k) or not F.clean(k) or w in FILLERS or len(w) < 2:
            continue
        d = F.dur(k)
        if d < 0.18:
            continue
        gb, ga = F.gap_before(k), F.gap_after(k)
        keep = max(0.12, 0.4 * d)                               # what is left of a word that is cut
        shapes = []
        if F.spread(k, "s") <= AGREE_EDGE:
            shapes.append(("start", -1, gb - PAUSE_MARGIN, "starts too early, in the silence before the word"))
            if k == 0 or gb >= NOT_TOUCHING:
                shapes.append(("start", +1, d - keep, "starts too late, the beginning of the word is cut off"))
        if F.spread(k, "e") <= AGREE_EDGE:
            if ga is not None:
                shapes.append(("end", +1, ga - PAUSE_MARGIN, "ends too late, in the silence after the word"))
            if ga is None or ga >= NOT_TOUCHING:
                shapes.append(("end", -1, d - keep, "ends too early, the end of the word is cut off"))
        for edge, sign, room, what in shapes:
            room = int(room * 100 + 1e-6) * 10                  # ms, rounded down to 10
            if room < 150:
                continue
            e = "s" if edge == "start" else "e"
            score = 3.0 - 50 * F.spread(k, e) + min(d, 0.5) + (0.5 if F.confirmed(k, e) else 0)
            out.append({"type": "BND", "k": k, "aff": {k}, "edge": edge, "sign": sign, "room": min(room, 700),
                        "what": what, "score": score, "agree_ms": round(F.spread(k, e) * 1000)})
    return out


def missing_candidates(F):
    out = []
    for k in range(1, F.n - 1):
        w = F.words[k]
        if not F.stable(k) or not F.clean(k) or w in FILLERS or w in NUMBERS or w in AVOID or F.count[w] != 1:
            continue
        if UNIQUE_IN_EVERY_PASS and any(sum(x["w"] == w for x in v) != 1 for v in F.V):
            continue                                            # said once in every pass, not only in the reference
        if not TARGET.fullmatch(w) or zipf(w) < 4.0 or w in DIACRITIC or accent_twin(w) or foreign(w):
            continue
        if MISS_RISK(F, k) if MISS_RISK else homophone_risk(w):
            continue
        if EXTRA_TARGET_CHECK and not EXTRA_TARGET_CHECK(w):
            continue
        if k not in F.machine_ok or any(x in FILLERS or x in AVOID or zipf(x) < 3.3 for x in (F.words[k - 1], F.words[k + 1])):
            continue                                            # ordinary words either side (no names, fillers, rare terms)
        d = F.dur(k)
        if d < 0.25 or F.hi(lambda v: v[k]["e"] - v[k]["s"]) > 1.0:
            continue
        if F.gap_before(k, max) > TOUCHING or F.gap_after(k, max) > TOUCHING:
            continue                                            # both neighbours touch it: the hole is exactly its span
        if F.spread(k, "s") > 0.04 or F.spread(k, "e") > 0.04:
            continue
        pinned, bonus = "both neighbours", 1.0
        score = 2.5 + bonus - 25 * (F.spread(k, "s") + F.spread(k, "e")) + min(d, 0.5) + zipf(w) / 10
        out.append({"type": "MISS", "k": k, "aff": {k}, "score": score, "pinned": pinned,
                    "agree_ms": round(max(F.spread(k, "s"), F.spread(k, "e")) * 1000)})
    return out


def hallucination_candidates(F):
    out = []
    for k in range(F.n - 1):
        a, b = F.words[k], F.words[k + 1]
        if not (F.stable(k) and F.stable(k + 1) and F.clean(k) and F.clean(k + 1)) or a in FILLERS or b in FILLERS:
            continue
        pause = F.gap_after(k)
        if pause < MIN_ADD_PAUSE or F.spread(k, "e") > 0.05 or F.spread(k + 1, "s") > 0.05:
            continue
        lo, hi = F.hi(lambda v: v[k]["e"]), F.lo(lambda v: v[k + 1]["s"])
        if any(lo < (ms + me) / 2 < hi for _, ms, me in F.item["machine"]):
            continue                                            # the machine put a chip in this pause: maybe a noise
        near = [F.words[j] for j in range(max(0, k - 6), min(F.n, k + 8))]
        texts = [t for t in FUNC if t in near and t not in (a, b)]      # what the machine really hallucinates here
        if not texts and (a in AVOID or a in NUMBERS or zipf(a) < 4.0):
            continue                                            # the fallback repeats the word before: ordinary words only
        score = 3.0 - 10 * (F.spread(k, "e") + F.spread(k + 1, "s")) + min(pause, 1.0) * 0.5
        out.append({"type": "HALL", "k": k, "aff": {k, k + 1}, "texts": texts, "pause": pause, "score": score,
                    "agree_ms": round(max(F.spread(k, "e"), F.spread(k + 1, "s")) * 1000)})
    return out


def accent_candidates(F):
    out = []
    for k in range(F.n):
        w = F.words[k]
        if not F.stable(k) or not F.clean(k) or w in DIACRITIC:
            continue
        if any(ch in ACCENT_MARKS for ch in w) and len(w) >= ACCENT_MIN_LEN:
            t = drop_accent(w)
            if not t or t in DIACRITIC or zipf(w) < 4.3 or zipf(w) - zipf(t) < ACCENT_GAP:
                continue                                        # the bare form must be only a misspelling
            if w[-1] in ACCENT_MARKS and w not in FINAL_ACCENT_OK:
                continue                                        # habló / hablo, estará / estara: both are verb forms
            out.append({"type": "ACC", "k": k, "aff": {k}, "text": t, "how": ACCENT_HOW, "score": 2.5 + zipf(w) / 10})
        elif w in ADDED_ACCENT:
            out.append({"type": "ACC", "k": k, "aff": {k}, "text": ADDED_ACCENT[w], "how": "wrong accent added",
                        "score": 2.0 + zipf(w) / 10})
    return out


def accent_twin(w):
    """True when the same letters with one accent are a common word too (quedo / quedó, trabajo / trabajó)."""
    return any(zipf(w[:i] + a + w[i + 1:]) >= 4.0 for i, ch in enumerate(w) for a in ACCENTED.get(ch, ""))


def foreign(t):
    return zipf_frequency(t, "en") - zipf(t) >= 1.0


def misspelling(t):
    """True when a commoner word is the same letters with an accent (habia < había): not a real replacement."""
    return any(zipf(t[:i] + a + t[i + 1:]) > zipf(t) for i, ch in enumerate(t) for a in ACCENTED.get(ch, ""))


def word_candidates(F):
    out = []
    for k in range(F.n):
        w = F.words[k]
        if not F.stable(k) or not F.clean(k) or k not in F.machine_ok or w in NUMBERS or w in DIACRITIC or w in AVOID:
            continue
        risk = WORD_RISK or homophone_risk
        if not TARGET.fullmatch(w) or zipf(w) < (4.3 if len(w) >= 5 else 4.8) or risk(w) or F.dur(k) < 0.25:
            continue
        if accent_twin(w) or foreign(w) or (EXTRA_TARGET_CHECK and not EXTRA_TARGET_CHECK(w)):
            continue
        alikes = sound_alikes(w)
        best = None
        for i in range(len(w) - 2):                             # never the last two letters (gender / number / mood)
            for c in LETTERS:
                t = w[:i] + c + w[i + 1:]
                if t == w or t in alikes or t in F.count or t in DIACRITIC or t in NUMBERS or t in AVOID or (w, t) in PAIR_AVOID:
                    continue
                if (w[i] in "aeiou") != (c in "aeiou") or w[i + 1:] == "mos" or (not VOWEL_SWAPS and w[i] in "aeiou"):
                    continue                                    # vowel for vowel, consonant for consonant; not -amos / -emos
                z = zipf(t)
                if z >= 4.0 and not misspelling(t) and not risk(t) and not foreign(t) and (best is None or z > best[0]):
                    best = (z, t)
        if best:
            out.append({"type": "WORD", "k": k, "aff": {k}, "text": best[1], "how": "one letter changed",
                        "score": 2.0 + min(F.dur(k), 0.5) + zipf(w) / 10})
    return out


GENERATORS = {"BND": boundary_candidates, "MISS": missing_candidates, "HALL": hallucination_candidates,
              "ACC": accent_candidates, "WORD": word_candidates}


# ------------------------------------------------------------------ planning
def apart(a, b, spacing):
    return all(abs(i - j) >= spacing for i in a["aff"] for j in b["aff"])


def best_pair(A, B, spacing):
    best = None
    for a in sorted(A, key=lambda c: -c["rank"])[:20]:
        for b in sorted(B, key=lambda c: -c["rank"])[:20]:
            if a is b or not apart(a, b, spacing):
                continue
            dist = min(abs(i - j) for i in a["aff"] for j in b["aff"])
            value = a["rank"] + b["rank"] + min(dist, 12) * 0.03
            if best is None or value > best[0]:
                best = (value, [a, b])
    return best and best[1]


def choose(F, rng, have, bands, shapes):
    """Two places for this file (one where two cannot be 3 words apart): a boundary mistake plus the other kind that
    is furthest below its share; two different kinds before two of a kind."""
    cands = {t: g(F) for t, g in GENERATORS.items()}
    for cs in cands.values():
        for c in cs:
            c["rank"] = c["score"] + rng.random() * 0.6 - REPEAT_PENALTY * USED[(c["type"], F.words[c["k"]])]
    tb, ts = sum(bands.values()) + 1, sum(shapes.values()) + 1
    want_band = min(BANDS, key=lambda b: bands[b[0]] / tb)
    for c in cands["BND"]:                                      # favour the band and the shape that are behind
        c["rank"] += (0.8 if c["room"] >= want_band[1] else 0) + 4.0 * (0.25 - shapes[(c["edge"], c["sign"])] / ts)
    others = sum(have[t] for t in OTHER_SHARE) + 1
    need = lambda t: OTHER_SHARE[t] - have[t] / others
    rest = sorted((t for t in OTHER_SHARE if cands[t]), key=lambda t: -need(t))
    for spacing in (MIN_SPACING, 3):                            # rule 17: at least 3 words apart
        orders = [("BND", t) for t in rest] + [(a, b) for i, a in enumerate(rest) for b in rest[i + 1:]] \
            + [("BND", "BND")] + [(t, t) for t in rest]
        for t1, t2 in orders:
            pair = best_pair(cands[t1], cands[t2], spacing)
            if pair:
                return pair
    singles = [c for cs in cands.values() for c in cs]
    if not singles:
        return []
    return [max(singles, key=lambda c: c["rank"] + {"MISS": 3, "HALL": 3, "BND": 2, "WORD": 1, "ACC": 0}[c["type"]])]


def finish(F, c, rng, bands):
    """Candidate -> plant (+ a line for the review sheet)."""
    k, w = c["k"], F.words[c["k"]]
    ref = F.ref[k]
    row = {"type": NAMES[c["type"]], "word_index": k, "word": w, "correct_start": ref["s"], "correct_end": ref["e"]}
    if c["type"] == "BND":
        tb = sum(bands.values()) + 1
        ok = [b for b in BANDS if c["room"] >= b[1]]
        if c.get("alone") and len(ok) > 1:
            ok = ok[1:]                                         # a file's only mistake is its must-catch: not minor
        name, lo, hi = min(ok, key=lambda b: (bands[b[0]] / tb, rng.random()))
        ms = rng.randrange(lo, min(hi, c["room"]) + 1, 10)
        bands[name] += 1
        shift = c["sign"] * ms
        plant = {"action": "move", "word": k, "edge": c["edge"], "shift_ms": shift}
        served = dict(ref); served["s" if c["edge"] == "start" else "e"] = round(served["s" if c["edge"] == "start" else "e"] + shift / 1000, 3)
        note = f"boundary mismatch · {name} · '{w}' {c['what']} ({abs(shift)} ms {'later' if shift > 0 else 'earlier'})"
        row.update(category=name, change=f"{c['edge']} moved {abs(shift)} ms {'later' if shift > 0 else 'earlier'}: {c['what']}",
                   served=f"{served['s']}-{served['e']}", fix=f"move the {c['edge']} back to {ref['s' if c['edge'] == 'start' else 'e']} s",
                   obvious={"critical": 3, "major": 2.5, "minor": 0.5}[name])
    elif c["type"] == "MISS":
        plant = {"action": "delete", "word": k}
        note = f"missing word · '{w}' is gone from the transcript and has no chip (spoken between '{F.words[k - 1]}' and '{F.words[k + 1]}'; hole pinned by {c['pinned']})"
        row.update(category="", change="word deleted (text and chip)", served="(no chip)",
                   fix=f"add '{w}' in the hole between '{F.words[k - 1]}' and '{F.words[k + 1]}' ({ref['s']}-{ref['e']} s)",
                   obvious=OBVIOUS["MISS"])
    elif c["type"] == "HALL":
        c["text"], c["how"] = (rng.choice(c["texts"]), "a short word of the same sentence") if c["texts"] else \
            (w, "a repeat of the word before")
        plant = {"action": "add", "after_word": k, "text": c["text"]}
        nxt = F.ref[k + 1]
        note = f"hallucinated word · extra '{c['text']}' in the {c['pause']:.2f} s pause between '{w}' and '{F.words[k + 1]}' ({c['how']})"
        row.update(type=NAMES["HALL"], word=c["text"], correct_start="", correct_end="", category="",
                   change=f"extra chip '{c['text']}' in the pause after '{w}' ({ref['e']}-{nxt['s']} s)",
                   served="inside that pause", fix="delete the extra chip", obvious=OBVIOUS["HALL"])
    else:
        plant = {"action": "replace", "word": k, "text": c["text"]}
        label = "accent error" if c["type"] == "ACC" else "wrong word"
        note = f"{label} · {c['how']} · '{w}' is written '{c['text']}'"
        row.update(category=c["how"], change=f"'{w}' written '{c['text']}'", served=f"{ref['s']}-{ref['e']}",
                   fix=f"type '{w}'", obvious=OBVIOUS[c["type"]])
    return plant, note, row


def main(src, template, out_dir=HERE, prefix="es_ES"):
    out_dir = pathlib.Path(out_dir)
    tpl = json.loads(pathlib.Path(template).read_text(encoding="utf-8"))
    have, bands, shapes = collections.Counter(), collections.Counter(), collections.Counter()
    decoys, review, dropped = [], [], []
    for item in load(src):
        F = File(item)
        why = F.reason_to_drop()
        picks = [] if why else choose(F, random.Random(f"{SEED}-{item['wid']}"), have, bands, shapes)
        if not picks:
            dropped.append({"work_item_id": item["wid"], "file_name": item["task"], "batch": item["batch"],
                            "words": len(F.ref), "reason": why or "no place where every pass agrees on word and timing"})
            continue
        rng = random.Random(f"{SEED}-{item['wid']}-shift")
        built = []
        for c in sorted(picks, key=lambda c: c["k"]):
            c["alone"] = len(picks) == 1
            plant, note, row = finish(F, c, rng, bands)
            row["agree"] = c.get("agree_ms", "")
            have[c["type"]] += 1
            USED[(c["type"], F.words[c["k"]])] += 1
            if c["type"] == "BND":
                shapes[(c["edge"], c["sign"])] += 1
            built.append((plant, note, row))
        top = max(range(len(built)), key=lambda i: built[i][2]["obvious"])
        plants = []
        for i, (plant, note, row) in enumerate(built):
            if i == top:
                plant["critical"] = True
            plant["note"] = note
            plants.append(plant)
            review.append({"file_name": item["task"], "work_item_id": item["wid"], "batch": item["batch"],
                           "mistake": i + 1, "must_catch": "yes" if i == top else "", "type": row["type"],
                           "category": row["category"], "word_index": row["word_index"], "word": row["word"],
                           "correct_start_s": row["correct_start"], "correct_end_s": row["correct_end"],
                           "what_was_changed": row["change"], "served_as": row["served"], "how_to_fix": row["fix"],
                           "annotator_passes": len(F.V), "passes_agree_within_ms": row["agree"],
                           "action": plant["action"]})
        decoys.append({"decoy_ref": item["task"], "work_item_id": item["wid"], "file_name": item["task"], "plants": plants})
    out = {"format": tpl["format"], "instructions": tpl["instructions"], "decoys": decoys}
    (out_dir / f"{prefix}_decoy_plants.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, rows in ((f"{prefix}_decoy_review.csv", review), (f"{prefix}_dropped.csv", dropped)):
        with open(out_dir / name, "w", newline="", encoding="utf-8-sig") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(rows[0])); wr.writeheader(); wr.writerows(rows)
    per = collections.Counter(len(d["plants"]) for d in decoys)
    print(f"{len(decoys) + len(dropped)} work items -> {len(decoys)} decoys, {len(dropped)} dropped | "
          f"{sum(have.values())} mistakes | per file {dict(sorted(per.items()))}")
    print("kinds   ", {NAMES[t]: have[t] for t in NAMES})
    print("bands   ", dict(bands))
    print("shapes  ", {f"{e} {'later' if s > 0 else 'earlier'}": n for (e, s), n in sorted(shapes.items())})
    print("dropped ", dict(collections.Counter(d["reason"] for d in dropped)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else HERE / "deliveries",
         sys.argv[2] if len(sys.argv) > 2 else HERE / "alignment-decoys-template.json")
