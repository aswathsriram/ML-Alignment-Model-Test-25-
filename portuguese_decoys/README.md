# Portuguese (pt_BR) decoys (platform deliveries)

Input: `forced-alignment-deliveries-pt_BR-2026-11-10.zip` (673 work items) and the pt_BR guidelines.
Run: `python portuguese_decoys/build_portuguese.py`. It uses `german_decoys/build_german.py` with Portuguese tables.

- `portuguese_decoy_plants.json`: 669 decoys in the align-decoys/v1 format, keyed on `work_item_id` (plus `file_name`).
  It has the same layout as the Hindi, Spanish and German plants files.
- `portuguese_skipped.json`: the 4 work items with no segments (entirely synthetic), skipped.

Errors: boundary mismatch (move / overlap / zero; minor 40-80 ms, major 100-300 ms, critical 310-700 ms), missing
segment, missing word, hallucinated word, absorbed filler, plus pt_BR guideline text errors: homophones (concerto/conserto,
sessão/seção, acento/assento, mas/mais ...), dropped accent / tilde / cedilla, colloquial forms (tô/estou, tá/está,
pra/para, cê/você, tava/estava), spelling slips, cut-off words, invented text over (( )). The 67 multi-speaker files
also carry `set_flag multi_speaker = false`.
No capitalisation, punctuation, digit, split or join errors.
