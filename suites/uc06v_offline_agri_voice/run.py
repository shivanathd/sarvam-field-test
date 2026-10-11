"""UC06v - Spoken farmer questions: the uc06 crop-advisory test with voice input.

Farmers ask by voice, so speech recognition sits in front of the answering model. All 70 uc06 questions are
synthesised (macOS `say` Indian voices + gemini TTS; never Sarvam's own TTS), clean and over a simulated phone line,
transcribed by four STT systems, and every transcript goes to the SAME answering model (gemini-3.8-flash, thinking off,
uc06 advisory-sheet prompt). Score differences between those pipelines therefore come only from speech recognition.
Also: an all-Sarvam pipeline (saaras:v4 -> sarvam-105b), Gemini answering straight from audio, and an oracle
(the reference question text -> gemini-3.8-flash) as the upper bound.

Stages (resumable; each skips work already in results/raw/uc06v_offline_agri_voice.jsonl):
  synth   audio for every question -> data/uc06v_offline_agri_voice/audio/{clean,phone}/<id>.wav
  stt     saaras:v4 + saaras:v3 (transcribe mode), gemini-3.8-flash (audio in), gpt-4o-transcribe
  answer  transcript -> gemini-3.8-flash; saaras:v4 -> sarvam-105b; audio -> gemini-3.8-flash; text -> gemini-3.8-flash
  score   recompute results/uc06v_offline_agri_voice.json
Usage: .venv/bin/python suites/uc06v_offline_agri_voice/run.py [synth stt answer score]   (no args = all)
"""
import importlib.util, json, os, re, statistics, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from common.bench import *  # noqa: E402,F403
from common.bench import _retry  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


U06 = _load("uc06_run", ROOT / "suites" / "uc06_offline_agri" / "run.py")  # questions, sheet prompt, scorer
U01 = _load("uc01_run", ROOT / "suites" / "uc01_voice_support" / "run.py")  # phone_line, to16k, gemini_tts_bytes, gclient

UC = "uc06v_offline_agri_voice"
D = DATA / UC
LANG = {"hi": ("Hindi", "Devanagari", "hi-IN"), "mr": ("Marathi", "Devanagari", "mr-IN"), "kn": ("Kannada", "Kannada", "kn-IN"),
        "te": ("Telugu", "Telugu", "te-IN"), "ta": ("Tamil", "Tamil", "ta-IN"), "pa": ("Punjabi", "Gurmukhi", "pa-IN")}
SAY_VOICE = {"hi": "Lekha", "kn": "Soumya", "te": "Geeta", "ta": "Vani"}  # macOS ships no Marathi or Punjabi voice
GEM_VOICES = ["Kore", "Puck", "Charon", "Aoede", "Fenrir", "Leda"]
CONDS = ("clean", "phone")
STT = ("saaras:v4", "saaras:v3", GEMINI_CHAT, "gpt-4o-transcribe")
# The 4 out-of-scope questions that only exist romanised need a native-script version to be spoken / to score CER.
OOS_NATIVE = {"oos1-mr-roman": "आजचा सोयाबीनचा बाजारभाव काय आहे?",
              "oos6-hi-roman": "गन्ने में एक एकड़ में कितना यूरिया डालना है?",
              "oos8-kn-roman": "ಪಿಎಂ-ಕಿಸಾನ್ ಕಂತು ಯಾವಾಗ ಬರುತ್ತೆ?",
              "oos9-te-roman": "మిర్చి పంటకు ఎకరానికి ఎంత డీఏపీ వేయాలి?"}
_lock = threading.Lock()
NO_CREDIT = threading.Event()


def spoken_text(q):
    """What the farmer says. A romanised item is the same question typed differently, so it is spoken from its
    native-script twin, by a different voice (see voice_for)."""
    if q["id"] in OOS_NATIVE:
        return OOS_NATIVE[q["id"]]
    if q["script"] == "roman" and not q["oos"]:
        return next(x["q"] for x in U06.QS if x["id"] == q["id"].replace("-roman", "-native"))
    return q["q"]


