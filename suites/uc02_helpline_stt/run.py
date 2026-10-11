"""UC02: citizen helplines across India's languages — speech-to-text on real human speech (FLEURS).

Steps (each resumable; rerunning never re-spends money):
  fetch    stream FLEURS test audio per Indic language and keep the first N distinct sentences (no full 400 MB download)
  stt      saaras:v3 (transcribe mode) and gemini-3.8-flash
  whisper  local openai/whisper-large-v3-turbo on Apple MPS
  score    recompute results/uc02_helpline_stt.json from results/raw/uc02_helpline_stt.jsonl

Usage: .venv/bin/python suites/uc02_helpline_stt/run.py [fetch stt whisper score]   (no args = all)
"""
import csv, io, json, re, sys, tarfile, threading, time, unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from common.bench import *  # noqa: E402,F403
from common.bench import _retry  # noqa: E402

UC = "uc02_helpline_stt"
D = DATA / "uc02"
N_PER_LANG = 25
MAX_S = 30  # saaras:v3 REST rejects audio over 30 s (batch API needed); same clip set for every system
# FLEURS config -> (name, script, Sarvam code, Whisper code or None if Whisper has no such language)
LANGS = {"hi_in": ("Hindi", "Devanagari", "hi-IN", "hi"), "bn_in": ("Bengali", "Bengali", "bn-IN", "bn"),
         "ta_in": ("Tamil", "Tamil", "ta-IN", "ta"), "te_in": ("Telugu", "Telugu", "te-IN", "te"),
         "ml_in": ("Malayalam", "Malayalam", "ml-IN", "ml"), "kn_in": ("Kannada", "Kannada", "kn-IN", "kn"),
         "mr_in": ("Marathi", "Devanagari", "mr-IN", "mr"), "gu_in": ("Gujarati", "Gujarati", "gu-IN", "gu"),
         "pa_in": ("Punjabi", "Gurmukhi", "pa-IN", "pa"), "or_in": ("Odia", "Odia", "od-IN", None),
         "as_in": ("Assamese", "Bengali", "as-IN", "as"), "ur_pk": ("Urdu", "Arabic", "ur-IN", "ur"),
         "ne_np": ("Nepali", "Devanagari", "ne-IN", "ne"), "sd_in": ("Sindhi", "Arabic", "sd-IN", "sd")}
SYSTEMS = ("saaras:v3-transcribe", "saaras:v4-transcribe", GEMINI_CHAT, "whisper-large-v3-turbo", "whisper-1", "gpt-4o-transcribe")
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


def manifest():
    return json.loads((D / "manifest.json").read_text())


def done_keys():
    # failed calls are retried on rerun; first-pass empty Gemini outputs (no empty_attempts field) get one re-check
    return {(r["id"], r["system"]) for r in raw_load(UC)
            if not r.get("error") and not (r["system"] == GEMINI_CHAT and not r.get("hyp") and "empty_attempts" not in r)}


def save(rec):
    with _lock:
        raw_append(UC, rec)


# ---------------- data ----------------
def fetch():
    from huggingface_hub import hf_hub_download, hf_hub_url
    mp = D / "manifest.json"
    man = json.loads(mp.read_text()) if mp.exists() else []
    man = [m for m in man if m["audio_s"] <= MAX_S]
    have = {c for c in LANGS if sum(m["lang"] == c for m in man) >= N_PER_LANG}
    man = [m for m in man if m["lang"] in have]
    for cfg in LANGS:
        if cfg in have:
            continue
        tsv = hf_hub_download("google/fleurs", f"data/{cfg}/test.tsv", repo_type="dataset")
        rows = {}
        with open(tsv, newline="") as f:
            for r in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                rows[r[1]] = {"sent_id": r[0], "raw": r[2], "gender": r[6] if len(r) > 6 else None}
        url = hf_hub_url("google/fleurs", f"data/{cfg}/audio/test.tar.gz", repo_type="dataset")
        got, seen = [], set()
        with requests.get(url, stream=True, timeout=120) as resp:  # stream and stop early: ~N clips, not 400 MB
            resp.raise_for_status()
            resp.raw.decode_content = True
            with tarfile.open(fileobj=resp.raw, mode="r|gz") as tar:
                for m in tar:
                    name = Path(m.name).name
                    if not m.isfile() or name not in rows or rows[name]["sent_id"] in seen:
                        continue
                    x, sr = sf.read(io.BytesIO(tar.extractfile(m).read()), dtype="float32")
                    if len(x) / sr > MAX_S:
                        continue
                    out = D / cfg / name.replace(".wav", ".wav")
                    out.parent.mkdir(parents=True, exist_ok=True)
                    sf.write(str(out), x, sr)
                    seen.add(rows[name]["sent_id"])
                    got.append({"id": f"{cfg}/{name}", "lang": cfg, "sent_id": rows[name]["sent_id"], "ref": rows[name]["raw"],
                                "gender": rows[name]["gender"], "path": str(out.relative_to(ROOT)), "audio_s": round(len(x) / sr, 2)})
                    if len(got) >= N_PER_LANG:
                        break
        man += got
        mp.write_text(json.dumps(man, ensure_ascii=False, indent=1))
        log(UC, "fetched", cfg, len(got), "clips", round(sum(g["audio_s"] for g in got)), "s")


