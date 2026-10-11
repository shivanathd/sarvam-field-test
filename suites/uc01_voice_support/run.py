"""UC01: code-mixed voice support & collections calls (banks, telecom, insurance).

Steps (each resumable; rerunning never re-spends money):
  synth    make caller audio for every item (macOS `say` Indian voices + gemini TTS; never Sarvam's own TTS)
  stt      saaras:v3 (codemix + transcribe modes) and gemini-3.8-flash on clean + phone-line audio
  whisper  local openai/whisper-large-v3-turbo on Apple MPS (open baseline)
  agent    20-turn voice-agent pipeline latency: STT -> LLM reply -> TTS (Sarvam stack vs Gemini stack)
  score    recompute results/uc01_voice_support.json from results/raw/uc01_voice_support.jsonl

Usage: .venv/bin/python suites/uc01_voice_support/run.py [synth stt whisper agent score]   (no args = all)
"""
import io, json, os, re, subprocess, sys, threading, time, unicodedata, wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests
import soundfile as sf
from scipy import signal

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from common.bench import *  # noqa: E402,F403
from common.bench import _retry  # noqa: E402

UC = "uc01_voice_support"
D = DATA / "uc01"
ITEMS = json.loads((D / "items.json").read_text())
LANG = {"hi": ("Hindi", "Devanagari", "hi-IN"), "ta": ("Tamil", "Tamil", "ta-IN"), "ml": ("Malayalam", "Malayalam", "ml-IN"),
        "bn": ("Bengali", "Bengali", "bn-IN"), "kn": ("Kannada", "Kannada", "kn-IN")}
MIX = {"hi": "Hinglish", "ta": "Tanglish", "ml": "Manglish", "bn": "Benglish", "kn": "Kanglish"}
SAY_VOICE = {"hi": "Lekha", "ta": "Vani", "bn": "Piya", "kn": "Soumya"}  # no Malayalam voice ships with macOS
GEM_VOICES = ["Kore", "Puck", "Charon", "Aoede", "Fenrir", "Leda"]
CONDS = ("clean", "phone")
STT_SYSTEMS = ("saaras:v3-codemix", "saaras:v3-transcribe", "saaras:v4-codemix", "saaras:v4-transcribe", GEMINI_CHAT, "whisper-large-v3-turbo", "whisper-1",
               "gpt-4o-transcribe")
AGENT_IDS = [f"{l}{n}" for l in LANG for n in ("01", "05", "07", "14")]
_lock = threading.Lock()
NO_CREDIT = threading.Event()  # set on Sarvam 402: stop calling Sarvam, record nothing, rerun later
_gc = None


def gclient():
    global _gc
    if _gc is None:
        from google import genai
        from google.genai import types
        _gc = genai.Client(http_options=types.HttpOptions(timeout=180_000))  # ms; calls can otherwise hang forever
    return _gc


def done_keys():
    return {(r["id"], r["system"], r.get("cond")) for r in raw_load(UC) if not r.get("error")}  # failed calls are retried on rerun


def save(rec):
    with _lock:
        raw_append(UC, rec)


def wav_path(item_id, cond):
    return D / "audio" / cond / f"{item_id}.wav"


def duration(p):
    return sf.info(str(p)).duration


# ---------------- synthesis ----------------
def phone_line(x, sr, seed):
    """16 kHz clean -> 8 kHz narrowband (300-3400 Hz) + G.711 mu-law + ~20 dB SNR noise -> back to 16 kHz."""
    y = signal.resample_poly(x, 1, 2)
    b, a = signal.butter(4, [300, 3400], btype="band", fs=8000)
    y = signal.lfilter(b, a, y)
    rng = np.random.default_rng(seed)
    p = np.mean(y ** 2) + 1e-12
    y = y + rng.normal(0, np.sqrt(p / 10 ** (20 / 10)), len(y))
    y = np.clip(y / (np.max(np.abs(y)) + 1e-9) * 0.9, -1, 1)
    mu = 255
    q = np.round((np.sign(y) * np.log1p(mu * np.abs(y)) / np.log1p(mu)) * 127) / 127  # 8-bit mu-law
    y = np.sign(q) * ((1 + mu) ** np.abs(q) - 1) / mu
    return signal.resample_poly(y, 2, 1).astype(np.float32)


def to16k(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-ar", "16000", "-ac", "1", str(dst)], check=True)


def gemini_tts_bytes(prompt, voice):
    from google import genai
    from google.genai import types
    cfg = types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))))
    r = gclient().models.generate_content(model=GEMINI_TTS, contents=prompt, config=cfg)
    part = r.candidates[0].content.parts[0].inline_data
    return part.data, part.mime_type, r.usage_metadata


