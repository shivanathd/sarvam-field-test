"""UC10 - Can an Indian business run Sarvam-30B on its own hardware instead of a cloud API?

Accuracy: 150 synthetic support/back-office items (data/uc10_selfhost_business/items.json, built by make_data.py),
5 tasks x 6 languages, scored against known answers (no AI judge). Speed: see speed.py.

Usage:
  .venv/bin/python suites/uc10_selfhost_business/run.py [system ...]   # default: all systems; resumable
  .venv/bin/python suites/uc10_selfhost_business/run.py --summarize    # recompute results/uc10_selfhost_business.json only
"""
import json, re, statistics, sys, unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from common.bench import *  # noqa
sys.path.insert(0, str(Path(__file__).parent))
from localcall import is_local, local_chat, healthy

UC = "uc10_selfhost_business"
ITEMS = json.loads((DATA / UC / "items.json").read_text())["items"]
SYSTEMS = ["sarvam-105b", "sarvam-105b-think", "gemini-3.8-flash", "sarvam-30b-local-nothink", "sarvam-30b-local-think",
           "qwen3-30b-local-nothink", "qwen3-30b-local-think", "openai:gpt-5.4-mini", "or:anthropic/claude-haiku-5.5"]
# frontier ceiling, thinking on, only on SUBSET (bench.ALWAYS_THINK models cannot turn thinking off anyway)
FRONTIER = ["gemini-pro-latest-think", "openai:gpt-5.5-think", "or:anthropic/claude-sonnet-5.5-think"]
SYSTEMS += FRONTIER
_LI = ["hi", "mr", "ta", "te", "bn", "hinglish"]
# fixed 30-item subset: per task, one item per language, rotating through the 5 scenarios
SUBSET = {it["id"] for it in ITEMS if (int(it["id"].split("-")[1]) - _LI.index(it["lang"])) % 5 == 0}
LANG_NAME = {"hi": "hindi", "mr": "marathi", "ta": "tamil", "te": "telugu", "bn": "bengali", "hinglish": "hinglish"}
INTENTS = ["refund_request", "delivery_delay", "damaged_item", "payment_failed", "account_access", "cancel_order",
           "product_question", "billing_error"]

PROMPTS = {
    "triage": (
        "You triage customer support tickets for ShopKart, an Indian online store. Reply with only a JSON object: "
        '{"intent": <one of ' + json.dumps(INTENTS) + '>, "urgency": <1, 2 or 3>, "language": <one of '
        + json.dumps(sorted(set(LANG_NAME.values()) | {"english"})) + ">}.\n"
        "Urgency rules: 3 = the customer has already lost money (debited or charged without getting what they paid "
        "for), there is a safety risk, or they need it resolved within 24 hours; 2 = a problem with an order with no "
        "money lost and no 24-hour deadline; 1 = an information question only.\n"
        "language = the language the customer wrote in; 'hinglish' means Hindi written in Latin letters mixed with English."),
    "crm": (
        "You write internal CRM notes for ShopKart's support team. Summarise the customer's complaint in English in "
        "2-3 sentences. Include the order or booking ID exactly as written, the amount in rupees as a plain number "
        "(e.g. 2499), and the date the customer mentions in YYYY-MM-DD format (assume the year is 2026). Write only the note."),
    "reply": (
        "You are a customer support agent for ShopKart, an Indian online store. Company policy:\n"
        "1. Products can be returned for a refund within {n} days of delivery.\n"
        "2. Never offer or promise compensation, cashback, vouchers or any money amount.\n"
        "3. Never promise a specific date or any time period other than the {n}-day return window.\n"
        "Reply to the customer in the same language and script they wrote in (if they wrote Hindi in Latin letters, "
        "reply the same way). Mention the {n}-day return window, writing the number in digits. 2-4 sentences. "
        "Write only the reply."),
    "escalate": (
        "You screen customer messages for ShopKart. Reply with only a JSON object: "
        '{"sentiment": "positive" | "neutral" | "negative", "escalate": true | false}.\n'
        "Escalate (true) only if the customer threatens legal action or consumer court, threatens to post on social "
        "media or go to the press, reports a safety hazard or injury, or says they have complained three or more times. "
        "Otherwise false."),
    "extract": (
        "Extract fields from this Indian business invoice / email. Reply with only a JSON object: "
        '{"invoice_no": string, "gstin": string, "total_inr": number (the total amount payable, including GST), '
        '"due_date": "YYYY-MM-DD"}.'),
}


