# Synthetic audio test: 25 transcripts → 25 .wav + 5 per-language .json

transcripts/ already holds the 25 transcripts (5 each: French, German, Italian, Portuguese, Spanish).
Preview them in transcripts/ALL_TRANSCRIPTS_preview.csv.
Running tts_to_wav.py turns them into:
  output/wav/<id>.wav    the audio (16 kHz mono)
  output/json/<locale>.json  one per language (e.g. de_DE.json): one item per clip with its
                             .wav name, transcript, voice used, duration and word timings

## A. Claude Code in the browser (claude.ai/code)
1. GitHub: create a new PRIVATE repository (github.com/new), then "uploading an existing file" →
   drag in everything from this folder (not .env). Commit.
2. claude.ai/code: connect GitHub when asked, and install the Claude GitHub App on that repository.
3. Environment (selector under the message box → settings icon on your environment):
   - Network access: Custom → Allowed domains: api.elevenlabs.io
     and tick "Also include default list of common package managers".
   - Environment variables: ELEVENLABS_API_KEY=your_key
   Save.
4. Start a session on that repository and send:
   "Follow CLAUDE.md: run the 5-file test, then all 25, then commit and push the output folder."
5. Download: open the branch Claude pushed on GitHub → Code → Download ZIP → output/wav and output/json.

## B. Or on your own computer (no GitHub needed)
1. Install Python 3 (python.org).
2. Copy .env.example to .env and put your key in: ELEVENLABS_API_KEY=sk_...
3. In this folder:  python tts_to_wav.py all --limit 1   (test)   then   python tts_to_wav.py all

## Japanese alignment test set (ja_JP)
25 Japanese clips, each with its own native Japanese ElevenLabs voice:
  output/wav/ja_0001.wav … ja_0025.wav       16 kHz mono
  output/json/ja_JP.json                     the test file, same format as the other languages
  output/answer_key/                         keep these away from whoever inspects the files:
    ja_JP_answer_key.csv / .json             which files are clean, and every planted mistake
    ja_JP_clean.json                         the fully correct alignment of all 25 files
- 20 files sound human ("synthetic": false): breaths, sighs, uneven pauses (eleven_v4 with audio tags).
- 5 files are synthetic ("synthetic": true): no breaths, exactly 0.16 s of silence between every word.
- 18 files are clean. 7 files have planted mistakes: boundary shifts, cut-off words, incorrect
  transcription, missing segments and hallucinated segments.
Rebuild: python make_japanese.py  (audio + clean alignment; --check runs speech-to-text on every clip)
         python inject_errors_ja.py  (plants the mistakes listed in its PLAN)
