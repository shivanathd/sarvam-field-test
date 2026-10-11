"""UC06 - Offline crop advisory where connectivity is poor.

A farmer asks a question (6 languages, native script or romanised); the model answers from a 770-word advisory sheet
placed in the prompt. Offline candidates are the open-weight models on this Mac, on GPU and on a CPU-only
llama-server (emulating a GPU-less office/kiosk box). Online references: sarvam-105b and gemini-3.8-flash.

Usage:
  .venv/bin/python suites/uc06_offline_agri/run.py [system ...]   # resumable; default = all systems whose server is up
  .venv/bin/python suites/uc06_offline_agri/run.py --summarize
CPU systems need the CPU-only server on :8111 (see README); run them one model at a time.
"""
import json, re, statistics, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "suites" / "uc10_selfhost_business"))
from common.bench import *  # noqa
from localcall import is_local, local_chat, healthy

UC = "uc06_offline_agri"
SHEET = (DATA / UC / "advisory_sheet.md").read_text()
QS = json.loads((DATA / UC / "questions.json").read_text())["questions"]
# fixed 30-question subset: all 10 out-of-scope + every 3rd fact (native and romanised) = 20 in-scope
_FACTS = list(dict.fromkeys(q["id"].rsplit("-", 2)[0] for q in QS if not q["oos"]))
SUBSET = {q["id"] for q in QS if q["oos"] or _FACTS.index(q["id"].rsplit("-", 2)[0]) % 3 == 0}
GPU = ["sarvam-30b-local-nothink", "sarvam-30b-local-think", "qwen3-30b-local-nothink", "qwen3-30b-local-think"]
CPU = ["sarvam-30b-cpu-nothink", "qwen3-30b-cpu-nothink"]
ONLINE = ["sarvam-105b", "gemini-3.8-flash", "openai:gpt-5.4-mini", "or:anthropic/claude-haiku-5.5"]
FRONTIER = ["gemini-pro-latest-think", "openai:gpt-5.5-think", "or:anthropic/claude-sonnet-5.5-think"]  # SUBSET only
SYSTEMS = GPU + CPU + ONLINE + FRONTIER
LANG = {"hi": "Hindi", "mr": "Marathi", "kn": "Kannada", "te": "Telugu", "ta": "Tamil", "pa": "Punjabi"}
SCRIPT = {"hi": "Devanagari", "mr": "Devanagari", "kn": "Kannada", "te": "Telugu", "ta": "Tamil", "pa": "Gurmukhi"}

SYSTEM_PROMPT = (
    "You are a crop advisory assistant for Indian farmers. Answer ONLY from the advisory sheet below.\n"
    "- Reply in the same language and script as the farmer's question. If the farmer writes their language in Latin "
    "letters (e.g. 'kitna urea dalna hai'), reply in that language in Latin letters, not in English.\n"
    "- Write all numbers in digits. Keep the answer short: 1 to 3 sentences.\n"
    "- If the sheet does not contain the answer, reply with the code NOT_IN_SHEET followed by one short sentence in the "
    "farmer's language telling them to call the KVK helpline. Never guess.\n\n" + SHEET)


def run_system(system):
    done = {r["id"] for r in raw_load(UC) if r.get("system") == system and not r.get("error")}
    todo = [q for q in QS if q["id"] not in done and (system not in FRONTIER or q["id"] in SUBSET)]
    if not todo:
        return
    if is_local(system) and not healthy(system):
        log(UC, system, "server not up; skipping")
        return
    think = system.endswith("-think")
    # CPU: one request at a time = latency a single farmer sees on a GPU-less box
    workers = 1 if "-cpu" in system else 3 if system.startswith("sarvam-105b") else 4
    log(UC, system, "running", len(todo))

    def one(q):
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": q["q"]}]
        try:
            r = local_chat(system, msgs, max_tokens=6000 if think else 800) if is_local(system) \
                else chat(system.removesuffix("-think"), msgs, max_tokens=4000 if think else 800, think=think)
        except Exception as e:
            r = {"text": "", "error": str(e)[:300]}
        raw_append(UC, {"id": q["id"], "system": system, **r})

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, todo))


# ---------- scoring ----------
def numbers(s):
    import unicodedata
    s = "".join(str(unicodedata.digit(c)) if c.isdigit() and not c.isascii() else c for c in s)
    return [int(x) for x in re.findall(r"\d+", s.replace(",", ""))]


