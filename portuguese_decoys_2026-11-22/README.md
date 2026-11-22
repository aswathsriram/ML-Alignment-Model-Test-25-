# Portuguese (pt_BR) decoys — strict build, 22 Nov 2026

Input: the platform delivery of 22 Nov 2026 (928 work items, batches 614e9151 / cb32dcec / f37a5b11 / f618854c; not
in git) and the updated template (`../spanish_decoys_2026-11-22/alignment-decoys-template.json`).

| File | What it is |
|---|---|
| `pt_BR_decoy_plants.json` | **The upload**: 789 decoys in the align-decoys/v1 template format, keyed on `work_item_id` |
| `pt_BR_decoy_review.csv` | One row per mistake: file, word, correct times, what was changed, how to fix it, must-catch |
| `pt_BR_dropped.csv` | The 139 work items left out, each with its reason |
| `validation_report.txt` | Output of the independent validator: every mistake re-checked against the template rules |

## What is planted

1,350 mistakes: two per file in 561 files, one in 228 (clips too short for two mistakes 3 words apart, or with a
single safe place). Exactly one per file is the must-catch (`"critical": true`).

| Mistake | Action | Count |
|---|---|---|
| Boundary mismatch: minor 150-250 ms (278), major 260-440 ms (275), critical 450-700 ms (193) | `move` | 746 |
| Missing word | `delete` | 238 |
| Accent error (você → voce, não → nao, posição → posiçao, preço → preco, aqui → aquí) | `replace` | 160 |
| Hallucinated word in a pause | `add` | 132 |
| Wrong word, one letter changed (valor → calor, certo → perto) | `replace` | 74 |

Not used: remove, zero, overlap, absorb, join, split, add_noise, replace_unintelligible, set_flag; no capital-letter,
punctuation or digit mistakes.

## Method

The same as the Spanish strict build (`../spanish_decoys_2026-11-22/README.md`): a mistake is planted only where
every annotator pass of the delivery (two blind passes, plus an adjudication on 337 files) has the same word at the
same index and agrees on its timing; boundary mistakes only on an edge next to a pause, 150-700 ms, no neighbour moved;
missing words deleted only when both neighbours touch them; hallucinated words in a pause of at least 0.40 s where the
machine pre-fill had no chip; text mistakes change exactly one letter.

Portuguese rules (`build_portuguese_strict.py`):
- **Accent errors** drop one mark where the result is only a misspelling — acute, circumflex, tilde or cedilla (the
  pt_BR guideline makes tilde and cedilla mandatory) — or add an accent that was never correct (aqui → aquí, item →
  ítem). Never the pairs only grammar tells apart (a / à / há, tem / têm, vem / vêm, por / pôr, pode / pôde,
  mas / mais) and never pre-2009 spellings (idéia, vôo).
- **Never deleted or swapped:** names and brands; words the guideline says to write as heard (para / pra,
  estava / tava, vamos); words that may be written as two (num, demais); contractions and demonstratives
  (esse / este, desse / nesse); words that sound like another spelling in Brazilian Portuguese (cem / sem, mal / mau,
  alto / auto, sexta / cesta, comprido / cumprido).

## Dropped (139)

8 with no transcript (synthetic / discarded), 42 with overlapping speech, 89 with no place where every pass agrees
on word and timing.

## Rebuilding

```bash
pip install wordfreq
python portuguese_decoys_2026-11-22/build_portuguese_strict.py <deliveries.zip|folder>      # seeded: same output every run
python spanish_decoys_2026-11-22/validate.py <deliveries> portuguese_decoys_2026-11-22 pt_BR "a-zçáàâãéêíóôõúü" "a-z" all
```
