# Forced-alignment decoys — instructions for Claude Code

## What is here
- `alignment_decoys/alignment_decoys_<locale>.zip` — the deliverables for de_DE, es_ES, it_IT, pt_BR, fr_FR: 20 files
  per locale, every file with 3-5 planted errors, 3 entirely synthetic per locale (synthetic is never visible in the
  pre-fill). See `alignment_decoys/README.md`.
- `alignment_decoys/decoy_spec.txt` -> `build_transcripts.py` -> `<locale>/transcripts.jsonl`. Transcripts must follow
  that locale's `Forced_Alignment_Guidelines_<locale>.pdf` (spoken form, lowercase, no punctuation, numbers as words,
  hyphens split, elisions/contractions per Part 5); `tts_text` must spell exactly the transcript once tags and
  punctuation are removed.
- `make_japanese.py --lang decoy-<locale>` makes the audio and the gold alignment (alignment_decoys/build/, not
  committed). `tts_to_wav.py` holds the shared ElevenLabs helpers.
- `alignment_decoys/build_alignment_decoys.py` plans and injects the errors, writes the package and the zip, and runs
  the self-test, which must pass: every injection MISSED on the decoy, CAUGHT on gold.
- Planted errors are intended: never "fix" them.

## ElevenLabs key
ELEVENLABS_API_KEY comes from the environment (cloud environment variable or .env). NEVER print, echo, log or
commit the key, and never write it into any file. If api.elevenlabs.io cannot be reached, tell the user to allow
that domain in the environment's network settings; if the key is refused (401/403), stop and tell the user.

## Earlier sets
The earlier output/, german/, transcripts/ sets were removed from this branch; they are in git history at commit
`7d5e4f0` (see README.md for the restore command). make_japanese.py still knows them (`--lang ja`, `--lang de`).
