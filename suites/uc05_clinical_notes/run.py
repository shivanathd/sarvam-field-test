"""uc05_clinical_notes: mixed-language doctor-patient consultations -> structured English clinical note.

Text track : dialogue text -> note JSON (sarvam-105b think off/on, gemini-3.8-flash think off/on, local models).
Audio track: 15 dialogues voiced with gemini-3.8-flash-tts (2 voices), then
             (a) saaras:v3 batch STT, mode=translate, diarization -> sarvam-105b note
             (b) gemini-3.8-flash on the audio directly -> note
             (c) saaras:v4 translate / codemix (diarized) -> sarvam-105b, (d) gpt-4o-transcribe -> gpt-5.4-mini.

Usage:
  .venv/bin/python suites/uc05_clinical_notes/run.py                 # TTS + API systems (text and audio)
  .venv/bin/python suites/uc05_clinical_notes/run.py --systems sarvam-30b-local qwen3-30b-local
  .venv/bin/python suites/uc05_clinical_notes/run.py --score-only
Resumable: (dialogue id, system) already in results/raw/uc05_clinical_notes.jsonl are skipped; audio and STT
outputs are cached under data/uc05_clinical_notes/.
"""
import argparse, io, json, os, re, sys, threading, time, unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from common.bench import (DATA, SCRIPTS, edit_distance, GEMINI_CHAT, GEMINI_TTS, SARVAM, _retry, bootstrap_ci, chat, extract_json, log, pctl,
                          raw_append, raw_load, sarvam_post, wait_for_local, write_result)

UC = "uc05_clinical_notes"
D = DATA / UC
AUDIO, STT = D / "audio", D / "stt"
TEXT_API = ["sarvam-105b", "sarvam-105b-think", GEMINI_CHAT, GEMINI_CHAT + "-think",
            "openai:gpt-5.4-mini", "openai:gpt-5.4-mini-think",  # price-matched tier, full set
            "or:anthropic/claude-haiku-5.5", "or:anthropic/claude-haiku-5.5-think"]
FRONTIER = ["gemini-pro-latest-think", "openai:gpt-5.5-think", "or:anthropic/claude-sonnet-5.5-think"]  # 30 dialogues
LOCAL = ["sarvam-30b-local", "qwen3-30b-local"]
AUDIO_SYSTEMS = ["audio:saaras-v3-translate+sarvam-105b", "audio:" + GEMINI_CHAT, "audio:gpt-4o-transcribe+gpt-5.4-mini"]
OAI_STT = D / "stt_openai"
# saaras pipelines: system -> (model, mode, cache dir). v4 takes with_diarization directly ('saaras:v4-multispk' is
# rejected as deprecated in favour of 'saaras-multispeaker').
SAARAS = {AUDIO_SYSTEMS[0]: ("saaras:v3", "translate", STT),
          "audio:saaras-v4-translate+sarvam-105b": ("saaras:v4", "translate", D / "stt_v4_translate"),
          "audio:saaras-v4-codemix+sarvam-105b": ("saaras:v4", "codemix", D / "stt_v4_codemix")}
AUDIO_SYSTEMS += list(SAARAS)[1:]
FRONTIER_IDS = {f"d{round(i * 40 / 30) + 1:02d}" for i in range(30)}  # 30 of 40, evenly spread over languages
LANG_CODE = {"hi-en": "hi-IN", "ml-en": "ml-IN", "ta-en": "ta-IN", "bn-en": "bn-IN", "mr-en": "mr-IN"}
SEM = {"sarvam": threading.Semaphore(3), "gemini": threading.Semaphore(4), "local": threading.Semaphore(1),
       "openai": threading.Semaphore(4), "openrouter": threading.Semaphore(4)}
LOCK = threading.Lock()
DEAD = set()

