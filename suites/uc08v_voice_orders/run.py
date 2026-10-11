"""UC08v: WhatsApp voice-note orders. The 86 UC08 order messages, spoken, then transcribed, then extracted.

Speech: gemini-3.8-flash-tts reads each message as written (romanised/code-mixed/native script; the model
picks the accent from the text). Two conditions: clean (24 kHz) and phone (8 kHz, 300-3400 Hz band, white
noise at 15 dB SNR, seeded per message).
ASR: saaras:v4 codemix, saaras:v4 codemix + fixed keyterm list, saaras:v3 codemix, gemini-3.8-flash (audio),
OpenAI gpt-4o-transcribe. Every transcript goes to the SAME extractor (gemini-3.8-flash, thinking off, UC08
order prompt), so differences come from speech recognition only. Also: all-Sarvam (saaras:v4 codemix ->
sarvam-105b thinking on) and direct-audio Gemini (audio + order prompt in one call).
Scoring reuses suites/uc08_quick_commerce (score_order, f1). Resumable via results/raw/uc08v_voice_orders.jsonl.
Usage: run.py [api|score]
"""
import importlib.util, io, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests
import soundfile as sf
from scipy.signal import butter, resample_poly, sosfilt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from common.bench import *  # noqa
from common.bench import _retry

_spec = importlib.util.spec_from_file_location("uc08", ROOT / "suites" / "uc08_quick_commerce" / "run.py")
U8 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(U8)

UC = "uc08v_voice_orders"
D = DATA / UC
ORDERS = [o for o in U8.ORDERS if o["kind"] == "order"]  # 86 orders; searches are not voice-noted here
VOICES = ("Kore", "Puck")  # alternate female/male by id
KEYTERMS = ["Amul", "Aashirvaad", "Fortune", "Tata", "Maggi", "Britannia", "Parle-G", "Haldiram's", "Surf Excel",
            "Vim", "Colgate", "Dettol", "Dove", "Bisleri", "Lays", "Thums Up", "Coca-Cola", "Mother Dairy", "Nandini",
            "Aavin", "Gokul", "iD", "MTR", "MDH", "Bru", "Kissan", "Whisper", "Pampers", "Saffola", "Gold Winner",
            "Idhayam", "Red Label", "Good Day", "Patanjali", "Nestle", "Cadbury", "Dabur", "Everest", "Kurkure",
            "kg", "gram", "litre", "ml", "dozen", "packet", "COD", "UPI",
            "GPay", "PhonePe", "Paytm"]  # one fixed store-wide list (brands stocked + units + payment words); API max is 50
ASR = ["saaras-v4-codemix", "saaras-v4-codemix-kt", "saaras-v3-codemix", "gemini-3.8-flash", "gpt-4o-transcribe"]
# Budget plan (Sarvam INR 30): Sarvam ASR variants beyond v4-codemix, and the all-Sarvam pipeline, run on phone only
PLAN = {"clean": ["saaras-v4-codemix", "gemini-3.8-flash", "gpt-4o-transcribe"], "phone": ASR}
ALL_SARVAM = {"phone"}
SARVAM_ASR = {"saaras-v4-codemix", "saaras-v4-codemix-kt", "saaras-v3-codemix"}
_gem = None


def gem():
    global _gem
    if _gem is None:
        from google import genai
        _gem = genai.Client(http_options={"timeout": 180_000})
    return _gem


def wav_bytes(a, sr):
    b = io.BytesIO()
    sf.write(b, a, sr, format="WAV", subtype="PCM_16")
    return b.getvalue()


# ---------------- audio ----------------
def tts_job(o):
    from google.genai import types
    voice = VOICES[o["id"] % 2]
    cfg = types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))))
    t = time.time()
    r = _retry(lambda: gem().models.generate_content(model=GEMINI_TTS, contents=o["message"], config=cfg))
    parts = r.candidates[0].content.parts if r.candidates and r.candidates[0].content else []
    pcm = b"".join(p.inline_data.data for p in parts if p.inline_data)
    rec = {"key": f"tts|{o['id']}", "task": "tts", "id": o["id"], "voice": voice, "ms": (time.time() - t) * 1000,
           "out_tok": r.usage_metadata.candidates_token_count if r.usage_metadata else None}
    if not pcm:
        return {**rec, "error": "no audio"}
    p = D / "clean" / f"{o['id']}.wav"
    p.parent.mkdir(parents=True, exist_ok=True)
    a = np.frombuffer(pcm, dtype="<i2")
    p.write_bytes(wav_bytes(a, 24000))
    return {**rec, "audio_s": len(a) / 24000}


