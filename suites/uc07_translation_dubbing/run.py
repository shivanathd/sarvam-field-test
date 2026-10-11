"""UC07: localise training content / product copy into Indian languages, then dub it.

Part A  translation  en->xx and xx->en on FLEURS/FLORES parallel sentences, scored with chrF++.
Part B  dubbing      native-script sentence -> TTS -> two independent STT judges -> round-trip CER.

Resumable: every call is stored in results/raw/uc07_translation_dubbing.jsonl keyed by `key`;
rerunning skips finished keys and only recomputes results/uc07_translation_dubbing.json.
Usage:  run.py [api|local|score]   (default: api then score)
"""
import io, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from common.bench import *  # noqa
from common.bench import _retry

UC = "uc07_translation_dubbing"
D = DATA / UC
AUDIO = D / "audio"
ITEMS = json.loads((D / "items.json").read_text())
NAMES = {"en": "English", "hi": "Hindi", "bn": "Bengali", "ta": "Tamil", "te": "Telugu", "kn": "Kannada",
         "ml": "Malayalam", "mr": "Marathi", "gu": "Gujarati", "pa": "Punjabi", "or": "Odia"}
INDIC = [l for l in NAMES if l != "en"]
CODE = {l: ("od" if l == "or" else l) + "-IN" for l in NAMES}  # Sarvam uses od-IN for Odia
API_MT = ["sarvam-translate:v1", "mayura:v1", "sarvam-105b", GEMINI_CHAT]
LOCAL_MT = ["sarvam-30b-local", "qwen3-30b-local"]
CHEAP_MT = ["openai:gpt-5.4-mini", "or:anthropic/claude-haiku-5.5"]  # price-matched tier, full set, think off
FRONTIER_MT = ["gemini-pro-latest", "openai:gpt-5.5", "or:anthropic/claude-sonnet-5.5"]  # ceiling, think on
FRONTIER_N = 3  # frontier subset: first 3 sentences x 10 langs = 30 sentence-language pairs, both directions
COLLOQ_N = 10  # mayura modern-colloquial subset (en->xx only)
LOCAL_N = 8  # local models share a saturated llama-server with other suites (~3 calls/min): first 8 sentences only

DUB_LANGS = ["hi", "bn", "ta", "te", "mr", "kn"]
PROBE_LANGS = ["ml", "gu", "pa", "or"]  # coverage probe: 3 sentences each
VOICE = {"hi": "priya", "bn": "ishita", "ta": "kavitha", "te": "shruti", "mr": "rupali", "kn": "roopa",
         "ml": "ritu", "gu": "neha", "pa": "simran", "or": "pooja"}
GEMINI_VOICE = "Kore"
OPENAI_TTS, OPENAI_VOICE, OPENAI_STT = "openai:gpt-4o-mini-tts", "alloy", "openai:gpt-4o-transcribe"
BULBUL4 = "bulbul:v4-flash"
# v4-flash voices are language-tagged (API validation error lists them); no ml/or voice exists, so those use the
# Hindi edtech voice (the API accepts any voice for any language). Female narration/edtech-style where available.
VOICE_V4 = {"hi": "ritu_hi_edtech", "bn": "roopa_bn_conversational", "ta": "vijay_ta_narration",
            "te": "kavitha_te_narration", "mr": "ritu_mr_narration", "kn": "suchitra_kn_narration",
            "ml": "ritu_hi_edtech", "gu": "pooja_gu_conversational", "pa": "harpreet_pa_narration", "or": "ritu_hi_edtech"}
V4_N = 16  # v4-flash price is undocumented; 16 of the 26 sentences keeps the worst case (v3 price) within INR 40
TTS = ["bulbul:v3", BULBUL4, GEMINI_TTS, OPENAI_TTS]
JUDGES = ["saaras:v3", GEMINI_CHAT, OPENAI_STT]  # gpt-4o-transcribe is the vendor-neutral judge for bulbul vs Gemini
SARVAM_SYSTEMS = {"sarvam-translate:v1", "mayura:v1", "mayura:v1-colloquial", "sarvam-105b", "bulbul:v3", BULBUL4,
                  "saaras:v3"}