NOTE_PROMPT = """You are a clinical scribe in an Indian outpatient clinic. Convert the consultation into a structured English OPD note.
Use ONLY what was said. Never add a medicine, dose, test or advice that was not said. List only the medicines the doctor finally prescribed (exclude medicines the patient already took on their own, medicines stopped or refused, and doses the doctor corrected — use the final dose).
Return JSON only, with exactly these keys:
{"chief_complaint": str, "duration": str (e.g. "3 days"),
 "vitals": {"bp": str|null, "pulse": number|null, "temperature_f": number|null, "spo2": number|null, "weight_kg": number|null, "blood_sugar": number|null},
 "diagnosis": str,
 "medications": [{"drug": str, "dose": str (number + unit, e.g. "500 mg", "5 ml"), "frequency": "OD"|"BD"|"TDS"|"QID"|"HS"|"SOS"|"weekly", "duration_days": int|null (null = continue long-term)}],
 "allergies": [str] (empty list if none),
 "red_flag_advice": [str],
 "follow_up": str}"""


# ---------- data ----------
def load():
    return [json.loads(p.read_text()) for p in sorted((D / "dialogues").glob("d*.json"))]


def other_role(d):
    return "Attendant" if any(t["speaker"] == "attendant" for t in d["turns"]) else "Patient"


def render(d):
    return "\n".join(f"{t['speaker'].capitalize()}: {t['text']}" for t in d["turns"])


# ---------- normalisation & scoring ----------
def norm(s):
    s = unicodedata.normalize("NFC", str(s or ""))
    s = "".join(str(unicodedata.digit(c)) if c.isdigit() and unicodedata.digit(c, None) is not None else c for c in s)
    return re.sub(r"(?<=\d),(?=\d)", "", s).casefold()


def nums(s):
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", norm(s))]


STOP = {"of", "the", "a", "an", "in", "on", "to", "and", "or", "with", "for", "from", "at", "by", "is", "be", "any"}


SYN = {}  # a few clinical synonyms so a correct paraphrase is not scored as a miss
for _canon, _words in {"bleed": "blood bleeding bleed bloody", "abdom": "abdomen abdominal stomach tummy belly",
                       "pain": "pain ache aches aching painful", "urin": "urine urination urinate urinating pee",
                       "drows": "drowsy drowsiness sleepy lethargic lethargy", "seiz": "seizure seizures fits convulsion convulsions",
                       "breath": "breath breathing breathless breathlessness"}.items():
    SYN.update({w: _canon for w in _words.split()})


def _toks(s):
    return [SYN.get(w, w) for w in re.findall(r"[a-z0-9]+", norm(s)) if w not in STOP]


def _tok_eq(a, b):
    return a == b or (len(a) >= 4 and len(b) >= 4 and a[:4] == b[:4])