def audio(cond, oid):
    """Clean clip, or its phone-line version (built locally, deterministic)."""
    p = D / cond / f"{oid}.wav"
    if cond == "phone" and not p.exists():
        a, sr = sf.read(D / "clean" / f"{oid}.wav")
        a = resample_poly(a, 1, 3)  # 24 kHz -> 8 kHz
        a = sosfilt(butter(4, [300, 3400], btype="band", fs=8000, output="sos"), a)
        rms = np.sqrt(np.mean(a ** 2))
        a = a + np.random.default_rng(oid).normal(0, rms / 10 ** (15 / 20), len(a))  # 15 dB SNR
        p.parent.mkdir(parents=True, exist_ok=True)
        sf.write(p, np.clip(a, -1, 1), 8000, subtype="PCM_16")
    return p


# ---------------- ASR ----------------
def stt_job(cond, o, asr):
    p = audio(cond, o["id"])
    rec = {"key": f"stt|{cond}|{o['id']}|{asr}", "task": "stt", "cond": cond, "id": o["id"], "asr": asr,
           "audio_s": sf.info(p).duration}
    t = time.time()
    if asr.startswith("saaras"):
        data = {"model": "saaras:v4" if "v4" in asr else "saaras:v3", "mode": "codemix"}
        if asr.endswith("-kt"):
            data["keyterms"] = json.dumps(KEYTERMS)
        d = sarvam_post("/speech-to-text", files={"file": (p.name, p.read_bytes(), "audio/wav")}, data=data)
        rec.update(text=d.get("transcript", ""), lang=d.get("language_code"), error=d.get("_body"))
    elif asr == "gpt-4o-transcribe":
        def go():
            r = requests.post("https://api.openai.com/v1/audio/transcriptions", timeout=180,
                              headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
                              files={"file": (p.name, p.read_bytes(), "audio/wav")}, data={"model": asr})
            if r.status_code == 429 or r.status_code >= 500:
                raise RuntimeError(r.text[:200])
            return r
        r = _retry(go)
        rec.update(text=r.json().get("text", "") if r.status_code == 200 else "",
                   error=None if r.status_code == 200 else r.text[:300])
    else:
        from google.genai import types
        r = _retry(lambda: gem().models.generate_content(
            model=GEMINI_CHAT, config=types.GenerateContentConfig(
                temperature=0, thinking_config=types.ThinkingConfig(thinking_budget=0)),
            contents=[types.Part.from_bytes(data=p.read_bytes(), mime_type="audio/wav"),
                      "Transcribe this voice note exactly as spoken. Write Indian-language words in their native "
                      "script and English words, brands and numbers as they are. Output only the transcript."]))
        rec.update(text=(r.text or "").strip(), in_tok=r.usage_metadata.prompt_token_count,
                   out_tok=r.usage_metadata.candidates_token_count)
        if not rec["text"] and r.prompt_feedback and r.prompt_feedback.block_reason:
            rec["blocked"] = str(r.prompt_feedback.block_reason)
    rec["ms"] = (time.time() - t) * 1000
    return rec


# ---------------- extraction ----------------
def ext_job(cond, o, pipe, transcript):
    rec = {"key": f"ext|{cond}|{o['id']}|{pipe}", "task": "ext", "cond": cond, "id": o["id"], "pipe": pipe}
    if pipe == "gemini-direct-audio":
        from google.genai import types
        t = time.time()
        r = _retry(lambda: gem().models.generate_content(
            model=GEMINI_CHAT, config=types.GenerateContentConfig(
                system_instruction=U8.PROMPT, temperature=0,
                thinking_config=types.ThinkingConfig(thinking_budget=0)),
            contents=[types.Part.from_bytes(data=audio(cond, o["id"]).read_bytes(), mime_type="audio/wav"),
                      "The customer's WhatsApp voice note is attached."]))
        rec.update(text=r.text or "", ms=(time.time() - t) * 1000, in_tok=r.usage_metadata.prompt_token_count,
                   out_tok=r.usage_metadata.candidates_token_count)
        return rec
    system, think = ("sarvam-105b", True) if pipe == "all-sarvam" else (GEMINI_CHAT, False)
    r = chat(system, [{"role": "system", "content": U8.PROMPT}, {"role": "user", "content": transcript}],
             max_tokens=16000 if think else 1500, think=think)
    rec.update(text=r["text"], ms=r["ms"], in_tok=r.get("in_tok"), out_tok=r.get("out_tok"),
               reasoning_tok=r.get("reasoning_tok"), error=r.get("error"), transcript=transcript)
    return rec


