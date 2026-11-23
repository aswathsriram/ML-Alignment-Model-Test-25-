#!/usr/bin/env python3
"""
German (de_DE) decoys, strict build — align-decoys/v1 plants keyed on work_item_id, at most 2 mistakes per file.

Same method, rules and checks as spanish_decoys_2026-11-22/build_spanish_strict.py (read its header): a mistake is
planted only where every annotator pass of the delivery has the same word at the same index and agrees on its timing;
boundary mistakes only on an edge that faces a pause (150-700 ms, no neighbour moved); a missing word is `delete`d
only when both neighbours touch it; a hallucinated word sits in a pause of at least 0.40 s; text mistakes change
exactly one letter. This file only swaps in the German language tables:

  accent error   the dots of one umlaut dropped (für -> fur, können -> konnen, zurück -> zuruck): what the machine
                 pre-fill really does in this delivery, and what the de_DE guideline forbids ("keep ä ö ü ß"). Only
                 where the bare form is no word of its own: never möchte / mochte, wäre / ware, schön / schon,
                 könnte / konnte, mütter / mutter. No ß mistakes (strasse is correct Swiss spelling).
  wrong word     one consonant changed inside a common word, giving another real word that sounds different.
                 Vowels are never changed: in German that is usually another form of the same verb (finden / fanden).
  never deleted / swapped: names; function words and auxiliaries; words with a colloquial twin the guideline says to
                 write as heard (habe / hab, nicht / nich, eine / 'ne, gerade / grad); compounds and words that may be
                 written as two (zurzeit, sodass, kennenlernen — the guideline leaves that open); number words; words
                 that sound like another spelling (das / dass, seit / seid, mehr / meer, wieder / wider, stadt / statt).

Run    : pip install wordfreq ; python german_decoys_2026-11-23/build_german_strict.py [deliveries.zip|folder] [template] [prefix]
Output : <prefix>_decoy_plants.json, <prefix>_decoy_review.csv, <prefix>_dropped.csv next to this script (prefix: de_DE)
The second batch (deliveries_part2/, 126 work items) is built on its own as de_DE_part2 so that the first batch's
decoys stay exactly as delivered; combine_german.py writes both into de_DE_all_decoy_plants.json.
"""
import pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "spanish_decoys_2026-11-22"))
import build_spanish_strict as eng                                     # noqa: E402

DOTS = {"ä": "a", "ö": "o", "ü": "u"}
NUM = ("null ein eins eine zwei drei vier fünf sechs sieben sieb acht neun zehn elf zwölf zwanzig dreißig vierzig fünfzig "
       "sechzig siebzig achtzig neunzig hundert tausend million millionen milliarde milliarden und sech").split()
NUM_RE = re.compile("(?:" + "|".join(sorted(NUM, key=len, reverse=True)) + ")+")


class Numbers:
    """Any word made only of number parts (einundzwanzig, dreihundert), and the ordinals."""
    extra = set("erste erster ersten zweite zweiter zweiten dritte dritter dritten halb halbe".split())

    def __contains__(self, w):
        return w in self.extra or bool(NUM_RE.fullmatch(w)) and w != "und"


def drop_accent(w):
    """The dots of the word's umlaut dropped; only words with exactly one umlaut."""
    marks = [i for i, ch in enumerate(w) if ch in DOTS]
    if len(marks) != 1:
        return None
    i = marks[0]
    return w[:i] + DOTS[w[i]] + w[i + 1:]


def sound_alikes(w):
    """Other spellings with the same sound: double / single consonants, s / ss / ß, final d / t, b / p, g / k,
    long-vowel marks (ie, h, doubled vowels), ai / ei, äu / eu, ä / e, f / v / ph, dt / tt, tz / z, ck / k, chs / x."""
    out = set()
    pairs = [("ss", "s"), ("s", "ss"), ("ß", "ss"), ("ss", "ß"), ("ß", "s"), ("d$", "t"), ("t$", "d"), ("b$", "p"),
             ("p$", "b"), ("g$", "k"), ("k$", "g"), ("dt", "t"), ("dt", "tt"), ("tt", "dt"), ("ie", "i"), ("i", "ie"),
             ("ih", "i"), ("ieh", "ie"), ("ee", "e"), ("oo", "o"), ("aa", "a"), ("ee", "eh"), ("eh", "ee"),
             ("ai", "ei"), ("ei", "ai"), ("äu", "eu"), ("eu", "äu"), ("ä", "e"), ("e", "ä"), ("v", "f"), ("f", "v"),
             ("ph", "f"), ("f", "ph"), ("tz", "z"), ("z", "tz"), ("ck", "k"), ("k", "ck"), ("chs", "x"), ("ks", "x"),
             ("x", "chs"), ("c", "k"), ("k", "c"), ("y", "i"), ("i", "y")]
    for c in "nmltpfrkbdg":
        pairs += [(c + c, c), (f"(?<!{c}){c}(?!{c})", c + c)]
    for v in "aeiouäöü":
        pairs += [(v + "h", v), (f"{v}(?!h)", v + "h")]
    for a, b in pairs:
        for m in re.finditer(a, w):
            out.add(w[:m.start()] + b + w[m.end():])
    out.discard(w)
    return out


