#!/usr/bin/env python3
"""
French (fr_FR) decoys, strict build — align-decoys/v1 plants keyed on work_item_id, at most 2 mistakes per file.

Same method, rules and checks as spanish_decoys_2026-11-22/build_spanish_strict.py (read its header): a mistake is
planted only where every annotator pass of the delivery has the same word at the same index and agrees on its timing;
boundary mistakes only on an edge that faces a pause (150-700 ms, no neighbour moved); a missing word is `delete`d
only when both neighbours touch it; a hallucinated word sits in a pause of at least 0.40 s; text mistakes change
exactly one letter. This file only swaps in the French language tables:

  words          an elided form is one word (l'homme, c'est, qu'il — fr_FR guideline): it can carry a boundary or an
                 accent mistake like any other word, and is never split.
  accent error   on a word with exactly one accent mark: the mark dropped (très -> tres, était -> etait, l'état ->
                 l'etat — what the machine pre-fill really does in this delivery) or è written é (problème ->
                 probléme). Only where the result is no word of its own: never marché / marche, parlé / parle,
                 près / prés, and never the pairs only grammar tells apart (a / à, ou / où, la / là, sur / sûr,
                 du / dû). Never î or û: since the 1990 spelling reform boite, connaitre, cout are accepted too.
  missing word,  only words with one possible spelling for their sound. French endings are mostly silent
  wrong word     (mange / mangent, allé / allée, petit / petits), so a word is used only when no same-sounding spelling
                 exists as a word: in practice adverbs and other invariable words (vraiment, toujours, beaucoup).
                 A wrong word changes one consonant, never a vowel.
  never deleted / swapped: names, function words, number words, words with a colloquial twin (bien / ben, cela / ça).

Run    : pip install wordfreq ; python french_decoys_2026-11-23/build_french_strict.py [deliveries.zip|folder] [template] [prefix]
Output : fr_FR_decoy_plants.json, fr_FR_decoy_review.csv, fr_FR_dropped.csv (next to this script)
"""
import pathlib, re, sys, zlib

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "spanish_decoys_2026-11-22"))
import build_spanish_strict as eng                                     # noqa: E402

L = "a-zàâäçéèêëîïôöùûüÿœæ"
DROP = {"é": "e", "è": "e", "ê": "e", "ë": "e", "à": "a", "â": "a", "ô": "o", "ç": "c", "ï": "i"}   # never î û ù ü
ANY_ACCENT = "éèêëàâäôöçïîûùüÿœæ"


FINAL_E_OK = set("café cafés clé clés degré degrés malgré moitié".split())


class Everything:
    def __contains__(self, w):
        return True


def drop_accent(w):
    """The word with its one accent mark dropped, or è written é; None when the result could be read as a word."""
    marks = [i for i, ch in enumerate(w) if ch in ANY_ACCENT]
    if len(marks) != 1 or w[marks[0]] not in DROP:
        return None
    i = marks[0]
    a = max(w.rfind("'", 0, i), w.rfind("’", 0, i)) + 1              # the part of an elided form that has the accent
    b = min([x for x in (w.find("'", i), w.find("’", i)) if x >= 0] or [len(w)])
    part, j = w[a:b], i - a
    if len(part) < 4 or part in eng.DIACRITIC or eng.zipf(part) < 4.3:
        return None
    if re.search("és?$", part) and not re.search("tés?$", part) and part not in FINAL_E_OK:
        return None                                            # privé / prive, sacré / sacre, utilisés / utilises
    dropped = part[:j] + DROP[part[j]] + part[j + 1:]
    swapped = part[:j] + "é" + part[j + 1:] if part[j] == "è" else None
    need = 0.4 if j == 0 and part[0] == "é" else 0.75                # Etat, Ecole: capitals are often left bare
    options = []
    if dropped not in eng.DIACRITIC and eng.zipf(part) - eng.zipf(dropped) >= need:
        options.append(dropped)
    if swapped and swapped not in eng.DIACRITIC and eng.zipf(part) - eng.zipf(swapped) >= 2.0:
        options.append(swapped)
    if not options:
        return None
    pick = options[zlib.crc32(part.encode()) % 3 == 0 and len(options) - 1 or 0]    # a third of the è words: è -> é
    return w[:a] + pick + w[b:]


