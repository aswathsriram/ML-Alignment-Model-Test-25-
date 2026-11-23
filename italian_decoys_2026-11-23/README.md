# Italian (it_IT) decoys — strict build, 23 Nov 2026

Input: the platform delivery of 23 Nov 2026 (577 work items, batches 93ac95a4 / 94d120b3 / 99c53623 / a7a67fe7 /
c651a04e; not in git) and the updated template (`../spanish_decoys_2026-11-22/alignment-decoys-template.json`).

| File | What it is |
|---|---|
| `it_IT_decoy_plants.json` | **The upload**: 390 decoys in the align-decoys/v1 template format, keyed on `work_item_id` |
| `it_IT_decoy_review.csv` | One row per mistake: file, word, correct times, what was changed, how to fix it, must-catch |
| `it_IT_dropped.csv` | The 187 work items left out, each with its reason |
| `validation_report.txt` | Output of the independent validator: every mistake re-checked against the template rules |
| `build_report.txt` | Counts printed by the build |

## What is planted

760 mistakes: two per file in 370 files, one in 20 (clips too short for two mistakes 3 words apart, or with a single
safe place). Exactly one per file is the must-catch (`"critical": true`).

| Mistake | Action | Count |
|---|---|---|
| Boundary mismatch: minor 150-250 ms (126), major 260-440 ms (126), critical 450-700 ms (125) | `move` | 377 |
| Missing word | `delete` | 153 |
| Accent error (più → piu, perché → perche, città → citta, qui → quì) | `replace` | 99 |
| Hallucinated word in a pause | `add` | 85 |
| Wrong word, one letter changed (progetto → protetto, ponte → fonte) | `replace` | 46 |

Not used: remove, zero, overlap, absorb, join, split, add_noise, replace_unintelligible, set_flag; no capital-letter,
punctuation or digit mistakes. An elided form (l'italia, dell'anno, c'è, un po') is one word and is never split.

## File names shared by several work items

In this delivery 35 audio file names (for example `000300.000-000600.000_00005.flac`) are used by two or more work
items, and they are different clips. A name like that cannot say which file is meant, so for the 71 decoys on such
files the entry has no `file_name`: the `work_item_id` alone names the file, and `decoy_ref` is the name plus the first
8 characters of the id (`000300.000-000600.000_00005.flac [55a4f8cb]`). The other 319 decoys carry `file_name` as in
the other languages. The review sheet shows the file name on every row.

## Method

The same as the Spanish strict build (`../spanish_decoys_2026-11-22/README.md`): a mistake is planted only where
every annotator pass of the delivery (two blind passes, plus an adjudication on 196 files) has the same word at the
same index and agrees on its timing; boundary mistakes only on an edge next to a pause, 150-700 ms, no neighbour moved;
missing words deleted only when both neighbours touch them; hallucinated words in a pause of at least 0.40 s where the
machine pre-fill had no chip; text mistakes change exactly one letter.

Italian rules (`build_italian_strict.py`):
- **Accent errors** are the accent dropped where the result is only a misspelling (città → citta, perché → perche,
  più → piu, università → universita), or an accent that is never correct on a short word (qui → quì, qua → quà,
  fa → fà, sta → stà, so → sò, va → và, su → sù, fu → fù). Never the pairs only grammar tells apart (e / è, la / là,
  si / sì, ne / né, se / sé, da / dà), never a real twin (papà / papa, metà / meta, però / pero), and never the
  direction of the accent (perché / perchè, così / cosí): annotators themselves differ on it in this delivery.
- **Wrong words** change one letter inside a common word and give another real word that sounds different.
- **Never deleted or swapped:** names and places; grammar words and discourse markers; number words, ordinals and
  punto / virgola; words with a shortened twin (signore / signor, buono / buon); words whose single / double consonant
  or silent h makes another word (anno / hanno, sete / sette, caro / carro); words also written as two
  (innanzitutto / innanzi tutto); English loanwords.

## Dropped (187)

81 with no transcript (entirely synthetic / discarded), 78 with overlapping speech and 28 with no place where every
pass agrees on word and timing.

100 of the 390 work items also have decoys in the earlier `../italian_decoys/italian_decoys_plants.json` (139 work
items, older rules). For those files use this build.

## Rebuilding

```bash
pip install wordfreq
python italian_decoys_2026-11-23/build_italian_strict.py <deliveries.zip|folder>      # seeded: same output every run
python spanish_decoys_2026-11-22/validate.py <deliveries> italian_decoys_2026-11-23 it_IT \
    "re:[a-zàèéìíòóùú]+(?:['’][a-zàèéìíòóùú]+)*['’]?" "a-z" all
```