def run_system(system):
    done = {r["id"] for r in raw_load(UC) if r.get("system") == system and "text" in r and not r.get("error")}
    todo = [it for it in ITEMS if it["id"] not in done and (system not in FRONTIER or it["id"] in SUBSET)]
    if not todo:
        return
    base, think = system.removesuffix("-think").removesuffix("-nothink"), system.endswith("-think")
    if is_local(system) and not healthy(system):
        log(UC, system, "local server not up; skipping")
        return
    workers = 3 if base.startswith("sarvam-105b") else 4
    log(UC, system, "running", len(todo), "items")

    def one(it):
        sys_p = PROMPTS[it["task"]].replace("{n}", str(it["gold"].get("refund_days", "")))
        msgs = [{"role": "system", "content": sys_p}, {"role": "user", "content": it["text"]}]
        try:
            if is_local(system):
                r = local_chat(system, msgs, max_tokens=6000 if think else 1500)
            else:
                r = chat(base, msgs, max_tokens=6000 if think else 1500, think=think)
        except Exception as e:  # keep going; a missing answer scores 0 and the error is recorded
            r = {"text": "", "error": str(e)[:300]}
        raw_append(UC, {"id": it["id"], "system": system, **r})

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, todo))


# ---------- scoring ----------
def ascii_digits(s):
    return "".join(str(unicodedata.digit(c)) if c.isdigit() and not c.isascii() else c for c in s)


def numbers(s):
    return [int(x) for x in re.findall(r"\d+", ascii_digits(s).replace(",", ""))]


HI_MARK = r"(है|हैं|आपके|आपका|आपको|करें|नहीं|वापस|किया|के लिए)"
MR_MARK = r"(आहे|आहेत|तुमच्या|तुम्ही|आम्ही|करू|नाही|परत|केले|साठी)"
HINGLISH_MARK = r"\b(hai|hain|aap|aapka|aapki|aapke|hum|ka|ki|ke|ko|se|mein|kar|karein|nahi|ho|din|sakte|sakti)\b"
WANT_SCRIPT = {"hi": "Devanagari", "mr": "Devanagari", "ta": "Tamil", "te": "Telugu", "bn": "Bengali", "hinglish": "Latin"}


def language_ok(text, lang):
    if dominant_script(text) != WANT_SCRIPT[lang]:
        return False
    if lang == "hinglish":
        return len(re.findall(HINGLISH_MARK, text.lower())) >= 3
    if lang in ("hi", "mr"):
        hi, mr = len(re.findall(HI_MARK, text)), len(re.findall(MR_MARK, text))
        return hi <= mr if lang == "mr" else mr <= hi  # only a clear lean to the other language fails
    return True


def score(it, text):
    g, t = it["gold"], it["task"]
    if t == "triage":
        j = extract_json(text) or {}
        s = {"intent": j.get("intent") == g["intent"], "urgency": str(j.get("urgency")) == str(g["urgency"]),
             "language": str(j.get("language", "")).lower() == LANG_NAME[g["language"]]}
        s["intent_urgency"] = s["intent"] and s["urgency"]  # triage without the language-ID field
    elif t == "crm":
        s = {"order_id": g["order_id"].lower() in text.lower(), "amount": g["amount"] in numbers(text),
             "date": g["date"] in text, "issue": bool(re.search(g["issue_re"], text, re.I)),
             "english": dominant_script(text) == "Latin"}
    elif t == "reply":
        rest = numbers(text.replace(g["order_id"], ""))
        s = {"language": language_ok(text, it["lang"]), "window_stated": g["refund_days"] in rest,
             "no_forbidden": bool(text.strip()) and all(n == g["refund_days"] for n in rest)}
    elif t == "escalate":
        j = extract_json(text) or {}
        s = {"sentiment": j.get("sentiment") == g["sentiment"], "escalate": j.get("escalate") is g["escalate"]}
    else:
        j = extract_json(text) or {}
        norm = lambda x: re.sub(r"\s", "", str(x)).upper()
        try:
            tot = float(str(j.get("total_inr")).replace(",", "").replace("₹", ""))
        except ValueError:
            tot = None
        s = {"invoice_no": norm(j.get("invoice_no")) == norm(g["invoice_no"]), "gstin": norm(j.get("gstin")) == g["gstin"],
             "total_inr": tot == g["total_inr"], "due_date": j.get("due_date") == g["due_date"]}
    s["all"] = all(s.values())
    return s