SILENT = ("", "s", "e", "es", "x", "t", "d", "ts", "ds", "nt", "ns", "ent", "z", "p", "ps", "g")     # endings not heard
SINGULAR_BEFORE = set("le la un une ce cette mon ma ton ta son sa notre votre leur du au chaque".split())


def miss_risk(F, k):
    """True when the word at k has another spelling with the same sound. One case is safe: a noun whose only
    same-sounding spelling is its own plural, right after a singular determiner (la maison: never maisons)."""
    w = F.words[k]
    twins = {v for v in sound_alikes(w) if eng.zipf(v) >= eng.HOMOPHONE_ZIPF}
    if not twins:
        return False
    return not (twins <= {w + "s", w + "x"} and k > 0 and F.words[k - 1] in SINGULAR_BEFORE)


def endings(w):
    """The word with each other silent ending (maison / maisons, parle / parles / parlent)."""
    out = set()
    for a in SILENT:
        if w.endswith(a) and len(w) - len(a) >= 2:
            out.update(w[:len(w) - len(a)] + b for b in SILENT)
    out.discard(w)
    return out


def word_risk(w):
    """For a swapped word the wrong word shows the ending, so same-sounding endings are no risk; any other
    same-sounding spelling is."""
    twins = {v for v in sound_alikes(w) if eng.zipf(v) >= eng.HOMOPHONE_ZIPF}
    return not twins <= endings(w)


def sound_alikes(w):
    """Other spellings that sound the same in French: silent endings (s, e, es, x, t, d, ent), verb endings
    (er / é / ez / ais / ait), nasal vowels (an / en, in / ain / ein, on / om), o sounds (o / au / eau),
    c / s / ss / ç, ph / f, double consonants, mute h, y / i, g / j, qu / c / k."""
    out = set()
    for a in SILENT:                                           # revient / reviens, voix / voie / voit, auront / aurons
        if w.endswith(a) and len(w) - len(a) >= 2:
            stem = w[:len(w) - len(a)]
            out.update(stem + b for b in SILENT)
    verb = ["er", "é", "ée", "és", "ées", "ez", "ai", "ais", "ait", "aient", "et", "è", "ê"]
    for a in verb:
        if w.endswith(a):
            out.update(w[:-len(a)] + b for b in verb)
    for a, b in (("i", "is"), ("i", "it"), ("i", "ie"), ("i", "ies"), ("u", "us"), ("u", "ut"), ("u", "ue"), ("u", "ues"),
                 ("is", "it"), ("us", "ut"), ("it", "is"), ("ut", "us"), ("ie", "i"), ("ue", "u"), ("al", "ale"),
                 ("el", "elle"), ("el", "els"), ("elle", "el"), ("eur", "eure"), ("eur", "eurs")):
        if w.endswith(a):
            out.add(w[:-len(a)] + b)
    pairs = [("an", "en"), ("en", "an"), ("am", "em"), ("em", "am"), ("in", "ain"), ("ain", "in"), ("ein", "in"),
             ("in", "ein"), ("ain", "ein"), ("ein", "ain"), ("on", "om"), ("om", "on"), ("eau", "au"), ("au", "eau"),
             ("au", "o"), ("o", "au"), ("eau", "o"), ("o", "eau"), ("o", "ô"), ("ce", "se"), ("ci", "si"), ("se", "ce"),
             ("si", "ci"), ("sc", "c"), ("sc", "s"), ("ss", "c"), ("ç", "ss"), ("ss", "ç"), ("ph", "f"), ("f", "ph"),
             ("y", "i"), ("i", "y"), ("ge", "je"), ("gi", "ji"), ("je", "ge"), ("qu", "c"), ("qu", "k"), ("c", "qu"),
             ("k", "qu"), ("k", "c"), ("c", "k"), ("ai", "è"), ("ai", "ê"), ("ai", "e"), ("ei", "ai"), ("ai", "ei"),
             ("e", "é"), ("e", "è"), ("e", "ê"), ("a", "â"), ("a", "à"), ("u", "û"), ("i", "î"), ("oe", "œ")]
    for c in "lnmtrpfcsdgb":
        pairs += [(c + c, c), (f"(?<!{c}){c}(?!{c})", c + c)]
    for a, b in pairs:
        for m in re.finditer(a, w):
            out.add(w[:m.start()] + b + w[m.end():])
    out.add(w[1:] if w.startswith("h") else "h" + w)
    out.discard(w)
    return out