def synth():
    meta_p = D / "synth.json"
    meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    per_lang = {}
    for it in ITEMS:
        per_lang.setdefault(it["lang"], []).append(it)
    todo = []
    for lang, its in per_lang.items():
        for i, it in enumerate(its):
            if it["id"] in meta and wav_path(it["id"], "phone").exists():
                continue
            use_say = lang in SAY_VOICE and i % 2 == 0
            todo.append((it, "say:" + SAY_VOICE[lang] if use_say else "gemini:" + GEM_VOICES[i % len(GEM_VOICES)]))

    def one(job):
        it, voice = job
        clean = wav_path(it["id"], "clean")
        tmp = D / "audio" / "src" / it["id"]
        tmp.parent.mkdir(parents=True, exist_ok=True)
        usage = {}
        if voice.startswith("say:"):
            src = tmp.with_suffix(".aiff")
            subprocess.run(["say", "-v", voice[4:], "-o", str(src), it["text"]], check=True)
        else:
            # bare text only: any style instruction ("Read aloud as a caller...") got spoken aloud in 38/48 clips
            data, mime, u = _retry(lambda: gemini_tts_bytes(it["text"], voice[7:]))
            if "wav" not in mime:
                raise RuntimeError(f"unexpected TTS mime {mime}")
            src = tmp.with_suffix(".wav")
            src.write_bytes(data)
            usage = {"in_tok": u.prompt_token_count, "out_tok": u.candidates_token_count}
        to16k(src, clean)
        x, sr = sf.read(str(clean), dtype="float32")
        ph = wav_path(it["id"], "phone")
        ph.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(ph), phone_line(x, sr, seed=sum(map(ord, it["id"]))), 16000)
        return it["id"], {"voice": voice, "audio_s": round(len(x) / sr, 2), **usage}

    with ThreadPoolExecutor(4) as ex:
        for k, v in ex.map(one, todo):
            meta[k] = v
            log(UC, "synth", k, v)
            meta_p.write_text(json.dumps(meta, indent=1))
    return meta


# ---------------- STT systems ----------------
def stt_saaras(path, lang, mode, model="saaras:v3"):
    for attempt in range(4):  # bench.sarvam_post re-sends a spent file handle after a 429 -> 400 "Failed to read the file"; reopen + retry
        t = time.time()
        with open(path, "rb") as f:
            d = sarvam_post("/speech-to-text", files={"file": (path.name, f, "audio/wav")},
                            data={"model": model, "mode": mode, "language_code": LANG[lang][2]})
        if "Failed to read the file" not in str(d.get("_body", "")):
            break
        time.sleep(3 * (attempt + 1))
    ms = (time.time() - t) * 1000
    if d.get("_credits") or d.get("_error") == 402 or re.search(r"credit|quota", str(d.get("_body", "")), re.I):
        NO_CREDIT.set()
        raise RuntimeError("Sarvam 402: no credits")
    if "_error" in d:
        return {"hyp": None, "error": d, "ms": ms}
    return {"hyp": d.get("transcript", ""), "ms": ms, "detected": d.get("language_code")}


def gemini_stt_prompt(lang):
    name, script, _ = LANG[lang]
    return (f"Transcribe this customer-care phone call audio. The caller speaks {name} mixed with English. "
            f"Write English words in Latin script and {name} words in {script} script, exactly as spoken; do not translate. "
            "Write all numbers as digits. Output only the transcript.")


def stt_gemini(path, lang):
    from google import genai
    from google.genai import types
    cfg = types.GenerateContentConfig(temperature=0, max_output_tokens=600,
                                      thinking_config=types.ThinkingConfig(thinking_budget=0))
    contents = [types.Part.from_bytes(data=path.read_bytes(), mime_type="audio/wav"), gemini_stt_prompt(lang)]
    t = time.time()
    r = _retry(lambda: gclient().models.generate_content(model=GEMINI_CHAT, contents=contents, config=cfg))
    u = r.usage_metadata
    return {"hyp": (r.text or "").strip(), "ms": (time.time() - t) * 1000,
            "in_tok": u.prompt_token_count, "out_tok": u.candidates_token_count}


OPENAI_STT = ("whisper-1", "gpt-4o-transcribe")