def voice_for(q):
    if q["script"] == "native" and q["lang"] in SAY_VOICE:
        return "say:" + SAY_VOICE[q["lang"]]
    k = sum(map(ord, q["id"])) % len(GEM_VOICES)
    return "gemini:" + GEM_VOICES[k]


def wav(qid, cond):
    return D / "audio" / cond / f"{qid}.wav"


def done(stage):
    return {(r["id"], r["system"], r["cond"]) for r in raw_load(UC) if r["stage"] == stage and not r.get("error")}


def save(rec):
    with _lock:
        raw_append(UC, rec)


# ---------------- synth ----------------
def synth():
    meta_p = D / "synth.json"
    meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    todo = [q for q in U06.QS if not (q["id"] in meta and wav(q["id"], "phone").exists())]

    def one(q):
        text, voice = spoken_text(q), voice_for(q)
        tmp = D / "audio" / "src" / q["id"]
        tmp.parent.mkdir(parents=True, exist_ok=True)
        usage = {}
        if voice.startswith("say:"):
            src = tmp.with_suffix(".aiff")
            subprocess.run(["say", "-v", voice[4:], "-o", str(src), text], check=True)
        else:  # bare text: uc01 found style instructions get read aloud
            data, mime, u = _retry(lambda: U01.gemini_tts_bytes(text, voice[7:]))
            src = tmp.with_suffix(".wav")
            src.write_bytes(data)
            usage = {"in_tok": u.prompt_token_count, "out_tok": u.candidates_token_count}
        clean = wav(q["id"], "clean")
        U01.to16k(src, clean)
        x, sr = sf.read(str(clean), dtype="float32")
        wav(q["id"], "phone").parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(wav(q["id"], "phone")), U01.phone_line(x, sr, seed=sum(map(ord, q["id"]))), 16000)
        return q["id"], {"voice": voice, "text": text, "audio_s": round(len(x) / sr, 2), **usage}

    with ThreadPoolExecutor(4) as ex:
        for k, v in ex.map(one, todo):
            meta[k] = v
            meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    log(UC, "synth done", len(meta))


# ---------------- STT ----------------
def stt_prompt(lang):
    name, script, _ = LANG[lang]
    return (f"Transcribe this farmer's spoken question. The farmer speaks {name}. Write it in {script} script exactly "
            "as spoken (keep English words such as fertiliser or chemical names as spoken); do not translate. "
            "Write numbers as digits. Output only the transcript.")


def stt_saaras(p, lang, model):
    for attempt in range(4):  # re-open the file on retry (uc01 found a spent handle -> 400 "Failed to read the file")
        t = time.time()
        with open(p, "rb") as f:
            d = sarvam_post("/speech-to-text", files={"file": (p.name, f, "audio/wav")},
                            data={"model": model, "mode": "transcribe", "language_code": LANG[lang][2]})
        if "Failed to read the file" not in str(d.get("_body", "")):
            break
        time.sleep(3 * (attempt + 1))
    if d.get("_error") == 402 or re.search(r"credit|quota", str(d.get("_body", "")), re.I):
        NO_CREDIT.set()
        return {"hyp": None, "error": "402 no credits"}
    if "_error" in d:
        return {"hyp": None, "error": d}
    return {"hyp": d.get("transcript", ""), "ms": (time.time() - t) * 1000, "detected": d.get("language_code")}


def stt_gemini(p, lang):
    from google.genai import types
    cfg = types.GenerateContentConfig(temperature=0, max_output_tokens=600, thinking_config=types.ThinkingConfig(thinking_budget=0))
    t = time.time()
    r = _retry(lambda: U01.gclient().models.generate_content(
        model=GEMINI_CHAT, contents=[types.Part.from_bytes(data=p.read_bytes(), mime_type="audio/wav"), stt_prompt(lang)], config=cfg))
    u = r.usage_metadata
    return {"hyp": (r.text or "").strip(), "ms": (time.time() - t) * 1000, "in_tok": u.prompt_token_count, "out_tok": u.candidates_token_count}


