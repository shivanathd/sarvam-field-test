"""UC11v: spoken voice-assistant commands -> tool calls. The voice-input variant of the uc11 tool-calling sub-test.

The same 50 commands (Hindi, Hinglish, Tamil, Bengali; 20 of them hard) are synthesised as audio WITHOUT Sarvam TTS
(macOS `say` Indian voices + gemini-3.8-flash-tts), on clean and phone-line audio, then:
  1. ASR comparison: saaras:v4, saaras:v3 (transcribe mode), gemini-3.8-flash (audio in), gpt-4o-transcribe; every
     transcript goes to the SAME tool model (gemini-3.8-flash, think off, same schema) -> differences come only from ASR.
  2. Stacks: saaras:v4 -> sarvam-105b tools (all-Sarvam); gemini-3.8-flash with audio in + function calling (no ASR step);
     and the text oracle (typed command -> gemini-3.8-flash).

  python suites/uc11v_voice_tools/run.py [synth stt tools score]   (no args = all; resumable, never re-spends)
"""
import json, os, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests
import soundfile as sf
from scipy import signal

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "suites" / "uc11_bharat_code"))
from common.bench import (sarvam_post, log, raw_append, raw_load, write_result, bootstrap_ci, pctl, _retry, DATA,
                          GEMINI_CHAT, GEMINI_TTS)
import tools as T  # uc11's 50 commands, tool schema, scorer and native tool callers

UC = "uc11v_voice_tools"
D = DATA / UC
LANG = {"hi": ("Hindi", "hi-IN", "hi"), "hinglish": ("Hindi (romanised Hinglish)", "hi-IN", "hi"),
        "ta": ("Tamil", "ta-IN", "ta"), "bn": ("Bengali", "bn-IN", "bn")}
SAY_VOICE = {"hi": "Lekha", "ta": "Vani", "bn": "Piya"}  # macOS Indian voices; `say` cannot read romanised Hinglish
GEM_VOICES = ["Kore", "Puck", "Charon", "Aoede", "Fenrir", "Leda"]
CONDS = ("clean", "phone")
STT = ("saaras:v4", "saaras:v3", "gemini-3.8-flash-audio", "gpt-4o-transcribe")
FRACTIONAL = {"h8", "h9", "h10", "x2", "x7", "x9", "x10", "b7", "b8", "b11"}  # dhai/paune/saadhe/dedh/sava, spoken
_lock = threading.Lock()
_gc = None


def spoken(text):
    """How a person says it: phone numbers digit by digit, UPI IDs as 'priya dot s at the rate oksbi'."""
    s = re.sub(r"[0-9০-৯]{10}", lambda m: " ".join(m.group(0)), text)
    s = re.sub(r"(\w+)\.(\w+)@", r"\1 dot \2@", s)
    return s.replace("@", " at the rate ")


# Audit (all four ASR systems agreed on the clean clip, so the TTS, not the ASR, was wrong) -> reworded or re-voiced:
SPOKEN_OVERRIDE = {
    "h9": "9 8 1 2 3 4 5 6 7 0 पर पौने दो हज़ार रुपये ट्रांसफर करो",  # `say` Lekha moved a phone digit before "रुपये"
    "t3": "9 8 7 6 5 0 1 2 3 4 என்ற நம்பருக்கு ஆயிரம் ரூபாய் அனுப்புங்க",  # Vani swallowed the last digit before "-க்கு"
    "t7": "அம்மா நம்பர் 9 4 4 5 5 6 6 7 7 8, அதுக்கு 199 ரூபாய் ரீசார்ஜ் பண்ணு",  # Vani garbled "8-க்கு 199"
    "t8": "ஆயிரத்து ஐநூறு ரூபாய் 9 8 4 0 0 1 2 3 4 5 என்ற நம்பருக்கு அனுப்பு",  # same Vani suffix issue
}
VOICE_OVERRIDE = {"b11": "gemini:Leda"}  # the Bengali `say` voice cannot pronounce the English UPI ID "rina at the rate ybl"
CASES = [{"id": c[0], "lang": c[1], "text": c[2], "spoken": SPOKEN_OVERRIDE.get(c[0], spoken(c[2])), "tool": c[3], "args": c[4]}
         for c in T.CASES]


def gclient():
    global _gc
    if _gc is None:
        from google import genai
        from google.genai import types
        _gc = genai.Client(http_options=types.HttpOptions(timeout=180_000))
    return _gc