BULBUL_LANGS = {"bn", "en", "gu", "hi", "kn", "ml", "mr", "or", "pa", "ta", "te"}  # documented enum (od-IN)
# items with digits are excluded from dubbing: STT judges legitimately write "10" for "ten"
DUB_ITEMS = [it for it in ITEMS if not any(c.isdigit() for l in NAMES for c in it[l])][:30]

_gem = None


def chat_any(system, messages, max_tokens, think=False):
    """bench.chat, except sarvam-30b-local: its GGUF ignores enable_thinking/<|nothink|> and spends the whole
    budget in reasoning_content, so we template via /apply-template, prefill an empty <think></think> and
    call /completion (thinking off, like every other system here)."""
    if system != "sarvam-30b-local" or think:
        return chat(system, messages, max_tokens=max_tokens, think=think)
    url, t = f"http://127.0.0.1:{LOCAL_PORTS[system]}", time.time()
    prompt = requests.post(url + "/apply-template", json={"messages": messages, "chat_template_kwargs": {
        "enable_thinking": False}}, timeout=120).json()["prompt"] + "<think></think>"
    d = _retry(lambda: requests.post(url + "/completion", json={"prompt": prompt, "n_predict": max_tokens,
                                                                "temperature": 0}, timeout=900).json())
    return {"text": d["content"].strip(), "ms": (time.time() - t) * 1000, "in_tok": d.get("tokens_evaluated"),
            "out_tok": d.get("tokens_predicted")}


def gem():
    global _gem
    if _gem is None:
        from google import genai
        _gem = genai.Client(http_options={"timeout": 180_000})  # ms; the SDK default never times out
    return _gem


# ---------------- Part A: translation ----------------
def mt_prompt(src, tgt, text):
    return [{"role": "user", "content": f"Translate the following {NAMES[src]} text into {NAMES[tgt]}. "
                                        f"Output only the translation, nothing else.\n\n{text}"}]


def mt_job(it, lang, direction, system):
    src, tgt = ("en", lang) if direction == "en2xx" else (lang, "en")
    rec = {"key": f"tr|{it['id']}|{lang}|{direction}|{system}", "task": "tr", "id": it["id"], "lang": lang,
           "dir": direction, "system": system, "src": it[src], "ref": it[tgt]}
    t = time.time()
    if system.startswith(("sarvam-translate", "mayura")):
        body = {"input": it[src], "source_language_code": CODE[src], "target_language_code": CODE[tgt],
                "model": system.split("-colloquial")[0]}
        if system.endswith("-colloquial"):
            body["mode"] = "modern-colloquial"
        d = sarvam_post("/translate", body)
        rec.update(hyp=d.get("translated_text", ""), ms=(time.time() - t) * 1000, chars=len(it[src]),
                   error=d.get("_body"))
    else:
        think = system in FRONTIER_MT
        r = chat_any(system, mt_prompt(src, tgt, it[src]), max_tokens=8000 if think else 600, think=think)
        rec.update(hyp=r["text"].strip(), ms=r["ms"], in_tok=r.get("in_tok"), out_tok=r.get("out_tok"),
                   reasoning_tok=r.get("reasoning_tok"), cost_usd=r.get("cost_usd"), error=r.get("error"))
    return rec


# ---------------- Part B: dubbing ----------------
def tts_bulbul(text, lang, model="bulbul:v3"):
    for i in range(6):  # 429 = account-wide rate limit shared with other suites; back off like bench._retry
        t = time.time()
        r = requests.post(SARVAM + "/text-to-speech/stream", headers={"api-subscription-key": os.environ["SARVAM_API_KEY"]},
                          json={"text": text, "target_language_code": CODE[lang], "model": model,
                                "speaker": (VOICE_V4 if model == BULBUL4 else VOICE)[lang], "output_audio_codec": "mp3"},
                          stream=True, timeout=120)
        if r.status_code != 429 and r.status_code < 500:
            break
        time.sleep(min(60, 2 ** i + random.random()))
    if r.status_code != 200:
        return None, {"error": f"{r.status_code} {r.text[:300]}"}
    buf, ttfb = b"", None
    for ch in r.iter_content(2048):
        ttfb = ttfb or (time.time() - t) * 1000
        buf += ch
    return buf, {"ttfb_ms": ttfb, "ms": (time.time() - t) * 1000, "fmt": "mp3"}