def ordinary(w):
    """False for a word that must not be deleted or swapped: long (likely a compound), made of two common words
    (the guideline leaves one word / two words open), with a common twin without its final -e (habe / hab), or an
    -en / -em ending whose other form is a word too."""
    if len(w) > 11:
        return False
    if w.endswith("e") and eng.zipf(w[:-1]) >= 4.0:
        return False
    if w[-2:] in ("en", "em") and eng.zipf(w[:-1] + ("m" if w.endswith("n") else "n")) >= 3.5:
        return False                                            # kleinen / kleinem: endings that are hard to hear
    return not any(eng.zipf(w[:i]) >= 4.5 and eng.zipf(w[i:]) >= 4.5 for i in range(3, len(w) - 2))


eng.LANG = "de"
eng.SEED = 20261124
eng.PLAIN = re.compile(r"[a-zäöüß]+")
eng.TARGET = re.compile(r"[a-z]{4,}")
eng.LETTERS = "bdfghklmnprstwz"
eng.VOWEL_SWAPS = False
eng.EXTRA_TARGET_CHECK = ordinary
eng.FILLERS = set("äh ähm öh hm hmm mm mhm tja ach naja ne hä na ah oh aha".split())
eng.FUNC = "und die der das in zu ist es so ja auch den".split()
eng.DIACRITIC = set("das dass daß seit seid wieder wider möchte möchtest möchten möchtet".split())   # mochte is a word
eng.ADDED_ACCENT = {}
eng.NUMBERS = Numbers()
eng.ACCENT_MARKS = "äöü"
eng.ACCENTED = {"a": "ä", "o": "ö", "u": "ü"}
eng.ACCENT_MIN_LEN = 3                                                  # für -> fur
eng.ACCENT_GAP = 2.0                  # a real twin (möchte / mochte 1.3, wäre / ware 1.5) is far commoner than a slip
eng.ACCENT_HOW = "umlaut dots dropped"
eng.REPEAT_PENALTY = 0.35
eng.UNIQUE_IN_EVERY_PASS = True
eng.FINAL_ACCENT_OK = set()
eng.AVOID = set("""eine einen einem einer eines kein keine keinen keinem keiner mein meine meinen meinem meiner dein deine
sein seine seinen seinem seiner ihre ihren ihrem ihrer unser unsere unseren euer eure dieser diese dieses diesen diesem
jeder jede jedes jeden jedem welche welcher welches aber oder auch noch schon sehr mehr viel viele nach unter hinter
neben durch gegen ohne wenn dann denn weil nicht nichts doch immer also dort hier ganz etwas alle alles allen jetzt
heute damit dabei davon dazu daher deshalb trotzdem obwohl sondern sowie bevor nachdem wird werden wurde wurden worden
sind waren hatte hatten habe haben hast habt kann kannst konnte konnten will wollen wollte wollten soll sollen sollte
sollten muss musste mussten darf mag sich mich dich euch uns ihm ihn ihr wir sie man
hab nich einmal gerade grad gerne gern alleine allein andere anderen unsere heraus herein herunter hinauf hinaus hinein
hinunter herum darauf daran darin darum drauf dran drin raus rein runter rauf rum
potenzial potential selbstständig selbständig aufwendig sodass mithilfe aufgrund zurzeit infrage zugunsten anstelle
okay zuhause nachhause soviel sowieso genauso ebenso nochmal erstmal kennenlernen irgendetwas irgendwas
deinen deiner seines meines deines ihres unserem unserer ihnen innen dies aller wegen weder nein lang lange
wahl wal mahl
katharina lena siemens williams schleswig friedrich sachsen hans peter anhalt schweden weber kiel heide
geil dumme benannt
apple city deal franken indien foto solange solchen island irland polen denen deren somit womit""".split())   # 2nd batch
# near-synonyms: either could be read as right
eng.PAIR_AVOID = {("gerechnet", "berechnet"), ("benutzt", "genutzt"), ("bezahlt", "gezahlt"), ("erhielt", "erzielt"),
                  ("behalten", "gehalten")}
eng.drop_accent = drop_accent
eng.sound_alikes = sound_alikes

if __name__ == "__main__":
    eng.main(sys.argv[1] if len(sys.argv) > 1 else HERE / "deliveries",
             sys.argv[2] if len(sys.argv) > 2 else HERE.parent / "spanish_decoys_2026-11-22" / "alignment-decoys-template.json",
             HERE, sys.argv[3] if len(sys.argv) > 3 else "de_DE")
