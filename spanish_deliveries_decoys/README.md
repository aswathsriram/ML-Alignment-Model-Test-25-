# Spanish (es_ES) decoys (platform deliveries)

Input: `forced-alignment-deliveries-es_ES-2026-11-10.zip` (769 work items) and the es_ES guidelines.
Run: `python spanish_deliveries_decoys/build_spanish.py`. It uses `german_decoys/build_german.py` with Spanish tables.

- `spanish_deliveries_decoy_plants.json`: 737 decoys in the align-decoys/v1 format, keyed on `work_item_id` (plus
  `file_name`). It has the same layout as the Hindi, German, Portuguese and French plants files.
- `spanish_deliveries_skipped.json`: the 32 work items with no segments (entirely synthetic), skipped.

This set is separate from `spanish_decoys_v1/` (the 297 files of Updated_spanish.json).

Errors: boundary mismatch (move / overlap / zero; minor 40-80 ms, major 100-300 ms, critical 310-700 ms), missing
segment, missing word, hallucinated word, absorbed filler, plus es_ES guideline text errors: homophones (hola/ola,
vaya/valla, hecho/echo, tubo/tuvo, ay/hay, sí/si, qué/que ...), dropped accents / ñ, colloquial forms (pa'/para,
ná/nada, bue/bueno), spelling slips (b/v, ll/y, silent h, z/s ...), cut-off words, invented text over (( )).
The 60 multi-speaker files also carry `set_flag multi_speaker = false`.
No capitalisation, punctuation, digit, split or join errors.