def stt_openai(p, lang):
    audio = p.read_bytes()
    data = {"model": "gpt-4o-transcribe", "language": lang, "prompt": stt_prompt(lang), "response_format": "json"}

    def go():
        r = requests.post("https://api.openai.com/v1/audio/transcriptions", timeout=180,
                          headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
                          files={"file": (p.name, audio, "audio/wav")}, data=data)
        if (r.status_code == 429 and "insufficient_quota" not in r.text) or r.status_code >= 500:
            raise RuntimeError(f"{r.status_code} {r.text[:200]}")
        return r

    t = time.time()
    r = _retry(go)
    if r.status_code == 400 and "language" in r.text.lower():  # unsupported language code: retry with auto-detect
        data.pop("language")
        r = _retry(go)
    if r.status_code != 200:
        return {"hyp": None, "error": {"_error": r.status_code, "_body": r.text[:300]}}
    return {"hyp": (r.json().get("text") or "").strip(), "ms": (time.time() - t) * 1000, "openai_usage": r.json().get("usage")}


def stt():
    have = done("stt")
    jobs = [(q, c, s) for q in U06.QS for c in CONDS for s in STT if (q["id"], s, c) not in have]
    log(UC, "stt jobs", len(jobs))

    def one(j):
        q, c, s = j
        p = wav(q["id"], c)
        if s.startswith("saaras"):
            if NO_CREDIT.is_set():
                return
            r = stt_saaras(p, q["lang"], s)
        elif s == GEMINI_CHAT:
            r = stt_gemini(p, q["lang"])
        else:
            r = stt_openai(p, q["lang"])
        save({"stage": "stt", "id": q["id"], "system": s, "cond": c, "audio_s": sf.info(str(p)).duration, **r})

    pools = {"saaras": ThreadPoolExecutor(3), "gemini": ThreadPoolExecutor(4), "gpt": ThreadPoolExecutor(4)}
    fs = [pools[j[2].split(":")[0].split("-")[0]].submit(one, j) for j in jobs]
    for f in fs:
        try:
            f.result()
        except Exception as e:
            log(UC, "stt job failed, rerun retries:", str(e)[:150])
    for p in pools.values():
        p.shutdown()
    if NO_CREDIT.is_set():
        log(UC, "STOPPED Sarvam calls: 402 no credits")


# ---------------- answering ----------------
def msgs(question):
    return [{"role": "system", "content": U06.SYSTEM_PROMPT}, {"role": "user", "content": question}]


def answer_audio(p):
    from google.genai import types
    cfg = types.GenerateContentConfig(system_instruction=U06.SYSTEM_PROMPT, temperature=0, max_output_tokens=800,
                                      thinking_config=types.ThinkingConfig(thinking_budget=0))
    t = time.time()
    r = _retry(lambda: U01.gclient().models.generate_content(
        model=GEMINI_CHAT, config=cfg, contents=[types.Part.from_bytes(data=p.read_bytes(), mime_type="audio/wav"),
                                                 "The farmer's question is in this audio."]))
    u = r.usage_metadata
    return {"text": r.text or "", "ms": (time.time() - t) * 1000, "in_tok": u.prompt_token_count,
            "out_tok": u.candidates_token_count, "reasoning_tok": u.thoughts_token_count}


