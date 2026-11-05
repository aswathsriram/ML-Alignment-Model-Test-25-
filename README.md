# Forced-alignment decoy packages

The latest deliverables are the five zips in `alignment_decoys/`, one per language:

| Zip | Language |
|---|---|
| `alignment_decoys/alignment_decoys_de_DE.zip` | German |
| `alignment_decoys/alignment_decoys_es_ES.zip` | Spanish (Spain) |
| `alignment_decoys/alignment_decoys_it_IT.zip` | Italian |
| `alignment_decoys/alignment_decoys_pt_BR.zip` | Portuguese (Brazil) |
| `alignment_decoys/alignment_decoys_fr_FR.zip` | French |

Each zip holds 20 audio files, the pre-fill `alignment_prefill_<locale>.json` with the planted errors, the answer
key and everything around it. Start with `README_DEVELOPER.md` inside the zip. Details: `alignment_decoys/README.md`.

## Earlier sets

The earlier sets (first 25 clips in five languages, the Japanese alignment test set, the 25 clean German files)
were removed from this branch to keep downloads small. They are still in the git history at commit `7d5e4f0`:

```bash
git checkout 7d5e4f0 -- output german transcripts inject_errors_ja.py extract_samples.py voices.json
```
