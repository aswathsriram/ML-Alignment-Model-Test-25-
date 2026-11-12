#!/usr/bin/env python3
"""
Make the 1000 French clips: audio + correct (gold) word alignment, all human-sounding voices, nothing synthetic.

Per clip:
  1. text-to-speech (eleven_v4, natural: audio tags such as [breathes] kept, no fixed timing), 16 kHz mono
  2. speech-to-text (scribe_v1, fr) of that audio, compared with the transcript; a clip that does not say exactly
     the transcript is made again (up to 3 takes with its voice, then up to 3 with another voice of the same gender)
  3. forced alignment of the audio against the transcript, then snap() (make_japanese.py) to fix the edges
Clips already made are skipped, so the run can be stopped and started again.

Input  : french_1000/transcripts.jsonl
Output : french_1000/build/wav/<id>.wav, french_1000/build/items/<id>.json, french_1000/build/failed.json
Key    : ELEVENLABS_API_KEY from the environment (never printed)
Run    : python french_1000/generate.py [--workers 6] [--limit N] [--ids a,b]
"""
import argparse, base64, concurrent.futures as cf, difflib, io, json, os, pathlib, random, re, ssl, sys, threading, time
import urllib.request, urllib.error, urllib.parse, uuid, wave

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from make_japanese import snap                                                    # noqa: E402

BASE = "https://api.elevenlabs.io/v1"
SR = 16000
BUILD = HERE / "build"
KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
FILLERS = {"euh", "ben", "bah", "hein", "bof", "ouais", "ah", "hmm", "heu", "hm", "mm", "oh", "hum", "mmh", "mh", "bon", "eh"}
FILLER_SPELLINGS = FILLERS - {"ouais", "bon"}         # speech-to-text writes these sounds in several ways (ben -> bah ...)
NUMS = set("""zéro un une deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze seize vingt trente
quarante cinquante soixante cent cents mille million millions milliard et virgule""".split())
LOCK = threading.Lock()


class ApiError(Exception):
    pass


def ctx():
    ca = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    return ssl.create_default_context(cafile=ca) if ca and os.path.exists(ca) else ssl.create_default_context()


def request(path, params=None, body=None, files=None):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    headers = {"Accept": "application/json", "xi-api-key": KEY}
    data = None
    if files is not None:
        b = uuid.uuid4().hex
        fields, wav = files
        data = b"".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items())
        data += (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n'
                 f'Content-Type: audio/wav\r\n\r\n').encode() + wav + f"\r\n--{b}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={b}"
    elif body is not None:
        data = json.dumps(body).encode(); headers["Content-Type"] = "application/json"
    for attempt in range(7):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=300, context=ctx()) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:300]
            if e.code in (401, 403):
                raise SystemExit(f"ElevenLabs refused the key ({e.code}): {msg}")
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(min(60, 3 * 2 ** attempt) + random.random()); continue
            raise ApiError(f"{e.code} on {path}: {msg}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            time.sleep(min(60, 3 * 2 ** attempt))
    raise ApiError(f"gave up on {path}")


def wav_bytes(pcm):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm)
    return buf.getvalue()


def norm(t):
    t = t.lower().replace("’", "'")
    t = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", t)                       # (rires), [breathes]
    t = re.sub(r"[^\w' ]", " ", t.replace("-", " "))
    t = t.replace("y'a", "il y a")
    toks = t.split()
    out = []
    for i, x in enumerate(toks):                                       # "il il y a" after the replace
        if not (x == "il" and toks[i + 1:i + 2] == ["il"]):
            out.append(x)
    return out


