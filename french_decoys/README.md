# French (fr_FR) decoys (platform delivery)

Input: `deliveries/…_SO-71312-20260915-20260919.json` (374 work items) and the fr_FR guidelines.
Run: `python french_decoys/build_french.py`. It uses `german_decoys/build_german.py` with French tables.

- `french_decoy_plants.json`: 110 decoys in the align-decoys/v1 format, keyed on `work_item_id` (plus `file_name`).
  It has the same layout as the Hindi, Spanish, German and Portuguese plants files.
- `french_skipped.json`: the 264 work items with no segments (entirely synthetic), skipped.

Errors: boundary mismatch (move / overlap / zero; minor 40-80 ms, major 100-300 ms, critical 310-700 ms), missing
segment, missing word, hallucinated word, absorbed filler, plus fr_FR guideline text errors: homophones (ver/verre/vers/vert,
mère/mer/maire, peut/peu, a/à, et/est, ou/où ...), dropped accents / cedilla, colloquial forms (ça/cela, ben/bien,
ouais/oui), spelling slips, cut-off words, invented text over (( )).
No capitalisation, punctuation, digit, split or join errors.