EN_STOP = {"the", "is", "are", "and", "of", "to", "for", "you", "your", "should", "apply", "with", "be", "it", "this",
           "after", "at", "on", "use", "please", "an", "a", "when", "if", "spray", "sow"}
HI_MARK = r"(है|हैं|आपके|आपका|आपको|करें|नहीं|डालें|चाहिए|के लिए|में)"
MR_MARK = r"(आहे|आहेत|तुमच्या|तुम्ही|करा|नाही|साठी|मध्ये|लागते|लागतात|द्यावे|करावी)"


def language_ok(q, text):
    t = text.replace("NOT_IN_SHEET", "")
    if q["script"] == "roman":
        words = re.findall(r"[a-z]+", t.lower())
        return dominant_script(t) == "Latin" and bool(words) and sum(w in EN_STOP for w in words) / len(words) < 0.2
    if dominant_script(t) != SCRIPT[q["lang"]]:
        return False
    if q["lang"] in ("hi", "mr"):
        hi, mr = len(re.findall(HI_MARK, t)), len(re.findall(MR_MARK, t))
        return hi <= mr if q["lang"] == "mr" else mr <= hi  # only a clear lean to the other language fails
    return True


HELPLINE = r"(?i)kvk|helpline|हेल्पलाइन|हेल्पलाईन|ಹೆಲ್ಪ್|ಕೆವಿಕೆ|హెల్ప్|కెవికె|ஹெல்ப்|கேவிகே|ਹੈਲਪਲਾਈਨ|ਕੇਵੀਕੇ"


def score(q, text):
    refused = "NOT_IN_SHEET" in text
    redirected = refused or bool(re.search(HELPLINE, text))  # lenient: a refusal that forgot the code
    lang = language_ok(q, text)
    if q["oos"]:
        return {"oos": True, "refused": refused, "refused_lenient": redirected, "language": lang, "pass": refused and lang}
    correct = not refused and all(g in numbers(text) for g in q["gold"])
    return {"oos": False, "correct": correct, "false_refusal": refused, "language": lang, "pass": correct and lang}