def answer():
    have = done("answer")
    stt_recs = {(r["id"], r["system"], r["cond"]): r for r in raw_load(UC) if r["stage"] == "stt" and not r.get("error")}
    jobs = []
    for q in U06.QS:
        for c in CONDS:
            for s in STT:
                k = (q["id"], s, c)
                if k in stt_recs and (q["id"], f"{s} -> {GEMINI_CHAT}", c) not in have:
                    jobs.append((q, c, f"{s} -> {GEMINI_CHAT}", GEMINI_CHAT, stt_recs[k]["hyp"]))
            k = (q["id"], "saaras:v4", c)
            if k in stt_recs and (q["id"], "saaras:v4 -> sarvam-105b", c) not in have:
                jobs.append((q, c, "saaras:v4 -> sarvam-105b", "sarvam-105b", stt_recs[k]["hyp"]))
            if (q["id"], f"audio -> {GEMINI_CHAT}", c) not in have:
                jobs.append((q, c, f"audio -> {GEMINI_CHAT}", "audio", None))
        if (q["id"], f"text -> {GEMINI_CHAT}", "text") not in have:
            jobs.append((q, "text", f"text -> {GEMINI_CHAT}", GEMINI_CHAT, spoken_text(q)))
    log(UC, "answer jobs", len(jobs))

    def one(j):
        q, c, pipe, model, question = j
        if model == "sarvam-105b" and NO_CREDIT.is_set():
            return
        if model == "audio":
            r = answer_audio(wav(q["id"], c))
        else:
            r = chat(model, msgs(question or "(empty)"), max_tokens=800)
            if model == "sarvam-105b" and r.get("error") and re.search(r"402|credit|quota", str(r["error"]), re.I):
                NO_CREDIT.set()
                return
        save({"stage": "answer", "id": q["id"], "system": pipe, "cond": c, "question_used": question, **r})

    with ThreadPoolExecutor(3) as es, ThreadPoolExecutor(4) as eg:
        fs = [(es if j[3] == "sarvam-105b" else eg).submit(one, j) for j in jobs]
        for f in fs:
            try:
                f.result()
            except Exception as e:
                log(UC, "answer job failed, rerun retries:", str(e)[:150])


