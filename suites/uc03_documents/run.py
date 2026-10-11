"""UC03 documents: read Indian-script business documents (GST invoices, KYC forms, land records, bills, ration cards).

Pipelines compared on 60 synthetic pages x 2 conditions (clean render, phone photo), plus a "harsh" bad-photo
condition on a 16-page subset (one page per type/language group + 5):
  sarvam-vision                      legacy Document Digitization job API (/doc-digitization/job/v1) -> markdown
  sarvam-vision+sarvam-105b          that markdown -> JSON fields with sarvam-105b (think off)
  sarvam-vision+gemini-3.8-flash     same markdown -> JSON fields with Gemini (separates OCR from extraction)
  gemini-3.8-flash                   image -> JSON fields directly
  gemini-3.8-flash-ocr               image -> plain transcription (for CER against the same gold)
  openai:gpt-5.4-mini, or:anthropic/claude-haiku-5.5    image -> JSON fields (price-matched tier, all images)
  sarvam-docai-extract               Sarvam Document AI Extract (/doc-ai/v1, Sarvam Vision 1.5): image + field schema ->
                                     JSON in one job; on FRONTIER_SET plus the clean render of the same 30 pages
  gemini-pro-latest, openai:gpt-5.5, or:anthropic/claude-sonnet-5.5   image -> JSON fields, think on, on the fixed
                                     30-image FRONTIER_SET (16 harsh photos + photo of the first 14 other pages)
Resumable: every API result is a line in results/raw/uc03_documents.jsonl keyed by (id, cond, system).
Run:  .venv/bin/python suites/uc03_documents/run.py   (after make_data.py)
"""
import base64, io, json, os, re, sys, threading, time, unicodedata, zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
from common.bench import *  # noqa
from common.bench import _retry
from make_data import DOC_TYPES

UC = "uc03_documents"
D = DATA / UC
LANG = {"hi": "hi-IN", "mr": "mr-IN", "ta": "ta-IN", "bn": "bn-IN", "kn": "kn-IN", "te": "te-IN", "gu": "gu-IN",
        "ml": "ml-IN"}
DOC_DESC = {"gst_invoice": "GST tax invoice", "kyc_form": "bank account-opening (KYC) form",
            "land_7_12": "Maharashtra 7/12 land record extract", "patta": "Tamil Nadu patta/chitta land extract",
            "electricity_bill": "electricity bill", "ration_card": "ration card"}
CONDS = {"clean": "{id}.png", "photo": "{id}_photo.jpg", "harsh": "{id}_harsh.jpg"}  # harsh: 16-page subset
VISION, S_EXT, G_EXT, G_IMG, G_OCR = ("sarvam-vision", "sarvam-vision+sarvam-105b", "sarvam-vision+gemini-3.8-flash",
                                      "gemini-3.8-flash", "gemini-3.8-flash-ocr")
CHEAP_IMG = ["openai:gpt-5.4-mini", "or:anthropic/claude-haiku-5.5"]
FRONTIER_IMG = ["gemini-pro-latest", "openai:gpt-5.5", "or:anthropic/claude-sonnet-5.5"]
_lock = threading.Lock()
STOP = {}  # api -> reason, set on credit/402 errors


def _frontier_set():
    from make_data import HARSH_IDS
    ids = [json.loads(l)["id"] for l in (DATA / "uc03_documents" / "gold.jsonl").read_text().splitlines()]
    return [(i, "harsh") for i in HARSH_IDS] + [(i, "photo") for i in ids if i not in HARSH_IDS][:14]


FRONTIER_SET = _frontier_set()  # fixed 30 images: all 16 harsh photos + phone photo of the first 14 other pages


def save(rec):
    with _lock:
        raw_append(UC, rec)


