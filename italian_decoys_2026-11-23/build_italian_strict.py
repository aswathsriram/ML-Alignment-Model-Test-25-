#!/usr/bin/env python3
"""
Italian (it_IT) decoys, strict build — align-decoys/v1 plants keyed on work_item_id, at most 2 mistakes per file.

Same method, rules and checks as spanish_decoys_2026-11-22/build_spanish_strict.py (read its header): a mistake is
planted only where every annotator pass of the delivery has the same word at the same index and agrees on its timing;
boundary mistakes only on an edge that faces a pause (150-700 ms, no neighbour moved); a missing word is `delete`d
only when both neighbours touch it; a hallucinated word sits in a pause of at least 0.40 s; text mistakes change
exactly one letter. This file only swaps in the Italian language tables:

  words          an elided form is one word (l'italia, dell'anno, c'è, un po'): it can carry a boundary or an accent
                 mistake like any other word, and is never split.
  accent error   the accent dropped where the result is only a misspelling (città -> citta, perché -> perche,
                 più -> piu, università -> universita), or a wrong accent that is never correct on a short word
                 (qui -> quì, qua -> quà, fa -> fà, sta -> stà, so -> sò, va -> và, su -> sù). Never the pairs only
                 grammar tells apart (e / è, la / là, li / lì, si / sì, ne / né, se / sé, da / dà, te / tè), never a
                 real twin (papà / papa, metà / meta, però / pero, parlò / parlo), and never the direction of the accent
                 (perché / perchè, più / piú): annotators themselves differ on it in this delivery.
  wrong word     one letter changed inside a common word, giving another real word that sounds different.
  never deleted / swapped: names and places; grammar words and discourse markers; number words; words with a
                 shortened twin (signore / signor, fare / far, sono / son); words whose single / double consonant or
                 silent h makes another word (anno / hanno, sete / sette, caro / carro, pala / palla).

Run    : pip install wordfreq ; python italian_decoys_2026-11-23/build_italian_strict.py [deliveries.zip|folder] [template] [prefix]
Output : it_IT_decoy_plants.json, it_IT_decoy_review.csv, it_IT_dropped.csv (next to this script)
"""
import pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "spanish_decoys_2026-11-22"))
import build_spanish_strict as eng                                     # noqa: E402

L = "a-zàèéìíòóùú"
DROP = dict(zip("àèéìòù", "aeeiou"))
ANY_ACCENT = "àèéìíîòóùú"
NUM = ("zero uno un una due tre tré quattro quattr cinque sei sette otto nove dieci undici dodici tredici quattordici "
       "quindici sedici diciassette diciotto diciannove venti vent trenta trent quaranta quarant cinquanta cinquant "
       "sessanta sessant settanta settant ottanta ottant novanta novant cento mille mila milione milioni miliardo "
       "miliardi").split()
NUM_RE = re.compile("(?:" + "|".join(sorted(NUM, key=len, reverse=True)) + ")+")


class Numbers:
    """Any word made only of number parts (ventidue, trecento, duemilaventitré), and the ordinals."""
    extra = set("""primo prima primi prime secondo seconda secondi terzo terza terzi quarto quarta quarti quinto quinta
    sesto sesta settimo settima ottavo ottava nono nona decimo decima mezzo mezza""".split())

    def __contains__(self, w):
        return w in self.extra or bool(NUM_RE.fullmatch(w))


class Everything:
    def __contains__(self, w):
        return True


def drop_accent(w):
    """The word with its one accent dropped; None when the result could be read as a word. For an elided form the
    test is made on the part that carries the accent (l'attività -> l'attivita)."""
    marks = [i for i, ch in enumerate(w) if ch in ANY_ACCENT]
    if len(marks) != 1 or w[marks[0]] not in DROP:
        return None
    i = marks[0]
    a = max(w.rfind("'", 0, i), w.rfind("’", 0, i)) + 1
    b = min([x for x in (w.find("'", i), w.find("’", i)) if x >= 0] or [len(w)])
    part, j = w[a:b], i - a
    if len(part) < 3 or part in eng.DIACRITIC or eng.zipf(part) < 4.3:
        return None
    t = part[:j] + DROP[part[j]] + part[j + 1:]
    if t in eng.DIACRITIC or eng.zipf(part) - eng.zipf(t) < 0.75:
        return None
    return w[:a] + t + w[b:]


def sound_alikes(w):
    """Other spellings that could be heard as the same: single / double consonants, silent h, qu / cu, cie / ce,
    gie / ge, scie / sce, gli / li, gn / ni, i / j / y, c / k."""
    out = set()
    pairs = [("qu", "cu"), ("cu", "qu"), ("cie", "ce"), ("ce", "cie"), ("gie", "ge"), ("ge", "gie"), ("scie", "sce"),
             ("sce", "scie"), ("gli", "li"), ("li", "gli"), ("gn", "ni"), ("ni", "gn"), ("j", "i"), ("y", "i"),
             ("k", "c"), ("k", "ch"), ("ch", "k"), ("x", "s"), ("x", "cs")]
    for c in "bcdfglmnprstvz":
        pairs += [(c + c, c), (f"(?<!{c}){c}(?!{c})", c + c)]
    for a, b in pairs:
        for m in re.finditer(a, w):
            out.add(w[:m.start()] + b + w[m.end():])
    out.add(w[1:] if w.startswith("h") else "h" + w)
    out.discard(w)
    return out


