#!/usr/bin/env python3
"""
Japanese test set: 25 .wav + clean (correct) word alignment, with ElevenLabs. Standard library only.

Input  : transcripts/ja.jsonl  {"id", "language", "words", "style", "voice_id", "tts_text"}
           style "natural"   -> eleven_v4 with [breathes]/[sighs]/... tags and natural pauses (human-like)
           style "synthetic" -> eleven_v4 at full stability, no tags, then every word is cut out and
                                re-joined with exactly the same silence between words (robotic, even timing)
Output : output/wav/<id>.wav                     16 kHz mono 16-bit
         output/answer_key/ja_JP_clean.json      the CORRECT alignment (same format as output/json)
Word timings come from ElevenLabs forced alignment of the audio against the transcript, then corrected
where it lets a pause run into a word or stops short of speech (see snap()).
Deliberate mistakes are added afterwards by inject_errors_ja.py.

Run    : python make_japanese.py            (clips already made are skipped)
         python make_japanese.py --check    (speech-to-text of every clip, to confirm audio = transcript)
"""
import argparse, array, base64, json, math, os, pathlib, sys, time, uuid, wave
import urllib.request, urllib.error
from tts_to_wav import BASE, SAMPLE_RATE, call, load_env, ssl_context, write_locale

HERE = pathlib.Path(__file__).parent
LOCALE = "ja_JP"
WAV_DIR = HERE / "output" / "wav"
CLEAN = HERE / "output" / "answer_key" / f"{LOCALE}_clean.json"
NATURAL = {"model_id": "eleven_v4"}
SYNTHETIC = {"model_id": "eleven_v4",                # v2 misreads Japanese too often
             "voice_settings": {"stability": 1.0, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": False}}
GAP, EDGE, FADE = 0.16, 0.30, 0.004          # synthetic: silence between words / at both ends, fade at cuts (s)
FRAME, MIN_PAUSE, REACH, HOLD = 0.01, 0.15, 0.25, 0.15   # boundary fixing: frame, shortest pause,
                                                         # furthest move, longest dip inside speech (s)


def post_file(path, fields, wav_bytes):
    b = uuid.uuid4().hex
    body = b"".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items())
    body += (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n'
             f'Content-Type: audio/wav\r\n\r\n').encode() + wav_bytes + f"\r\n--{b}--\r\n".encode()
    headers = {"Content-Type": f"multipart/form-data; boundary={b}", "Accept": "application/json"}
    if KEY:
        headers["xi-api-key"] = KEY
    for attempt in range(5):
        req = urllib.request.Request(BASE + path, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=300, context=ssl_context()) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(3 * 2 ** attempt); continue
            sys.exit(f"ElevenLabs error {e.code} on {path}: {msg}")
        except urllib.error.URLError as e:
            sys.exit(f"Could not reach api.elevenlabs.io ({e.reason}).")
    sys.exit("Gave up after repeated rate-limit/server errors.")


def wav_bytes(pcm):
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SAMPLE_RATE); w.writeframes(pcm)
    return buf.getvalue()


def align(pcm, words):
    """Forced alignment on the unspaced transcript; characters are mapped back onto words."""
    res = post_file("/forced-alignment", {"text": "".join(words)}, wav_bytes(pcm))
    chars = [c for c in res.get("characters", []) if c["text"].strip()]
    if "".join(c["text"] for c in chars) != "".join(words):
        sys.exit(f"Forced alignment returned different text: {''.join(c['text'] for c in chars)}")
    out, pos = [], 0
    for w in words:
        span = chars[pos:pos + len(w)]; pos += len(w)
        out.append({"word": w, "start": round(span[0]["start"], 3), "end": round(span[-1]["end"], 3)})
    return out