def wav(cid, cond):
    return D / "audio" / cond / f"{cid}.wav"


def save(rec):
    with _lock:
        raw_append(UC, rec)


# ---------------- synthesis (same phone-line model as uc01_voice_support) ----------------
def phone_line(x, sr, seed):
    """16 kHz clean -> 8 kHz narrowband (300-3400 Hz) + ~20 dB SNR noise + G.711 mu-law -> back to 16 kHz."""
    y = signal.resample_poly(x, 1, 2)
    b, a = signal.butter(4, [300, 3400], btype="band", fs=8000)
    y = signal.lfilter(b, a, y)
    rng = np.random.default_rng(seed)
    y = y + rng.normal(0, np.sqrt((np.mean(y ** 2) + 1e-12) / 10 ** 2), len(y))
    y = np.clip(y / (np.max(np.abs(y)) + 1e-9) * 0.9, -1, 1)
    mu = 255
    q = np.round((np.sign(y) * np.log1p(mu * np.abs(y)) / np.log1p(mu)) * 127) / 127
    y = np.sign(q) * ((1 + mu) ** np.abs(q) - 1) / mu
    return signal.resample_poly(y, 2, 1).astype(np.float32)


def synth():
    meta_p = D / "synth.json"
    meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    jobs = []
    for i, c in enumerate(CASES):
        say = c["lang"] in SAY_VOICE and i % 2 == 0
        voice = VOICE_OVERRIDE.get(c["id"]) or ("say:" + SAY_VOICE[c["lang"]] if say else "gemini:" + GEM_VOICES[i % len(GEM_VOICES)])
        m = meta.get(c["id"])
        if m and m["spoken_text"] == c["spoken"] and m["voice"] == voice and wav(c["id"], "phone").exists():
            continue
        jobs.append((c, voice))

    def one(job):
        c, voice = job
        src = D / "audio" / "src" / c["id"]
        src.parent.mkdir(parents=True, exist_ok=True)
        usage = {}
        if voice.startswith("say:"):
            src = src.with_suffix(".aiff")
            subprocess.run(["say", "-v", voice[4:], "-o", str(src), c["spoken"]], check=True)
        else:
            from google.genai import types
            cfg = types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice[7:]))))
            r = _retry(lambda: gclient().models.generate_content(model=GEMINI_TTS, contents=c["spoken"], config=cfg))
            part = r.candidates[0].content.parts[0].inline_data
            if "wav" in part.mime_type:
                src = src.with_suffix(".wav"); src.write_bytes(part.data)
            elif "L16" in part.mime_type or "pcm" in part.mime_type:  # raw 24 kHz s16le
                rate = int(re.search(r"rate=(\d+)", part.mime_type).group(1)) if "rate=" in part.mime_type else 24000
                src = src.with_suffix(".wav")
                sf.write(str(src), np.frombuffer(part.data, dtype="<i2").astype(np.float32) / 32768, rate)
            else:
                raise RuntimeError(f"unexpected TTS mime {part.mime_type}")
            usage = {"in_tok": r.usage_metadata.prompt_token_count, "out_tok": r.usage_metadata.candidates_token_count}
        clean = wav(c["id"], "clean")
        clean.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-ar", "16000", "-ac", "1", str(clean)], check=True)
        x, sr = sf.read(str(clean), dtype="float32")
        wav(c["id"], "phone").parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(wav(c["id"], "phone")), phone_line(x, sr, seed=sum(map(ord, c["id"]))), 16000)
        return c["id"], {"voice": voice, "spoken_text": c["spoken"], "audio_s": round(len(x) / sr, 2), **usage}

    with ThreadPoolExecutor(4) as ex:
        for k, v in ex.map(one, jobs):
            meta[k] = v
            meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
            log(UC, "synth", k, v["voice"], v["audio_s"])
    return meta


# ---------------- ASR ----------------
class NoCredit(Exception):
    pass


def stt_saaras(path, lang, model):
    t = time.time()
    with open(path, "rb") as f:
        audio = f.read()
    d = sarvam_post("/speech-to-text", files={"file": (path.name, audio, "audio/wav")},
                    data={"model": model, "mode": "transcribe", "language_code": LANG[lang][1]})
    if d.get("_error") == 402 or re.search(r"credit|quota", str(d.get("_body", "")), re.I):
        raise NoCredit(str(d)[:200])
    if "_error" in d:
        raise RuntimeError(str(d)[:300])
    return {"hyp": d.get("transcript", ""), "ms": (time.time() - t) * 1000}


