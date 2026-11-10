#!/usr/bin/env python3
"""
Spanish (es_ES) decoys from the platform's forced-alignment deliveries (769 work items), in the align-decoys/v1 format
laid out like the Hindi / German / Portuguese / French plants files, keyed on work_item_id.

Uses the German builder (german_decoys/build_german.py: same correct-alignment choice, same timing checks against
both blind passes, same spacing and critical rules) with the Spanish tables from Forced_Alignment_Guidelines_es_ES:
  boundary_start / boundary_end  move   minor 40-80 ms, major 100-300 ms, critical 310-700 ms
  boundary_overlap / zero_length overlap / zero
  word_deletion / filler_deleted delete         missing_segment  remove         word_hallucination  add
  filler_absorbed                absorb (eh, em, mmm, ah ...)
  word_substitution              replace: homophones (Part 5: hola / ola, vaya / valla, hecho / echo, tubo / tuvo,
                                 ay / hay) and accent pairs / near words (sí / si, tú / tu, él / el, qué / que ...)
  accent_missing                 replace: á é í ó ú ñ ü dropped (Part 5: keep them)
  colloquial_form                replace: pa' / ná / bue / profe written in full, or the full form written colloquially
  spelling_slip                  replace: b / v, ll / y, silent h dropped, z / s, ce ci / se si, rr / r, g / j
  truncation_introduced / truncation_completed   replace (4.3 cut-off words)
  unintelligible_invented        replace_unintelligible on (()) / ((guess))
  multiple_speakers_off          set_flag multi_speaker = false on files with several speakers
No capitalisation, punctuation, digit, split or join errors.

Run    : python spanish_deliveries_decoys/build_spanish.py [deliveries.zip|folder] [template.json]
Output : spanish_deliveries_decoys/spanish_deliveries_decoy_plants.json, spanish_deliveries_skipped.json
"""
import pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "german_decoys"))
import build_german as bg                                              # noqa: E402

GROUPS = [("hola", "ola"), ("vaya", "valla", "baya"), ("hecho", "echo"), ("tubo", "tuvo"), ("ay", "hay", "ahí"),
          ("a", "ha"), ("sí", "si"), ("tú", "tu"), ("él", "el"), ("mí", "mi"), ("más", "mas"), ("sé", "se"),
          ("té", "te"), ("dé", "de"), ("qué", "que"), ("cómo", "como"), ("dónde", "donde"), ("cuándo", "cuando"),
          ("cuánto", "cuanto"), ("votar", "botar"), ("vello", "bello"), ("vez", "ves"), ("casa", "caza"),
          ("cien", "sien"), ("haya", "halla"), ("hierba", "hierva"), ("rayar", "rallar"), ("este", "esta"),
          ("un", "una"), ("lo", "la"), ("del", "de"), ("al", "el"), ("los", "las"), ("muy", "mucho"), ("y", "e")]
SUBST = {}
for g in GROUPS:
    for i, w in enumerate(g):
        SUBST.setdefault(w, g[(i + 1) % len(g)])
COLLOQUIAL = {"pa'": "para", "ná": "nada", "bue": "bueno", "profe": "profesor",
              "para": "pa'", "nada": "ná", "bueno": "bue"}
STRIP = str.maketrans("áéíóúñü", "aeiounu")


def accent(w):
    return w.translate(STRIP) if re.search("[áéíóúñü]", w) and not w.startswith("((") else None


def slip(w, rng):
    opts = []
    for a, b in (("b", "v"), ("v", "b"), ("ll", "y"), ("rr", "r"), ("z", "s"), ("ce", "se"), ("ci", "si"),
                 ("ge", "je"), ("gi", "ji"), ("y", "ll")):
        if a in w[1:] or (a in "bvz" and a in w):
            opts.append(w.replace(a, b, 1))
    if w.startswith("h") and len(w) >= 5:
        opts.append(w[1:])
    opts = sorted(set(o for o in opts if o != w and len(o) >= 4))
    return rng.choice(opts) if opts else None


bg.SEED = 20261113
bg.SHARE = {"move": 0.40, "overlap": 0.04, "zero": 0.03, "delete": 0.08, "remove": 0.08, "add": 0.08, "absorb": 0.01,
            "word_substitution": 0.09, "umlaut_replaced": 0.08, "spoken_form": 0.02, "spelling_slip": 0.05,
            "truncation_introduced": 0.03, "truncation_completed": 0.01, "unintelligible": 0.01}
bg.ACCENT_LABEL, bg.REDUCE_LABEL = "accent_missing", "colloquial_form"
bg.SUBST, bg.REDUCE = SUBST, COLLOQUIAL
bg.FILLERS = {"eh", "em", "mmm", "mm", "ah", "ehm", "hmm", "mm-hm"}
bg.umlaut, bg.spelling_slip = accent, slip

if __name__ == "__main__":
    bg.main(sys.argv[1] if len(sys.argv) > 1 else HERE / "forced-alignment-deliveries-es_ES-2026-11-10.zip",
            sys.argv[2] if len(sys.argv) > 2 else HERE.parent / "hindi_decoys" / "alignment-decoys-template.json",
            HERE, "spanish_deliveries")