def stt_openai(path, model, lang_code, prompt=None):
    """OpenAI hosted STT. lang_code: ISO-639-1 or None (auto). Unsupported language -> retried once without it."""
    audio = path.read_bytes()  # bytes, not a file handle, so retries re-send the full upload
    data = {"model": model, "response_format": "json", **({"language": lang_code} if lang_code else {}),
            **({"prompt": prompt} if prompt else {})}

    def go():
        r = requests.post("https://api.openai.com/v1/audio/transcriptions", timeout=180,
                          headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
                          files={"file": (path.name, audio, "audio/wav")}, data=data)
        if r.status_code == 429 and "insufficient_quota" in r.text:
            return r.status_code, r.text
        if r.status_code == 429 or r.status_code >= 500:
            raise RuntimeError(f"{r.status_code} {r.text[:200]}")
        return r.status_code, (r.json() if r.status_code == 200 else r.text)

    t = time.time()
    code, d = _retry(go)
    dropped = False
    if code == 400 and "language" in data and "language" in str(d).lower():
        data.pop("language")
        dropped = True
        t = time.time()
        code, d = _retry(go)
    ms = (time.time() - t) * 1000
    if code != 200:
        if "insufficient_quota" in str(d):
            raise RuntimeError("OpenAI insufficient_quota")
        return {"hyp": None, "error": {"_error": code, "_body": str(d)[:500]}, "ms": ms}
    u = d.get("usage") or {}
    return {"hyp": (d.get("text") or "").strip(), "ms": ms, "language_dropped": dropped,
            "in_tok": u.get("input_tokens"), "out_tok": u.get("output_tokens"), "openai_usage": u}


def stt():
    done = done_keys()
    jobs_s, jobs_g, jobs_o = [], [], []
    for it in ITEMS:
        for cond in CONDS:
            p = wav_path(it["id"], cond)
            for ver in ("v3", "v4"):
                for mode in ("codemix", "transcribe"):
                    if (it["id"], f"saaras:{ver}-{mode}", cond) not in done:
                        jobs_s.append((it, cond, p, mode, ver))
            if (it["id"], GEMINI_CHAT, cond) not in done:
                jobs_g.append((it, cond, p))
            for m in OPENAI_STT:
                if (it["id"], m, cond) not in done:
                    jobs_o.append((it, cond, p, m))

    def run_s(j):
        it, cond, p, mode, ver = j
        if NO_CREDIT.is_set():
            return
        r = stt_saaras(p, it["lang"], mode, f"saaras:{ver}")
        save({"id": it["id"], "system": f"saaras:{ver}-{mode}", "cond": cond, "audio_s": duration(p), **r})

    def run_g(j):
        it, cond, p = j
        r = stt_gemini(p, it["lang"])
        save({"id": it["id"], "system": GEMINI_CHAT, "cond": cond, "audio_s": duration(p), **r})

    def run_o(j):  # gpt-4o-transcribe gets the same convention instruction as Gemini; whisper-1 takes no instruction
        it, cond, p, m = j
        r = stt_openai(p, m, it["lang"], gemini_stt_prompt(it["lang"]) if m == "gpt-4o-transcribe" else None)
        save({"id": it["id"], "system": m, "cond": cond, "audio_s": duration(p), **r})

    log(UC, f"stt: {len(jobs_s)} saaras + {len(jobs_g)} gemini + {len(jobs_o)} openai jobs")
    with ThreadPoolExecutor(3) as es, ThreadPoolExecutor(4) as eg, ThreadPoolExecutor(4) as eo:
        fs = ([es.submit(run_s, j) for j in jobs_s] + [eg.submit(run_g, j) for j in jobs_g]
              + [eo.submit(run_o, j) for j in jobs_o])
        for f in fs:
            try:
                f.result()
            except Exception as e:  # 429s that outlast bench's backoff etc.: skip now, a rerun retries
                if not NO_CREDIT.is_set():
                    log(UC, "job failed, will retry on rerun:", str(e)[:150])
    if NO_CREDIT.is_set():
        log(UC, "STOPPED Sarvam calls: 402 no credits")


def whisper():
    import torch
    from transformers import pipeline
    done = done_keys()
    todo = [(it, c) for it in ITEMS for c in CONDS if (it["id"], "whisper-large-v3-turbo", c) not in done]
    if not todo:
        return
    asr = pipeline("automatic-speech-recognition", model="openai/whisper-large-v3-turbo",
                   torch_dtype=torch.float16, device="mps")
    asr(np.zeros(16000, dtype=np.float32), generate_kwargs={"language": "hi", "task": "transcribe"})  # warm-up
    for it, cond in todo:
        p = wav_path(it["id"], cond)
        x, sr = sf.read(str(p), dtype="float32")
        t = time.time()
        out = asr({"raw": x, "sampling_rate": sr}, generate_kwargs={"language": it["lang"], "task": "transcribe"})
        ms = (time.time() - t) * 1000
        save({"id": it["id"], "system": "whisper-large-v3-turbo", "cond": cond, "audio_s": len(x) / sr,
              "hyp": out["text"].strip(), "ms": ms})
        log(UC, "whisper", it["id"], cond, round(ms), out["text"][:60])