def alias_hit(text, aliases):
    """Free-text field match: an alias hits if >= 2/3 of its content words occur in the output (4-letter stem
    match, so 'urine'~'urination', 'blurred'~'blurring'). Exact substring always counts."""
    t, tt = norm(text), _toks(text)
    for a in aliases:
        at = _toks(a)
        if norm(a) in t or (at and sum(any(_tok_eq(x, y) for y in tt) for x in at) >= max(1, -(-2 * len(at) // 3))):
            return True
    return False


FREQ = [(r"\b(qid|qds|four times|1-1-1-1)\b", "QID"), (r"\b(tds|tid|thrice|three times|1-1-1)\b", "TDS"),
        (r"\b(bd|bid|twice|two times|1-0-1|morning and (evening|night))\b", "BD"),
        (r"\b(hs|bedtime|at night before sleep|0-0-1)\b", "HS"), (r"\b(sos|prn|as needed|when needed|if needed|after (every|each))\b", "SOS"),
        (r"\b(weekly|once a week)\b", "weekly"), (r"\b(od|qd|once daily|once a day|1-0-0|daily)\b", "OD")]


def canon_freq(f):
    f = norm(f).strip()
    if f.upper() in ("OD", "BD", "TDS", "QID", "HS", "SOS"):
        return f.upper()
    for pat, code in FREQ:
        if re.search(pat, f):
            return code
    return f


def freq_eq(out, gold):
    """HS ('once at night') and OD are both once-daily; dialogues often say 'once a day, at night'."""
    return out == gold or {out, gold} == {"OD", "HS"}


def canon_dose(s):
    """'1 g' -> (1000.0, 'mg'); '7.5ml' -> (7.5, 'ml'); unit-less -> (x, '')."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(mg|g|ml|mcg|µg|units?|iu|tablet|tab)?", norm(s))
    if not m:
        return None
    v, u = float(m.group(1)), (m.group(2) or "").replace("µg", "mcg")
    if u == "g":
        v, u = v * 1000, "mg"
    if u in ("unit", "units", "iu"):
        u = "units"
    return v, u


def dose_eq(out, gold):
    """Any amount in the output equal to the gold dose ('250 mg/5 ml, 7.5 ml' contains 7.5 ml)."""
    b = canon_dose(gold)
    parts = re.findall(r"\d+(?:\.\d+)?\s*(?:mg|g|ml|mcg|µg|units?|iu|tablet|tab)?", norm(out))
    return any(a and b and a[0] == b[0] and (a[1] == b[1] or a[1] in ("", "tablet", "tab"))
               for a in map(canon_dose, parts))


def duration_days(s):
    t = norm(s)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(day|week|month|din|d\b|wk)", t)
    if not m:
        word = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "ten": 10}
        m2 = re.search(r"\b(one|two|three|four|five|six|seven|ten|a)\s*(day|week|month)", t)
        if not m2:
            return None
        v, u = word.get(m2.group(1), 1), m2.group(2)
    else:
        v, u = float(m.group(1)), m.group(2)
    return v * (7 if u.startswith("w") else 30 if u.startswith("m") else 1)


def vital_hit(key, gold, vit):
    alt = {"temp_f": "temperature_f"}.get(key, key)
    v = (vit or {}).get(alt, (vit or {}).get(key))
    if v is None:
        return False
    if key == "bp":
        return nums(v)[:2] == nums(gold)[:2]
    n = nums(v)
    return bool(n) and abs(n[0] - float(gold)) < 0.05


def match_med(out_drug, gold_med):
    """Alias contained in the output (or vice versa); a 1-2 letter misspelling of a long name ('Glimipride') also
    counts, since a pharmacist would read it correctly and it is not an invented drug."""
    o = norm(out_drug)
    first = o.split()[0] if o.split() else ""
    return any(norm(a) in o or (len(o) > 3 and o in norm(a)) or
               (len(norm(a)) >= 7 and edit_distance(first, norm(a).split()[0]) <= 2) for a in gold_med["drug"])


def score(d, note):
    g = d["gold"]
    if not isinstance(note, dict):
        return {"parse_ok": False}
    dialogue_nums = set(nums(render(d)))
    meds = [m for m in (note.get("medications") or []) if isinstance(m, dict)]
    s = {"parse_ok": True,
         "chief_complaint": alias_hit(note.get("chief_complaint"), g["chief_complaint"]),
         "duration": duration_days(str(note.get("duration"))) == g["duration"]["value"] * {"days": 1, "weeks": 7, "months": 30}[g["duration"]["unit"]],
         "diagnosis": alias_hit(note.get("diagnosis"), g["diagnosis"]),
         "follow_up": alias_hit(note.get("follow_up"), g["follow_up"]),
         "vitals": [vital_hit(k, v, note.get("vitals")) for k, v in g["vitals"].items()]}
    red = " | ".join(map(str, note.get("red_flag_advice") or []))
    s["red_flags"] = [alias_hit(red, a) for a in g["red_flags"]]
    allg = " | ".join(map(str, note.get("allergies") or []))
    no_allergy = not allg.strip() or re.search(r"\b(none|nil|no known|nkda|not known)\b", norm(allg))
    s["allergy_captured"] = all(alias_hit(allg, a) for a in g["allergies"]) if g["allergies"] else None
    s["false_allergy"] = None if g["allergies"] else not no_allergy
    s["meds"], used = [], set()
    for gm in g["medications"]:
        hit = next((i for i, m in enumerate(meds) if i not in used and match_med(str(m.get("drug")), gm)), None)
        if hit is None:
            s["meds"].append({"found": False})
            continue
        used.add(hit)
        m = meds[hit]
        dose_ok = dose_eq(str(m.get("dose")), gm["dose"])
        dn = canon_dose(str(m.get("dose")))
        s["meds"].append({"found": True, "dose": dose_ok, "freq": freq_eq(canon_freq(str(m.get("frequency"))), gm["frequency"]),
                          "dur": (m.get("duration_days") in (None, "null", "") if gm["duration_days"] is None
                                  else nums(m.get("duration_days"))[:1] == [float(gm["duration_days"])]),
                          "dose_hallucinated": bool(dn) and dn[0] not in dialogue_nums and not dose_ok})
    extra = [str(m.get("drug")) for i, m in enumerate(meds) if i not in used]
    s["extra_meds"] = extra
    # the note must be in English: no Indic-script characters anywhere in it
    s["english_only"] = not any(lo <= ord(c) <= hi for c in json.dumps(note, ensure_ascii=False)
                                for k, (lo, hi) in SCRIPTS.items() if k != "Latin")
    s["trap_meds"] = [x for x in extra if any(norm(t) in norm(x) for t in g["not_prescribed"])]
    return s


FIELDS = ["chief_complaint", "duration", "diagnosis", "follow_up"]


def field_recall(s, field):
    if not s.get("parse_ok"):
        return 0.0 if field not in ("allergy",) else None
    if field in FIELDS:
        return float(s[field])
    if field in ("vitals", "red_flags"):
        return sum(s[field]) / len(s[field]) if s[field] else None
    if field == "med_found":
        return sum(m["found"] for m in s["meds"]) / len(s["meds"])
    if field == "med_exact":  # drug + dose + frequency all right
        return sum(m.get("found", False) and m["dose"] and m["freq"] for m in s["meds"]) / len(s["meds"])
    if field == "med_exact_with_duration":
        return sum(m.get("found", False) and m["dose"] and m["freq"] and m["dur"] for m in s["meds"]) / len(s["meds"])


def halluc_count(s):
    """Safety metric: medicines listed that were not prescribed + doses with a number never said in the dialogue."""
    if not s.get("parse_ok"):
        return None
    return len(s["extra_meds"]) + sum(m.get("dose_hallucinated", False) for m in s["meds"])


# ---------- audio: TTS ----------
def tts(d):
    """Two-voice audio with gemini-3.8-flash-tts. Returns path (cached)."""
    p = AUDIO / f"{d['id']}.wav"
    if p.exists():
        return p
    from google import genai
    from google.genai import types
    import numpy as np, soundfile as sf
    role2 = other_role(d)
    # gemini-3.8-flash-tts multi-speaker needs one text part per turn tagged with speech_metadata.speaker
    style = f"natural conversation in an Indian outpatient clinic, {d['lang']} mixed with English, normal pace"
    turns = [types.Part(text=t["text"], speech_metadata=types.SpeechMetadata(
        speaker="Doctor" if t["speaker"] == "doctor" else role2, style=style)) for t in d["turns"]]
    voices = [("Doctor", "Charon"), (role2, "Kore")]
    cfg = types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(
        multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(speaker_voice_configs=[
            types.SpeakerVoiceConfig(speaker=n, voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=v))) for n, v in voices])))
    c = genai.Client()
    r = _retry(lambda: c.models.generate_content(model=GEMINI_TTS, contents=[types.Content(role="user", parts=turns)], config=cfg))
    pcm = r.candidates[0].content.parts[0].inline_data.data
    AUDIO.mkdir(parents=True, exist_ok=True)
    sf.write(p, np.frombuffer(pcm, dtype=np.int16), 24000, subtype="PCM_16")
    u = r.usage_metadata
    with LOCK:
        raw_append(UC, {"id": d["id"], "system": "tts:" + GEMINI_TTS, "in_tok": u.prompt_token_count,
                        "out_tok": u.candidates_token_count, "audio_s": len(pcm) / 2 / 24000})
    return p


# ---------- audio: Sarvam batch STT ----------
def _sarvam_get(path):
    h = {"api-subscription-key": os.environ["SARVAM_API_KEY"]}
    return _retry(lambda: requests.get(SARVAM + path, headers=h, timeout=60).json())


def saaras_batch(dialogues, model, mode, outdir):
    """One batch job per language with diarization (2 speakers). Outputs cached in outdir, one JSON per dialogue."""
    outdir.mkdir(parents=True, exist_ok=True)
    by_lang = {}
    for d in dialogues:
        if not (outdir / f"{d['id']}.json").exists():
            by_lang.setdefault(d["pair"], []).append(d)
    for pair, ds in by_lang.items():
        params = {"model": model, "mode": mode, "language_code": LANG_CODE[pair],
                  "with_diarization": True, "num_speakers": 2}
        job = sarvam_post("/speech-to-text/job/v1", {"job_parameters": params})
        if "_error" in job:
            log(UC, "saaras job create failed", pair, job)
            if job["_error"] == 402:
                DEAD.add("sarvam")
                return
            continue
        jid = job["job_id"]
        names = [f"{d['id']}.wav" for d in ds]
        up = sarvam_post("/speech-to-text/job/v1/upload-files", {"job_id": jid, "files": names})
        for n in names:
            url = up["upload_urls"][n]
            url = url["file_url"] if isinstance(url, dict) else url
            r = requests.put(url, data=(AUDIO / n).read_bytes(), headers={"x-ms-blob-type": "BlockBlob"}, timeout=300)
            r.raise_for_status()
        sarvam_post(f"/speech-to-text/job/v1/{jid}/start", {})
        t0 = time.time()
        while True:
            st = _sarvam_get(f"/speech-to-text/job/v1/{jid}/status")
            if st.get("job_state") in ("Completed", "Failed", "PartiallyCompleted") or time.time() - t0 > 1800:
                break
            time.sleep(10)
        log(UC, "saaras job", pair, st.get("job_state"), st.get("error_message"), f"{time.time() - t0:.0f}s")
        # quirk: outputs are named by upload index ("0.json", "1.json"...), not by input file; map via job_details
        out2in = {o["file_name"]: det["inputs"][0]["file_name"] for det in st.get("job_details") or []
                  for o in det.get("outputs") or []}
        dl = sarvam_post("/speech-to-text/job/v1/download-files", {"job_id": jid, "files": list(out2in)})
        for n, url in (dl.get("download_urls") or {}).items():
            url = url["file_url"] if isinstance(url, dict) else url
            out = requests.get(url, timeout=120).json()
            did = Path(out2in[n]).stem
            out["_job"] = {"job_id": jid, "elapsed_s": time.time() - t0, "params": params}
            (outdir / f"{did}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


def stt_dialogue_text(out):
    """Render a saaras diarized output as 'SPEAKER_x: text' lines (falls back to plain transcript)."""
    ents = ((out.get("diarized_transcript") or {}).get("entries")) or []
    if ents:
        return "\n".join(f"Speaker {e.get('speaker_id')}: {e.get('transcript', '').strip()}" for e in ents)
    return out.get("transcript", "")


def speaker_sanity(d, out):
    ents = ((out.get("diarized_transcript") or {}).get("entries")) or []
    spk = [e.get("speaker_id") for e in ents]
    changes = sum(a != b for a, b in zip(spk, spk[1:]))
    gold_changes = sum(a["speaker"] != b["speaker"] for a, b in zip(d["turns"], d["turns"][1:]))
    return {"speakers_detected": len(set(spk)), "speaker_changes": changes, "gold_speaker_changes": gold_changes}


# ---------- running ----------
def kind_of(system):
    return ("sarvam" if "sarvam-105b" in system else "local" if system in LOCAL else
            "openai" if "openai:" in system or "gpt-" in system else "openrouter" if system.startswith("or:") else "gemini")


def note_from_text(system, text):
    base, think = system.replace("-think", ""), system.endswith("-think")
    msgs = [{"role": "system", "content": NOTE_PROMPT},
            {"role": "user", "content": f"Consultation transcript:\n{text}\n\nReturn the JSON note."}]
    return chat(base, msgs, max_tokens=8000 if think else 5000 if base in LOCAL else 1500, think=think)


def note_from_audio_gemini(path):
    from google import genai
    from google.genai import types
    c = genai.Client()
    t = time.time()
    cfg = types.GenerateContentConfig(system_instruction=NOTE_PROMPT, temperature=0, max_output_tokens=1500,
                                      thinking_config=types.ThinkingConfig(thinking_budget=0))
    contents = [types.Content(role="user", parts=[types.Part.from_bytes(data=path.read_bytes(), mime_type="audio/wav"),
                                                  types.Part(text="This is the consultation recording. Return the JSON note.")])]
    r = _retry(lambda: c.models.generate_content(model=GEMINI_CHAT, contents=contents, config=cfg))
    u = r.usage_metadata
    return {"text": r.text or "", "ms": (time.time() - t) * 1000, "in_tok": u.prompt_token_count,
            "out_tok": u.candidates_token_count}


def openai_transcribe(d):
    """gpt-4o-transcribe on the TTS audio, source-language transcript (no diarization). Cached."""
    p = OAI_STT / f"{d['id']}.json"
    if not p.exists():
        lang = LANG_CODE[d["pair"]][:2]

        def go():
            r = requests.post("https://api.openai.com/v1/audio/transcriptions",
                              headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
                              data={"model": "gpt-4o-transcribe", "language": lang},
                              files={"file": (f"{d['id']}.wav", (AUDIO / f"{d['id']}.wav").read_bytes(), "audio/wav")},
                              timeout=300)
            if r.status_code == 429 or r.status_code >= 500:
                raise RuntimeError(f"{r.status_code} {r.text[:200]}")
            r.raise_for_status()
            return r.json()
        OAI_STT.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(_retry(go), ensure_ascii=False, indent=1))
    return json.loads(p.read_text())["text"]


def run_one(d, system):
    kind = kind_of(system)
    if kind in DEAD:
        return {"id": d["id"], "system": system, "skipped": True}
    extra = {}
    with SEM[kind]:
        try:
            if system in SAARAS:
                out = json.loads((SAARAS[system][2] / f"{d['id']}.json").read_text())
                extra = {"stt_text": stt_dialogue_text(out), "speaker": speaker_sanity(d, out)}
                r = note_from_text("sarvam-105b", extra["stt_text"])
            elif system == AUDIO_SYSTEMS[2]:
                extra = {"stt_text": openai_transcribe(d)}
                r = note_from_text("openai:gpt-5.4-mini", extra["stt_text"])
            elif system == AUDIO_SYSTEMS[1]:
                r = note_from_audio_gemini(AUDIO / f"{d['id']}.wav")
            else:
                r = note_from_text(system, render(d))
        except Exception as e:
            r = {"text": "", "error": repr(e)[:300]}
    if "402" in str(r.get("error")):
        DEAD.add(kind)
        log(UC, f"credit error on {system}; no more {kind} calls")
    rec = {"id": d["id"], "system": system, **extra, **r, "note": extract_json(r.get("text") or "")}
    with LOCK:
        raw_append(UC, rec)
    return rec


def run(pairs):
    done = {(r["id"], r["system"]) for r in raw_load(UC) if not r.get("error") and "note" in r}
    todo = [(d, s) for d, s in pairs if (d["id"], s) not in done]
    log(UC, f"{len(todo)} notes to make")
    with ThreadPoolExecutor(8) as ex:
        for i, rec in enumerate(ex.map(lambda t: run_one(*t), todo)):
            if not rec.get("skipped"):
                log(UC, i, rec["system"], rec["id"], "parsed" if rec.get("note") else "NO-JSON", rec.get("error", ""))


# ---------- results ----------
def summarise(dialogues):
    dby = {d["id"]: d for d in dialogues}
    recs, tts_recs = {}, []
    for r in raw_load(UC):
        if r["system"].startswith("tts:"):
            tts_recs.append(r)
        elif not r.get("error") and "note" in r and r["id"] in dby:
            recs[(r["id"], r["system"])] = r
    systems = [s for s in TEXT_API + FRONTIER + LOCAL + AUDIO_SYSTEMS if any(k[1] == s for k in recs)]
    S = {k: score(dby[k[0]], r["note"]) for k, r in recs.items()}
    audio_ids = [d["id"] for d in dialogues if d.get("audio_subset")]

    def ci(sysname, fn, ids=None):
        return bootstrap_ci([fn(S[(i, sysname)]) for i in (ids or dby) if (i, sysname) in S])

    mdefs = [("fact_recall_overall", True, lambda s: None if not s.get("parse_ok") else
              sum(x for x in [field_recall(s, f) for f in FIELDS + ["vitals", "red_flags", "med_found"]] if x is not None) /
              len([x for x in [field_recall(s, f) for f in FIELDS + ["vitals", "red_flags", "med_found"]] if x is not None]))]
    mdefs += [(f"recall_{f}", True, lambda s, f=f: field_recall(s, f)) for f in FIELDS + ["vitals", "red_flags", "med_found"]]
    mdefs += [("medication_exact_drug_dose_freq", True, lambda s: field_recall(s, "med_exact")),
              ("medication_exact_incl_duration", True, lambda s: field_recall(s, "med_exact_with_duration")),
              ("hallucinated_meds_or_doses_per_note", False, halluc_count),
              ("notes_with_any_hallucinated_med_or_dose", False, lambda s: None if halluc_count(s) is None else float(halluc_count(s) > 0)),
              ("trap_drug_listed_as_prescribed", False, lambda s: None if not s.get("parse_ok") else float(bool(s["trap_meds"]))),
              ("allergy_capture_rate", True, lambda s: None if not s.get("parse_ok") or s["allergy_captured"] is None else float(s["allergy_captured"])),
              ("false_allergy_rate", False, lambda s: None if not s.get("parse_ok") or s["false_allergy"] is None else float(s["false_allergy"])),
              ("note_fully_in_english", True, lambda s: None if not s.get("parse_ok") else float(s["english_only"])),
              ("json_parse_ok", True, lambda s: float(s.get("parse_ok", False)))]
    metrics = []
    for name, hib, fn in mdefs:
        m = {"name": name, "higher_is_better": hib, "unit": "fraction" if "per_note" not in name else "count",
             "values": {s: ci(s, fn) for s in systems}}
        # apples-to-apples: every system on the 15 audio-subset dialogues
        m["values_audio_subset"] = {s: ci(s, fn, audio_ids) for s in systems}
        m["values_frontier_subset"] = {s: ci(s, fn, sorted(FRONTIER_IDS)) for s in systems}
        metrics.append(m)
    pairs = sorted({d["pair"] for d in dialogues})
    per_language = {n: {p: {s: ci(s, fn, [d["id"] for d in dialogues if d["pair"] == p])["mean"] for s in systems}
                        for p in pairs}
                    for n, _, fn in mdefs if n in ("fact_recall_overall", "medication_exact_drug_dose_freq",
                                                   "hallucinated_meds_or_doses_per_note")}
    speed, usage = {}, {}
    for s in systems:
        rs = [r for k, r in recs.items() if k[1] == s]
        speed[s] = {"p50_ms": pctl([r.get("ms") for r in rs], .5), "p95_ms": pctl([r.get("ms") for r in rs], .95)}
        usage[s] = {"in_tok": sum(r.get("in_tok") or 0 for r in rs), "out_tok": sum(r.get("out_tok") or 0 for r in rs),
                    "reasoning_tok": sum(r.get("reasoning_tok") or 0 for r in rs), "calls": len(rs),
                    "cost_usd": round(sum(r.get("cost_usd") or 0 for r in rs), 4) or None}
    if tts_recs:
        usage["tts:" + GEMINI_TTS] = {"in_tok": sum(r["in_tok"] or 0 for r in tts_recs),
                                      "out_tok": sum(r["out_tok"] or 0 for r in tts_recs),
                                      "audio_s": sum(r["audio_s"] for r in tts_recs), "calls": len(tts_recs)}
    for model, mode, outdir in SAARAS.values():
        files = sorted(outdir.glob("*.json")) if outdir.exists() else []
        if files:
            usage[f"{model} (batch, {mode}, diarization)"] = {
                "audio_s": sum(sf_dur(AUDIO / f"{p.stem}.wav") for p in files), "files": len(files)}
    if OAI_STT.exists() and list(OAI_STT.glob("*.json")):
        usage["gpt-4o-transcribe"] = {"audio_s": sum(sf_dur(AUDIO / f"{p.stem}.wav") for p in OAI_STT.glob("*.json")),
                                      "files": len(list(OAI_STT.glob("*.json")))}
    speaker = {}
    for sysname in SAARAS:
        spk = [r["speaker"] for k, r in recs.items() if k[1] == sysname and r.get("speaker")]
        if spk:
            speaker[sysname] = {"n": len(spk), "two_speakers_detected": bootstrap_ci([float(x["speakers_detected"] == 2) for x in spk]),
                                "speaker_change_ratio_median": pctl([x["speaker_changes"] / max(1, x["gold_speaker_changes"]) for x in spk], .5)}
    return systems, metrics, per_language, speed, usage, recs, S, speaker


def sf_dur(p):
    import soundfile as sf
    return sf.info(str(p)).duration if p.exists() else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", nargs="*", default=TEXT_API + AUDIO_SYSTEMS)
    ap.add_argument("--score-only", action="store_true")
    a = ap.parse_args()
    dialogues = load()
    audio = [d for d in dialogues if d.get("audio_subset")]
    if not a.score_only:
        if any(s.startswith("audio:") for s in a.systems):
            with ThreadPoolExecutor(4) as ex:
                list(ex.map(tts, audio))
            log(UC, f"audio ready: {len(list(AUDIO.glob('*.wav')))} files")
            for sysname, (model, mode, outdir) in SAARAS.items():
                if sysname in a.systems:
                    saaras_batch(audio, model, mode, outdir)
        pairs = [(d, s) for s in a.systems if s not in LOCAL and not s.startswith("audio:") for d in dialogues
                 if s not in FRONTIER or d["id"] in FRONTIER_IDS]
        pairs += [(d, AUDIO_SYSTEMS[2]) for d in audio if AUDIO_SYSTEMS[2] in a.systems]
        pairs += [(d, AUDIO_SYSTEMS[1]) for d in audio if AUDIO_SYSTEMS[1] in a.systems]
        pairs += [(d, s) for s, (_, _, outdir) in SAARAS.items() if s in a.systems
                  for d in audio if (outdir / f"{d['id']}.json").exists()]
        run(pairs)
        for s in [s for s in a.systems if s in LOCAL]:  # one local model at a time
            if wait_for_local(s):
                run([(d, s) for d in dialogues])
            else:
                log(UC, f"{s} not up, skipping")
    systems, metrics, per_language, speed, usage, recs, S, speaker = summarise(dialogues)
    extra_p = ROOT / "suites" / UC / "summary.json"
    extra = json.loads(extra_p.read_text()) if extra_p.exists() else {}
    dby = {d["id"]: d for d in dialogues}
    examples = []
    for did in extra.get("example_ids", ["d01", "d26"]):
        ex = {"id": did, "pair": dby[did]["pair"], "trap": dby[did]["trap"], "dialogue": render(dby[did]),
              "gold": dby[did]["gold"], "outputs": {}}
        for s in systems:
            if (did, s) in recs:
                ex["outputs"][s] = {"note": recs[(did, s)]["note"], "score": S[(did, s)]}
        examples.append(ex)
    write_result(UC, {
        "uc": UC, "title": "Mixed-language doctor-patient consultation -> English clinical note",
        "business_question": "A clinic records an outpatient consultation held in Hinglish / Malayalam-English / Tamil-English / "
                             "Bengali-English / Marathi-English. Which model turns it into a correct structured English "
                             "note, and which one invents medicines or doses (the safety risk)?",
        "dataset": {"name": "uc05 synthetic OPD consultations", "source": "authored for this benchmark",
                    "license": "CC-BY-4.0 (this repo)", "n": len(dialogues), "n_audio": len(audio),
                    "languages": sorted({d["pair"] for d in dialogues}), "synthetic": True,
                    "frontier_subset_ids": sorted(FRONTIER_IDS),
                    "how_made": "40 fictional outpatient dialogues (8 per language pair; fever, diabetes, hypertension, "
                                "pregnancy follow-up, paediatrics; 11-16 turns) written by an LLM author (Claude) with "
                                "gold facts (complaint, duration, vitals, diagnosis, each medicine with dose/frequency/"
                                "duration, allergies, red flags, follow-up). Every dialogue has a trap: a drug mentioned "
                                "but not prescribed, a dose corrected mid-conversation, or a late-disclosed allergy. 15 "
                                "dialogues voiced with gemini-3.8-flash-tts (2 prebuilt voices). Fake names only."},
        "systems": systems, "metrics": metrics, "per_language": per_language, "speed": speed, "usage": usage,
        "speaker_attribution": speaker,
        "findings": extra.get("findings", []), "caveats": extra.get("caveats", []), "verdict": extra.get("verdict", ""),
        "examples": examples,
    })
    for m in metrics:
        log(UC, m["name"], {s: (round(v["mean"], 3) if v["mean"] is not None else None, v["n"]) for s, v in m["values"].items()})


if __name__ == "__main__":
    main()