# ---------- Sarvam Vision (job API: create -> upload-files -> PUT -> start -> poll status -> download-files) ----------
def sarvam_vision(img: Path, lang):
    hdr = {"api-subscription-key": os.environ["SARVAM_API_KEY"]}
    t = time.time()
    j = sarvam_post("/doc-digitization/job/v1", {"job_parameters": {"language": LANG[lang], "output_format": "md"}})
    if "_error" in j:
        return {"error": j}
    jid = j["job_id"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:  # upload accepts only PDF or ZIP; a 1-image ZIP keeps the original pixels
        z.write(img, "page_001" + img.suffix)
    u = sarvam_post("/doc-digitization/job/v1/upload-files", {"job_id": jid, "files": ["page.zip"]})
    if "_error" in u:
        return {"error": u}
    url = u["upload_urls"]["page.zip"]["file_url"]
    _retry(lambda: requests.put(url, data=buf.getvalue(), timeout=120,
                                headers={"x-ms-blob-type": "BlockBlob", "Content-Type": "application/zip"}
                                ).raise_for_status())
    s = sarvam_post(f"/doc-digitization/job/v1/{jid}/start", {})
    if "_error" in s:
        return {"error": s}
    while True:
        s = _retry(lambda: requests.get(f"{SARVAM}/doc-digitization/job/v1/{jid}/status", headers=hdr,
                                        timeout=60).json())
        if s.get("job_state") in ("Completed", "PartiallyCompleted", "Failed"):
            break
        if time.time() - t > 900:
            return {"error": "timeout", "job_id": jid}
        time.sleep(1.5)
    if s["job_state"] == "Failed":
        return {"error": s.get("error_message") or s, "job_id": jid}
    d = sarvam_post(f"/doc-digitization/job/v1/{jid}/download-files", {})
    md = []
    for v in d["download_urls"].values():
        z = zipfile.ZipFile(io.BytesIO(_retry(lambda: requests.get(v["file_url"], timeout=120).content)))
        md += [z.read(n).decode() for n in z.namelist() if n.endswith(".md")]
    pages = sum(x.get("pages_processed", 0) for x in s.get("job_details", []))
    return {"text": "\n".join(md), "ms": (time.time() - t) * 1000, "pages": pages, "job_id": jid}


# ---------- Sarvam Document AI Extract (/doc-ai/v1, Sarvam Vision 1.5; supersedes doc-digitization) ----------
DOCAI = "sarvam-docai-extract"


def docai_schema(g):
    props = {k: {"type": "string", "description": f"{v}. Copy exactly as printed, in the original script."}
             for k, v in DOC_TYPES[g["doc_type"]][1].items()}
    return {"type": "object", "properties": props}


def sarvam_docai_extract(img: Path, g):
    """POST /doc-ai/v1/job/extract (multipart: file, schema as JSON string, language, output_format=json),
    poll /job/{id}/status until terminal, then GET /job/{id}/results -> {"result": {...}}."""
    hdr = {"api-subscription-key": os.environ["SARVAM_API_KEY"]}
    base = SARVAM + "/doc-ai/v1/job"
    mime = "image/png" if img.suffix == ".png" else "image/jpeg"
    data = img.read_bytes()
    t = time.time()

    def submit():
        r = requests.post(base + "/extract", headers=hdr, timeout=120,
                          files={"file": (img.name, data, mime)},
                          data={"schema": json.dumps(docai_schema(g), ensure_ascii=False),
                                "language": LANG[g["lang"]], "output_format": "json"})
        if r.status_code == 429 or r.status_code >= 500:
            raise RuntimeError(f"{r.status_code} {r.text[:200]}")
        return r

    r = _retry(submit)
    if r.status_code >= 400:
        return {"error": {"_error": r.status_code, "_body": r.text[:400],
                          "_credits": r.status_code == 402 or bool(re.search(r"credit|quota", r.text, re.I))}}
    jid = r.json()["job_id"]
    while True:
        st = _retry(lambda: requests.get(f"{base}/{jid}/status", headers=hdr, timeout=60).json())
        if str(st.get("status", "")).lower() in ("completed", "partially_completed", "failed", "rejected"):
            break
        if time.time() - t > 900:
            return {"error": "timeout", "job_id": jid}
        time.sleep(1)
    if st["status"].lower() in ("failed", "rejected"):
        return {"error": st, "job_id": jid}
    res = _retry(lambda: requests.get(f"{base}/{jid}/results", headers=hdr, timeout=60).json())
    out = res.get("result", res)
    if isinstance(out, list) and len(out) == 1:  # per-page list for multi-page inputs
        out = out[0]
    return {"fields": out, "raw": res, "ms": (time.time() - t) * 1000,
            "pages": (st.get("usage") or {}).get("pages_processed"), "job_id": jid}


# ---------- Gemini on the image ----------
def gemini_image(img: Path, prompt, model=GEMINI_CHAT, think=False):
    from google import genai
    from google.genai import types
    c = genai.Client(http_options=types.HttpOptions(timeout=180_000))
    t = time.time()
    mime = "image/png" if img.suffix == ".png" else "image/jpeg"
    cfg = types.GenerateContentConfig(temperature=0, max_output_tokens=16000 if think else 4000,
                                      thinking_config=types.ThinkingConfig(thinking_budget=-1 if think else 0))
    r = _retry(lambda: c.models.generate_content(
        model=model, config=cfg,
        contents=[types.Part.from_bytes(data=img.read_bytes(), mime_type=mime), prompt]))
    u = r.usage_metadata
    return {"text": r.text or "", "ms": (time.time() - t) * 1000, "in_tok": u.prompt_token_count,
            "out_tok": u.candidates_token_count, "reasoning_tok": u.thoughts_token_count}


def openai_image(system, img: Path, prompt, think=False):
    """Image + prompt to OpenAI ("openai:<model>") or OpenRouter ("or:<model>") in OpenAI chat format."""
    prov, model = system.split(":", 1)
    url, key = (("https://api.openai.com/v1/chat/completions", "OPENAI_API_KEY") if prov == "openai"
                else ("https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY"))
    mime = "image/png" if img.suffix == ".png" else "image/jpeg"
    uri = f"data:{mime};base64," + base64.b64encode(img.read_bytes()).decode()
    msgs = [{"role": "user", "content": [{"type": "text", "text": prompt},
                                         {"type": "image_url", "image_url": {"url": uri}}]}]
    mt = 16000 if think else 4000
    body = {"model": model, "messages": msgs, "max_completion_tokens" if prov == "openai" else "max_tokens": mt}
    if prov == "openai":
        body["reasoning_effort"] = "medium" if think else "none"
    else:
        body["reasoning"] = {"enabled": True} if think else {"enabled": False}
        body["temperature"] = 0
    t = time.time()

    def go():
        r = requests.post(url, headers={"Authorization": "Bearer " + os.environ[key]}, json=body, timeout=300)
        if r.status_code == 429 or r.status_code >= 500:
            raise RuntimeError(f"{r.status_code} {r.text[:200]}")
        return r.json()

    d = _retry(go)
    if "error" in d:
        return {"error": str(d["error"])[:300]}
    u = d.get("usage") or {}
    return {"text": (d["choices"][0]["message"].get("content") or "").strip(), "ms": (time.time() - t) * 1000,
            "in_tok": u.get("prompt_tokens"), "out_tok": u.get("completion_tokens"),
            "reasoning_tok": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "cost_usd": u.get("cost")}


def field_prompt(g, source):
    schema = DOC_TYPES[g["doc_type"]][1]
    keys = "\n".join(f'  "{k}": {v}' for k, v in schema.items())
    return (f"Extract fields from this Indian {DOC_DESC[g['doc_type']]} ({source}).\n"
            f"Return ONLY a JSON object with exactly these keys:\n{keys}\n"
            "Copy every value exactly as printed: keep the original script (do not translate or transliterate "
            "names or places), keep numbers as printed. Use null if a field is absent.")


OCR_PROMPT = ("Transcribe all text on this document page exactly as printed, in reading order, line by line. "
              "Keep the original scripts and digits. Output only the text, no commentary, no markdown tables.")


# ---------- scoring ----------
ZW = dict.fromkeys(map(ord, "​‌‍﻿"), None)


def ascii_digits(s):
    return "".join(str(unicodedata.digit(c)) if c.isdigit() and not c.isascii() else c for c in s)


def norm_field(v):
    if v is None:
        return ""
    s = ascii_digits(unicodedata.normalize("NFC", str(v)).translate(ZW)).lower().strip()
    s = re.sub(r"^(rs\.?|inr|₹)\s*", "", s)
    return re.sub(r"[\s,.\-/:₹()'\"]", "", s)


def as_number(v):
    s = ascii_digits("" if v is None else str(v)).replace(",", "").replace("₹", "").strip()
    s = re.sub(r"^(rs\.?|inr)\s*", "", s, flags=re.I)
    return float(s) if re.fullmatch(r"\d+(\.\d+)?", s) else None


def field_match(gold, pred):
    gn, pn = as_number(gold), as_number(pred)
    if gn == 0 and (pred is None or str(pred).strip() == ""):
        return True  # an absent tax line reported as null is the same fact as 0.00
    if gn is not None and pn is not None:
        return abs(gn - pn) < 0.005
    return norm_field(gold) == norm_field(pred) and norm_field(gold) != ""


def strip_markup(md):
    s = re.sub(r"<br\s*/?>|</(td|th|tr|p|div|li)>", "\n", md)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", s)
    s = re.sub(r"[|#*`]+|^-{3,}$|:?-{3,}:?", " ", s, flags=re.M)
    return s


def text_scores(gold, hyp):
    """(order-free CER, gold-word recall). Reading order on forms and tables is ambiguous (label beside or
    above value, row- vs column-major), so plain CER punished perfect transcriptions by up to 0.4 in testing.
    Order-free CER: exact word matches cost 0; each remaining gold word is aligned to its closest remaining
    output word (edit distance); unmatched gold words cost their length (deletions), leftover output words
    cost theirs (insertions); total / gold characters, capped at 1."""
    from collections import Counter
    nc = lambda t: norm_text(re.sub(r"(?<=\d),(?=\d)", "", ascii_digits(t))).split()
    gw, hw = nc(gold), nc(strip_markup(hyp))
    common = Counter(gw) & Counter(hw)
    rec = sum(common.values()) / max(1, len(gw))
    g_left, h_left = list((Counter(gw) - common).elements()), list((Counter(hw) - common).elements())
    cost = 0
    for w in sorted(g_left, key=len, reverse=True):
        if not h_left:
            cost += len(w)
            continue
        j = min(range(len(h_left)), key=lambda k: edit_distance(w, h_left[k]))
        cost += min(len(w), edit_distance(w, h_left[j]))
        if edit_distance(w, h_left[j]) < len(w):
            h_left.pop(j)
    cost += sum(map(len, h_left))
    return min(1.0, cost / max(1, sum(map(len, gw)))), rec


# ---------- run ----------
def main():
    golds = [json.loads(l) for l in (D / "gold.jsonl").read_text().splitlines()]
    if len(sys.argv) > 1:  # smoke test on the first N pages
        golds = golds[:int(sys.argv[1])]
    done = {(r["id"], r["cond"], r["system"]): r for r in raw_load(UC) if "error" not in r}
    jobs = [(g, c) for g in golds for c in CONDS if (D / "pages" / CONDS[c].format(id=g["id"])).exists()]

    def do_vision(g, c):
        if (g["id"], c, VISION) in done or "sarvam" in STOP:
            return
        out = sarvam_vision(D / "pages" / CONDS[c].format(id=g["id"]), g["lang"])
        if "error" in out and ("402" in str(out["error"]) or "nsufficient credits" in str(out["error"])):
            STOP["sarvam"] = out["error"]
        rec = {"id": g["id"], "cond": c, "system": VISION, **out}
        save(rec)
        if "error" not in out:
            done[(g["id"], c, VISION)] = rec
        log(UC, VISION, g["id"], c, "err" if "error" in out else f"{out['ms']:.0f}ms")

    def do_gemini(g, c, system):
        if (g["id"], c, system) in done:
            return
        img = D / "pages" / CONDS[c].format(id=g["id"])
        prompt = OCR_PROMPT if system == G_OCR else field_prompt(g, "page image")
        think = system in FRONTIER_IMG
        try:
            if system.startswith(("openai:", "or:")):
                out = openai_image(system, img, prompt, think)
            else:
                out = gemini_image(img, prompt, GEMINI_CHAT if system in (G_IMG, G_OCR) else system, think)
        except Exception as e:
            out = {"error": str(e)[:300]}
        if system != G_OCR and "error" not in out:
            out["fields"] = extract_json(out["text"])
        save({"id": g["id"], "cond": c, "system": system, **out})
        done[(g["id"], c, system)] = out
        log(UC, system, g["id"], c, "err" if "error" in out else f"{out['ms']:.0f}ms")

    def do_docai(g, c):
        if (g["id"], c, DOCAI) in done or "sarvam" in STOP:
            return
        try:
            out = sarvam_docai_extract(D / "pages" / CONDS[c].format(id=g["id"]), g)
        except Exception as e:
            out = {"error": str(e)[:300]}
        if "error" in out and "_credits" in str(out["error"]) and out["error"].get("_credits"):
            STOP["sarvam"] = out["error"]
        save({"id": g["id"], "cond": c, "system": DOCAI, **out})
        if "error" not in out:
            done[(g["id"], c, DOCAI)] = out
        log(UC, DOCAI, g["id"], c, "err " + str(out["error"])[:150] if "error" in out else f"{out['ms']:.0f}ms")

    def do_extract(g, c, system):
        v = done.get((g["id"], c, VISION))
        if not v or (g["id"], c, system) in done or (system == S_EXT and "sarvam" in STOP):
            return
        model = "sarvam-105b" if system == S_EXT else GEMINI_CHAT
        msg = field_prompt(g, "OCR markdown below") + "\n\n---\n" + v["text"][:20000]
        try:
            out = chat(model, [{"role": "user", "content": msg}], max_tokens=1500)
        except Exception as e:
            out = {"error": str(e)[:300]}
        if "error" not in out:
            out["fields"] = extract_json(out["text"])
        save({"id": g["id"], "cond": c, "system": system, **out})
        done[(g["id"], c, system)] = out
        log(UC, system, g["id"], c, "err" if "error" in out else f"{out['ms']:.0f}ms")

    gold_by_id = {g["id"]: g for g in golds}
    frontier = [(gold_by_id[i], c) for i, c in FRONTIER_SET if i in gold_by_id]
    with ThreadPoolExecutor(3) as sp, ThreadPoolExecutor(4) as gp, ThreadPoolExecutor(4) as op:
        fs = [sp.submit(do_vision, g, c) for g, c in jobs]
        fs += [gp.submit(do_gemini, g, c, s) for g, c in jobs for s in (G_IMG, G_OCR)]
        fs += [op.submit(do_gemini, g, c, s) for g, c in jobs for s in CHEAP_IMG]
        fs += [op.submit(do_gemini, g, c, s) for g, c in frontier for s in FRONTIER_IMG]
        fs += [sp.submit(do_docai, g, c) for g, c in frontier + [(g, "clean") for g, _ in frontier]]
        [f.result() for f in fs]
    with ThreadPoolExecutor(3) as sp, ThreadPoolExecutor(4) as gp:
        fs = [sp.submit(do_extract, g, c, S_EXT) for g, c in jobs]
        fs += [gp.submit(do_extract, g, c, G_EXT) for g, c in jobs]
        [f.result() for f in fs]
    if STOP:
        log(UC, "STOPPED", STOP)
    summarize(golds)


def summarize(golds):
    from report import build
    write_result(UC, build(golds, raw_load(UC)))
    log(UC, "wrote results")


if __name__ == "__main__":
    main()