def summarize():
    recs = {}
    for r in raw_load(UC):
        if not r.get("error"):
            recs[(r["id"], r["system"])] = r
    systems = [s for s in SYSTEMS if any(k[1] == s for k in recs)]
    byq = {q["id"]: q for q in QS}
    sc = {s: {i: score(byq[i], recs[(i, s)]["text"]) for i in byq if (i, s) in recs} for s in systems}

    def ci(s, key, pred=lambda q: True):
        return bootstrap_ci([v[key] for i, v in sc[s].items() if pred(byq[i]) and key in v])

    ins, oos = (lambda q: not q["oos"]), (lambda q: q["oos"])
    sub = lambda q: q["id"] in SUBSET
    metrics = [
        {"name": "overall_pass_subset30", "higher_is_better": True, "unit": "overall pass on the fixed 30-question subset (10 OOS + 20 in-scope) - compare frontier here",
         "values": {s: ci(s, "pass", sub) for s in systems}},
        {"name": "oos_refusal_subset30", "higher_is_better": True, "unit": "same as oos_refusal (all 10 OOS are in the subset)",
         "values": {s: ci(s, "refused", lambda q: q["oos"]) for s in systems}},
        {"name": "grounded_correct_subset30", "higher_is_better": True, "unit": "grounded correct on the subset's 20 in-scope questions",
         "values": {s: ci(s, "correct", lambda q: sub(q) and not q["oos"]) for s in systems}},
        {"name": "grounded_correct", "higher_is_better": True, "unit": "share of 60 in-scope answers with every gold number and no refusal",
         "values": {s: ci(s, "correct", ins) for s in systems}},
        {"name": "reply_language_correct", "higher_is_better": True, "unit": "share of all 70 answers in the farmer's language+script",
         "values": {s: ci(s, "language") for s in systems}},
        {"name": "oos_refusal", "higher_is_better": True, "unit": "share of 10 out-of-scope questions answered NOT_IN_SHEET",
         "values": {s: ci(s, "refused", oos) for s in systems}},
        {"name": "oos_refusal_lenient", "higher_is_better": True, "unit": "share of out-of-scope questions refused with the code OR redirected to the KVK helpline",
         "values": {s: ci(s, "refused_lenient", oos) for s in systems}},
        {"name": "false_refusal", "higher_is_better": False, "unit": "share of in-scope questions wrongly refused",
         "values": {s: ci(s, "false_refusal", ins) for s in systems}},
        {"name": "overall_pass", "higher_is_better": True, "unit": "share of 70 (in-scope: correct+language; OOS: refused+language)",
         "values": {s: ci(s, "pass") for s in systems}},
        {"name": "grounded_correct_native_script", "higher_is_better": True, "unit": "share",
         "values": {s: ci(s, "correct", lambda q: not q["oos"] and q["script"] == "native") for s in systems}},
        {"name": "grounded_correct_romanised", "higher_is_better": True, "unit": "share",
         "values": {s: ci(s, "correct", lambda q: not q["oos"] and q["script"] == "roman") for s in systems}},
    ]
    per_lang = {m: {LANG[l]: {s: round(statistics.fmean([v[k] for i, v in sc[s].items() if byq[i]["lang"] == l and k in v] or [0]), 3)
                              for s in systems} for l in LANG}
                for m, k in (("grounded_correct", "correct"), ("reply_language_correct", "language"), ("overall_pass", "pass"))}
    speed = {}
    for s in systems:
        rs = [recs[k] for k in recs if k[1] == s]
        speed[s] = {"p50_ms": pctl([r["ms"] for r in rs], 0.5), "p95_ms": pctl([r["ms"] for r in rs], 0.95),
                    "mean_ms": statistics.fmean(r["ms"] for r in rs),
                    "mean_out_tok": statistics.fmean(r.get("out_tok") or 0 for r in rs)}
        tm = [r["timings"] for r in rs if r.get("timings")]
        if tm:
            speed[s]["prompt_tok_per_s_median"] = statistics.median(t["prompt_per_second"] for t in tm)
            speed[s]["gen_tok_per_s_median"] = statistics.median(t["predicted_per_second"] for t in tm)
            speed[s]["concurrency"] = 1 if "-cpu" in s else 4
    usage = {s: {"in_tok": sum(recs[k].get("in_tok") or 0 for k in recs if k[1] == s),
                 "out_tok": sum(recs[k].get("out_tok") or 0 for k in recs if k[1] == s),
                 "calls": sum(k[1] == s for k in recs)} for s in systems}
    ex_ids = ["cotton_spacing-te-roman", "scheme_cap-hi-native", "aphid_threshold-pa-native", "oos7-mr-native", "soy_rhizobium-kn-roman"]
    examples = [{"id": i, "question": byq[i]["q"], "gold_numbers": byq[i]["gold"], "sheet_line": byq[i]["sheet"],
                 "outputs": {s: {"text": recs[(i, s)]["text"][:500], "score": sc[s][i]} for s in systems if (i, s) in recs}}
                for i in ex_ids]
    prev = json.loads((RESULTS / f"{UC}.json").read_text()) if (RESULTS / f"{UC}.json").exists() else {}
    write_result(UC, {
        "uc": UC, "title": "Offline crop advisory",
        "business_question": "Can an open-weight model running on a local box (no internet, possibly no GPU) answer "
                             "farmers' questions correctly from an advisory sheet, in their own language and script?",
        "dataset": {"name": "uc06 advisory sheet + farmer questions", "source": "authored for this benchmark (make_data.py, advisory_sheet.md)",
                    "license": "CC-BY-4.0 (this repo)", "n": len(QS), "languages": list(LANG.values()), "synthetic": True,
                    "how_made": "770-word English advisory sheet (paddy, cotton, soybean, wheat, a clearly FICTIONAL seed "
                                "scheme, spraying rules) modelled on typical package-of-practice figures; 30 facts x "
                                "(native script + romanised) = 60 in-scope questions, 5 per language per script, plus 10 "
                                "out-of-scope questions; gold = the number(s) from the sheet."},
        "systems": systems, "metrics": metrics, "per_language": per_lang, "speed": speed, "usage": usage,
        "findings": prev.get("findings", []), "caveats": prev.get("caveats", []), "verdict": prev.get("verdict", ""),
        "examples": examples})
    return metrics, per_lang, speed


if __name__ == "__main__":
    if "--summarize" not in sys.argv:
        for s in [a for a in sys.argv[1:] if not a.startswith("--")] or SYSTEMS:
            run_system(s)
    m, pl, sp = summarize()
    for x in m:
        print(x["name"], {s: (round(v["mean"], 3) if v["mean"] is not None else None) for s, v in x["values"].items()})
    for s, v in sp.items():
        print(s, {k: round(x, 1) for k, x in v.items()})
