#!/usr/bin/env python3
"""
Portuguese (pt_BR) decoys from the platform's forced-alignment deliveries, in the align-decoys/v1 format laid out
like the Hindi / Spanish / German plants files, keyed on work_item_id.

Uses the German builder (german_decoys/build_german.py: same correct-alignment choice, same timing checks against
both blind passes, same spacing and critical rules) with the Portuguese tables from Forced_Alignment_Guidelines_pt_BR:
  boundary_start / boundary_end  move   minor 40-80 ms, major 100-300 ms, critical 310-700 ms
  boundary_overlap / zero_length overlap / zero
  word_deletion / filler_deleted delete         missing_segment  remove         word_hallucination  add
  filler_absorbed                absorb
  word_substitution              replace: homophones (Part 5: concerto / conserto, sessão / seção, acento / assento ...)
                                 and near words (mas / mais, esse / este ...)
  accent_missing                 replace: tilde / cedilla / accent dropped (Part 5: they are mandatory)
  colloquial_form                replace: tô / tá / pra / cê / tava written in full, or the full form written colloquially
  spelling_slip                  replace: ss / s, rr / r, ch / x, s / z, ç / ss, g / j slips
  truncation_introduced / truncation_completed   replace (4.3 cut-off words)
  unintelligible_invented        replace_unintelligible on (()) / ((guess))
  multiple_speakers_off          set_flag multi_speaker = false on files with several speakers
No capitalisation, punctuation, digit, split or join errors.

Run    : python portuguese_decoys/build_portuguese.py [deliveries.zip|folder] [template.json]
Output : portuguese_decoys/portuguese_decoy_plants.json, portuguese_decoys/portuguese_skipped.json
"""
import pathlib, random, re, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "german_decoys"))
import build_german as bg                                              # noqa: E402

HOMOPHONES = [("concerto", "conserto"), ("cela", "sela"), ("sessão", "seção"), ("cessão", "sessão"), ("acento", "assento"),
              ("mas", "mais"), ("mal", "mau"), ("há", "a"), ("sem", "cem"), ("traz", "trás"), ("cheque", "xeque"),
              ("censo", "senso"), ("está", "esta"), ("nós", "nos"), ("por", "pôr"), ("pode", "pôde"), ("tem", "têm"),
              ("vem", "vêm"), ("onde", "aonde"), ("porque", "porquê"), ("sexta", "cesta"), ("cede", "sede"),
              ("conselho", "concelho"), ("esse", "este"), ("essa", "esta"), ("isso", "isto"), ("um", "uma"),
              ("do", "no"), ("da", "na"), ("eu", "meu"), ("ele", "eles"), ("muito", "muita"), ("de", "dê"), ("e", "é")]
SUBST = {}
for a, b in HOMOPHONES:
    SUBST.setdefault(a, b); SUBST.setdefault(b, a)
COLLOQUIAL = {"tô": "estou", "tá": "está", "pra": "para", "cê": "você", "tava": "estava", "tavam": "estavam",
              "estou": "tô", "está": "tá", "para": "pra", "você": "cê", "estava": "tava"}
STRIP = str.maketrans("àáâãéêíóôõúç", "aaaaeeiooouc")


def accent(w):
    return w.translate(STRIP) if re.search("[àáâãéêíóôõúç]", w) and not w.startswith("((") else None


def slip(w, rng):
    opts = []
    for a, b in (("ss", "s"), ("rr", "r"), ("ch", "x"), ("ç", "ss"), ("lh", "li"), ("nh", "ni")):
        if a in w:
            opts.append(w.replace(a, b, 1))
    for m in re.finditer(r"(?<=[aeiouáéíóú])s(?=[aeiou])", w):
        opts.append(w[:m.start()] + "z" + w[m.start() + 1:])
    for m in re.finditer(r"(?<=[aeiouáéíóú])z(?=[aeiou])", w):
        opts.append(w[:m.start()] + "s" + w[m.start() + 1:])
    for m in re.finditer(r"x(?=[aeiou])", w):
        opts.append(w[:m.start()] + "ch" + w[m.start() + 1:])
    for m in re.finditer(r"g(?=[ei])", w):
        opts.append(w[:m.start()] + "j" + w[m.start() + 1:])
    opts = sorted(set(o for o in opts if o != w and len(o) >= 4))
    return rng.choice(opts) if opts else None


bg.SEED = 20261111
bg.SHARE = {"move": 0.40, "overlap": 0.04, "zero": 0.03, "delete": 0.08, "remove": 0.08, "add": 0.08, "absorb": 0.01,
            "word_substitution": 0.08, "umlaut_replaced": 0.08, "spoken_form": 0.04, "spelling_slip": 0.04,
            "truncation_introduced": 0.03, "truncation_completed": 0.01, "unintelligible": 0.01}
bg.ACCENT_LABEL, bg.REDUCE_LABEL = "accent_missing", "colloquial_form"
bg.SUBST, bg.REDUCE = SUBST, COLLOQUIAL
bg.FILLERS = {"ah", "hmm", "hm", "mm", "eita", "ué", "uh", "ahn", "eh"}
bg.umlaut, bg.spelling_slip = accent, slip

if __name__ == "__main__":
    bg.main(sys.argv[1] if len(sys.argv) > 1 else HERE / "forced-alignment-deliveries-pt_BR-2026-11-10.zip",
            sys.argv[2] if len(sys.argv) > 2 else HERE.parent / "hindi_decoys" / "alignment-decoys-template.json",
            HERE, "portuguese")
