# German (de_DE) decoys — strict build, 23 Nov 2026

Input: the platform delivery of 23 Nov 2026 (501 work items, batches 1477b628 / 190576f1 / 8cf9e216; not in git) and
the updated template (`../spanish_decoys_2026-11-22/alignment-decoys-template.json`).

| File | What it is |
|---|---|
| `de_DE_decoy_plants.json` | **The upload**: 284 decoys in the align-decoys/v1 template format, keyed on `work_item_id` |
| `de_DE_decoy_review.csv` | One row per mistake: file, word, correct times, what was changed, how to fix it, must-catch |
| `de_DE_dropped.csv` | The 217 work items left out, each with its reason |
| `validation_report.txt` | Output of the independent validator: every mistake re-checked against the template rules |

## What is planted

499 mistakes: two per file in 215 files, one in 69 (clips too short for two mistakes 3 words apart, or with a single
safe place). Exactly one per file is the must-catch (`"critical": true`).

| Mistake | Action | Count |
|---|---|---|
| Boundary mismatch: minor 150-250 ms (98), major 260-440 ms (99), critical 450-700 ms (98) | `move` | 295 |
| Missing word | `delete` | 74 |
| Accent error: umlaut dots dropped (für → fur, können → konnen, nächsten → nachsten) | `replace` | 54 |
| Hallucinated word in a pause | `add` | 48 |
| Wrong word, one consonant changed (preis → kreis, licht → sicht) | `replace` | 28 |

Not used: remove, zero, overlap, absorb, join, split, add_noise, replace_unintelligible, set_flag; no capital-letter,
punctuation or digit mistakes.

## Method

The same as the Spanish strict build (`../spanish_decoys_2026-11-22/README.md`): a mistake is planted only where
every annotator pass of the delivery (two blind passes, plus an adjudication on 162 files) has the same word at the
same index and agrees on its timing; boundary mistakes only on an edge next to a pause, 150-700 ms, no neighbour moved;
missing words deleted only when both neighbours touch them; hallucinated words in a pause of at least 0.40 s where the
machine pre-fill had no chip; text mistakes change exactly one letter.

German rules (`build_german_strict.py`):
- **Accent errors** drop the dots of one umlaut — what the machine pre-fill really does in this delivery (für → fur,
  zurück → zuruck) and what the de_DE guideline forbids. Only where the bare form is no word of its own: never
  möchte / mochte, wäre / ware, schön / schon, könnte / konnte. No ß mistakes (strasse is correct Swiss spelling).
- **Wrong words** change one consonant only: a changed vowel is usually another form of the same verb
  (finden / fanden).
- **Never deleted or swapped:** names; function words and auxiliaries; words the guideline says to write as heard
  (habe / hab, nicht / nich, gerade / grad); long words and compounds, and words that may be written as two
  (the guideline leaves that open); number words; adjective endings that are hard to hear (kleinen / kleinem); words
  that sound like another spelling (das / dass, seit / seid, mehr / meer, stadt / statt).

## Dropped (217)

188 with no transcript (entirely synthetic / discarded) and 29 with no place where every pass agrees on word and
timing.

## Rebuilding

```bash
pip install wordfreq
python german_decoys_2026-11-23/build_german_strict.py <deliveries.zip|folder>      # seeded: same output every run
python spanish_decoys_2026-11-22/validate.py <deliveries> german_decoys_2026-11-23 de_DE "a-zäöüß" "a-z" all
```
