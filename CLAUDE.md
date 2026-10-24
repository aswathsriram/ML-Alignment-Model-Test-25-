# Synthetic audio test — instructions for Claude Code

## The job
Run `python tts_to_wav.py all`. It reads the 25 ready transcripts in transcripts/*.jsonl
(fr, de, it, pt, es — 5 each) and writes, per transcript:
- output/wav/<id>.wav   (16 kHz mono)
- output/json/<locale>.json, one per language (de_DE, fr_FR, it_IT, pt_BR, es_ES): fileMetadata
  (locale, workitemsCount) + one item per clip (id, name = <id>.wav, transcript, voice, duration, word timings)
Each language's 5 files use 5 different ElevenLabs voices (picked automatically by the script).

## How to run it
1. First a 5-file test: `python tts_to_wav.py all --limit 1`. If it works, run `python tts_to_wav.py all`
   (files already made are skipped, so nothing is paid for twice).
2. The script uses only the Python standard library — no pip install needed.
3. The ElevenLabs key comes from the ELEVENLABS_API_KEY environment variable (cloud environment
   variable or .env), or from a network secret on api.elevenlabs.io. NEVER print, echo, log or
   commit the key, and never write it into any file.
4. If the script says it cannot reach api.elevenlabs.io, stop and tell the user to allow the domain
   `api.elevenlabs.io` in the cloud environment's network settings (Custom access). Don't try workarounds.
5. If it says the key was refused (401/403), stop and tell the user — don't retry in a loop.

## When finished
- Check: 25 .wav and 5 per-language .json in output/, each wav non-empty, each json valid, 25 items in total.
- Commit ONLY the output/ folder (never .env) and push the branch, so the user can download it from GitHub.
- Reply with a short table: id, voice name, duration.

## Later (scaling to 200–300 per language)
New transcripts follow the rules in samples/ (real examples) — spoken form, lowercase, no punctuation,
numbers as words, letters as "s. m. s.", no tags, every transcript new, each clip under 30 s.
Format: {"id": "fr_0006", "language": "fr", "words": ["...", "..."]} one per line in transcripts/<lang>.jsonl.

## Japanese alignment test set
transcripts/ja.jsonl also has "style" (natural/synthetic), "voice_id" and "tts_text" (the text sent to
ElevenLabs, with breath/sigh tags; it must spell exactly the transcript once tags and punctuation are removed).
`python make_japanese.py` makes the audio and the clean alignment (output/answer_key/ja_JP_clean.json);
`python inject_errors_ja.py` writes output/json/ja_JP.json with the planted mistakes in its PLAN and the
answer key. Clean files must stay identical to the clean alignment.