def stt_gemini(path, lang):
    from google.genai import types
    cfg = types.GenerateContentConfig(temperature=0, max_output_tokens=400, thinking_config=types.ThinkingConfig(thinking_budget=0))
    prompt = (f"Transcribe this voice command. The speaker uses {LANG[lang][0]}. Write exactly what is said in the "
              "language and script it is spoken in; do not translate. Output only the transcript.")
    t = time.time()
    r = _retry(lambda: gclient().models.generate_content(
        model=GEMINI_CHAT, contents=[types.Part.from_bytes(data=path.read_bytes(), mime_type="audio/wav"), prompt], config=cfg))
    u = r.usage_metadata
    return {"hyp": (r.text or "").strip(), "ms": (time.time() - t) * 1000, "in_tok": u.prompt_token_count,
            "out_tok": u.candidates_token_count}


def stt_openai(path, lang):
    audio = path.read_bytes()

    def go():
        r = requests.post("https://api.openai.com/v1/audio/transcriptions", timeout=180,
                          headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
                          files={"file": (path.name, audio, "audio/wav")},
                          data={"model": "gpt-4o-transcribe", "language": LANG[lang][2], "response_format": "json"})
        if r.status_code == 429 and "insufficient_quota" in r.text:
            raise NoCredit(r.text[:200])
        if r.status_code == 429 or r.status_code >= 500:
            raise RuntimeError(f"{r.status_code} {r.text[:200]}")
        if r.status_code != 200:
            raise ValueError(f"{r.status_code} {r.text[:300]}")
        return r.json()
    t = time.time()
    d = _retry(go, tries=4)
    u = d.get("usage") or {}
    return {"hyp": (d.get("text") or "").strip(), "ms": (time.time() - t) * 1000, "openai_usage": u}


def stt():
    done = {(r["id"], r["system"], r["cond"]) for r in raw_load(UC) if r["kind"] == "stt"}
    stopped = set()
    jobs = [(c, s, cond) for s in STT for cond in CONDS for c in CASES if (c["id"], s, cond) not in done]

    def one(job):
        c, s, cond = job
        prov = "sarvam" if s.startswith("saaras") else s
        if prov in stopped:
            return
        p = wav(c["id"], cond)
        try:
            r = (stt_saaras(p, c["lang"], s) if s.startswith("saaras") else stt_gemini(p, c["lang"])
                 if s.startswith("gemini") else stt_openai(p, c["lang"]))
        except NoCredit as e:
            stopped.add(prov); log(UC, "HARD STOP (credits)", prov, str(e)); return
        except Exception as e:
            log(UC, "stt ERROR (retried on rerun)", s, c["id"], cond, str(e)[:200]); return
        save({"kind": "stt", "id": c["id"], "system": s, "cond": cond, "audio_s": sf.info(str(p)).duration, **r})
        log(UC, "stt", s, cond, c["id"], r["hyp"][:60])

    with ThreadPoolExecutor(3) as ex:  # <= 3 concurrent Sarvam requests
        list(ex.map(one, jobs))


# ---------------- tool calling ----------------
def gemini_audio_tools(path):
    """Gemini function calling straight from audio (no transcript step)."""
    from google.genai import types
    decls = [types.FunctionDeclaration(name=t["name"], description=t["description"], parameters_json_schema=t["parameters"])
             for t in T.TOOLS]
    cfg = types.GenerateContentConfig(system_instruction=T.SYSTEM, temperature=0, max_output_tokens=800,
                                      tools=[types.Tool(function_declarations=decls)],
                                      automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                                      thinking_config=types.ThinkingConfig(thinking_budget=0))
    t = time.time()
    r = _retry(lambda: gclient().models.generate_content(
        model=GEMINI_CHAT, contents=[types.Part.from_bytes(data=path.read_bytes(), mime_type="audio/wav")], config=cfg))
    fcs = r.function_calls or []
    u = r.usage_metadata
    return {"call": {"name": fcs[0].name, "args": dict(fcs[0].args or {}), "n_calls": len(fcs)} if fcs else None,
            "text": None if fcs else (r.text or ""), "ms": (time.time() - t) * 1000,
            "in_tok": u.prompt_token_count, "out_tok": u.candidates_token_count}


