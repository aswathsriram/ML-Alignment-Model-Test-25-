# German test set (de_DE): 25 clean files

- `wav/de_0101.wav … de_0125.wav`: audio, 16 kHz mono, each under 30 s, each with its own native German
  ElevenLabs voice (13 female, 12 male)
- `json/de_DE.json`: the file to ingest, same format as before (fileMetadata + one item per clip: id, name,
  transcript, source with voice, sample rate, duration and word timings). No "synthetic" field.
- `transcripts.jsonl`: the transcripts (spoken form: lowercase, no punctuation, numbers as words,
  spelled letters as "s. m. s.") and the text each voice was given
- `answer_key/de_DE_voice_key.csv` / `.json`: which files are synthetic and which are human-sounding
- `answer_key/de_DE_clean.json`: the same as json/de_DE.json, plus "synthetic": true/false

17 files sound human (breathing, sighs, uneven pauses, fillers like "ähm"). 8 files are synthetic
(de_0102, 0105, 0109, 0112, 0116, 0119, 0122, 0125): no breathing, exactly 0.16 s of silence between
every word. No planted errors: every transcript and word timing is correct.

Rebuild: `python make_japanese.py --lang de` then `python make_japanese.py --lang de --export`
(`--check` runs speech-to-text on every clip).
