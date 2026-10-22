#!/usr/bin/env python3
"""
Make one .wav + one .json per transcript with the ElevenLabs API (no ElevenLabs website needed).
Uses only Python's standard library - nothing to install.

Input  : transcripts/<lang>.jsonl   (already filled: fr, de, it, pt, es - 5 each)
Output : output/wav/<id>.wav        16 kHz mono 16-bit audio      (25 files)
         output/json/<id>.json      transcript, language, voice used, duration, word timings (25 files)

Voices : the 5 transcripts of each language each get a DIFFERENT voice, picked automatically from
         your ElevenLabs account (voices verified for that language first, mixing female/male).
         To force voices, list voice IDs per language in voices.json.

Key    : ELEVENLABS_API_KEY from the environment or a .env file next to this script.
         If no key is set, requests are sent without one (for a Claude Code cloud environment
         where the key is stored as a "network secret" and attached automatically).

Run    : python tts_to_wav.py all              -> all 25
         python tts_to_wav.py all --limit 1    -> 1 per language (5 files) as a cheap test
         python tts_to_wav.py fr de            -> chosen languages only
"""
import argparse, base64, json, os, pathlib, ssl, sys, time, wave
import urllib.request, urllib.error, urllib.parse

HERE = pathlib.Path(__file__).parent
BASE = "https://api.elevenlabs.io/v1"
MODEL = "eleven_multilingual_v2"
SAMPLE_RATE = 16000
VOICES_PER_LANG = 5
LANG_NAME = {"fr": "French (France)", "de": "German (Germany)", "it": "Italian (Italy)",
             "pt": "Portuguese (Brazil)", "es": "Spanish (Spain)"}


def load_env():
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def ssl_context():
    ca = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    return ssl.create_default_context(cafile=ca) if ca and os.path.exists(ca) else ssl.create_default_context()


def call(method, path, key, params=None, body=None):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    headers = {"Accept": "application/json"}
    if key:
        headers["xi-api-key"] = key
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8"); headers["Content-Type"] = "application/json"
    for attempt in range(5):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=120, context=ssl_context()) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503, 504):
                wait = 3 * 2 ** attempt
                print(f"   ElevenLabs {e.code}, retrying in {wait}s"); time.sleep(wait); continue
            if e.code in (401, 403):
                sys.exit(f"ElevenLabs refused the request ({e.code}). Check the API key and that it can use "
                         f"Text to Speech and read Voices.\n{msg}")
            sys.exit(f"ElevenLabs error {e.code}: {msg}")
        except urllib.error.URLError as e:
            sys.exit(f"Could not reach api.elevenlabs.io ({e.reason}). In a Claude Code cloud session, allow "
                     f"the domain api.elevenlabs.io in the environment's network settings.")
    sys.exit("Gave up after repeated rate-limit/server errors.")


_voices = None

def pick_voices(lang, key, fixed):
    ids = [v for v in fixed.get(lang, []) if isinstance(v, str) and v.strip()]
    if ids:
        return [{"voice_id": v, "name": v, "gender": ""} for v in ids]
    global _voices
    if _voices is None:
        _voices = call("GET", "/voices", key).get("voices", [])
        if not _voices:
            sys.exit("No voices found on this ElevenLabs account.")

    def speaks(v):
        return any((l.get("language") or "").lower().startswith(lang) for l in (v.get("verified_languages") or []))

    def gender(v):
        return ((v.get("labels") or {}).get("gender") or "").lower()

    ordered = []
    for group in ([v for v in _voices if speaks(v)], [v for v in _voices if not speaks(v)]):
        f = [v for v in group if gender(v) == "female"]
        m = [v for v in group if gender(v) == "male"]
        while f or m:
            if f: ordered.append(f.pop(0))
            if m: ordered.append(m.pop(0))
        ordered += [v for v in group if gender(v) not in ("female", "male")]
    picked = ordered[:VOICES_PER_LANG]
    if len(picked) < VOICES_PER_LANG:
        print(f"   note: only {len(picked)} voices on the account, so some will repeat")
    return [{"voice_id": v["voice_id"], "name": v.get("name", ""), "gender": gender(v)} for v in picked]


def word_times(alignment, words):
    chars = alignment.get("characters") or []
    st = alignment.get("character_start_times_seconds") or []
    en = alignment.get("character_end_times_seconds") or []
    out, pos = [], 0
    for w in words:
        a, b = pos, pos + len(w)
        if b <= len(chars):
            out.append({"word": w, "start": round(st[a], 3), "end": round(en[b - 1], 3)})
        pos = b + 1                                   # +1 for the space between words
    return out


def run(lang, key, fixed, limit):
    rows = [json.loads(l) for l in (HERE / "transcripts" / f"{lang}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = rows[:limit] if limit else rows
    wav_dir, json_dir = HERE / "output" / "wav", HERE / "output" / "json"
    wav_dir.mkdir(parents=True, exist_ok=True); json_dir.mkdir(parents=True, exist_ok=True)
    pool = pick_voices(lang, key, fixed)
    print(f"[{lang}] voices: " + ", ".join(f"{v['name']} ({v['gender'] or '?'})" for v in pool))
    for i, row in enumerate(rows):
        wav_path, json_path = wav_dir / f"{row['id']}.wav", json_dir / f"{row['id']}.json"
        if wav_path.exists() and json_path.exists():
            print(f"[{lang}] {row['id']} already done, skipping"); continue
        voice = pool[i % len(pool)]
        text = " ".join(row["words"])
        print(f"[{lang}] {i+1}/{len(rows)} {row['id']}  voice={voice['name']}")
        res = call("POST", f"/text-to-speech/{voice['voice_id']}/with-timestamps", key,
                   params={"output_format": f"pcm_{SAMPLE_RATE}"}, body={"text": text, "model_id": MODEL})
        pcm = base64.b64decode(res["audio_base64"])
        with wave.open(str(wav_path), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SAMPLE_RATE); w.writeframes(pcm)
        rec = {"id": row["id"], "audio_file": f"{row['id']}.wav", "language": LANG_NAME.get(lang, lang),
               "spoken_form_transcription": text, "synthetic": True,
               "voice": {"voice_id": voice["voice_id"], "name": voice["name"], "gender": voice["gender"]},
               "tts_model": MODEL, "sample_rate_hz": SAMPLE_RATE,
               "duration_seconds": round(len(pcm) / 2 / SAMPLE_RATE, 3),
               "words": word_times(res.get("alignment") or {}, row["words"])}
        json_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{lang}] done")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("langs", nargs="+", help="fr de it pt es ... or 'all'")
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args()
    load_env()
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if key.startswith("paste_"):
        key = ""
    if not key:
        print("No ELEVENLABS_API_KEY set - sending requests without a key (expects a network secret).")
    langs = sorted(f.stem for f in (HERE / "transcripts").glob("*.jsonl")) if a.langs == ["all"] else a.langs
    vf = HERE / "voices.json"
    fixed = json.loads(vf.read_text(encoding="utf-8")) if vf.exists() else {}
    for lang in langs:
        run(lang, key, fixed, a.limit)
    n = len(list((HERE / "output" / "wav").glob("*.wav")))
    print(f"\nAll done: {n} .wav files in output/wav and {n} .json files in output/json")
