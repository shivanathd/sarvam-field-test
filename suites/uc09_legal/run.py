"""UC09 legal: translate and summarise court texts into Indian languages without losing facts.

Task A (translate): 40 English passages -> Hindi & Tamil (all 40) and Marathi & Bengali (first 20).
  Systems: sarvam-translate:v1, mayura:v1, sarvam-105b (think off), gemini-3.8-flash.
  Metric: entity preservation (numbers, amounts, dates, names; see score.py), dropped/altered facts,
  unsupported numbers, output-language correctness.
Task B (summarise for a litigant): 40 passages -> plain Hindi and Tamil.
  Systems: sarvam-105b think off / on, gemini-3.8-flash (+ local sarvam-30b / qwen3-30b if their servers are up).
  Metric: recall of the passage's 5-6 key facts, unsupported (hallucinated/altered) numbers, language correctness.
Resumable: results/raw/uc09_legal.jsonl keyed by (task, id, lang, system).
Run:  .venv/bin/python suites/uc09_legal/run.py
"""
import json, sys, threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
from common.bench import *  # noqa
from score import entity_found, script_share, unsupported_numbers

UC = "uc09_legal"
LANGS = {"hi": ("Hindi", "hi-IN", "Devanagari"), "ta": ("Tamil", "ta-IN", "Tamil"),
         "mr": ("Marathi", "mr-IN", "Devanagari"), "bn": ("Bengali", "bn-IN", "Bengali")}
A_LANGS = {"hi": 40, "ta": 40, "mr": 20, "bn": 20}  # passages per language (translate API chars are the budget)
B_LANGS = ["hi", "ta"]
CHEAP = ["openai:gpt-5.4-mini", "or:anthropic/claude-haiku-5.5"]  # price-matched tier, full sets, think off
FRONTIER = ["gemini-pro-latest", "openai:gpt-5.5", "or:anthropic/claude-sonnet-5.5"]  # think on, FRONTIER_N subset
FRONTIER_N = 15  # first 15 passages x hi/ta = fixed 30 items per task
A_SYS = ["sarvam-translate:v1", "mayura:v1", "sarvam-105b", GEMINI_CHAT] + CHEAP + FRONTIER
B_SYS = ["sarvam-105b", "sarvam-105b-think", GEMINI_CHAT] + CHEAP + FRONTIER
THINK_RETRY = "sarvam-105b-think-16k"  # reruns of think-on replies that came back empty at max_tokens 6000
LOCAL = ["sarvam-30b-local", "qwen3-30b-local"]
LOCAL_N = 5  # passages per language for local models: 4-8 min per summary on the shared Mac
INR = {"translate_per_char": 20 / 10_000, "105b_in": 15 / 1e6, "105b_out": 60 / 1e6}
_lock = threading.Lock()
STOP = {}


def translate_prompt(lang, text):
    return [{"role": "user", "content":
             f"Translate the following English court text into {LANGS[lang][0]}. Keep every number, date, amount, "
             f"section and case number exactly; write personal names and place names in {LANGS[lang][0]} script. "
             f"Output only the translation.\n\n{text}"}]


def summary_prompt(lang, text):
    return [{"role": "user", "content":
             f"A litigant who does not read English received this court text. Explain it to them in simple, plain "
             f"{LANGS[lang][0]} in 5-7 short sentences: who the parties are, what was decided, and every amount, "
             f"date, deadline and case number they need to act on. Do not add anything that is not in the text. "
             f"Write only the {LANGS[lang][0]} explanation.\n\n{text}"}]


def call(task, p, lang, system):
    if system.startswith("sarvam") and not system.endswith("local") and "sarvam" in STOP:
        return None
    if system in ("sarvam-translate:v1", "mayura:v1"):
        t = time.time()
        d = sarvam_post("/translate", {"input": p["text"], "source_language_code": "en-IN",
                                       "target_language_code": LANGS[lang][1], "model": system})
        out = {"error": d} if "_error" in d else {"text": d.get("translated_text", ""), "chars": len(p["text"])}
        out["ms"] = (time.time() - t) * 1000
    else:
        msgs = (translate_prompt if task == "A" else summary_prompt)(lang, p["text"])
        think = system in ("sarvam-105b-think", THINK_RETRY) or system in FRONTIER
        model = "sarvam-105b" if system.startswith("sarvam-105b") else system
        mt = {"sarvam-105b-think": 6000, THINK_RETRY: 16000}.get(system, 16000 if system in FRONTIER
                                                                    else 1500 if system in LOCAL else 2500)
        try:
            out = chat(model, msgs, max_tokens=mt, think=think)
        except Exception as e:
            out = {"error": str(e)[:300]}
    err = str(out.get("error", ""))
    if "_credits" in err or "402" in err or "nsufficient" in err or "No credits" in err:
        STOP["sarvam"] = err[:200]
    return out


