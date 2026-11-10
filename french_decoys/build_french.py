#!/usr/bin/env python3
"""
French (fr_FR) decoys from the platform's forced-alignment delivery, in the align-decoys/v1 format laid out like the
Hindi / Spanish / German / Portuguese plants files, keyed on work_item_id.

Uses the German builder (german_decoys/build_german.py: same correct-alignment choice, same timing checks against
both blind passes, same spacing and critical rules) with the French tables from Forced_Alignment_Guidelines_fr_FR:
  boundary_start / boundary_end  move   minor 40-80 ms, major 100-300 ms, critical 310-700 ms
  boundary_overlap / zero_length overlap / zero
  word_deletion / filler_deleted delete         missing_segment  remove         word_hallucination  add
  filler_absorbed                absorb (euh, ben, bah, hein, hmm ...)
  word_substitution              replace: homophones (Part 5: ver / verre / vers / vert, mère / mer / maire, peut / peu,
                                 and a / à, et / est, ou / où, son / sont, ces / ses ...)
  accent_missing                 replace: accent / cedilla dropped (Part 5: keep all accents)
  colloquial_form                replace: ça written cela, ben written bien, ouais written oui, and back
  spelling_slip                  replace: double consonant, ph / f, eau / au, silent final letter dropped
  truncation_introduced / truncation_completed   replace (4.3 cut-off words)
  unintelligible_invented        replace_unintelligible on (()) / ((guess))
  multiple_speakers_off          set_flag multi_speaker = false on files with several speakers
No capitalisation, punctuation, digit, split or join errors (elided forms such as l'homme are never touched apart).

Run    : python french_decoys/build_french.py [deliveries folder|zip] [template.json]
Output : french_decoys/french_decoy_plants.json, french_decoys/french_skipped.json
"""
import pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "german_decoys"))
import build_german as bg                                              # noqa: E402

GROUPS = [("ver", "verre", "vers", "vert"), ("mère", "mer", "maire"), ("sain", "saint", "sein"), ("peut", "peu"),
          ("a", "à"), ("et", "est"), ("ou", "où"), ("son", "sont"), ("ces", "ses"), ("ce", "se"), ("on", "ont"),
          ("la", "là"), ("c'est", "s'est"), ("sa", "ça"), ("quand", "quant"), ("leur", "leurs"), ("mais", "mes"),
          ("cet", "cette"), ("tout", "tous"), ("près", "prêt"), ("vingt", "vin"), ("cent", "sans", "sang"),
          ("fois", "foi", "foie"), ("conte", "compte"), ("cour", "cours", "court"), ("voix", "voie", "voit"),
          ("pain", "pin"), ("du", "dû"), ("sur", "sûr"), ("été", "était"), ("le", "les"), ("un", "une"),
          ("de", "des"), ("au", "aux"), ("ma", "mon"), ("ils", "il"), ("elle", "elles"), ("notre", "nôtre")]
SUBST = {}
for g in GROUPS:
    for i, w in enumerate(g):
        SUBST.setdefault(w, g[(i + 1) % len(g)])
COLLOQUIAL = {"ça": "cela", "cela": "ça", "ben": "bien", "ouais": "oui", "oui": "ouais", "bien": "ben"}
STRIP = str.maketrans("éèêëàâîïôùûüÿç", "eeeeaaiiouuuyc")


def accent(w):
    return w.translate(STRIP) if re.search("[éèêëàâîïôùûüÿç]", w) and not w.startswith("((") else None


def slip(w, rng):
    if "'" in w:
        return None
    opts = []
    for m in re.finditer(r"([lmnprst])\1", w):
        opts.append(w[:m.start()] + w[m.start() + 1:])
    for a, b in (("ph", "f"), ("eau", "au"), ("qu", "k"), ("ai", "è")):
        if a in w:
            opts.append(w.replace(a, b, 1))
    if re.search(r"[aeiouéèê][tsdx]$", w) and len(w) >= 5:
        opts.append(w[:-1])
    opts = sorted(set(o for o in opts if o != w and len(o) >= 4))
    return rng.choice(opts) if opts else None


bg.SEED = 20261112
bg.SHARE = {"move": 0.40, "overlap": 0.04, "zero": 0.03, "delete": 0.08, "remove": 0.08, "add": 0.08, "absorb": 0.01,
            "word_substitution": 0.09, "umlaut_replaced": 0.08, "spoken_form": 0.02, "spelling_slip": 0.05,
            "truncation_introduced": 0.03, "truncation_completed": 0.01, "unintelligible": 0.01}
bg.ACCENT_LABEL, bg.REDUCE_LABEL = "accent_missing", "colloquial_form"
bg.SUBST, bg.REDUCE = SUBST, COLLOQUIAL
bg.FILLERS = {"euh", "ben", "bah", "hein", "bof", "hmm", "hm", "mm", "ah", "heu"}
bg.umlaut, bg.spelling_slip = accent, slip

if __name__ == "__main__":
    bg.main(sys.argv[1] if len(sys.argv) > 1 else HERE / "deliveries",
            sys.argv[2] if len(sys.argv) > 2 else HERE.parent / "hindi_decoys" / "alignment-decoys-template.json",
            HERE, "french")