# grammar words and discourse markers: never deleted or swapped (too little weight in the sentence, or optional in speech)
FUNCTION = set("""avec dans pour sans sous chez vers entre comme mais donc alors aussi cette cela ceci elle elles nous vous
leur leurs notre votre tout tous toute toutes quel quelle quels quelles plus moins bien avoir sont suis sommes avait
fait faire peut veut doit vais vont allez quand parce puis encore autre autres chaque plusieurs quelque quelques aucun
aucune celui celle ceux dont quoi petit petite enfin voici ainsi lorsque puisque afin selon parmi sauf depuis pendant
lequel laquelle lesquels lesquelles auquel duquel desquels
avant durant jusque contre sinon cependant pourtant toutefois or car soit ni lui eux moi toi soi mon ton son mes tes
ses nos vos ces des les une que qui est pas rien tant tel telle tels telles ici pourquoi comment combien peu""".split())


def ordinary(w):
    return w not in FUNCTION and len(w) <= 13


eng.LANG = "fr"
eng.SEED = 20261125
eng.PLAIN = re.compile(rf"[{L}]+(?:['’][{L}]+)*")                      # l'homme, c'est, aujourd'hui: one word each
eng.TARGET = re.compile(r"[a-z]{4,}")
eng.LETTERS = "bcdfglmnprstv"
eng.VOWEL_SWAPS = False
eng.HOMOPHONE_ZIPF = 3.0
eng.EXTRA_TARGET_CHECK = ordinary
eng.FILLERS = set("euh heu ben bah hein bof ouais hmm hm mm mh ah oh eh hum".split())
eng.FUNC = "et de la le à les des en un une est que il du au".split()
eng.DIACRITIC = set("""a à ou où la là sur sûr du dû mur mûr des dès dés ça sa ca cote côte cotes côtes côté tache tâche
notre nôtre votre vôtre mais maïs cru crû jeune jeûne près prés pécheur pêcheur jésus""".split())
eng.ADDED_ACCENT = {}
eng.NUMBERS = set("""zéro un une deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze seize vingt
vingts trente quarante cinquante soixante cent cents mille million millions milliard milliards premier première second
seconde demi demie""".split())
eng.ACCENT_MARKS = ANY_ACCENT
eng.ACCENTED = {"a": "àâ", "e": "éèêë", "i": "îï", "o": "ô", "u": "ùûü", "c": "ç"}
eng.ACCENT_MIN_LEN = 4
eng.ACCENT_GAP = -99.0                # drop_accent() applies the test itself, on the accented part of an elided form
eng.ACCENT_HOW = "accent missing or wrong"
eng.REPEAT_PENALTY = 0.35
eng.UNIQUE_IN_EVERY_PASS = True
eng.FINAL_ACCENT_OK = Everything()
eng.MISS_RISK = miss_risk
eng.WORD_RISK = word_risk
# every candidate word of this delivery was read through: places and names, loanwords, and words whose sound is also
# two words or another word the spelling rules above do not reach
eng.AVOID = set("""allemagne angleterre arabie australie bordeaux madrid syrie toulouse turquie design
mettre davantage autant plateforme public publique camille lille simon cons dieu seigneur jean arnaud com""".split())
# replacements that are grammar words, could both be said (il vaut / il faut mieux), or are grim
eng.PAIR_AVOID = {("jour", "pour"), ("peur", "leur"), ("veux", "ceux"), ("soins", "moins"), ("lien", "bien"),
                  ("vaut", "faut"), ("port", "mort"), ("veux", "peux"), ("peux", "veux")}
eng.drop_accent = drop_accent
eng.sound_alikes = sound_alikes

if __name__ == "__main__":
    eng.main(sys.argv[1] if len(sys.argv) > 1 else HERE / "deliveries",
             sys.argv[2] if len(sys.argv) > 2 else HERE.parent / "spanish_decoys_2026-11-22" / "alignment-decoys-template.json",
             HERE, sys.argv[3] if len(sys.argv) > 3 else "fr_FR")