def compare(said_words, heard_text):
    """Differences that matter between the transcript and what speech-to-text heard (numbers written as digits and
    fillers left out by speech-to-text are not differences)."""
    said, heard = norm(" ".join(said_words)), norm(heard_text)
    diffs = []
    for op, a1, a2, b1, b2 in difflib.SequenceMatcher(None, said, heard, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        A, B = said[a1:a2], heard[b1:b2]
        if any(re.search(r"\d", x) for x in B) and all(re.search(r"\d", x) or x in ("h", "heures", "heure", "euros", "pour", "cent")
                                                         for x in B) and all(x in NUMS | {"heures", "heure", "euros", "pour"} for x in A):
            continue                                                   # quatorze heures -> 14 h, trente euros -> 30 euros
        if A and B and len(A) == len(B) and all(x in FILLER_SPELLINGS for x in A + B):
            continue                                                   # ben / bah, hmm / hum: the same sound
        if not B and all(x in FILLERS for x in A):
            continue
        if not A and all(x in FILLERS - {"ouais"} for x in B) and len(B) == 1:
            diffs.append(("extra filler", A, B)); continue
        diffs.append((op, A, B))
    return diffs


def tts(row, voice_id):
    url = f"/text-to-speech/{voice_id}/with-timestamps"
    res = request(url, params={"output_format": f"pcm_{SR}"}, body={"text": row["tts_text"], "model_id": "eleven_v4"})
    return base64.b64decode(res["audio_base64"])


def stt(pcm):
    return request("/speech-to-text", files=({"model_id": "scribe_v1", "language_code": "fr", "tag_audio_events": "false"},
                                             wav_bytes(pcm))).get("text", "")


def align(pcm, words):
    res = request("/forced-alignment", files=({"text": " ".join(words)}, wav_bytes(pcm)))
    chars = [c for c in res.get("characters", []) if c["text"].strip()]
    if "".join(c["text"] for c in chars) != "".join(words):
        raise ApiError("forced alignment returned different text")
    out, pos = [], 0
    for w in words:
        span = chars[pos:pos + len(w)]; pos += len(w)
        out.append({"word": w, "start": round(span[0]["start"], 3), "end": round(span[-1]["end"], 3)})
    return out


def make(row, voices):
    out_json = BUILD / "items" / f"{row['id']}.json"
    if out_json.exists():
        return "skip", row["id"]
    same = [v for v in voices[row["gender"]] if v["voice_id"] != row["voice_id"]]
    rng = random.Random(row["id"])
    plan = [row["voice_id"]] * 3 + [v["voice_id"] for v in rng.sample(same, 3)]
    tries = []
    for n, vid in enumerate(plan, 1):
        pcm = tts(row, vid)
        heard = stt(pcm)
        diffs = compare(row["words"], heard)
        tries.append({"voice_id": vid, "heard": heard, "diffs": diffs})
        if diffs:
            continue
        times = snap(pcm, align(pcm, row["words"]))
        short = [t["word"] for t in times if t["end"] - t["start"] < 0.03]
        if short or any(a["end"] > b["start"] for a, b in zip(times, times[1:])):
            tries[-1]["diffs"] = [("alignment", short, [])]          # a word with (almost) no length: new take
            continue
        (BUILD / "wav" / f"{row['id']}.wav").write_bytes(wav_bytes(pcm))
        v = next(x for g in voices.values() for x in g if x["voice_id"] == vid)
        item = {"id": row["id"], "name": f"{row['id']}.wav", "synthetic": False, "transcript": " ".join(row["words"]),
                "source": {"voice": {"name": v["name"], "gender": v["gender"], "voice_id": vid, "age": v.get("age")},
                           "sample_rate_hz": SR, "duration_seconds": round(len(pcm) / 2 / SR, 3), "words": times},
                "takes": n, "stt_heard": heard}
        out_json.write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")
        return "ok", row["id"]
    with LOCK:
        f = BUILD / "failed.json"
        failed = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        failed[row["id"]] = {"tts_text": row["tts_text"], "tries": tries}
        f.write_text(json.dumps(failed, ensure_ascii=False, indent=1), encoding="utf-8")
    return "failed", row["id"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--ids", default="")
    a = p.parse_args()
    if not KEY:
        raise SystemExit("ELEVENLABS_API_KEY is not set")
    (BUILD / "wav").mkdir(parents=True, exist_ok=True); (BUILD / "items").mkdir(parents=True, exist_ok=True)
    rows = [json.loads(l) for l in (HERE / "transcripts.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if a.ids:
        want = set(a.ids.split(","))
        rows = [r for r in rows if r["id"] in want]
    if a.limit:
        rows = rows[:a.limit]
    voices = json.loads((HERE / "voices_fr.json").read_text(encoding="utf-8"))
    count = {"ok": 0, "skip": 0, "failed": 0, "error": 0}
    t0 = time.time()
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(make, r, voices): r["id"] for r in rows}
        for n, fut in enumerate(cf.as_completed(futs), 1):
            try:
                st, rid = fut.result()
            except ApiError as e:
                st, rid = "error", futs[fut]
                print(f"   {rid}: {e}", flush=True)
            count[st] += 1
            if st != "skip" and (n % 10 == 0 or st != "ok"):
                print(f"{n}/{len(rows)} {rid} {st} | {count} | {time.time() - t0:.0f}s", flush=True)
    print(f"done: {count}", flush=True)


if __name__ == "__main__":
    main()