# ---------------- systems ----------------
def stt_saaras(path, cfg, model="saaras:v3"):
    for attempt in range(4):  # bench.sarvam_post re-sends a spent file handle after a 429 -> 400 "Failed to read the file"; reopen + retry
        t = time.time()
        with open(path, "rb") as f:
            d = sarvam_post("/speech-to-text", files={"file": (path.name, f, "audio/wav")},
                            data={"model": model, "mode": "transcribe", "language_code": LANGS[cfg][2]})
        if "Failed to read the file" not in str(d.get("_body", "")):
            break
        time.sleep(3 * (attempt + 1))
    ms = (time.time() - t) * 1000
    if d.get("_credits") or d.get("_error") == 402 or re.search(r"credit|quota", str(d.get("_body", "")), re.I):
        NO_CREDIT.set()
        raise RuntimeError("Sarvam 402: no credits")
    if "_error" in d:
        return {"hyp": None, "error": d, "ms": ms}
    return {"hyp": d.get("transcript", ""), "ms": ms}


def stt_gemini(path, cfg):
    from google.genai import types
    name, script = LANGS[cfg][:2]
    prompt = (f"Transcribe this {name} speech verbatim in {script} script. Do not translate. "
              "Output only the transcript.")
    cfg_ = types.GenerateContentConfig(temperature=0, max_output_tokens=800,
                                       thinking_config=types.ThinkingConfig(thinking_budget=0))
    blocks = []
    for attempt in range(3):  # Gemini sometimes blocks the audio prompt (block_reason OTHER) and returns nothing
        t = time.time()
        r = _retry(lambda: gclient().models.generate_content(
            model=GEMINI_CHAT, contents=[types.Part.from_bytes(data=path.read_bytes(), mime_type="audio/wav"), prompt], config=cfg_))
        if (r.text or "").strip():
            break
        blocks.append(str(r.prompt_feedback.block_reason) if r.prompt_feedback else "empty")
    u = r.usage_metadata
    return {"hyp": (r.text or "").strip(), "ms": (time.time() - t) * 1000, "empty_attempts": blocks,
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
    man = manifest()
    js = [(m, v) for v in ("v3", "v4") for m in man if (m["id"], f"saaras:{v}-transcribe") not in done]
    jg = [m for m in man if (m["id"], GEMINI_CHAT) not in done]
    jo = [(m, s) for s in OPENAI_STT for m in man if (m["id"], s) not in done]

    def run_s(job):
        m, v = job
        if NO_CREDIT.is_set():
            return
        save({"id": m["id"], "system": f"saaras:{v}-transcribe", "audio_s": m["audio_s"],
              **stt_saaras(ROOT / m["path"], m["lang"], f"saaras:{v}")})

    def run_g(m):
        save({"id": m["id"], "system": GEMINI_CHAT, "audio_s": m["audio_s"], **stt_gemini(ROOT / m["path"], m["lang"])})

    def run_o(job):  # language forced like the others (Whisper family has no Odia -> auto); gpt-4o-transcribe also gets the script hint
        m, s = job
        name, script, _, code = LANGS[m["lang"]]
        prompt = f"Transcribe this {name} speech verbatim in {script} script." if s == "gpt-4o-transcribe" else None
        save({"id": m["id"], "system": s, "audio_s": m["audio_s"], **stt_openai(ROOT / m["path"], s, code, prompt)})

    log(UC, f"stt: {len(js)} saaras + {len(jg)} gemini + {len(jo)} openai jobs")
    with ThreadPoolExecutor(3) as es, ThreadPoolExecutor(4) as eg, ThreadPoolExecutor(4) as eo:
        for f in [es.submit(run_s, m) for m in js] + [eg.submit(run_g, m) for m in jg] + [eo.submit(run_o, j) for j in jo]:
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
    todo = [m for m in manifest() if (m["id"], "whisper-large-v3-turbo") not in done]
    if not todo:
        return
    asr = pipeline("automatic-speech-recognition", model="openai/whisper-large-v3-turbo",
                   torch_dtype=torch.float16, device="mps")
    asr(np.zeros(16000, dtype=np.float32), generate_kwargs={"language": "hi", "task": "transcribe"})  # warm-up
    for m in todo:
        x, sr = sf.read(str(ROOT / m["path"]), dtype="float32")
        code = LANGS[m["lang"]][3]
        gk = {"task": "transcribe", **({"language": code} if code else {})}  # Odia: Whisper has no code, auto-detect
        t = time.time()
        out = asr({"raw": x, "sampling_rate": sr}, generate_kwargs=gk)
        save({"id": m["id"], "system": "whisper-large-v3-turbo", "audio_s": m["audio_s"], "hyp": out["text"].strip(),
              "ms": (time.time() - t) * 1000, "language_forced": code})
    log(UC, "whisper done", len(todo))


# ---------------- scoring ----------------
CHILLU = {"ൺ": "ണ്", "ൻ": "ന്", "ർ": "ര്", "ൽ": "ല്", "ൾ": "ള്", "ൿ": "ക്"}


def canon(s):
    s = unicodedata.normalize("NFC", s or "").replace("‌", "").replace("‍", "")
    for k, v in CHILLU.items():
        s = s.replace(k, v)
    s = "".join(str(unicodedata.digit(c)) if unicodedata.category(c) == "Nd" else c for c in s)
    s = re.sub(r"[ً-ْٰ]", "", s)  # Arabic-script short-vowel marks (rarely written consistently)
    return re.sub(r"[،؟۔]", " ", s)


def score():
    man = {m["id"]: m for m in manifest()}
    allraw = [r for r in raw_load(UC) if r["id"] in man]
    best = {}
    for r in allraw:  # one record per (clip, system): a later record (success or re-checked failure) wins
        k = (r["id"], r["system"])
        if k not in best or best[k].get("error") or not best[k].get("hyp"):
            best[k] = r
    raw = list(best.values())
    rows = []
    for r in raw:
        m = man[r["id"]]
        hyp = r.get("hyp")
        failed = hyp is None
        w = 1.0 if failed else min(1.0, wer(canon(m["ref"]), canon(hyp)))  # cap at 1 so one hallucination can't dominate
        c = 1.0 if failed else min(1.0, cer(canon(m["ref"]), canon(hyp)))
        script_ok = (not failed) and dominant_script(hyp) == LANGS[m["lang"]][1]
        rows.append({**r, "lang": m["lang"], "wer": w, "cer": c, "script_ok": script_ok, "failed": failed})

    per_lang = {"WER": {}, "CER": {}, "WER 95% CI": {}, "output in correct script": {}}
    lang_means = {s: {} for s in SYSTEMS}
    for cfg, (name, *_rest) in LANGS.items():
        for k in per_lang:
            per_lang[k][name] = {}
        for s in SYSTEMS:
            xs = [x for x in rows if x["system"] == s and x["lang"] == cfg]
            if not xs:
                continue
            ci = bootstrap_ci([x["wer"] for x in xs])
            per_lang["WER"][name][s] = round(ci["mean"], 4)
            per_lang["WER 95% CI"][name][s] = [round(ci["lo"], 4), round(ci["hi"], 4)]
            per_lang["CER"][name][s] = round(statistics.fmean(x["cer"] for x in xs), 4)
            per_lang["output in correct script"][name][s] = round(statistics.fmean(x["script_ok"] for x in xs), 3)
            lang_means[s][name] = {"wer": ci["mean"], "cer": per_lang["CER"][name][s],
                                   "script": per_lang["output in correct script"][name][s]}

    metrics = [
        {"name": "WER, macro-average over languages", "higher_is_better": False, "unit": "fraction (capped at 1 per clip)",
         "values": {s: bootstrap_ci([x["wer"] for x in rows if x["system"] == s]) for s in SYSTEMS}},
        {"name": "CER, macro-average over languages", "higher_is_better": False, "unit": "fraction (capped at 1 per clip)",
         "values": {s: bootstrap_ci([x["cer"] for x in rows if x["system"] == s]) for s in SYSTEMS}},
    ]
    worst, cant = {}, {}
    for s in SYSTEMS:
        if not lang_means[s]:
            continue
        wl = max(lang_means[s], key=lambda k: lang_means[s][k]["wer"])
        cl = max(lang_means[s], key=lambda k: lang_means[s][k]["cer"])
        cfg_of = {v[0]: k for k, v in LANGS.items()}
        xs = [x["wer"] for x in rows if x["system"] == s and x["lang"] == cfg_of[wl]]
        worst[s] = {"worst_wer_language": wl, "wer": bootstrap_ci(xs), "worst_cer_language": cl, "cer": lang_means[s][cl]["cer"]}
        # "cannot handle" = most output in another script than the reference, or CER >= 0.5
        cant[s] = {"other_script_than_reference": sorted(k for k, v in lang_means[s].items() if v["script"] < 0.5),
                   "cer_at_least_0.5": sorted(k for k, v in lang_means[s].items() if v["script"] >= 0.5 and v["cer"] >= 0.5)}
        ok = {k: v for k, v in lang_means[s].items() if v["script"] >= 0.5}
        if ok:
            wl2 = max(ok, key=lambda k: ok[k]["wer"])
            worst[s]["worst_wer_language_scorable_script"] = wl2
            worst[s]["wer_scorable_script"] = bootstrap_ci([x["wer"] for x in rows if x["system"] == s and x["lang"] == cfg_of[wl2]])
    metrics.append({"name": "WER in the system's WORST language", "higher_is_better": False, "unit": "fraction",
                    "values": {s: worst[s]["wer"] for s in worst}})
    metrics.append({"name": "WER in the WORST language, excluding languages output in another script", "higher_is_better": False,
                    "unit": "fraction", "values": {s: worst[s].get("wer_scorable_script") for s in worst}})
    metrics.append({"name": "Clips with no transcript at all (blocked/empty after retries)", "higher_is_better": False,
                    "unit": "fraction", "values": {s: bootstrap_ci([float(not x.get("hyp")) for x in rows if x["system"] == s])
                                                   for s in SYSTEMS}})

    speed, usage = {}, {}
    for s in SYSTEMS:
        xs = [x for x in rows if x["system"] == s]
        ms = [x["ms"] for x in xs]
        speed[s] = {"p50_ms": pctl(ms, .5), "p95_ms": pctl(ms, .95),
                    "real_time_factor": round(sum(ms) / 1000 / max(1e-9, sum(x["audio_s"] for x in xs)), 3) if xs else None}
        usage[s] = {"calls": len(xs), "audio_s": round(sum(x["audio_s"] for x in xs), 1),
                    "in_tok": sum(x.get("in_tok") or 0 for x in xs), "out_tok": sum(x.get("out_tok") or 0 for x in xs),
                    "final_errors": sum(x["failed"] for x in xs),
                    "transient_error_records": sum(1 for r in allraw if r["system"] == s and r.get("error")),
                    "first_pass_empty": sum(1 for r in allraw if r["system"] == s and r.get("hyp") == "" and "empty_attempts" not in r)}
    for v in ("v3", "v4"):  # v4 assumed at the v3 list price
        usage[f"saaras:{v}-transcribe"]["inr_at_v3_list_price"] = round(usage[f"saaras:{v}-transcribe"]["audio_s"] / 3600 * 30, 2)

    examples = []
    for cfg in ("ta_in", "or_in", "as_in", "ur_pk", "sd_in"):
        ids = [i for i, m in man.items() if m["lang"] == cfg][:1]
        for i in ids:
            ex = {"id": i, "language": LANGS[cfg][0], "reference": man[i]["ref"], "outputs": {}}
            for x in rows:
                if x["id"] == i:
                    ex["outputs"][x["system"]] = {"hyp": x.get("hyp"), "wer": round(x["wer"], 3), "cer": round(x["cer"], 3)}
            examples.append(ex)

    langs_present = sorted({m["lang"] for m in man.values()})
    res = {"uc": UC, "title": "Citizen helpline speech-to-text across India's languages",
           "business_question": "A state or national citizen helpline takes calls in many Indian languages: which speech-to-text "
                                "works in all of them, and how bad is its weakest language?",
           "dataset": {"name": "FLEURS (google/fleurs) test split", "source": "https://huggingface.co/datasets/google/fleurs",
                       "license": "CC-BY-4.0", "n": len(man), "languages": [LANGS[c][0] for c in langs_present],
                       "synthetic": False,
                       "how_made": f"First {N_PER_LANG} distinct sentences of at most {MAX_S} s (in archive order) of each Indic FLEURS test set, "
                                   "real volunteers reading Wikipedia sentences; reference = FLEURS raw_transcription."},
           "systems": list(SYSTEMS), "metrics": metrics,
           "per_language": per_lang, "worst_language": worst, "cannot_handle": cant,
           "speed": speed, "usage": usage, "examples": examples, "findings": [], "caveats": [], "verdict": ""}
    old = RESULTS / f"{UC}.json"
    if old.exists():
        prev = json.loads(old.read_text())
        for k in ("findings", "caveats", "verdict"):
            res[k] = prev.get(k) or res[k]
    write_result(UC, res)
    return res, rows


if __name__ == "__main__":
    for s in sys.argv[1:] or ["fetch", "stt", "whisper", "score"]:
        log(UC, "== step", s)
        globals()[s]()