# ---------------- score ----------------
def score():
    by = {q["id"]: q for q in U06.QS}
    ref = {q["id"]: spoken_text(q) for q in U06.QS}
    stt_r, ans = {}, {}
    for r in raw_load(UC):
        if r.get("error"):
            continue
        (stt_r if r["stage"] == "stt" else ans)[(r["id"], r["system"], r["cond"])] = r
    pipes = [f"text -> {GEMINI_CHAT}"] + [f"{s} -> {GEMINI_CHAT}" for s in STT] + ["saaras:v4 -> sarvam-105b", f"audio -> {GEMINI_CHAT}"]

    def sc(k):
        q = dict(by[k[0]], script="native")  # a spoken question has no script: the reply should be in native script
        return U06.score(q, ans[k]["text"])

    metrics, speed, per_lang = [], {}, {}
    cond_of = lambda p: ["text"] if p.startswith("text") else list(CONDS)
    cols = [(p, c) for p in pipes for c in cond_of(p)]
    label = lambda p, c: f"{p} [{c}]"
    for name, key, pred in [("grounded_correct", "correct", lambda q: not q["oos"]), ("oos_refusal", "refused", lambda q: q["oos"]),
                            ("oos_refusal_lenient", "refused_lenient", lambda q: q["oos"]),
                            ("false_refusal", "false_refusal", lambda q: not q["oos"]),
                            ("reply_language_correct", "language", lambda q: True), ("overall_pass", "pass", lambda q: True)]:
        metrics.append({"name": name, "higher_is_better": name != "false_refusal", "unit": "share",
                        "values": {label(p, c): bootstrap_ci([sc((i, p, c))[key] for i in by if pred(by[i]) and (i, p, c) in ans])
                                   for p, c in cols}})
    for s in STT:
        metrics.append({"name": f"cer_{s}", "higher_is_better": False, "unit": "character error rate vs spoken question text",
                        "values": {c: bootstrap_ci([cer(ref[i], stt_r[(i, s, c)]["hyp"]) for i in by if (i, s, c) in stt_r]) for c in CONDS}})
    per_lang["cer"] = {LANG[l][0]: {f"{s} [{c}]": round(statistics.fmean([cer(ref[i], stt_r[(i, s, c)]["hyp"]) for i in by
                                                                           if by[i]["lang"] == l and (i, s, c) in stt_r] or [float("nan")]), 3)
                                    for s in STT for c in CONDS} for l in LANG}
    per_lang["overall_pass"] = {LANG[l][0]: {label(p, c): round(statistics.fmean([sc((i, p, c))["pass"] for i in by
                                                                                  if by[i]["lang"] == l and (i, p, c) in ans] or [float("nan")]), 3)
                                             for p, c in cols} for l in LANG}
    for s in STT:
        for c in CONDS:
            ms = [stt_r[k]["ms"] for k in stt_r if k[1] == s and k[2] == c and stt_r[k].get("ms")]
            speed[f"stt {s} [{c}]"] = {"p50_ms": pctl(ms, 0.5), "p95_ms": pctl(ms, 0.95)}
    for p, c in cols:
        ms = [ans[k]["ms"] for k in ans if k[1] == p and k[2] == c]
        speed[f"answer {label(p, c)}"] = {"p50_ms": pctl(ms, 0.5), "p95_ms": pctl(ms, 0.95)}
    audio_s = {s: round(sum(r["audio_s"] for k, r in stt_r.items() if k[1] == s), 1) for s in STT}
    usage = {**{s: {"audio_s": audio_s[s], "calls": sum(k[1] == s for k in stt_r)} for s in STT}}
    for s in ("saaras:v4", "saaras:v3"):
        usage[s]["inr_list_price"] = round(audio_s[s] / 3600 * 30, 2)
    for m in ("sarvam-105b", GEMINI_CHAT):
        rs = [r for k, r in ans.items() if k[1].endswith(m)]
        usage[f"{m} (answering)"] = {"in_tok": sum(r.get("in_tok") or 0 for r in rs), "out_tok": sum(r.get("out_tok") or 0 for r in rs), "calls": len(rs)}
    u = usage["sarvam-105b (answering)"]
    u["inr_list_price"] = round(u["in_tok"] * 15e-6 + u["out_tok"] * 60e-6, 2)
    synth_meta = json.loads((D / "synth.json").read_text())
    ex_ids = ["cotton_spacing-te-native", "aphid_threshold-pa-roman", "oos4-ta-native", "soy_rhizobium-kn-native"]
    examples = [{"id": i, "spoken": ref[i], "voice": synth_meta[i]["voice"], "gold_numbers": by[i]["gold"],
                 "transcripts": {f"{s} [{c}]": stt_r[(i, s, c)]["hyp"] for s in STT for c in CONDS if (i, s, c) in stt_r},
                 "answers": {label(p, c): {"text": ans[(i, p, c)]["text"][:300], "score": sc((i, p, c))} for p, c in cols if (i, p, c) in ans}}
                for i in ex_ids]
    prev = json.loads((RESULTS / f"{UC}.json").read_text()) if (RESULTS / f"{UC}.json").exists() else {}
    write_result(UC, {
        "uc": UC, "title": "Spoken farmer questions (voice-in crop advisory)",
        "business_question": "When farmers ask by voice (clean or over a phone line), how much does speech recognition "
                             "cost the crop-advisory answer, and which STT front-end should a voice advisory line use?",
        "dataset": {"name": "uc06 questions, synthesised speech", "source": "uc06 questions.json + advisory_sheet.md; audio from macOS say "
                    "(Lekha hi, Soumya kn, Geeta te, Vani ta) and gemini-3.8-flash-tts voices; phone line = uc01's 8 kHz G.711 + 20 dB SNR noise",
                    "license": "CC-BY-4.0 (this repo)", "n": len(U06.QS), "languages": [v[0] for v in LANG.values()], "synthetic": True,
                    "how_made": "Each uc06 question spoken once per item: native-script items by the macOS voice where one exists, "
                                "romanised items (spoken from their native-script twin) by a gemini TTS voice, so each fact is heard "
                                "from two speakers. Marathi and Punjabi have no macOS voice, so both of their forms use gemini voices."},
        "systems": [label(p, c) for p, c in cols], "metrics": metrics, "per_language": per_lang, "speed": speed, "usage": usage,
        "findings": prev.get("findings", []), "caveats": prev.get("caveats", []), "verdict": prev.get("verdict", ""),
        "examples": examples})
    for m in metrics:
        print(m["name"], {k: round(v["mean"], 3) if v["mean"] is not None else None for k, v in m["values"].items()})


if __name__ == "__main__":
    stages = sys.argv[1:] or ["synth", "stt", "answer", "score"]
    for st in stages:
        {"synth": synth, "stt": stt, "answer": answer, "score": score}[st]()
