# French (fr_FR) alignment decoys — 1000 files

The same package as `alignment_decoys/alignment_decoys_fr_FR.zip`, for 1000 new French clips, split into 10
self-contained parts of 100 files (one zip of 1000 wav files would be about 210 MB):

`alignment_decoys_fr_FR_1000_part01of10.zip` … `part10of10.zip` — each holds `audio/` (100 wav, 16 kHz mono), the
pre-fill `alignment_prefill_fr_FR.json` (with the planted errors), the answer key `decoy_corpus.json`, the CSVs, the
change manifest, `decoy_summary.xlsx`, `alignmentDecoyScorer.js`, `run_selftest.js` + `selftest_report.txt`,
`README_DEVELOPER.md`, `OPS_NOTES.md` and the fr_FR guideline PDF. Each part is scored on its own 100 points.
`fr_FR_1000_index.csv` lists all 1000 files: part, decoy_id, file name, voice, gender, duration, errors, transcript.

**Audio:** 1000 transcripts written to the fr_FR guideline (500 female / 500 male speakers, 15-31 words, 4.8-10.4 s,
about 2 hours in total), voiced with ElevenLabs by 50 native French voices (25 female, 25 male; young, middle-aged and
older; 49 of them cloned from real speakers). Every file is natural, human-sounding speech with breathing, sighs and
uneven pauses — none is synthetic or robotic. Every clip was checked by speech-to-text against its transcript and made
again (another take or another voice of the same gender) until it matched. Gold alignment: ElevenLabs forced alignment
plus loudness-based correction at pauses.

**Planted errors:** 3997 (3-5 per file): boundary mismatch 1996 (minor 40-80 ms 499, major 100-300 ms 599, over 300 ms
399, into the next word 250, zero length 250), missing segment 512, hallucinated segment 466, wrong word 511
(homophone, small form change, different word, complete word written cut off, spelling slip, spoken form),
guideline 511 (accent dropped 405, filler misspelt 106). Score shares: boundary 50 %, the other four 12.5 % each.
No split, join, capital-letter, punctuation or digit errors; no synthetic files. Errors are at least 3 words apart,
hallucinated words sit between two words, and no edge is moved inward next to a word it touches, so the same errors
import as align-decoys/v1 plants.
Self-test of every part: every error MISSED on the decoy, CAUGHT on gold (also with ±20 ms jitter).

## The two downloads (export_deliverables.py)

- `fr_FR_1000_audio.zip` (195 MB, not in git: over GitHub's 100 MB limit; the same audio is in the 10 parts) — the 1000
  wav files + `fr_FR.json`, the correct transcription and word timings (no errors), + voice key and README.
  The same JSON without audio: `fr_FR_1000_transcripts.json`.
- `fr_FR_1000_decoy_plants.json` — the 1000 files with their decoys in the align-decoys/v1 format: `words` (correct
  alignment) + `plants` (every planted error as a typed action, 1-2 critical per file). Applying the plants to `words`
  gives each package pre-fill exactly. File names match the audio zip and the package parts.

## Rebuilding

```bash
python french_1000/build_transcripts.py   # spec/batch_*.txt -> transcripts.jsonl (1000 clips, voices)
python french_1000/generate.py            # ElevenLabs audio + speech-to-text check + gold alignment -> build/ (not committed)
python french_1000/build_package.py       # plan + inject + 10 packages + self-test + zips
python french_1000/export_deliverables.py # audio zip + transcripts JSON + decoy plants JSON
```
