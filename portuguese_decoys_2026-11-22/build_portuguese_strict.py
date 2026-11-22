#!/usr/bin/env python3
"""
Portuguese (pt_BR) decoys, strict build — align-decoys/v1 plants keyed on work_item_id, at most 2 mistakes per file.

Same method, rules and checks as spanish_decoys_2026-11-22/build_spanish_strict.py (read its header): a mistake is
planted only where every annotator pass of the delivery has the same word at the same index and agrees on its timing;
boundary mistakes only on an edge that faces a pause (150-700 ms, no neighbour moved); a missing word is `delete`d
only when both neighbours touch it; a hallucinated word sits in a pause of at least 0.40 s; text mistakes change
exactly one letter. This file only swaps in the Portuguese language tables:

  accent error   one mark dropped where the result is only a misspelling: você -> voce, não -> nao, também -> tambem,
                 informação -> informaçao (tilde), serviço -> servico (cedilla — tilde and cedilla are mandatory in the
                 pt_BR guideline); or a wrong accent that was never correct: aqui -> aquí, item -> ítem, juiz -> juíz.
                 Never the pairs only grammar tells apart (a / à / há, tem / têm, vem / vêm, por / pôr, pode / pôde,
                 mas / mais, porque / porquê) and never pre-2009 spellings (idéia, vôo), which some people still accept.
  wrong word     one letter changed inside a common word, giving another real word that sounds different
                 (bolas -> molas is what the machine really does in this data).
  never deleted / swapped: names and brands, words with a colloquial twin the guideline says to write as heard
                 (para / pra, estava / tava, vamos / vamo), words that may be written as two (num / em um, demais),
                 and words that sound like another spelling (cem / sem, mal / mau, sessão / seção, comprido / cumprido).

Run    : pip install wordfreq ; python portuguese_decoys_2026-11-22/build_portuguese_strict.py [deliveries.zip|folder]
Output : pt_BR_decoy_plants.json, pt_BR_decoy_review.csv, pt_BR_dropped.csv (next to this script)
"""
import pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "spanish_decoys_2026-11-22"))
import build_spanish_strict as eng                                     # noqa: E402

DROP = dict(zip("áàâãéêíóôõúç", "aaaaeeiooouc"))


def drop_accent(w):
    """One mark dropped: the last accent on a vowel if the result is only a misspelling, else the cedilla."""
    marks = [i for i, ch in enumerate(w) if ch in DROP]
    vowels = [i for i in marks if w[i] != "ç"]
    for i in list(reversed(vowels)) + [i for i in marks if w[i] == "ç"]:
        t = w[:i] + DROP[w[i]] + w[i + 1:]
        if t not in eng.DIACRITIC and eng.zipf(w) - eng.zipf(t) >= 0.75:
            return t
    return None


def sound_alikes(w):
    """Other spellings with the same sound in Brazilian Portuguese: s / ss / ç / c / sc / x / z, ch / x, g / j,
    silent h, l / u at the end of a syllable, unstressed e / i and o / u."""
    out = set()
    for a, b in (("ss", "ç"), ("ç", "ss"), ("ss", "s"), ("s", "ss"), ("s", "z"), ("z", "s"), ("ç", "s"), ("s", "ç"),
                 ("ce", "se"), ("ci", "si"), ("se", "ce"), ("si", "ci"), ("ce", "sse"), ("ci", "ssi"), ("sse", "ce"),
                 ("ssi", "ci"), ("sc", "c"), ("sc", "ss"), ("ch", "x"), ("x", "ch"), ("x", "s"), ("x", "z"), ("x", "ss"),
                 ("s", "x"), ("z", "x"), ("ge", "je"), ("gi", "ji"), ("je", "ge"), ("ji", "gi"), ("lh", "li"),
                 ("e", "i"), ("i", "e"), ("o", "u"), ("u", "o"), ("l(?=[^aeiou]|$)", "u"), ("(?<=[aeiou])u(?=[^aeiou]|$)", "l")):
        for m in re.finditer(a, w):
            out.add(w[:m.start()] + b + w[m.end():])
    out.add(w[1:] if w.startswith("h") else "h" + w)
    out.discard(w)
    return out