def tools():
    raw = raw_load(UC)
    hyps = {(r["id"], r["system"], r["cond"]): r["hyp"] for r in raw if r["kind"] == "stt"}
    done = {(r["id"], r["pipeline"], r["cond"]) for r in raw if r["kind"] == "tool"}
    jobs = []
    for c in CASES:
        for cond in CONDS:
            for s in STT:
                if (c["id"], s, cond) in hyps:
                    jobs.append((c, f"{s} -> gemini-3.8-flash", cond, hyps[(c["id"], s, cond)]))
            if (c["id"], "saaras:v4", cond) in hyps:
                jobs.append((c, "saaras:v4 -> sarvam-105b", cond, hyps[(c["id"], "saaras:v4", cond)]))
            jobs.append((c, "gemini-3.8-flash audio-direct", cond, None))
        jobs.append((c, "typed text (oracle) -> gemini-3.8-flash", "text", c["text"]))
    jobs = [j for j in jobs if (j[0]["id"], j[1], j[2]) not in done]
    stop = threading.Event()

    def one(job):
        c, pipe, cond, transcript = job
        if stop.is_set() and "sarvam" in pipe:
            return
        try:
            if pipe.endswith("audio-direct"):
                r = gemini_audio_tools(wav(c["id"], cond))
            elif pipe.endswith("sarvam-105b"):
                r = T.call_sarvam(transcript, False)
            else:
                r = T.call_gemini(transcript, False)
        except Exception as e:
            if re.search(r"402|credit|quota", str(e), re.I):
                stop.set(); log(UC, "HARD STOP (Sarvam credits)", str(e)[:200]); return
            log(UC, "tool ERROR (retried on rerun)", pipe, c["id"], cond, str(e)[:200]); return
        sc = T.score((c["id"], c["lang"], c["text"], c["tool"], c["args"]), r["call"])
        save({"kind": "tool", "id": c["id"], "lang": c["lang"], "pipeline": pipe, "cond": cond, "transcript": transcript,
              "gold": {"name": c["tool"], "args": c["args"]}, **{k: r.get(k) for k in ("call", "text", "ms", "in_tok", "out_tok")},
              **sc})
        log(UC, "tool", pipe, cond, c["id"], "exact" if sc["exact"] else f"MISS {r['call']} <- {str(transcript)[:60]}")

    with ThreadPoolExecutor(3) as ex:
        list(ex.map(one, jobs))