# grammar words and discourse markers: never deleted or swapped
FUNCTION = set("""come cosa dove quando anche ancora sempre molto poco tutto tutti tutta tutte questo questa questi queste
quello quella quelli quelle quel quei ogni altro altra altri altre loro nostro nostra nostri nostre vostro vostra mio mia
miei suo sua suoi sue tuo tua essere avere sono siamo siete hanno abbiamo avete aveva avevano fare fatto stato stata
stati state stare deve devo devono posso possono vuole voglio vogliono della dello delle degli dalla dalle dagli dallo
nella nello nelle negli sulla sulle sugli sullo alla allo alle agli con per tra fra che chi cui non quindi allora dunque
invece mentre oppure ossia anzi infatti inoltre comunque quasi solo soltanto proprio ecco poi dopo prima ora adesso
oggi qui qua diciamo tipo niente guarda senti capito praticamente insomma magari appunto ovviamente forse certo bene
male meno senza verso sopra sotto dentro fuori contro durante secondo circa era erano sia siano stava aveva ebbe fosse
uno una gli del dal nel sul col dei dai nei sui alla nessuno nessuna qualche qualcosa qualcuno ciascuno ognuno
abbia avevi avuto sarai saranno sarebbe sarebbero dobbiamo dovesse dovevo dovrebbe dovrebbero fanno faranno faremo
potesse potrebbe potreste potuto possiamo vogliamo volevo vorrei danno sarete farai farebbe sapete
quali quale quante quanti quanto quanta qualsiasi nulla nemmeno neanche almeno appena attraverso mediante siccome
peraltro alcuni alcune ella essa esso essi molta molti molte tanta tante tanti tanto troppi troppo troppa stesso stessa
stessi stesse propria propri oltre eppure fino dello nostre vostre nostri vostri manco guardi senta scusi""".split())


def ordinary(w):
    """False for a word that must not be deleted or swapped: a grammar word, a long compound, or a word with a common
    shortened twin (signore / signor, fare / far, buono / buon)."""
    if w in FUNCTION or len(w) > 13:
        return False
    if w[-1] in "nrl" and max(eng.zipf(w + "e"), eng.zipf(w + "o")) >= 4.0:
        return False                                            # buon / buono, maggior / maggiore, alcun / alcuno
    return not (w[-1] in "eo" and eng.zipf(w[:-1]) >= 4.0)


eng.LANG = "it"
eng.SEED = 20261126
eng.PLAIN = re.compile(rf"[{L}]+(?:['’][{L}]+)*['’]?")                 # l'italia, dell'anno, c'è, po': one word each
eng.TARGET = re.compile(r"[a-z]{4,}")
eng.LETTERS = "abcdefgilmnoprstuvz"
eng.MOOD_TAILS = ("no",)                                               # parlano / parlino: one verb, two moods
eng.EXTRA_TARGET_CHECK = ordinary
eng.FILLERS = set("eh ehm mmm mm hmm hm ah oh beh boh mah bah uhm ehi vabbè mh".split())
eng.FUNC = "e il è un o i in che di la a per le del non una si".split()    # what the machine hallucinates in this data
eng.DIACRITIC = set("""e è la là li lì si sì ne né se sé da dà te tè di dì che ché papa papà meta metà pero però sara sarà
faro farò ancora necessità gesù""".split())            # necessita is a verb form; no decoy on a sacred name
eng.ADDED_ACCENT = {"qui": "quì", "qua": "quà", "fa": "fà", "sta": "stà", "sto": "stò", "so": "sò", "va": "và",
                    "fu": "fù", "blu": "blù", "su": "sù"}
eng.NUMBERS = Numbers()
eng.ACCENT_MARKS = ANY_ACCENT
eng.ACCENTED = {"a": "à", "e": "èé", "i": "ì", "o": "ò", "u": "ù"}
eng.ACCENT_MIN_LEN = 3                                                  # più -> piu, già -> gia, può -> puo
eng.ACCENT_GAP = -99.0                # drop_accent() applies the test itself, on the accented part of an elided form
eng.REPEAT_PENALTY = 0.35
eng.UNIQUE_IN_EVERY_PASS = True
eng.FINAL_ACCENT_OK = Everything()    # Italian accents are final: the twin test in drop_accent() decides
eng.REPLACEMENT_CHECK = lambda t: t not in FUNCTION
# every candidate word and every possible replacement of this delivery was read through: names and places, English
# loanwords, swear words, sacred and grim words, punto / virgola (said inside numbers: nove punto sei), and words that
# are also written as two
eng.AVOID = set("""benedetto francia parigi pisa roma rosario sergio svezia toscana washington wikipedia bibbia vergine
cina pietro carlo marco maria mafia martino siena rocco siria dante lord lega
club database leader network post record super mega master mister cover live extra
cazzo cazzi stupido sesso morte morti morto muore tomba bomba peste punto virgola
innanzitutto anzitutto soprattutto sopratutto dopotutto oltretutto perlomeno perlopiù tuttalpiù dappertutto pertanto
infine apposta apposto buongiorno buonasera buonanotte arrivederci stasera stamattina stanotte stavolta dopodomani
ebbene eccetera nonostante ciononostante tuttora talvolta talora finora sinora ormai oramai suppergiù pressappoco
cosiddetto cosiddetta cosiddetti cosiddette""".split())      # last four lines: words also written as two (innanzi tutto)
eng.drop_accent = drop_accent
eng.sound_alikes = sound_alikes

if __name__ == "__main__":
    eng.main(sys.argv[1] if len(sys.argv) > 1 else HERE / "deliveries",
             sys.argv[2] if len(sys.argv) > 2 else HERE.parent / "spanish_decoys_2026-11-22" / "alignment-decoys-template.json",
             HERE, sys.argv[3] if len(sys.argv) > 3 else "it_IT")