def tts_gemini(text, lang):
    from google.genai import types
    cfg = types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=GEMINI_VOICE))))
    t, pcm, ttfb, usage = time.time(), b"", None, None
    for ch in gem().models.generate_content_stream(model=GEMINI_TTS, contents=text, config=cfg):
        usage = ch.usage_metadata or usage
        for p in (ch.candidates[0].content.parts or []) if ch.candidates and ch.candidates[0].content else []:
            if p.inline_data and p.inline_data.data:
                ttfb = ttfb or (time.time() - t) * 1000
                pcm += p.inline_data.data
    if not pcm:
        return None, {"error": "no audio returned"}
    out = io.BytesIO()
    sf.write(out, np.frombuffer(pcm, dtype="<i2"), 24000, format="WAV", subtype="PCM_16")  # audio/l16 rate=24000
    return out.getvalue(), {"ttfb_ms": ttfb, "ms": (time.time() - t) * 1000, "fmt": "wav",
                            "in_tok": usage.prompt_token_count if usage else None,
                            "out_tok": usage.candidates_token_count if usage else None}


def _openai_post(path, **kw):
    for i in range(6):  # back off on 429/5xx like bench._retry
        r = requests.post("https://api.openai.com/v1" + path, timeout=180,
                          headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]}, **kw)
        if r.status_code != 429 and r.status_code < 500:
            return r
        time.sleep(min(60, 2 ** i + random.random()))
    return r


def tts_openai(text, lang):
    t = time.time()
    r = _openai_post("/audio/speech", stream=True, json={
        "model": OPENAI_TTS.split(":")[1], "voice": OPENAI_VOICE, "input": text, "response_format": "mp3",
        "instructions": f"Read this {NAMES[lang]} text aloud with natural, native {NAMES[lang]} pronunciation."})
    if r.status_code != 200:
        return None, {"error": f"{r.status_code} {r.text[:300]}"}
    buf, ttfb = b"", None
    for ch in r.iter_content(2048):
        ttfb = ttfb or (time.time() - t) * 1000
        buf += ch
    return buf, {"ttfb_ms": ttfb, "ms": (time.time() - t) * 1000, "fmt": "mp3"}


def tts_job(it, lang, system):
    rec = {"key": f"tts|{it['id']}|{lang}|{system}", "task": "tts", "id": it["id"], "lang": lang, "system": system,
           "text": it[lang], "chars": len(it[lang])}
    audio, meta = {"bulbul:v3": tts_bulbul, GEMINI_TTS: tts_gemini, OPENAI_TTS: tts_openai,
                   BULBUL4: lambda t, l: tts_bulbul(t, l, BULBUL4)}[system](it[lang], lang)
    rec.update(meta)
    if audio:
        p = AUDIO / system.replace(":", "_") / f"{lang}_{it['id']}.{meta['fmt']}"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(audio)
        rec["path"] = str(p.relative_to(ROOT))
        d, sr = sf.read(p)
        rec["audio_s"] = len(d) / sr
    return rec