# ---------------- score ----------------
def score():
    raw = raw_load(UC)
    tl = {}
    for r in raw:
        if r["kind"] == "tool":
            tl[(r["id"], r["pipeline"], r["cond"])] = r
    tl = list(tl.values())
    st = {}
    for r in raw:
        if r["kind"] == "stt":
            st[(r["id"], r["system"], r["cond"])] = r
    st = list(st.values())
    def lenient(r):
        """exact, except a UPI handle's name part may differ only in vowel spelling (dipak/deepak, rina/reena):
        that spelling is not recoverable from speech, a real app would confirm it against the contact list."""
        if r["exact"] or not r["call"] or r["call"]["name"] != r["gold"]["name"] or "payee" not in r["gold"]["args"]:
            return r["exact"]
        g, c = dict(r["gold"]["args"]), dict(r["call"].get("args") or {})
        f = lambda v: re.sub(r"ee|i", "i", re.sub(r"oo|u", "u", re.sub(r"aa", "a", str(v).lower())))
        return c.pop("payee", None) is not None and f(r["call"]["args"]["payee"]) == f(g.pop("payee")) and \
            T.norm_args(r["gold"]["name"], c) == T.norm_args(r["gold"]["name"], g)
    for r in tl:
        r["lenient"] = lenient(r)
    pipes = sorted({r["pipeline"] for r in tl}, key=lambda p: (p.startswith("typed"), p))
    ex = lambda rs: bootstrap_ci([1.0 if r["exact"] else 0.0 for r in rs])
    metrics, per_lang = [], {}
    for name, filt in (("exact (all 50)", lambda r: True), ("exact: fractional spoken amounts (10)", lambda r: r["id"] in FRACTIONAL),
                       ("exact: other commands (40)", lambda r: r["id"] not in FRACTIONAL),
                       ("exact: hard 20", lambda r: r["id"] in T.HARD)):
        for cond in ("clean", "phone", "text"):
            vals = {p: ex([r for r in tl if r["pipeline"] == p and r["cond"] == cond and filt(r)]) for p in pipes}
            vals = {p: v for p, v in vals.items() if v["n"]}
            if vals:
                metrics.append({"name": f"tool call {name}, {cond} audio" if cond != "text" else f"tool call {name}, typed text",
                                "higher_is_better": True, "unit": "fraction", "values": vals})
    for cond in ("clean", "phone"):
        vals = {p: bootstrap_ci([1.0 if r["lenient"] else 0.0 for r in tl if r["pipeline"] == p and r["cond"] == cond]) for p in pipes}
        metrics.append({"name": f"tool call exact, payee vowel-spelling tolerant (all 50), {cond} audio", "higher_is_better": True,
                        "unit": "fraction", "values": {p: v for p, v in vals.items() if v["n"]}})
    empty = {s: sum(1 for r in st if r["system"] == s and not r["hyp"].strip()) for s in STT}
    for cond in CONDS:
        for lang in LANG:
            per_lang.setdefault(f"exact ({cond})", {})[lang] = {
                p: ex([r for r in tl if r["pipeline"] == p and r["cond"] == cond and r["lang"] == lang])["mean"] for p in pipes
                if any(r["pipeline"] == p and r["cond"] == cond for r in tl)}
    speed = {s: {"p50_ms": pctl([r["ms"] for r in st if r["system"] == s], .5), "p95_ms": pctl([r["ms"] for r in st if r["system"] == s], .95)}
             for s in STT}
    speed.update({p: {"p50_ms": pctl([r["ms"] for r in tl if r["pipeline"] == p], .5)} for p in pipes})
    usage = {s: {"audio_s": round(sum(r["audio_s"] for r in st if r["system"] == s), 1), "calls": sum(r["system"] == s for r in st)} for s in STT}
    for s in ("saaras:v4", "saaras:v3"):
        usage[s]["est_cost_inr_list_price"] = round(usage[s]["audio_s"] / 3600 * 30, 2)
    sv = [r for r in tl if r["pipeline"] == "saaras:v4 -> sarvam-105b"]
    usage["sarvam-105b (tools)"] = {"calls": len(sv)}
    meta = json.loads((D / "synth.json").read_text())
    usage["gemini-3.8-flash-tts (test audio)"] = {"clips": sum(v["voice"].startswith("gemini") for v in meta.values())}
    # examples: every fractional command, all pipelines on phone audio
    examples = []
    for cid in ("h9", "x9", "b8", "x7", "b7"):
        c = next(x for x in CASES if x["id"] == cid)
        examples.append({"id": cid, "spoken_text": c["spoken"], "gold": {"name": c["tool"], "args": c["args"]},
                         "phone": {r["pipeline"]: {"transcript": r["transcript"], "call": r["call"], "exact": r["exact"]}
                                   for r in tl if r["id"] == cid and r["cond"] == "phone"}})
    res = {"uc": UC, "title": "Voice-in tool calling: spoken Indian-language payment commands",
           "business_question": "When a user SPEAKS 'mera 299 wala recharge kar do' (or the Tamil/Bengali equivalent) into a "
                                "payments app, which speech stack gets the right action with the right arguments?",
           "dataset": {"name": "uc11 tool-calling commands, spoken", "n": len(CASES), "languages": list(LANG), "synthetic": True,
                       "source": "the 50 uc11 commands (30 base + 20 hard); spoken form reads phone numbers digit by digit and "
                                 "'@' as 'at the rate'; audio from macOS say (Lekha/Vani/Piya) and gemini-3.8-flash-tts voices "
                                 "(never Sarvam TTS); phone condition = 8 kHz band-limited + ~20 dB noise + mu-law (uc01 recipe)",
                       "license": "CC-BY-4.0", "audio_s_total": round(sum(v["audio_s"] for v in meta.values()), 1)},
           "systems": pipes, "metrics": metrics, "empty_transcripts_of_100": empty, "per_language": per_lang, "speed": speed, "usage": usage, "examples": examples}
    try:
        import voice_narrative as narrative
        res.update(narrative.make(res, tl, st))
    except ImportError:
        pass
    write_result(UC, res)
    return res


if __name__ == "__main__":
    steps = sys.argv[1:] or ["synth", "stt", "tools", "score"]
    for s in steps:
        globals()[s]()