# ---------------- voice agent pipeline ----------------
AGENT_SYS = ("You are a phone support agent for an Indian bank, telecom and insurance helpline. Reply in the caller's "
             "language and the same English code-mixing style they use, in one or two short spoken sentences. "
             "Repeat back any number, amount or date the caller gave so they can confirm it. No markdown, no lists.")


def sarvam_tts_stream(text, lang, model="bulbul:v3"):
    h = {"api-subscription-key": os.environ["SARVAM_API_KEY"]}
    speaker = "shubh" if model == "bulbul:v3" else V4_SPEAKER.get(lang)
    body = {"text": text, "target_language_code": LANG[lang][2], "model": model, **({"speaker": speaker} if speaker else {}),
            "output_audio_codec": "mp3"}
    for attempt in range(5):  # shared-account 429s: back off; latency is timed on the successful attempt only
        t = time.time()
        r = requests.post(SARVAM + "/text-to-speech/stream", headers=h, json=body, stream=True, timeout=120)
        if r.status_code != 429:
            break
        time.sleep(2 ** attempt + 1)
    if r.status_code != 200:
        return {"error": f"{r.status_code} {r.text[:300]}"}
    first, buf = None, bytearray()
    for ch in r.iter_content(4096):
        if first is None:
            first = (time.time() - t) * 1000
        buf += ch
    total = (time.time() - t) * 1000
    tmp = D / "agent_tmp.mp3"
    tmp.write_bytes(buf)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(tmp)],
                               capture_output=True, text=True).stdout.strip() or 0)
    return {"ttfb_ms": first, "total_ms": total, "audio_s": dur, "chars": len(text)}


def gemini_tts_stream(text, lang):
    from google import genai
    from google.genai import types
    cfg = types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore"))))
    t, first, nbytes, rate, usage = time.time(), None, 0, 24000, None
    for ch in gclient().models.generate_content_stream(model=GEMINI_TTS, contents=f"Say in a friendly customer-care voice: {text}", config=cfg):
        usage = ch.usage_metadata or usage
        for pt in ((ch.candidates or [None])[0] and ch.candidates[0].content and ch.candidates[0].content.parts) or []:
            if pt.inline_data and pt.inline_data.data:
                if first is None:
                    first = (time.time() - t) * 1000
                m = re.search(r"rate=(\d+)", pt.inline_data.mime_type or "")
                rate = int(m.group(1)) if m else rate
                nbytes += len(pt.inline_data.data)
    return {"ttfb_ms": first, "total_ms": (time.time() - t) * 1000, "audio_s": nbytes / (2 * rate), "chars": len(text),
            "in_tok": usage and usage.prompt_token_count, "out_tok": usage and usage.candidates_token_count}


# stack name -> (STT, reply LLM, TTS). The last two keep Sarvam's speech ends and swap only the LLM.
STACKS = {"agent-sarvam": ("saaras", "sarvam-105b", "bulbul"),
          "agent-gemini": ("gemini", GEMINI_CHAT, "gemini-tts"),
          "agent-openai": ("gpt-4o-transcribe", "openai:gpt-5.4-mini", "gpt-4o-mini-tts"),
          "agent-sarvam-speech+gpt-5.4-mini": ("saaras", "openai:gpt-5.4-mini", "bulbul"),
          "agent-sarvam-speech+claude-haiku-5.5": ("saaras", "or:anthropic/claude-haiku-5.5", "bulbul"),
          "agent-sarvam-v4": ("saaras:v4", "sarvam-105b", "bulbul:v4-flash")}
# bulbul:v4-flash voices are per language ('shubh' is rejected); it has no Malayalam voice, so ml uses the API default
V4_SPEAKER = {"hi": "shubh_hi_customer", "ta": "gokul_ta_narration", "bn": "arnab_bn_conversation", "kn": "chetan_kn_conversation"}


def openai_tts_stream(text):
    body = {"model": "gpt-4o-mini-tts", "voice": "alloy", "input": text, "response_format": "pcm",
            "instructions": "Speak like a friendly Indian customer-care agent, in the language of the text."}
    for attempt in range(5):
        t = time.time()
        r = requests.post("https://api.openai.com/v1/audio/speech", json=body, stream=True, timeout=120,
                          headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]})
        if r.status_code != 429 or "insufficient_quota" in r.text:
            break
        time.sleep(2 ** attempt + 1)
    if r.status_code != 200:
        return {"error": f"{r.status_code} {r.text[:300]}"}
    first, n = None, 0
    for ch in r.iter_content(4096):
        if first is None:
            first = (time.time() - t) * 1000
        n += len(ch)
    return {"ttfb_ms": first, "total_ms": (time.time() - t) * 1000, "audio_s": n / 48000, "chars": len(text)}  # 24 kHz s16 mono