def main():
    passages = [json.loads(l) for l in (DATA / UC / "passages.jsonl").read_text().splitlines()]
    raws = raw_load(UC)
    done = {(r["task"], r["id"], r["lang"], r["system"]) for r in raws if "error" not in r}
    b_sys = B_SYS + [s for s in LOCAL if _up(s)]
    n_for = lambda s, n: min(n, FRONTIER_N) if s in FRONTIER else n
    jobs = [("A", p, l, s) for s in A_SYS for l, n in A_LANGS.items() if l in B_LANGS or s not in FRONTIER
            for p in passages[:n_for(s, n)]]
    jobs += [("B", p, l, s) for s in b_sys for l in B_LANGS
             for p in (passages[:LOCAL_N] if s in LOCAL else passages[:n_for(s, len(passages))])]
    P = {p["id"]: p for p in passages}
    jobs += [("B", P[r["id"]], r["lang"], THINK_RETRY) for r in raws
             if r["system"] == "sarvam-105b-think" and "error" not in r and not r["text"].strip()]
    jobs = [j for j in jobs if (j[0], j[1]["id"], j[2], j[3]) not in done]
    jobs = [j for j in jobs if (j[0], j[1]["id"], j[2], j[3]) not in done]
    log(UC, f"{len(jobs)} calls to make; systems B: {b_sys}")

    def run(job):
        task, p, lang, system = job
        out = call(task, p, lang, system)
        if out is None:
            return
        with _lock:
            raw_append(UC, {"task": task, "id": p["id"], "lang": lang, "system": system, **out})
        log(UC, task, system, p["id"], lang, "err " + str(out["error"])[:120] if "error" in out
            else f"{out['ms']:.0f}ms")

    pools = {"sarvam": ThreadPoolExecutor(3), "gemini": ThreadPoolExecutor(4), "local": ThreadPoolExecutor(1),
             "openai": ThreadPoolExecutor(4), "or": ThreadPoolExecutor(4)}
    kind = lambda s: ("local" if s in LOCAL else "gemini" if s.startswith("gemini") else
                      s.split(":")[0] if s.startswith(("openai:", "or:")) else "sarvam")
    fs = [pools[kind(j[3])].submit(run, j) for j in jobs]
    [f.result() for f in fs]
    if STOP:
        log(UC, "Sarvam calls stopped:", STOP)
    write_result(UC, build(passages, raw_load(UC)))
    log(UC, "wrote results")


def _up(system):
    try:
        return requests.get(f"http://127.0.0.1:{LOCAL_PORTS[system]}/health", timeout=3).json().get("status") == "ok"
    except Exception:
        return False


# ---------- scoring / report ----------
def score(rec, p):
    text = rec["text"]
    lang = rec["lang"]
    lo_hi = SCRIPTS[LANGS[lang][2]]
    share = script_share(text, lo_hi)
    lang_ok = bool(text.strip()) and dominant_script(text) == LANGS[lang][2] and share >= 0.5
    if rec["task"] == "A":
        ents = p["entities"]
    else:
        ents = [e for e in p["entities"] if e["key"] in p["key_facts"]]
    found = {e["key"]: entity_found(text, e) for e in ents}
    return {"recall": sum(found.values()) / len(found), "missed": [k for k, v in found.items() if not v],
            "by_type": [(e["type"], found[e["key"]]) for e in ents], "lang_ok": lang_ok,
            "unsupported": unsupported_numbers(text, p["text"], p["entities"])}