# ---------------- driver ----------------
NO_CREDIT = []


def ok(r):
    return not r.get("error")


def run(jobs, workers):
    done = {r["key"] for r in raw_load(UC) if ok(r)}
    todo = [j for j in jobs if j[0] not in done]
    if not todo:
        return
    log(UC, f"running {len(todo)} jobs ({todo[0][0]} ...)")

    def go(j):
        if NO_CREDIT and j[2]:
            return
        try:
            rec = j[1]()
        except Exception as e:  # retried on next run
            log(UC, "FAIL", j[0], repr(e)[:300])
            return
        if re.search(r"credit|quota", str(rec.get("error")), re.I):
            NO_CREDIT.append(1)
            log(UC, "Sarvam: no credits; stopping Sarvam jobs")
            return
        raw_append(UC, rec)
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(go, todo))


def api():
    run([(f"tts|{o['id']}", lambda o=o: tts_job(o), False) for o in ORDERS], 4)
    for cond, asrs in PLAN.items():
        for asr in asrs:
            sar = asr in SARVAM_ASR
            run([(f"stt|{cond}|{o['id']}|{asr}", lambda o=o, c=cond, a=asr: stt_job(c, o, a), sar) for o in ORDERS],
                3 if sar else 4)
    tx = {(r["cond"], r["id"], r["asr"]): r["text"] for r in raw_load(UC) if r["task"] == "stt" and ok(r)}
    for cond, asrs in PLAN.items():
        for asr in asrs:
            run([(f"ext|{cond}|{o['id']}|{asr}", lambda o=o, c=cond, a=asr: ext_job(c, o, a, tx[(c, o["id"], a)]),
                  False) for o in ORDERS if (cond, o["id"], asr) in tx], 4)
        run([(f"ext|{cond}|{o['id']}|gemini-direct-audio", lambda o=o, c=cond: ext_job(c, o, "gemini-direct-audio", ""),
              False) for o in ORDERS], 4)
        if cond in ALL_SARVAM:
            run([(f"ext|{cond}|{o['id']}|all-sarvam",
                  lambda o=o, c=cond: ext_job(c, o, "all-sarvam", tx[(c, o["id"], "saaras-v4-codemix")]), True)
                 for o in ORDERS if (cond, o["id"], "saaras-v4-codemix") in tx], 3)