def stt_job(tts_rec, judge):
    lang = tts_rec["lang"]
    rec = {"key": f"stt|{tts_rec['id']}|{lang}|{tts_rec['system']}|{judge}", "task": "stt", "id": tts_rec["id"],
           "lang": lang, "tts": tts_rec["system"], "judge": judge, "ref": tts_rec["text"]}
    p = ROOT / tts_rec["path"]
    mime = "audio/mpeg" if p.suffix == ".mp3" else "audio/wav"
    t = time.time()
    if judge == "saaras:v3":
        d = sarvam_post("/speech-to-text", files={"file": (p.name, p.read_bytes(), mime)},
                        data={"model": "saaras:v3", "mode": "transcribe", "language_code": CODE[lang]})
        rec.update(hyp=d.get("transcript", ""), error=d.get("_body"), audio_s=tts_rec["audio_s"])
    elif judge == OPENAI_STT:
        f = {"file": (p.name, p.read_bytes(), mime)}
        r = _openai_post("/audio/transcriptions", files=f, data={"model": judge.split(":")[1], "language": lang})
        if r.status_code == 400:  # language code not accepted -> let the model detect it
            rec["no_language_hint"] = True
            r = _openai_post("/audio/transcriptions", files=f, data={"model": judge.split(":")[1]})
        d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        rec.update(hyp=(d.get("text") or "").strip(), usage=d.get("usage"), audio_s=tts_rec["audio_s"],
                   error=None if r.status_code == 200 else f"{r.status_code} {r.text[:300]}")
    else:
        from google.genai import types
        cfg = types.GenerateContentConfig(temperature=0, thinking_config=types.ThinkingConfig(thinking_budget=0))
        r = _retry(lambda: gem().models.generate_content(model=GEMINI_CHAT, config=cfg, contents=[
            types.Part.from_bytes(data=p.read_bytes(), mime_type=mime),
            f"Transcribe this {NAMES[lang]} speech verbatim in {NAMES[lang]} script. Output only the transcript."]))
        u = r.usage_metadata
        rec.update(hyp=(r.text or "").strip(), in_tok=u.prompt_token_count, out_tok=u.candidates_token_count)
        if not rec["hyp"] and r.prompt_feedback and r.prompt_feedback.block_reason:
            rec["judge_blocked"] = str(r.prompt_feedback.block_reason)  # Gemini intermittently blocks benign audio
    rec["ms"] = (time.time() - t) * 1000
    rec["cer"] = cer(rec["ref"], rec["hyp"]) if rec.get("hyp") else 1.0
    return rec


# ---------------- driver ----------------
def ok(r):
    """A finished record: no API error and a non-empty output (failed calls are retried on rerun)."""
    return not r.get("error") and bool(r.get("hyp") or r.get("text") or r.get("path") or r.get("judge_blocked"))


NO_CREDIT = []  # set once Sarvam answers insufficient_quota_error; remaining Sarvam jobs are skipped


def run(jobs, workers):
    """jobs: list of (key, fn, args). Skips keys already in raw."""
    done = {r["key"] for r in raw_load(UC) if ok(r)}
    todo = [j for j in jobs if j[0] not in done]
    if not todo:
        return
    log(UC, f"running {len(todo)} jobs ({todo[0][0].split('|')[-1]} ...)")

    def go(j):
        if NO_CREDIT and j[0].split("|")[-1] in SARVAM_SYSTEMS:
            return
        try:
            rec = j[1](*j[2])
        except Exception as e:  # keep going; a failed key is retried on the next run
            log(UC, "FAIL", j[0], repr(e)[:300])
            return
        if "insufficient_quota" in str(rec.get("error")):
            NO_CREDIT.append(1)
            log(UC, "Sarvam: no credits; skipping remaining Sarvam jobs")
        raw_append(UC, rec)
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(go, todo))


def workers_for(system):
    return 1 if system in LOCAL_PORTS else (4 if system.startswith(("gemini", "openai:", "or:")) else 3)


def mt_jobs(systems):
    for s in systems:
        items = ITEMS[:LOCAL_N] if s in LOCAL_PORTS else ITEMS[:FRONTIER_N] if s in FRONTIER_MT else ITEMS
        js = [(f"tr|{it['id']}|{l}|{d}|{s}", mt_job, (it, l, d, s)) for it in items for l in INDIC
              for d in ("en2xx", "xx2en")]
        if s == "mayura:v1":
            s2 = "mayura:v1-colloquial"
            js += [(f"tr|{it['id']}|{l}|en2xx|{s2}", mt_job, (it, l, "en2xx", s2)) for it in ITEMS[:COLLOQ_N]
                   for l in INDIC]
        run(js, workers_for(s))


