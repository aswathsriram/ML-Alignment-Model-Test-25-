# Spanish (es_ES) decoys — strict build, 22 Nov 2026

Input: the platform delivery of 22 Nov 2026 (926 work items, batches 182b012c / 8af2e1d5 / f1266970; not in git)
and the updated `alignment-decoys-template.json`.

| File | What it is |
|---|---|
| `es_ES_decoy_plants.json` | **The upload**: 748 decoys in the align-decoys/v1 template format, keyed on `work_item_id` |
| `es_ES_decoy_review.csv` | One row per mistake: file, word, correct times, what was changed, how to fix it, must-catch |
| `es_ES_dropped.csv` | The 178 work items left out, each with its reason |
| `validation_report.txt` | Output of `validate.py`: every mistake re-checked against the template rules |

## What is planted

1,283 mistakes: two per file in 535 files, one in 213 (clips too short for two mistakes 3 words apart, or with a
single safe place). Exactly one per file is the must-catch (`"critical": true`).

| Mistake | Action | Count |
|---|---|---|
| Boundary mismatch: minor 150-250 ms (287), major 260-440 ms (288), critical 450-700 ms (162) | `move` | 737 |
| Missing word | `delete` | 218 |
| Accent error (también → tambien, fue → fué) | `replace` | 142 |
| Hallucinated word in a pause | `add` | 118 |
| Wrong word, one letter changed (punto → junto) | `replace` | 68 |

Not used: remove, zero, overlap, absorb, join, split, add_noise, replace_unintelligible, set_flag; no capital-letter,
punctuation or digit mistakes.

## Why a fix will be recognised

The delivery holds two independent annotator passes per file (plus an adjudication on 321) and the machine pre-fill.
A mistake is planted only where they prove the correct answer:

- **Same word number in every pass.** The word, and two words either side, are identical at the same index in all
  passes, so the plant lands on the intended word whichever pass the platform holds.
- **Boundary mistakes only on a pause edge the passes agree on (within 30 ms).** The chip either runs into the silence
  of a pause or cuts off part of the word on its pause side. No boundary inside running speech, no neighbour is moved,
  and shifts are 150-700 ms as rule 3 asks (the earlier 40-80 ms shifts were within normal annotator variation).
- **Missing words are deleted, not removed,** and only plain, common, unaccented words said once in the file, at
  least 0.25 s long, touching both neighbours: the hole is exactly the word's span, so the chip added back fits.
- **Hallucinated words** sit in a pause of at least 0.40 s (rule 13: 0.35 s) where the machine pre-fill had no chip.
- **Text mistakes** change exactly one letter of a word all passes agree on; accent pairs that only grammar tells
  apart (que / qué, mas / más, el / él, solo / sólo ...) are never used.

## Dropped (178)

37 with no transcript (synthetic / discarded), 41 with overlapping speech, 1 with a broken delivered alignment,
99 with no place where every pass agrees on word and timing.

## Rebuilding

```bash
pip install wordfreq
python spanish_decoys_2026-11-22/build_spanish_strict.py <deliveries.zip|folder>   # seeded: same output every run
python spanish_decoys_2026-11-22/validate.py <deliveries.zip|folder>
```

The builder takes its language tables from the top of the file; `portuguese_decoys_2026-11-22/` reuses it with the
Portuguese ones. The Spanish output is unchanged by that (checked byte for byte).
