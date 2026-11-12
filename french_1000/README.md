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

**Planted errors:** 4000 (3-5 per file): boundary mismatch 2000 (minor 40-80 ms 500, major 100-300 ms 600, over 300 ms
399, into the next word 250, zero length 251), missing segment 501, hallucinated segment 498, wrong word 500
(homophone, small form change, different word, complete word written cut off, spelling slip, spoken form),
guideline 501 (accent dropped 378, filler misspelt 123). Score shares: boundary 50 %, the other four 12.5 % each.
No split, join, capital-letter, punctuation or digit errors; no synthetic files.
Self-test of every part: every error MISSED on the decoy, CAUGHT on gold (also with ±20 ms jitter).

## Rebuilding

```bash
python french_1000/build_transcripts.py   # spec/batch_*.txt -> transcripts.jsonl (1000 clips, voices)
python french_1000/generate.py            # ElevenLabs audio + speech-to-text check + gold alignment -> build/ (not committed)
python french_1000/build_package.py       # plan + inject + 10 packages + self-test + zips
```