def dub_jobs():
    pairs = [(it, l) for l in DUB_LANGS for it in DUB_ITEMS] + [(it, l) for l in PROBE_LANGS for it in DUB_ITEMS[:3]]
    pairs4 = [(it, l) for l in DUB_LANGS for it in DUB_ITEMS[:V4_N]] + [(it, l) for l in PROBE_LANGS for it in DUB_ITEMS[:3]]
    for s in TTS:
        run([(f"tts|{it['id']}|{l}|{s}", tts_job, (it, l, s)) for it, l in (pairs4 if s == BULBUL4 else pairs)],
            workers_for(s))
    tts = [r for r in raw_load(UC) if r["task"] == "tts" and r.get("path")]
    for j in JUDGES:
        run([(f"stt|{r['id']}|{r['lang']}|{r['system']}|{j}", stt_job, (r, j)) for r in tts], workers_for(j))


# ---------------- scoring ----------------
def first_par(s):
    return next((x.strip() for x in (s or "").split("\n\n") if x.strip()), "")


def latin_share(s):
    letters = [c for c in s if c.isalpha()]
    return sum(c.isascii() for c in letters) / max(1, len(letters))


def score():
    latest = {r["key"]: r for r in raw_load(UC)}.values()  # last write wins
    raw = [r for r in latest if ok(r)]  # drop failed calls (credits, rate limits); they are retried on rerun
    refused = [r for r in latest if r["task"] == "tts" and not ok(r) and "429" not in str(r.get("error"))
               and "insufficient_quota" not in str(r.get("error"))]  # genuine refusals, e.g. unsupported language
    tr = [r for r in raw if r["task"] == "tr"]
    for r in tr:
        r["verbose"] = len([x for x in r["hyp"].split("\n\n") if x.strip()]) > 1
        r["hyp"] = first_par(r["hyp"])  # e.g. sarvam-30b appends an unrequested "Explanation" section
        r["chrf"] = chrf(r["ref"], r["hyp"]) if r.get("hyp") else 0.0
    mt_systems = [s for s in API_MT + CHEAP_MT + FRONTIER_MT + LOCAL_MT if any(r["system"] == s for r in tr)]
    metrics, per_lang, speed, usage = [], {}, {}, {}
    for d, label in (("en2xx", "chrF++ English->Indic"), ("xx2en", "chrF++ Indic->English")):
        metrics.append({"name": label, "higher_is_better": True, "unit": "chrF++ (0-100)", "values": {
            s: bootstrap_ci([r["chrf"] for r in tr if r["system"] == s and r["dir"] == d]) for s in mt_systems}})
        per_lang[label] = {l: {s: round(statistics.fmean(v), 1) if (v := [r["chrf"] for r in tr if r["system"] == s
                                                                         and r["dir"] == d and r["lang"] == l]) else None
                               for s in mt_systems} for l in INDIC}
    loc = {it["id"] for it in ITEMS[:LOCAL_N]}  # same-sentence comparison including the local models
    for d, label in (("en2xx", "chrF++ English->Indic, 8-sentence subset (all systems)"),
                     ("xx2en", "chrF++ Indic->English, 8-sentence subset (all systems)")):
        metrics.append({"name": label, "higher_is_better": True, "unit": "chrF++ (0-100)", "values": {
            s: bootstrap_ci([r["chrf"] for r in tr if r["system"] == s and r["dir"] == d and r["id"] in loc])
            for s in mt_systems}})
    fr = {it["id"] for it in ITEMS[:FRONTIER_N]}
    for d, label in (("en2xx", "chrF++ English->Indic, frontier subset: 30 sentence-language pairs (all systems)"),
                     ("xx2en", "chrF++ Indic->English, frontier subset: 30 sentence-language pairs (all systems)")):
        metrics.append({"name": label, "higher_is_better": True, "unit": "chrF++ (0-100)", "values": {
            s: bootstrap_ci([r["chrf"] for r in tr if r["system"] == s and r["dir"] == d and r["id"] in fr])
            for s in mt_systems}})
    # mayura formal vs colloquial on the same subset
    sub = {it["id"] for it in ITEMS[:COLLOQ_N]}
    col = {s: [r for r in tr if r["system"] == s and r["dir"] == "en2xx" and r["id"] in sub]
           for s in ("mayura:v1", "mayura:v1-colloquial")}
    if col["mayura:v1-colloquial"]:
        metrics.append({"name": "Mayura formal vs modern-colloquial: chrF++ vs formal reference (en->xx subset)",
                        "higher_is_better": True, "unit": "chrF++", "values": {
                            s: bootstrap_ci([r["chrf"] for r in v]) for s, v in col.items()}})
        metrics.append({"name": "Mayura formal vs modern-colloquial: share of Latin letters in output",
                        "higher_is_better": None, "unit": "fraction", "values": {
                            s: bootstrap_ci([latin_share(r["hyp"]) for r in v]) for s, v in col.items()}})
    for s in mt_systems + ["mayura:v1-colloquial"]:
        rs = [r for r in tr if r["system"] == s]
        if not rs:
            continue
        speed[s] = {"p50_ms": pctl([r["ms"] for r in rs], .5), "p95_ms": pctl([r["ms"] for r in rs], .95)}
        usage[s] = {"calls": len(rs), "chars": sum(r.get("chars") or 0 for r in rs),
                    "in_tok": sum(r.get("in_tok") or 0 for r in rs), "out_tok": sum(r.get("out_tok") or 0 for r in rs),
                    "reasoning_tok": sum(r.get("reasoning_tok") or 0 for r in rs),
                    "cost_usd": round(sum(r.get("cost_usd") or 0 for r in rs), 4),
                    "verbose_replies": sum(1 for r in rs if r["verbose"]),
                    "errors": sum(1 for r in rs if r.get("error") or not r.get("hyp"))}
    wrong_script = {s: sum(1 for r in tr if r["system"] == s and r["dir"] == "en2xx" and r.get("hyp")
                           and dominant_script(r["hyp"]) != dominant_script(r["ref"])) for s in mt_systems}

    # dubbing
    tts = [r for r in raw if r["task"] == "tts"]
    stt = [r for r in raw if r["task"] == "stt"]  # judge-blocked calls stay in, scored as CER 1.0 (failures)
    blocked = sum(1 for r in raw if r.get("judge_blocked"))
    main = set(DUB_LANGS)
    for j in JUDGES:
        metrics.append({"name": f"Dubbing intelligibility: round-trip CER, judge={j}", "higher_is_better": False,
                        "unit": "CER (0-1+)", "values": {t: bootstrap_ci([r["cer"] for r in stt if r["tts"] == t and
                                                                          r["judge"] == j and r["lang"] in main])
                                                         for t in TTS}})
        per_lang[f"Dubbing CER judge={j}"] = {l: {t: round(statistics.fmean(v), 3) if (v := [
            r["cer"] for r in stt if r["tts"] == t and r["judge"] == j and r["lang"] == l]) else None for t in TTS}
            for l in DUB_LANGS + PROBE_LANGS}
    v4ids = {it["id"] for it in DUB_ITEMS[:V4_N]}
    for j in JUDGES:
        metrics.append({"name": f"Dubbing CER, judge={j}, bulbul:v4-flash matched subset ({V4_N} sentences x 6 langs)",
                        "higher_is_better": False, "unit": "CER (0-1+)", "values": {
                            t: bootstrap_ci([r["cer"] for r in stt if r["tts"] == t and r["judge"] == j and
                                             r["lang"] in main and r["id"] in v4ids]) for t in TTS}})
    for name, f in (("TTS time to first audio byte", "ttfb_ms"), ("TTS time to full audio", "ms")):
        metrics.append({"name": name, "higher_is_better": False, "unit": "ms", "values": {
            t: bootstrap_ci([r.get(f) for r in tts if r["system"] == t and r["lang"] in main]) for t in TTS}})
    metrics.append({"name": "TTS audio duration per sentence", "higher_is_better": None, "unit": "s", "values": {
        t: bootstrap_ci([r.get("audio_s") for r in tts if r["system"] == t and r["lang"] in main]) for t in TTS}})
    for t in TTS:
        rs = [r for r in tts if r["system"] == t]
        speed[t] = {"p50_ms": pctl([r.get("ms") for r in rs], .5), "p95_ms": pctl([r.get("ms") for r in rs], .95),
                    "ttfb_p50_ms": pctl([r.get("ttfb_ms") for r in rs], .5),
                    "ttfb_p95_ms": pctl([r.get("ttfb_ms") for r in rs], .95)}
        chars = sum(r["chars"] for r in rs)
        usage[t] = {"calls": len(rs), "chars": chars, "audio_s": round(sum(r.get("audio_s") or 0 for r in rs), 1),
                    "in_tok": sum(r.get("in_tok") or 0 for r in rs), "out_tok": sum(r.get("out_tok") or 0 for r in rs),
                    "errors": sum(1 for r in rs if r.get("error"))}
        if t == "bulbul:v3":
            usage[t]["cost_inr"] = round(chars / 1e4 * 30, 2)
            usage[t]["cost_per_10k_chars"] = "INR 30 (Sarvam list price, bulbul:v3)"
        elif t == BULBUL4:
            usage[t]["cost_inr_if_v3_price"] = round(chars / 1e4 * 30, 2)
            usage[t]["cost_per_10k_chars"] = "not on the Sarvam pricing page at test time; v3 price used as upper bound"
        elif t == OPENAI_TTS:
            usage[t]["cost_usd_approx"] = round(usage[t]["audio_s"] / 60 * 0.015, 3)
            usage[t]["cost_note"] = "approx. US$0.015 per audio minute (OpenAI list estimate for gpt-4o-mini-tts)"
            usage[t]["cost_usd_per_10k_chars_approx"] = round(usage[t]["cost_usd_approx"] / max(1, chars) * 1e4, 3)
        else:
            usage[t]["audio_tokens_per_10k_chars"] = round(usage[t]["out_tok"] / max(1, chars) * 1e4)
    for j in JUDGES:
        rs = [r for r in stt if r["judge"] == j]
        usage[f"judge:{j}"] = {"calls": len(rs), "audio_s": round(sum(r.get("audio_s") or 0 for r in rs), 1),
                               "in_tok": sum(r.get("in_tok") or 0 for r in rs),
                               "out_tok": sum(r.get("out_tok") or 0 for r in rs)}
        if j == OPENAI_STT:
            usage[f"judge:{j}"]["cost_usd_approx"] = round(usage[f"judge:{j}"]["audio_s"] / 60 * 0.006, 3)
    coverage = {l: {t: {"ok": sum(1 for r in tts if r["system"] == t and r["lang"] == l and r.get("path")),
                        "refused": sum(1 for r in refused if r["system"] == t and r["lang"] == l),
                        "documented": (l in BULBUL_LANGS) if t == "bulbul:v3" else
                        (bool([v for v in VOICE_V4.values() if f"_{l}_" in v]) if t == BULBUL4 else None)}
                    for t in TTS} for l in DUB_LANGS + PROBE_LANGS}
    sarvam_inr = sum(usage.get(s, {}).get("chars", 0) for s in ("sarvam-translate:v1", "mayura:v1",
                                                                 "mayura:v1-colloquial")) / 1e4 * 20
    sarvam_inr += usage.get("bulbul:v3", {}).get("cost_inr", 0) + usage.get(BULBUL4, {}).get("cost_inr_if_v3_price", 0)
    sarvam_inr += usage.get("judge:saaras:v3", {}).get("audio_s", 0) / 3600 * 30
    s105 = usage.get("sarvam-105b", {})
    sarvam_inr += s105.get("in_tok", 0) / 1e6 * 15 + s105.get("out_tok", 0) / 1e6 * 60

    examples = []
    for it, l in ((ITEMS[3], "ta"), (ITEMS[8], "hi"), (ITEMS[15], "bn")):
        ex = {"task": "translation en->xx", "lang": l, "input": it["en"], "gold": it[l], "outputs": {}}
        for r in tr:
            if r["id"] == it["id"] and r["lang"] == l and r["dir"] == "en2xx":
                ex["outputs"][r["system"]] = {"text": r["hyp"], "chrF++": round(r["chrf"], 1)}
        examples.append(ex)
    for it, l in ((DUB_ITEMS[0], "ta"), (DUB_ITEMS[1], "bn")):
        ex = {"task": "dubbing round trip", "lang": l, "input": it[l], "outputs": {}}
        for r in stt:
            if r["id"] == it["id"] and r["lang"] == l:
                ex["outputs"][f"{r['tts']} -> {r['judge']}"] = {"transcript": r["hyp"], "cer": round(r["cer"], 3)}
        examples.append(ex)

    write_result(UC, {
        "uc": UC, "title": "Translation and dubbing of training content / product copy",
        "business_question": "Localising training content and product copy into Indian languages, then dubbing it: "
                             "which translation system and which TTS should an Indian business use?",
        "dataset": {"name": "FLEURS test transcriptions (= FLORES-101 sentences) aligned by id",
                    "source": "google/fleurs on Hugging Face, data/<lang>/test.tsv", "license": "CC-BY 4.0",
                    "n": len(ITEMS), "languages": list(NAMES), "synthetic": False,
                    "how_made": f"{len(ITEMS)} sentence ids present in all 11 languages with 50-110 English chars, "
                                f"seeded shuffle (seed 7). Translation: {len(ITEMS)} x {len(INDIC)} langs x 2 "
                                f"directions = {len(ITEMS) * len(INDIC) * 2} items per system. Dubbing: "
                                f"{len(DUB_ITEMS)} digit-free sentences x {len(DUB_LANGS)} langs per TTS, plus a "
                                f"3-sentence coverage probe in {PROBE_LANGS}. References are human FLEURS "
                                f"transcriptions (native-speaker translations of English FLORES)."},
        "systems": mt_systems + ["mayura:v1-colloquial"] + TTS + JUDGES[2:],
        "metrics": metrics, "per_language": per_lang, "speed": speed, "usage": usage,
        "extra": {"tts_language_coverage": coverage,
                  "voices": {"bulbul:v3": VOICE, BULBUL4: VOICE_V4, GEMINI_TTS: GEMINI_VOICE, OPENAI_TTS: OPENAI_VOICE},
                  "frontier_subset": f"first {FRONTIER_N} sentence ids x 10 langs, both directions, think on: "
                                     + ", ".join(it["id"] for it in ITEMS[:FRONTIER_N]),
                  "openai_judge_no_language_hint": sum(1 for r in stt if r.get("no_language_hint")),
                  "en2xx_wrong_script_outputs": wrong_script,
                  "gemini_judge_blocked_calls": blocked, "sarvam_spend_inr_estimate": round(sarvam_inr, 1)},
        "examples": examples,
        "findings": FINDINGS, "caveats": CAVEATS, "verdict": VERDICT,
    })
    log(UC, "scored; Sarvam spend estimate INR", round(sarvam_inr, 1))


FINDINGS, CAVEATS, VERDICT = [], [], ""
_notes = Path(__file__).with_name("notes.json")
if _notes.exists():
    FINDINGS, CAVEATS, VERDICT = (json.loads(_notes.read_text())[k] for k in ("findings", "caveats", "verdict"))

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "api"
    if mode == "api":
        mt_jobs(API_MT + CHEAP_MT + FRONTIER_MT)
        dub_jobs()
    if mode == "local":
        for s in LOCAL_MT:
            if wait_for_local(s):
                mt_jobs([s])
            else:
                log(UC, s, "not up after wait; skipped")
    score()