def build(passages, raws):
    P = {p["id"]: p for p in passages}
    rec = {}
    subset = {p["id"] for p in passages[:LOCAL_N]}  # local models only ran on these (slow on the shared Mac)
    for r in raws:
        if "error" not in r and (r["system"] not in LOCAL or r["id"] in subset):
            rec[(r["task"], r["id"], r["lang"], r["system"])] = r
    # virtual system: think-on with the empty-at-6000-token replies rerun at max_tokens 16000
    retry_name = "sarvam-105b-think (empties rerun at 16k)"
    for k, r in list(rec.items()):
        if k[3] == "sarvam-105b-think":
            rec[k[:3] + (retry_name,)] = rec.get(k[:3] + (THINK_RETRY,), r)
    rec = {k: r for k, r in rec.items() if k[3] != THINK_RETRY}
    sc = {k: score(r, P[k[1]]) for k, r in rec.items()}
    systems = {"A": [s for s in A_SYS if any(k[0] == "A" and k[3] == s for k in sc)],
               "B": [s for s in B_SYS[:2] + [retry_name] + B_SYS[2:] + LOCAL
                     if any(k[0] == "B" and k[3] == s for k in sc)]}
    label = {"A": "translation", "B": "litigant summary"}
    metrics, per_language = [], {}

    def vals(task, s, f, lang=None):
        return [f(v) for k, v in sc.items() if k[0] == task and k[3] == s and (lang is None or k[2] == lang)]

    defs = {"A": [("entity preservation rate", True, "fraction of source entities kept", lambda v: v["recall"]),
                  ("facts dropped or altered per passage", False, "count",
                   lambda v: len(v["missed"])),
                  ("distinct unsupported numbers per passage", False, "count", lambda v: len(v["unsupported"])),
                  ("output in target language", True, "fraction", lambda v: float(v["lang_ok"]))],
            "B": [("key-fact recall", True, "fraction of 5-6 key facts", lambda v: v["recall"]),
                  ("distinct hallucinated/altered numbers per summary", False, "count", lambda v: len(v["unsupported"])),
                  ("summaries with zero unsupported numbers", True, "fraction",
                   lambda v: float(not v["unsupported"])),
                  ("output in target language", True, "fraction", lambda v: float(v["lang_ok"]))]}
    for task in "AB":
        for name, hib, unit, f in defs[task]:
            metrics.append({"name": f"{name} ({label[task]})", "higher_is_better": hib, "unit": unit,
                            "values": {s: bootstrap_ci(vals(task, s, f)) for s in systems[task]}})
            per_language[f"{name} ({label[task]})"] = {
                l: {s: round(statistics.fmean(x), 4) for s in systems[task] if (x := vals(task, s, f, l))}
                for l in (A_LANGS if task == "A" else B_LANGS)}
    if any(s in LOCAL for s in systems["B"]):  # like-for-like comparison on the local models' subset
        for name, hib, unit, f in defs["B"][:2]:
            metrics.append({"name": f"{name} (litigant summary, {LOCAL_N}-passage x hi/ta subset all systems ran)",
                            "higher_is_better": hib, "unit": unit, "values": {
                                s: bootstrap_ci([f(v) for k, v in sc.items() if k[0] == "B" and k[3] == s
                                                 and k[1] in subset]) for s in systems["B"]}})
    fsub = {p["id"] for p in passages[:FRONTIER_N]}  # frontier models ran on these x hi/ta only
    for task in "AB":  # like-for-like on the frontier subset
        for name, hib, unit, f in defs[task][:2]:
            metrics.append({"name": f"{name} ({label[task]}, frontier subset: first {FRONTIER_N} passages x hi/ta)",
                            "higher_is_better": hib, "unit": unit, "values": {
                                s: bootstrap_ci([f(v) for k, v in sc.items() if k[0] == task and k[3] == s
                                                 and k[1] in fsub and k[2] in B_LANGS]) for s in systems[task]}})
    by_type = {}
    for task in "AB":
        for s in systems[task]:
            c = defaultdict(list)
            for k, v in sc.items():
                if k[0] == task and k[3] == s:
                    for t, ok in v["by_type"]:
                        c[t].append(ok)
            by_type[f"{label[task]} / {s}"] = {t: round(sum(x) / len(x), 4) for t, x in c.items()}

    speed, usage = {}, {}
    for task in "AB":
        for s in systems[task]:
            rs = [r for k, r in rec.items() if k[0] == task and k[3] == s]
            key = f"{s} [{label[task]}]"
            speed[key] = {"p50_ms": round(pctl([r["ms"] for r in rs], .5)),
                          "p95_ms": round(pctl([r["ms"] for r in rs], .95)), "n": len(rs)}
            u = Counter()
            for r in rs:
                u["calls"] += 1
                for f in ("in_tok", "out_tok", "reasoning_tok", "chars", "cost_usd"):
                    u[f] += r.get(f) or 0
            usage[key] = dict(u)
    spend = 0.0
    for key, u in usage.items():
        if key.startswith(("sarvam-translate", "mayura")):
            spend += u.get("chars", 0) * INR["translate_per_char"]
        elif key.startswith("sarvam-105b") and retry_name not in key:
            spend += u.get("in_tok", 0) * INR["105b_in"] + u.get("out_tok", 0) * INR["105b_out"]
    rr = [r for r in raws if r["system"] == THINK_RETRY and "error" not in r]
    usage[f"{THINK_RETRY} [16k reruns of the empty think-on replies]"] = {
        "calls": len(rr), "in_tok": sum(r.get("in_tok") or 0 for r in rr),
        "out_tok": sum(r.get("out_tok") or 0 for r in rr), "reasoning_tok": sum(r.get("reasoning_tok") or 0 for r in rr)}
    spend += sum((r.get("in_tok") or 0) * INR["105b_in"] + (r.get("out_tok") or 0) * INR["105b_out"] for r in rr)
    usage["_sarvam_spend_inr_list_price"] = round(spend, 2)
    usage["_openrouter_cost_usd"] = round(sum(r.get("cost_usd") or 0 for r in raws if r["system"].startswith("or:")), 4)

    examples = []
    for task, lang in (("A", "ta"), ("A", "hi"), ("B", "hi"), ("B", "ta")):
        sys_list = systems[task]
        # the passage where systems differ most in recall
        spread = lambda i: [sc[(task, i, lang, s)]["recall"] for s in sys_list if (task, i, lang, s) in sc]
        ids = sorted(P, key=lambda i: -(max(spread(i), default=0) - min(spread(i), default=0)))
        for i in ids[:1]:
            p = P[i]
            examples.append({"task": label[task], "id": i, "lang": lang, "source": p["text"],
                             "gold_facts": {e["key"]: e["surface"] for e in p["entities"]
                                            if task == "A" or e["key"] in p["key_facts"]},
                             "systems": {s: {"output": rec[(task, i, lang, s)]["text"],
                                             "recall": round(sc[(task, i, lang, s)]["recall"], 3),
                                             "missed": [next(e["surface"] for e in p["entities"] if e["key"] == m)
                                                        for m in sc[(task, i, lang, s)]["missed"]],
                                             "unsupported_numbers": sc[(task, i, lang, s)]["unsupported"]}
                                         for s in sys_list if (task, i, lang, s) in rec}})
    notes_p = Path(__file__).with_name("notes.json")
    notes = json.loads(notes_p.read_text()) if notes_p.exists() else {}
    return {
        "uc": UC, "title": "Courts and legal: translating and summarising judgments without losing facts",
        "business_question": "If I translate or summarise English court orders, RTI replies and tribunal awards "
                             "into Hindi, Tamil, Marathi or Bengali for litigants, which system keeps every "
                             "amount, date, section, case number and party name intact?",
        "dataset": {"name": "uc09-synthetic-legal-passages", "source": "authored for this benchmark: 12 hand-"
                    "written templates (s.138 NI Act conviction and appeal, regular and anticipatory bail, consumer "
                    "builder refund and insurance appeal, rent eviction, land partition, RTI fee reply and RTI "
                    "penalty, MACT death and injury awards) filled with invented parties, places and numbers "
                    "(suites/uc09_legal/make_data.py)", "license": "CC0 (synthetic)", "n": len(passages),
                    "n_entities": sum(len(p["entities"]) for p in passages),
                    "translation_items_per_system": sum(A_LANGS.values()),
                    "summary_items_per_system": len(passages) * len(B_LANGS),
                    "languages": list(LANGS), "synthetic": True},
        "systems": sorted(set(systems["A"]) | set(systems["B"])), "metrics": metrics,
        "per_language": per_language, "preservation_by_entity_type": by_type, "speed": speed, "usage": usage,
        "examples": examples, "findings": notes.get("findings", []), "caveats": notes.get("caveats", []),
        "verdict": notes.get("verdict", ""),
    }


if __name__ == "__main__":
    main()