def agent():
    done = done_keys()
    by_id = {it["id"]: it for it in ITEMS}
    for stack, (stt_name, llm_name, tts_name) in STACKS.items():
        for iid in AGENT_IDS:
            if (iid, stack, "clean") in done:
                continue
            it, p = by_id[iid], wav_path(iid, "clean")
            s = (stt_saaras(p, it["lang"], "codemix", "saaras:v4" if stt_name == "saaras:v4" else "saaras:v3")
                 if stt_name.startswith("saaras") else stt_gemini(p, it["lang"]) if stt_name == "gemini"
                 else stt_openai(p, stt_name, it["lang"], gemini_stt_prompt(it["lang"])))
            llm = chat(llm_name, [{"role": "system", "content": AGENT_SYS}, {"role": "user", "content": s["hyp"] or ""}],
                       max_tokens=1000, think=False)
            text = llm["text"]
            tts = (sarvam_tts_stream(text, it["lang"], "bulbul:v4-flash" if tts_name == "bulbul:v4-flash" else "bulbul:v3")
                   if tts_name.startswith("bulbul") else gemini_tts_stream(text, it["lang"])
                   if tts_name == "gemini-tts" else openai_tts_stream(text))
            if tts.get("error") or llm.get("error") or s.get("hyp") is None:
                log(UC, stack, iid, "failed, will retry on rerun:", str(tts.get("error") or llm.get("error") or s.get("error"))[:200])
                continue
            rec = {"id": iid, "system": stack, "cond": "clean", "audio_s": duration(p), "stt": s,
                   "llm": {k: llm.get(k) for k in ("text", "ms", "in_tok", "out_tok", "reasoning_tok", "cost_usd", "error")},
                   "tts": tts}
            save(rec)
            log(UC, stack, iid, f"stt {s['ms']:.0f} llm {llm['ms']:.0f} tts_ttfb {tts.get('ttfb_ms') or -1:.0f}", text[:70])


# ---------------- scoring ----------------
CHILLU = {"ൺ": "ണ്", "ൻ": "ന്", "ർ": "ര്", "ൽ": "ല്", "ൾ": "ള്", "ൿ": "ക്"}
CURRENCY = {"rs", "inr", "rupees", "rupee", "रुपये", "रुपए", "रुपया", "ரூபாய்", "രൂപ", "টাকা", "ರೂಪಾಯಿ"}
MONTHS = {"nov": ["nov", "नवंबर", "नवम्बर", "नोवेंबर", "நவம்ப", "நவெம்ப", "நவம்ப", "നവംബ", "നവമ്പ", "নভেম্বর", "ನವೆಂಬ", "ನವಂಬ"],
          "oct": ["oct", "अक्टूबर", "अक्तूबर", "ऑक्टोबर", "அக்டோப", "ஆக்டோப", "ഒക്ടോബ", "অক্টোবর", "ಅಕ್ಟೋಬ", "ಆಕ್ಟೋಬ"],
          "dec": ["dec", "दिसंबर", "दिसम्बर", "डिसेंबर", "டிசம்ப", "டிசெம்ப", "ഡിസംബ", "ডিসেম্বর", "ಡಿಸೆಂಬ", "ಡಿಸಂಬ"]}  # spelling variants seen
MONTH_NUM = {"oct": "10", "nov": "11", "dec": "12"}


def canon(s):
    """Script-neutral cleanup applied to reference AND hypothesis: NFC, no ZWJ/ZWNJ, atomic chillus, ASCII digits,
    digit groups joined ("4 8 2 1", "2,500", "98450-12367" -> one number), rupee sign dropped."""
    s = unicodedata.normalize("NFC", s or "").replace("‌", "").replace("‍", "")
    for k, v in CHILLU.items():
        s = s.replace(k, v)
    s = "".join(str(unicodedata.digit(c)) if unicodedata.category(c) == "Nd" else c for c in s)
    s = s.replace("₹", " ").lower()
    return re.sub(r"(?<=\d)[\s,\-]+(?=\d)", "", s)


def wer_c(ref, hyp):
    strip = lambda s: " ".join(w for w in norm_text(canon(s)).split() if w not in CURRENCY)
    return wer(strip(ref), strip(hyp)), cer(strip(ref), strip(hyp))