def frames_db(pcm):
    """Loudness per 10 ms frame (dBFS), median-smoothed over 3 frames."""
    a, n = array.array("h", pcm), int(FRAME * SAMPLE_RATE)
    raw = []
    for i in range(0, len(a) - n + 1, n):
        e = sum(x * x for x in a[i:i + n]) / n
        raw.append(10 * math.log10(e / 32768 ** 2) if e else -120.0)
    return [sorted(raw[max(0, i - 1):i + 2])[len(raw[max(0, i - 1):i + 2]) // 2] for i in range(len(raw))]


def snap(pcm, times):
    """Fix the two mistakes forced alignment makes around pauses, judged against the clip's own loudness:
    1. a word that runs on through a silent pause ends where the silence starts (and if speech follows the
       silence inside that span, the next word starts there);
    2. a boundary that stops short of speech-level sound (also across a stop consonant's short silent hold,
       e.g. the k in eki) is extended to where that sound fades out / begins, at the clip edges too.
    Breaths and sighs are quieter than speech, so they are never pulled into a word."""
    f = frames_db(pcm)
    idx = lambda t: min(len(f), max(0, int(round(t / FRAME))))
    speech = sorted(v for t in times for v in f[idx(t["start"]):idx(t["end"])])
    speech = speech[len(speech) // 2]
    sil, loud, run_len, reach = speech - 20, speech - 8, int(MIN_PAUSE / FRAME), int(REACH / FRAME)
    for i, w in enumerate(times):                                    # 1. silence inside a word
        a, b = idx(w["start"]), idx(w["end"])
        k = a + 3
        while k < b:
            if f[k] < sil:
                j = k
                while j < len(f) and f[j] < sil:
                    j += 1
                rest_loud = j < b and max(f[j:b]) >= loud           # speech again before the word's end
                geminate = "っ" in w["word"] or "ッ" in w["word"]     # っ is a real silent hold inside the word
                if j - k >= run_len and max(f[a:k]) >= loud and not (rest_loud and geminate):
                    w["end"] = round(k * FRAME, 3)
                    if i + 1 < len(times):
                        s1 = idx(times[i + 1]["start"])
                        if j < s1 and s1 - j <= reach and max(f[j:s1]) >= loud:
                            times[i + 1]["start"] = round(j * FRAME, 3)
                    break
                k = j
            else:
                k += 1
    def walk(k, stop, step):
        """From k toward stop, over speech-level frames and dips of at most HOLD (a consonant hold or quiet consonant).
        Returns the frame index just past the last speech-level frame reached, or None."""
        last, dip = None, 0
        while (k < stop if step > 0 else k > stop) and abs(k - start) < reach:
            if f[k if step > 0 else k - 1] >= loud:
                last, dip = k + step, 0
            else:
                dip += 1
                if dip > hold:
                    break
            k += step
        return last

    hold = int(HOLD / FRAME)
    for i in range(-1, len(times)):                                  # 2. speech left outside the words
        e = idx(times[i]["end"]) if i >= 0 else 0
        s1 = idx(times[i + 1]["start"]) if i + 1 < len(times) else len(f)
        if s1 - e < 2:
            continue
        if i >= 0:                                                   # word i stops short of its own sound
            start = e
            k = walk(e, s1, 1)
            if k is not None:
                t = k
                while t < s1 and f[t] >= sil and t - k < 8:          # let the sound fade out (max 80 ms)
                    t += 1
                times[i]["end"] = round(t * FRAME, 3); e = t
        if i + 1 < len(times) and s1 > e:                            # word i+1 starts after its own sound
            start = s1
            k = walk(s1, e, -1)
            if k is not None:
                t = k
                while t > e and f[t - 1] >= sil and k - t < 3:       # soft onset (max 30 ms)
                    t -= 1
                times[i + 1]["start"] = round(t * FRAME, 3)
    for a, b in zip(times, times[1:]):                               # never let rounding make words overlap
        a["end"] = min(a["end"], b["start"])
    return times


def retime(pcm, times):
    """Cut each word out and rejoin with identical silences: perfectly even, machine-like timing."""
    src = array.array("h", pcm)
    sil = lambda s: array.array("h", bytes(2 * int(round(s * SAMPLE_RATE))))
    out, new = sil(EDGE), []
    f = int(FADE * SAMPLE_RATE)
    for i, t in enumerate(times):
        seg = src[int(t["start"] * SAMPLE_RATE):int(t["end"] * SAMPLE_RATE)]
        for k in range(min(f, len(seg) // 2)):
            seg[k] = int(seg[k] * k / f); seg[-1 - k] = int(seg[-1 - k] * k / f)
        start = len(out) / SAMPLE_RATE
        out += seg
        new.append({"word": t["word"], "start": round(start, 3), "end": round(len(out) / SAMPLE_RATE, 3)})
        out += sil(GAP if i < len(times) - 1 else EDGE)
    return out.tobytes(), new


def voice_info(ids):
    info, page = {}, 0
    while set(ids) - set(info) and page < 10:
        r = call("GET", "/shared-voices", KEY, params={"language": "ja", "page_size": 100, "page": page})
        for v in r.get("voices", []):
            info[v["voice_id"]] = {"name": v.get("name", ""), "gender": v.get("gender", "")}
        if not r.get("has_more"):
            break
        page += 1
    return info


def make(rows):
    WAV_DIR.mkdir(parents=True, exist_ok=True); CLEAN.parent.mkdir(parents=True, exist_ok=True)
    done = {it["id"]: it for it in json.loads(CLEAN.read_text(encoding="utf-8"))["items"]} if CLEAN.exists() else {}
    voices = voice_info([r["voice_id"] for r in rows])
    for n, row in enumerate(rows, 1):
        wav_path = WAV_DIR / f"{row['id']}.wav"
        if wav_path.exists() and row["id"] in done:
            print(f"{row['id']} already done, skipping"); continue
        synthetic = row["style"] == "synthetic"
        voice = voices.get(row["voice_id"], {"name": row["voice_id"], "gender": ""})
        print(f"{n}/{len(rows)} {row['id']}  {row['style']}  voice={voice['name']}")
        if wav_path.exists() and not synthetic:           # natural audio already made: only (re)align it
            with wave.open(str(wav_path)) as w:
                pcm = w.readframes(w.getnframes())
        else:
            res = call("POST", f"/text-to-speech/{row['voice_id']}/with-timestamps", KEY,
                       params={"output_format": f"pcm_{SAMPLE_RATE}"},
                       body={"text": row["tts_text"], **(SYNTHETIC if synthetic else NATURAL)})
            pcm = base64.b64decode(res["audio_base64"])
        times = snap(pcm, align(pcm, row["words"]))
        if synthetic:
            pcm, times = retime(pcm, times)
        wav_path.write_bytes(wav_bytes(pcm))
        done[row["id"]] = {"id": row["id"], "name": wav_path.name, "synthetic": synthetic,
                           "transcript": "".join(row["words"]),
                           "source": {"voice": voice, "sample_rate_hz": SAMPLE_RATE,
                                      "duration_seconds": round(len(pcm) / 2 / SAMPLE_RATE, 3), "words": times}}
        write_locale(CLEAN, LOCALE, done)


def check(rows):
    """Speech-to-text each clip and compare with its transcript (spoken numbers/fillers may be written differently)."""
    for row in rows:
        res = post_file("/speech-to-text", {"model_id": "scribe_v1", "language_code": "ja"},
                        (WAV_DIR / f"{row['id']}.wav").read_bytes())
        heard = "".join(c for c in res.get("text", "") if c not in "、。！？… ")
        mark = "OK  " if heard == "".join(row["words"]) else "DIFF"
        print(f"{mark} {row['id']}\n     transcript: {''.join(row['words'])}\n     heard     : {heard}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true")
    a = p.parse_args()
    load_env()
    KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    rows = [json.loads(l) for l in (HERE / "transcripts" / "ja.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    check(rows) if a.check else make(rows)
