# French (fr_FR) decoys — strict build, 23 Nov 2026

Input: the platform delivery of 23 Nov 2026 (1,422 work items, batches 13c12457 / 352d913a / 4b02bbae / dd118483 /
f127d4eb; not in git) and the updated template (`../spanish_decoys_2026-11-22/alignment-decoys-template.json`).

| File | What it is |
|---|---|
| `fr_FR_decoy_plants.json` | **The upload**: 585 decoys in the align-decoys/v1 template format, keyed on `work_item_id` |
| `fr_FR_decoy_review.csv` | One row per mistake: file, word, correct times, what was changed, how to fix it, must-catch |
| `fr_FR_dropped.csv` | The 837 work items left out, each with its reason |
| `validation_report.txt` | Output of the independent validator: every mistake re-checked against the template rules |

## What is planted

1,005 mistakes: two per file in 420 files, one in 165 (clips too short for two mistakes 3 words apart, or with a
single safe place). Exactly one per file is the must-catch (`"critical": true`).

| Mistake | Action | Count |
|---|---|---|
| Boundary mismatch: minor 150-250 ms (229), major 260-440 ms (215), critical 450-700 ms (167) | `move` | 611 |
| Missing word | `delete` | 121 |
| Accent error (était → etait, l'état → l'etat, numéro → numero, très → trés) | `replace` | 115 |
| Hallucinated word in a pause | `add` | 99 |
| Wrong word, one consonant changed (raison → maison, nord → bord) | `replace` | 59 |

Not used: remove, zero, overlap, absorb, join, split, add_noise, replace_unintelligible, set_flag; no capital-letter,
punctuation or digit mistakes. An elided form (l'homme, c'est) is one word and is never split.

## Method

The same as the Spanish strict build (`../spanish_decoys_2026-11-22/README.md`): a mistake is planted only where
every annotator pass of the delivery (two blind passes, plus an adjudication on 289 files) has the same word at the
same index and agrees on its timing; boundary mistakes only on an edge next to a pause, 150-700 ms, no neighbour moved;
missing words deleted only when both neighbours touch them; hallucinated words in a pause of at least 0.40 s where the
machine pre-fill had no chip; text mistakes change exactly one letter.

French rules (`build_french_strict.py`):
- **Accent errors** are planted on words with exactly one accent mark: the mark dropped (what the machine pre-fill
  really does here: etats, l'eglise, l'etat) or è written é. Only where the result is no word of its own: never
  marché / marche, privé / prive, près / prés, and never the pairs only grammar tells apart (a / à, ou / où, la / là,
  sur / sûr, du / dû). Never î or û: boite, connaitre, cout are accepted spellings since the 1990 reform.
- **Missing words** are only words with one possible spelling for their sound. French endings are mostly silent
  (mange / mangent, allé / allée), so a word is deleted only when no same-sounding spelling exists as a word
  (vraiment, maintenant, convaincre), or when it is a noun right after a singular determiner whose only twin is its
  own plural (la maison).
- **Wrong words** change one consonant, never a vowel. The wrong word shows the ending, so only words with a
  same-sounding spelling other than an ending (voie / voix are fine, cent / sans are not) are left out.
- **Never deleted or swapped:** names and places, grammar words, number words, words with a colloquial twin
  (bien / ben, cela / ça).

## Dropped (837)

765 with no transcript (entirely synthetic / discarded) and 72 with no place where every pass agrees on word and
timing.

## Rebuilding

```bash
pip install wordfreq
python french_decoys_2026-11-23/build_french_strict.py <deliveries.zip|folder>      # seeded: same output every run
python spanish_decoys_2026-11-22/validate.py <deliveries> french_decoys_2026-11-23 fr_FR \
    "re:[a-zàâäçéèêëîïôöùûüÿœæ]+(?:['’][a-zàâäçéèêëîïôöùûüÿœæ]+)*" "a-z" all
```
