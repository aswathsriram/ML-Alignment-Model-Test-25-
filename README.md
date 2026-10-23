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