eng.LANG = "pt"
eng.SEED = 20261123
eng.PLAIN = re.compile(r"[a-zçáàâãéêíóôõúü]+")
eng.TARGET = re.compile(r"[a-z]{4,}")
eng.LETTERS = "abcdefgijlmnoprstuv"
eng.FILLERS = set("ah ahn ahã aham eh eita hm hmm hum humm hã ih mm né ó oh ô uh uhum ué".split())
eng.FUNC = "e o é os um no com que eu em a de para na se as do da".split()   # what the machine hallucinates in this data
eng.DIACRITIC = set("""a à há e é eh o ó tem têm vem vêm contem contém contêm mantem mantém mantêm porque porquê que quê
por pôr pode pôde da dá de dê do dó nos nós mas más mais para pára pelo pêlo pela esta está este pais país sai saí
ai aí la lá ca cá ja já so só as às ás""".split())
eng.ADDED_ACCENT = {"aqui": "aquí", "ali": "alí", "item": "ítem", "itens": "ítens", "juiz": "juíz", "raiz": "raíz",
                    "ruim": "ruím", "gratuito": "gratuíto", "saiu": "saíu", "caiu": "caíu"}
eng.NUMBERS = set("""zero um uma dois duas três quatro cinco seis sete oito nove dez onze doze treze catorze quatorze quinze
dezesseis dezessete dezoito dezenove vinte trinta quarenta cinquenta sessenta setenta oitenta noventa cem cento mil
milhão milhões bilhão bilhões primeiro primeira segundo segunda meia""".split())
eng.ACCENT_MARKS = "áàâãéêíóôõúç"
eng.ACCENTED = {"a": "áàâã", "e": "éê", "i": "í", "o": "óôõ", "u": "ú", "c": "ç"}
eng.ACCENT_MIN_LEN = 3                                                  # não -> nao, mês -> mes
eng.REPEAT_PENALTY = 0.35                                               # spread text mistakes over many words
eng.UNIQUE_IN_EVERY_PASS = True
eng.FINAL_ACCENT_OK = set("você até café avó avô vovó vovô bebê sofá josé jacaré guaraná paraná ceará piauí amanhã irmã manhã maçã".split())
# every candidate word and every possible replacement of this delivery was read through: names, brands and foreign
# words; words with a colloquial twin or a two-word spelling; words that sound like another spelling; contractions
# and demonstratives (esse / este, desse / nesse: easy to mix up, hard to hear); swear words and grim replacements
eng.AVOID = set("""alves anderson arthur barbosa barcelona bruno caetano carlos carvalho catarina center chile coelho
cruzeiro diego domingos gabriel geraldo guarani guilherme instagram isabel israel jesus lucas mail manaus maria marte
mateus mendes moura natal neto online paulo ribeiro rodrigo rodrigues salvador santos trump washington whatsapp wilson
youtube bahia ranking links super major foda
para estava estavam estamos estou estar tava vamos tipo num numa nuns numas dum duma onde aonde afim acerca embaixo
enfim devagar demais traz voz vez viagem alto altos auto autos sexta cesta
dessa dessas desse desses deste destes desta destas nessa nessas nesse nesses neste nestes nesta nestas disso disto
nisso nisto dele dela deles delas nele nela neles nelas naquela naquele naquilo daquela daquele daquilo daquelas
daqueles pelas pelos essa essas esse esses estes estas isso isto aquilo aquele aquela nossa nosso nossas nossos minha
minhas seus suas como
atenas braga malta congo gomes vegas deus merda rabo aborto negra negras morte morre morrer morrendo morta mortas
mortal""".split())
# two forms of one verb: an annotator may read either as right
eng.PAIR_AVOID = {("fazemos", "fizemos"), ("fizemos", "fazemos"), ("fazer", "fizer"), ("dizia", "diria"), ("somos", "fomos")}
eng.drop_accent = drop_accent
eng.sound_alikes = sound_alikes

if __name__ == "__main__":
    eng.main(sys.argv[1] if len(sys.argv) > 1 else HERE / "deliveries",
             sys.argv[2] if len(sys.argv) > 2 else HERE.parent / "spanish_decoys_2026-11-22" / "alignment-decoys-template.json",
             HERE, "pt_BR")
