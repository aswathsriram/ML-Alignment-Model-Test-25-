# Forced-alignment decoy packages

One zip per language, ready to hand over — each holds everything for that language:

| Zip | Language |
|---|---|
| `alignment_decoys_de_DE.zip` | German |
| `alignment_decoys_es_ES.zip` | Spanish (Spain) |
| `alignment_decoys_it_IT.zip` | Italian |
| `alignment_decoys_pt_BR.zip` | Portuguese (Brazil) |
| `alignment_decoys_fr_FR.zip` | French |

Each zip: 20 audio files (17 human-sounding, 3 entirely synthetic — only the answer key says which), the pre-fill
`alignment_prefill_<locale>.json` (word start/end with the planted errors), the answer key `decoy_corpus.json`,
`decoy_corpus_ALL.csv`, `decoy_corpus_CHANGED.csv`, `decoy_change_manifest.json`, `decoy_summary.xlsx` (bands &
weights), `alignmentDecoyScorer.js`, `run_selftest.js` + `selftest_report.txt`, `README_DEVELOPER.md`,
`OPS_NOTES.md` and the language's guideline PDF. Start with `README_DEVELOPER.md` inside the zip.

Every file carries 3–5 decoys; per language 83 injections: 40 boundary mismatches (minor 40–80 ms, major
100–300 ms, more than 300 ms or into the next word, zero length), 8 missing segments, 8 hallucinated segments,
8 wrong words, 8 segmentation errors, 8 guideline errors, and the 3 synthetic files' "not marked" check.
Score shares: boundary 50 %, the other five groups 10 % each.

## Rebuilding

```bash
python alignment_decoys/build_transcripts.py                 # decoy_spec.txt -> <locale>/transcripts.jsonl
python make_japanese.py --lang decoy-de_DE                   # audio + gold alignment (ElevenLabs), per locale
python alignment_decoys/build_alignment_decoys.py            # plan + inject + package + self-test + zip, all locales
```

`build/` (audio and intermediate files) is not committed; the zips contain everything.

## align-decoys/v1 packs (`packs/`)

`packs/alignment-decoys-pack-<locale>-<date>.json` is the same set in the `align-decoys/v1` pack format: per file
the correct alignment (`words`: i, w, s, e) and 3–6 `plants` (`move` / `remove` / `add` / `join`) that the platform
applies itself. Decoys from the zip that fit the pack rules are carried over; the rest are re-planned.
Build: `python alignment_decoys/build_pack.py de_DE 2026-10-29`.