def entity_hits(ents, hyp):
    s = canon(hyp)
    out = []
    for e in ents:
        if e[0] == "date":
            day, mon = e[1], e[2]
            stems = "|".join(map(re.escape, MONTHS[mon]))
            ok = bool(re.search(rf"(?<!\d){day}(?:st|nd|rd|th)?(?!\d).{{0,6}}?(?:{stems})", s)
                      or re.search(rf"(?:{stems})\S*\s*{day}(?!\d)", s)
                      or re.search(rf"(?<!\d)0?{day}[/.\-]{MONTH_NUM[mon]}(?!\d)", s))
        else:
            ok = bool(re.search(rf"(?<!\d){e[1]}(?!\d)", s))
        out.append(ok)
    return out


def script_share(text, script):
    """Share of letters in `script` (code-mixed replies legitimately carry Latin English words)."""
    lo, hi = SCRIPTS[script]
    letters = [c for c in text or "" if c.isalpha()]
    return sum(lo <= ord(c) <= hi for c in letters) / max(1, len(letters))


def score():
    raw = raw_load(UC)
    by_id = {it["id"]: it for it in ITEMS}
    synth_meta = json.loads((D / "synth.json").read_text()) if (D / "synth.json").exists() else {}
    stt_recs = [r for r in raw if r["system"] in STT_SYSTEMS]
    rows = []
    for r in stt_recs:
        it = by_id[r["id"]]
        if r.get("hyp") is None:
            continue
        w, c = (min(1.0, v) for v in wer_c(it["text"], r["hyp"]))  # cap per clip: one hallucination loop can't dominate
        wn = min(1.0, wer_c(it["native"], r["hyp"])[0])
        hits = entity_hits(it["ent"], r["hyp"])
        rows.append({**r, "lang": it["lang"], "wer": w, "cer": c, "wer_best": min(w, wn), "hits": hits})

    def vals(sys_, cond, key):
        return [x[key] for x in rows if x["system"] == sys_ and x["cond"] == cond]

    metrics = []
    for cond in CONDS:
        for key, name, hib, unit in (("wer", "WER vs code-mix reference", False, "fraction"),
                                     ("cer", "CER vs code-mix reference", False, "fraction"),
                                     ("wer_best", "WER, best of code-mix / all-native-script reference", False, "fraction")):
            metrics.append({"name": f"{name} [{cond}]", "higher_is_better": hib, "unit": unit,
                            "values": {s: bootstrap_ci(vals(s, cond, key)) for s in STT_SYSTEMS}})
        metrics.append({"name": f"Entity accuracy (digits/amounts/dates exactly captured) [{cond}]", "higher_is_better": True,
                        "unit": "fraction of entities", "values": {s: bootstrap_ci([float(h) for x in rows if x["system"] == s and x["cond"] == cond for h in x["hits"]]) for s in STT_SYSTEMS}})
        metrics.append({"name": f"Calls with every entity correct [{cond}]", "higher_is_better": True, "unit": "fraction of utterances",
                        "values": {s: bootstrap_ci([float(all(x["hits"])) for x in rows if x["system"] == s and x["cond"] == cond]) for s in STT_SYSTEMS}})

    entity_miss_types = {}  # separates "said the number in words" from "got the digits wrong"
    for cond in CONDS:
        for s_ in STT_SYSTEMS:
            xs = [x for x in rows if x["system"] == s_ and x["cond"] == cond]
            miss = [(x, h) for x in xs for h in x["hits"] if not h]
            words = sum(1 for x, _ in miss if not re.search(r"\d", canon(x["hyp"])))
            entity_miss_types[f"{s_} [{cond}]"] = {"entities": sum(len(x["hits"]) for x in xs), "missed": len(miss),
                                                   "missed_no_digits_in_output": words,
                                                   "missed_digits_wrong_or_partial": len(miss) - words}

    by_source = {}  # fairness check: does gemini STT do better on gemini-TTS audio? (Malayalam excluded: gemini-only)
    for src in ("say", "gemini"):
        for s_ in STT_SYSTEMS:
            xs = [x for x in rows if x["system"] == s_ and x["lang"] != "ml"
                  and synth_meta.get(x["id"], {}).get("voice", "").startswith(src)]
            if xs:
                by_source[f"{src}-voiced audio | {s_}"] = {
                    "n_clips": len(xs), "wer": round(statistics.fmean(x["wer"] for x in xs), 4),
                    "entity_accuracy": round(statistics.fmean(float(h) for x in xs for h in x["hits"]), 4)}

    per_language = {}
    for cond in CONDS:
        for key, mname in (("wer", "WER"), ("ent", "Entity accuracy")):
            tab = {}
            for lang in LANG:
                tab[MIX[lang]] = {}
                for s in STT_SYSTEMS:
                    xs = [x for x in rows if x["system"] == s and x["cond"] == cond and x["lang"] == lang]
                    v = ([float(h) for x in xs for h in x["hits"]] if key == "ent" else [x["wer"] for x in xs])
                    tab[MIX[lang]][s] = round(statistics.fmean(v), 4) if v else None
            per_language[f"{mname} [{cond}]"] = tab

    speed, usage = {}, {}
    for s in STT_SYSTEMS:
        ms = [x["ms"] for x in rows if x["system"] == s]
        aud = [x["audio_s"] for x in rows if x["system"] == s]
        speed[s] = {"p50_ms": pctl(ms, .5), "p95_ms": pctl(ms, .95),
                    "real_time_factor": round(sum(ms) / 1000 / max(1e-9, sum(aud)), 3) if ms else None}
        rs = [r for r in stt_recs if r["system"] == s and not r.get("error")]  # failed calls are not billed
        usage[s] = {"calls": len(rs), "failed_calls_retried": sum(1 for r in stt_recs if r["system"] == s and r.get("error")), "audio_s": round(sum(r["audio_s"] for r in rs), 1),
                    "in_tok": sum(r.get("in_tok") or 0 for r in rs), "out_tok": sum(r.get("out_tok") or 0 for r in rs)}
    for ver in ("v3", "v4"):
        k = f"saaras:{ver} (all modes)"
        usage[k] = {"audio_s": round(sum(usage[s]["audio_s"] for s in STT_SYSTEMS if s.startswith(f"saaras:{ver}")), 1)}
        usage[k]["inr_at_v3_list_price"] = round(usage[k]["audio_s"] / 3600 * 30, 2)
    usage["gemini-tts (test-audio synthesis)"] = {"in_tok": sum(v.get("in_tok", 0) for v in synth_meta.values()),
                                                  "out_tok": sum(v.get("out_tok", 0) for v in synth_meta.values()),
                                                  "clips": sum(v["voice"].startswith("gemini") for v in synth_meta.values())}

    # agent pipeline
    agent_res = {}
    for stack, (stt_name, llm_name, tts_name) in STACKS.items():
        rs = [r for r in raw if r["system"] == stack]
        if not rs:
            continue
        stt_ms = [r["stt"]["ms"] for r in rs]
        llm_ms = [r["llm"]["ms"] for r in rs]
        ttfb = [r["tts"].get("ttfb_ms") for r in rs]
        tts_total = [r["tts"].get("total_ms") for r in rs]
        ttfa = [a + b + c for a, b, c in zip(stt_ms, llm_ms, ttfb) if c is not None]
        lang_ok = [float(script_share(r["llm"]["text"], LANG[by_id[r["id"]]["lang"]][1]) >= 0.3) for r in rs]
        thought = sum(1 for r in rs if (r["llm"].get("reasoning_tok") or 0) > 0)
        echo = [float(h) for r in rs for h in entity_hits(by_id[r["id"]]["ent"], r["llm"]["text"] or "")]
        caller_s = sum(r["audio_s"] for r in rs)
        agent_s = sum(r["tts"].get("audio_s") or 0 for r in rs)
        conv_min = (caller_s + agent_s) / 60
        in_tok = sum(r["llm"].get("in_tok") or 0 for r in rs)
        out_tok = sum(r["llm"].get("out_tok") or 0 for r in rs)
        a = {"turns": len(rs),
             "stt_ms": {"p50": pctl(stt_ms, .5), "p95": pctl(stt_ms, .95)},
             "llm_ms": {"p50": pctl(llm_ms, .5), "p95": pctl(llm_ms, .95)},
             "tts_first_byte_ms": {"p50": pctl(ttfb, .5), "p95": pctl(ttfb, .95)},
             "tts_full_ms": {"p50": pctl(tts_total, .5), "p95": pctl(tts_total, .95)},
             "time_to_first_audio_ms": {"p50": pctl(ttfa, .5), "p95": pctl(ttfa, .95)},
             "reply_in_caller_language_script": bootstrap_ci(lang_ok),
             "turns_with_thinking_tokens_despite_think_off": thought,
             "caller_entities_echoed_correctly": bootstrap_ci(echo),
             "caller_audio_s": round(caller_s, 1), "agent_audio_s": round(agent_s, 1),
             "llm_in_tok": in_tok, "llm_out_tok": out_tok, "tts_chars": sum(r["tts"].get("chars") or 0 for r in rs)}
        a["components"] = {"stt": stt_name, "llm": llm_name, "tts": tts_name}
        per_min = {"llm_in_tok": round(in_tok / conv_min), "llm_out_tok": round(out_tok / conv_min),
                   "tts_chars": round(a["tts_chars"] / conv_min, 1)}
        if stt_name.startswith("saaras"):  # v4 assumed at the v3 list price (no v4 price published to us)
            per_min["inr_saaras_stt"] = round(caller_s / 3600 * 30 / conv_min, 4)
        else:
            per_min["stt_in_tok"] = round(sum(r["stt"].get("in_tok") or 0 for r in rs) / conv_min)
        if tts_name.startswith("bulbul"):  # v4-flash assumed at the v3 price
            per_min["inr_bulbul_tts"] = round(a["tts_chars"] / 1e4 * 30 / conv_min, 4)  # Rs 30 per 10k characters
        if llm_name == "sarvam-105b":
            per_min["inr_sarvam_105b"] = round((in_tok / 1e6 * 15 + out_tok / 1e6 * 60) / conv_min, 4)
        cost = [r["llm"].get("cost_usd") for r in rs if r["llm"].get("cost_usd") is not None]
        if cost:
            per_min["usd_llm_openrouter_reported"] = round(sum(cost) / conv_min, 6)
        if tts_name == "gemini-tts":
            per_min["tts_out_tok"] = round(sum(r["tts"].get("out_tok") or 0 for r in rs) / conv_min)
        inr = [v for k, v in per_min.items() if k.startswith("inr_")]
        if stt_name.startswith("saaras") and llm_name == "sarvam-105b" and tts_name.startswith("bulbul"):
            per_min["inr_total_all_sarvam"] = round(sum(inr), 4)
        a["usage_per_conversation_minute"] = per_min
        agent_res[stack] = a
        usage[stack] = {"calls": len(rs), "audio_s": round(caller_s, 1), "in_tok": in_tok, "out_tok": out_tok,
                        "chars": a["tts_chars"]}

    examples = []
    for iid in ("hi02", "ta06", "ml07", "bn15", "kn05"):
        it = by_id[iid]
        ex = {"id": iid, "mix": MIX[it["lang"]], "reference": it["text"], "gold_entities": it["ent"],
              "voice": synth_meta.get(iid, {}).get("voice"), "outputs": {}}
        for x in rows:
            if x["id"] == iid and x["cond"] == "phone":
                ex["outputs"][x["system"]] = {"hyp": x["hyp"], "wer": round(x["wer"], 3), "entities_ok": x["hits"]}
        examples.append(ex)

    res = {"uc": UC, "title": "Code-mixed voice support & collections calls",
           "business_question": "A bank, telecom or insurer handling Hinglish/Tanglish/Manglish/Benglish/Kanglish calls: which "
                                "speech-to-text gets the caller's card digits, amounts, dates and phone numbers right, and which "
                                "voice-agent stack answers fastest?",
           "dataset": {"name": "uc01 code-mixed customer-care utterances", "source": "authored for this benchmark",
                       "license": "CC-BY-4.0 (this repo)", "n": len(ITEMS), "languages": [MIX[l] for l in LANG],
                       "synthetic": True,
                       "how_made": "80 customer-side utterances (16 per code-mix: card block, UPI failure, EMI/collections, "
                                   "telecom recharge/porting, insurance claims) written by hand with a code-mix reference "
                                   "(English in Latin, Indic in native script, numbers as digits), an all-native-script reference, "
                                   "and gold entities. Audio synthesised with macOS `say` Indian voices (Lekha, Vani, Piya, Soumya) "
                                   "and gemini-3.8-flash-tts voices; Sarvam's TTS was not used so the test does not favour Sarvam. "
                                   "Phone condition: 8 kHz 300-3400 Hz band, G.711 mu-law, ~20 dB SNR noise, back to 16 kHz. "
                                   "Phone numbers are arbitrary, not real customers."},
           "systems": list(STT_SYSTEMS) + list(agent_res), "metrics": metrics, "per_language": per_language,
           "entity_miss_types": entity_miss_types, "by_synthesis_source": by_source, "speed": speed, "agent_pipeline": agent_res, "usage": usage, "examples": examples,
           "findings": [], "caveats": [], "verdict": ""}
    old = RESULTS / f"{UC}.json"
    if old.exists():  # keep hand-written findings/caveats/verdict across re-scores
        prev = json.loads(old.read_text())
        for k in ("findings", "caveats", "verdict"):
            res[k] = prev.get(k) or res[k]
    write_result(UC, res)
    return res, rows


if __name__ == "__main__":
    steps = sys.argv[1:] or ["synth", "stt", "whisper", "agent", "score"]
    for s in steps:
        log(UC, "== step", s)
        globals()[s]()