# ---------------- scoring ----------------
def score():
    raw = [r for r in {r["key"]: r for r in raw_load(UC)}.values() if ok(r)]
    gold = {o["id"]: o["gold"] for o in ORDERS}
    ids = set(gold)
    ext = [r for r in raw if r["task"] == "ext"]
    for r in ext:
        r["s"] = U8.score_order(gold[r["id"]], extract_json(r["text"] or ""))
        r["system"] = f"{r['cond']}: {r['pipe']}"
    # text baselines from UC08 (same 86 messages, same extractor / same all-Sarvam model)
    for r in raw_load("uc08_quick_commerce"):
        if r["task"] == "A" and r["id"] in ids and r["system"] in (GEMINI_CHAT, "sarvam-105b-think"):
            ext.append({"system": f"typed text: {r['system']}", "id": r["id"],
                        "s": U8.score_order(gold[r["id"]], extract_json(r["text"] or ""))})
    systems = list(dict.fromkeys(r["system"] for r in sorted(ext, key=lambda r: r["system"])))
    metrics = []

    def m(name, fn, hib=True):
        metrics.append({"name": name, "higher_is_better": hib, "unit": "fraction", "values": {
            s: bootstrap_ci(fn([r["s"] for r in ext if r["system"] == s])) for s in systems}})
    m("Exact whole-order accuracy", lambda ss: [s["exact"] for s in ss])
    m("Item F1 (name+qty/unit+brand)", lambda ss: U8.f1(ss, "strict_tp"))
    m("Item F1 (catalog name only)", lambda ss: U8.f1(ss, "name_tp"))
    for k in ("pincode", "payment", "slot", "valid"):
        m(f"{k} accuracy" if k != "valid" else "JSON validity", lambda ss, k=k: [s[k] for s in ss])
    per_lang = {"Exact order by message language": {
        g: {s: round(statistics.fmean(v), 3) if (v := [r["s"]["exact"] for r in ext if r["system"] == s and
                                                       U8.ORDERS[r["id"] - 1]["lang"] == g]) else None
            for s in systems} for g in sorted({o["lang"] for o in ORDERS})}}
    stt = [r for r in raw if r["task"] == "stt"]
    tts = [r for r in raw if r["task"] == "tts"]
    speed, usage = {}, {}
    for asr in ASR:
        rs = [r for r in stt if r["asr"] == asr]
        if rs:
            speed[f"asr:{asr}"] = {"p50_ms": pctl([r["ms"] for r in rs], .5), "p95_ms": pctl([r["ms"] for r in rs], .95)}
            usage[f"asr:{asr}"] = {"calls": len(rs), "audio_s": round(sum(r["audio_s"] for r in rs), 1),
                                   "blocked": sum(1 for r in rs if r.get("blocked"))}
    for pipe in {r["pipe"] for r in ext if "pipe" in r}:
        rs = [r for r in ext if r.get("pipe") == pipe]
        speed[f"extract:{pipe}"] = {"p50_ms": pctl([r["ms"] for r in rs], .5), "p95_ms": pctl([r["ms"] for r in rs], .95)}
        usage[f"extract:{pipe}"] = {"calls": len(rs), "in_tok": sum(r.get("in_tok") or 0 for r in rs),
                                    "out_tok": sum(r.get("out_tok") or 0 for r in rs),
                                    "reasoning_tok": sum(r.get("reasoning_tok") or 0 for r in rs)}
    usage["tts:gemini-3.8-flash-tts"] = {"calls": len(tts), "audio_s": round(sum(r.get("audio_s") or 0 for r in tts), 1),
                                         "out_tok": sum(r.get("out_tok") or 0 for r in tts)}
    inr = sum(u["audio_s"] for k, u in usage.items() if k.startswith("asr:saaras")) / 3600 * 30
    s105 = usage.get("extract:all-sarvam", {})
    inr += s105.get("in_tok", 0) / 1e6 * 15 + s105.get("out_tok", 0) / 1e6 * 60

    examples = []
    for oid in (25, 43, 67, 93):
        ex = {"input_text": U8.ORDERS[oid - 1]["message"], "gold": gold.get(oid), "transcripts": {}, "extractions": {}}
        for r in stt:
            if r["id"] == oid and r["cond"] == "phone":
                ex["transcripts"][r["asr"]] = r["text"]
        for r in ext:
            if r["id"] == oid and r["system"].startswith("phone"):
                ex["extractions"][r["system"]] = {"exact": r["s"]["exact"], "strict_tp": r["s"]["strict_tp"],
                                                  "n_gold": r["s"]["n_gold"]}
        examples.append(ex)

    write_result(UC, {
        "uc": UC, "title": "WhatsApp voice-note orders: speech recognition in front of order extraction",
        "business_question": "Many quick-commerce orders arrive as WhatsApp voice notes. Which speech-to-text "
                             "should sit in front of the order extractor, and does a phone line break it?",
        "dataset": {"name": "UC08 order messages (86), spoken by gemini-3.8-flash-tts", "source":
                    "suites/uc08_quick_commerce/build_data.py + this suite", "license": "CC-BY 4.0", "n": len(ORDERS),
                    "languages": sorted({o["lang"] for o in ORDERS}), "synthetic": True,
                    "how_made": "Each of the 86 hand-written order messages is read as written by gemini-3.8-flash-tts "
                                "(voices Kore/Puck alternating; accent inferred from the text). The phone condition "
                                "is resampled to 8 kHz, band-passed to 300-3400 Hz, with white noise at 15 dB SNR. "
                                "Gold JSON is the UC08 gold. Synthetic voices are cleaner than real customers."},
        "systems": systems, "metrics": metrics, "per_language": per_lang, "speed": speed, "usage": usage,
        "extra": {"plan": PLAN, "all_sarvam_conditions": sorted(ALL_SARVAM), "keyterms": KEYTERMS,
                  "sarvam_spend_inr_estimate": round(inr, 2)},
        "examples": examples, "findings": FINDINGS, "caveats": CAVEATS, "verdict": VERDICT})
    log(UC, "scored; Sarvam spend estimate INR", round(inr, 2))


FINDINGS, CAVEATS, VERDICT = [], [], ""
_notes = Path(__file__).with_name("notes.json")
if _notes.exists():
    FINDINGS, CAVEATS, VERDICT = (json.loads(_notes.read_text())[k] for k in ("findings", "caveats", "verdict"))

if __name__ == "__main__":
    if (sys.argv[1] if len(sys.argv) > 1 else "api") == "api":
        api()
    score()
