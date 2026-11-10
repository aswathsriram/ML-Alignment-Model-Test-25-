# German decoys (platform deliveries, de_DE)

Input: `forced-alignment-deliveries-de_DE-2026-11-10.zip` (671 work items) and the de_DE guidelines.
Run: `python german_decoys/build_german.py`

- `german_decoy_plants.json`: 385 decoys in the align-decoys/v1 format, keyed on `work_item_id` (plus `file_name`).
  It has the same layout as the Hindi and Spanish plants files. Each note reads `<error type> · <severity> · <detail>`.
- `german_skipped.json`: the 286 work items with no segments (entirely synthetic), skipped.

The correct alignment is the adjudication answer when there is one, else the blind-pass answer. Every timing rule is
checked against both blind passes. Each file gets 1-6 mistakes depending on its length, at least 3 words apart, never
on a tag, and 1-2 are marked critical.
Boundary sizes: minor 40-80 ms, major 100-300 ms, critical 310-700 ms.

Errors: boundary mismatch (move / overlap / zero), missing segment, missing word, hallucinated word, absorbed filler,
plus German guideline text errors: homophones (das/dass, seite/saite ...), umlaut/ß written ae/oe/ue/ss, spelling slips,
spoken reductions (ist/is, nicht/nich, eine/'ne), cut-off words, invented text over (( )).
No capitalisation, punctuation, digit, split or join errors.