def summarize():
    recs = {}
    for r in raw_load(UC):
        if "text" in r and "system" in r and not r.get("error"):
            recs[(r["id"], r["system"])] = r  # last successful write wins; errors (e.g. 402 no credits) are retried
    by_id = {it["id"]: it for it in ITEMS}
    systems = [s for s in SYSTEMS if any(k[1] == s for k in recs)]
    scored = {s: {i: score(by_id[i], recs[(i, s)]["text"]) for i in by_id if (i, s) in recs} for s in systems}
    tasks = ["triage", "crm", "reply", "escalate", "extract"]
    metrics = [{"name": "overall_all_correct", "higher_is_better": True, "unit": "share of items fully correct (frontier systems: 30-item subset only)",
                "values": {s: bootstrap_ci([v["all"] for v in scored[s].values()]) for s in systems}},
               {"name": "overall_all_correct_subset30", "higher_is_better": True,
                "unit": "share fully correct on the fixed 30-item subset (6 per task, one per language) - compare frontier here",
                "values": {s: bootstrap_ci([v["all"] for i, v in scored[s].items() if i in SUBSET]) for s in systems}}]
    for t in tasks:
        keys = [k for k in score(next(it for it in ITEMS if it["task"] == t), "") if k != "all"]
        metrics.append({"name": f"{t}_all_correct", "higher_is_better": True, "unit": "share",
                        "values": {s: bootstrap_ci([v["all"] for i, v in scored[s].items() if by_id[i]["task"] == t]) for s in systems}})
        for k in keys:
            metrics.append({"name": f"{t}_{k}", "higher_is_better": True, "unit": "share",
                            "values": {s: bootstrap_ci([v[k] for i, v in scored[s].items() if by_id[i]["task"] == t]) for s in systems}})
    langs = list(LANG_NAME)
    def mean(xs):
        xs = list(xs)
        return round(statistics.fmean(xs), 3) if xs else None

    per_lang = {"overall_all_correct": {l: {s: mean(v["all"] for i, v in scored[s].items() if by_id[i]["lang"] == l)
                                            for s in systems} for l in langs}}
    for t in tasks:
        per_lang[f"{t}_all_correct"] = {l: {s: mean(v["all"] for i, v in scored[s].items()
                                                    if by_id[i]["lang"] == l and by_id[i]["task"] == t)
                                            for s in systems} for l in langs}
    speed = {s: {"p50_ms": pctl([recs[k]["ms"] for k in recs if k[1] == s and "ms" in recs[k]], 0.5),
                 "p95_ms": pctl([recs[k]["ms"] for k in recs if k[1] == s and "ms" in recs[k]], 0.95)} for s in systems}
    usage = {s: {"in_tok": sum(recs[k].get("in_tok") or 0 for k in recs if k[1] == s),
                 "out_tok": sum(recs[k].get("out_tok") or 0 for k in recs if k[1] == s),
                 "reasoning_tok": sum(recs[k].get("reasoning_tok") or 0 for k in recs if k[1] == s),
                 "calls": sum(k[1] == s for k in recs),
                 "api_errors_retried": sum(1 for r in raw_load(UC) if r.get("system") == s and r.get("error"))}
             for s in systems}
    for s in systems:
        if s.startswith("sarvam-105b"):
            usage[s]["inr_list_price"] = round(usage[s]["in_tok"] * 15e-6 + usage[s]["out_tok"] * 60e-6, 2)
    ex_ids = ["triage-4-ta", "crm-4-mr", "reply-0-hinglish", "escalate-2-te", "extract-4-bn"]
    examples = [{"id": i, "task": by_id[i]["task"], "input": by_id[i]["text"], "gold": by_id[i]["gold"],
                 "outputs": {s: {"text": recs[(i, s)]["text"][:600], "score": scored[s][i]} for s in systems if (i, s) in recs}}
                for i in ex_ids]
    hw = {}
    if (DATA / UC / "speed.json").exists():  # compact view: one entry per repeat, raw timings stay in speed.json
        for tgt, runs in json.loads((DATA / UC / "speed.json").read_text()).items():
            hw[tgt] = [{k: v for k, v in r.items() if k not in ("raw", "server_cmd")} | {"server_cmd": r["server_cmd"].split("llama-server ")[-1]}
                       for r in (runs if isinstance(runs, list) else [runs])]
    prev = json.loads((RESULTS / f"{UC}.json").read_text()) if (RESULTS / f"{UC}.json").exists() else {}
    write_result(UC, {
        "uc": UC, "title": "Self-hosting Sarvam-30B for business text",
        "business_question": "Can an Indian business run Sarvam-30B on its own hardware instead of a cloud API, "
                             "and what does it give up in accuracy and speed?",
        "dataset": {"name": "uc10 synthetic support & back-office set", "source": "authored for this benchmark (make_data.py)",
                    "license": "CC-BY-4.0 (this repo)", "n": len(ITEMS), "languages": ["Hindi", "Marathi", "Tamil", "Telugu", "Bengali", "Hinglish"],
                    "synthetic": True,
                    "how_made": "5 tasks x 5 scenarios, each scenario hand-written in 6 languages (not machine-translated); "
                                "ids, amounts, dates, invoice numbers and checksum-valid SAMPLE GSTINs are randomised per item."},
        "systems": systems, "metrics": metrics, "per_language": per_lang, "speed": speed, "usage": usage,
        "hardware": hw,
        "findings": prev.get("findings", []), "caveats": prev.get("caveats", []), "verdict": prev.get("verdict", ""),
        "examples": examples})
    return metrics, per_lang, usage, speed


if __name__ == "__main__":
    if "--summarize" not in sys.argv:
        for s in [a for a in sys.argv[1:] if not a.startswith("--")] or SYSTEMS:
            run_system(s)
    m, pl, u, sp = summarize()
    for x in m:
        print(x["name"], {s: (round(v["mean"], 3) if v["mean"] is not None else None) for s, v in x["values"].items()})
    print(json.dumps(u, indent=0)); print(sp)
