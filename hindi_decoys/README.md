# Hindi decoys in the align-decoys/v1 format

Input: `hi_alignment_decoys.json` (125 files, 706 planted errors) and `alignment-decoys-template.json`.
Run: `python hindi_decoys/convert_hindi.py`

| File | What it is |
|---|---|
| `hindi_decoys_plants.json` | **Typed**: one `plants` action per error (move / overlap / replace / delete / split / join / add_noise / set_flag), each with a note naming the Hindi error type and severity |
| `hindi_decoys_decoy_words.json` | **Exact**: the Hindi decoy alignment as `decoy_words`; the platform turns each difference into a mistake. Joined chips are written with spaces (`किस तरीक़े`) so they read as joins, not retyped words |
| `hindi_conversion_report.json` | Counts and, per file, whether the typed plants reproduce the Hindi decoy exactly |

Files are keyed on `file_id` and `file_name` (= audio_id); `decoy_ref` = decoy_id. Word numbers = the answer key's
`gold_index`. Each file has 1-2 `"critical": true` (2 when it has 5+ mistakes). The 6 multi-speaker files carry
`set_flag multi_speaker = false` in both files.

Where the typed form differs from the Hindi decoy (the exact file has none of these):
- 296 boundary moves are under 150 ms (Hindi minors 40-80 ms, majors 100-149 ms); the template suggests 150-700 ms.
- 100 moves go away from a touching neighbour: the platform moves the neighbour along, the Hindi decoy leaves a gap.
- 27 hallucinated words are cut out of the word before them (no 0.35 s pause), so they are sent as `add_noise`
  with the decoy chip's times; the Hindi decoy also shortens that word.
- 27 of the 30 joins are of short words, so the true boundary is under 0.2 s from the chip's middle.
