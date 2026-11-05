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

The platform only accepts decoys on its OWN files whose alignment a reviewer has finalized: it looks each decoy up
by `file_id` (and `gold_fingerprint`). So the working flow is: export a pack from the platform, fill its `plants`,
import it back unchanged otherwise.

- `alignment-decoys-pack-de_DE-2026-10-29.json` — the pack exported by the platform with its plants filled
  (6 plants, nothing else changed). This one imports.
  Fill any exported pack: `python alignment_decoys/build_pack.py --fill exported.json filled.json`
- `our-files_not-in-platform_de_DE-2026-10-29.json` — our 20 German files in pack format (90 plants). The platform
  rejects these ("Not a reviewer-finalized alignment") until the 20 audio files are uploaded there, aligned and
  reviewer-finalized; then export them as a pack and fill it with `--fill`.

## align-decoy-kit/v1 kits (`kits/`) — import with our own audio

`kits/alignment_decoy_kit_<locale>.zip` = `decoy_corpus.json` (align-decoy-kit/v1) + `audio/` (20 clips). The platform
imports these directly: no need for the files to exist there first. Only the four families the platform keeps are
used (BND-MAJOR >= 150 ms, WD, WH, SEG-MERGE), 3-6 per clip, each clip with an A1 (must-catch).
All 20 clips import: the platform skips clips tagged `synthetic_speech`, so every clip is tagged `none`; the
entirely synthetic ones are listed in `kits/synthetic_files_<locale>.json`.
Build: `python alignment_decoys/build_kit.py` (uses the same plan as `build_pack.py`).
