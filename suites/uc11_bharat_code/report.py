"""Recompute results/uc11_bharat_code.json from raw records (no API calls)."""
import random, statistics, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.bench import raw_load, write_result, bootstrap_ci, pctl
from prompts import LANGS, TASKS, user_prompt

UC = "uc11_bharat_code"
ORDER = ["sarvam-105b", "sarvam-105b-think", "sarvam-105b-think-t0", "sarvam-105b-t0.7", "gemini-3.8-flash",
         "gemini-3.8-flash-think", "gpt-5.4-mini", "gpt-5.4-mini-think", "claude-haiku-5.5", "claude-haiku-5.5-think",
         "gemini-pro-latest-think", "gpt-5.5-think", "claude-sonnet-5.5-think", "sarvam-30b-local", "qwen3-30b-local"]
TOOL_LANGS = ["hi", "hinglish", "ta", "bn"]


def paired_diff_ci(a, b, iters=2000, seed=0):
    """Mean of a-b over paired items with a percentile bootstrap CI (items resampled together)."""
    d = [x - y for x, y in zip(a, b)]
    if not d:
        return {"mean": None, "lo": None, "hi": None, "n": 0}
    rnd = random.Random(seed)
    ms = sorted(statistics.fmean(rnd.choices(d, k=len(d))) for _ in range(iters))
    return {"mean": statistics.fmean(d), "lo": ms[int(0.025 * iters)], "hi": ms[int(0.975 * iters)], "n": len(d)}


def latest(recs):
    out = {}
    for r in recs:
        out[(r["id"], r["system"])] = r  # last write wins
    return list(out.values())


def build():
    raw = raw_load(UC)
    code = latest([r for r in raw if r.get("kind") == "code"])
    tool = latest([r for r in raw if r.get("kind") == "tool"])
    systems = [s for s in ORDER if any(r["system"] == s for r in code + tool)]
    by = {s: [r for r in code if r["system"] == s] for s in systems}

    def pass_at(rs, k):
        return [1.0 if r["solved_at"] and r["solved_at"] <= k else 0.0 for r in rs]

    metrics, per_lang, penalty, speed, usage, cum = [], {}, {}, {}, {}, {}
    m1 = {"name": "pass@1 (single shot)", "higher_is_better": True, "unit": "fraction of task-language items (160 full set; 120 = tasks 1-30 for frontier; 80 = odd tasks for local)", "values": {}}
    m3 = {"name": "pass@3 with repair loop", "higher_is_better": True, "unit": "fraction of task-language items (160 full set; 120 = tasks 1-30 for frontier; 80 = odd tasks for local)", "values": {}}
    for s in systems:
        rs = by[s]
        if not rs:
            continue
        m1["values"][s] = bootstrap_ci(pass_at(rs, 1))
        if s not in ("sarvam-30b-local", "qwen3-30b-local"):  # local models were run single-shot (no repair loop)
            m3["values"][s] = bootstrap_ci(pass_at(rs, 3))
        cum[s] = {f"after_{k}": round(statistics.fmean(pass_at(rs, k)), 4) for k in (1, 2, 3)}
        for lang in LANGS:
            lr = [r for r in rs if r["lang"] == lang]
            per_lang.setdefault("pass@1", {}).setdefault(lang, {})[s] = bootstrap_ci(pass_at(lr, 1))
            per_lang.setdefault("pass@3 with repair", {}).setdefault(lang, {})[s] = bootstrap_ci(pass_at(lr, 3))
        en = {r["task"]: r for r in rs if r["lang"] == "en"}
        for lang in LANGS[1:]:
            pairs = [(en[r["task"]], r) for r in rs if r["lang"] == lang and r["task"] in en]
            for k, name in ((1, "pass@1"), (3, "pass@3")):
                a = [1.0 if e["solved_at"] and e["solved_at"] <= k else 0.0 for e, _ in pairs]
                b = [1.0 if o["solved_at"] and o["solved_at"] <= k else 0.0 for _, o in pairs]
                penalty.setdefault(name, {}).setdefault(lang, {})[s] = paired_diff_ci(a, b)
        calls = [a for r in rs for a in r["attempts"]]
        speed[s] = {"p50_ms": pctl([a["ms"] for a in calls], 0.5), "p95_ms": pctl([a["ms"] for a in calls], 0.95)}
        solved = [r for r in rs if r["solved_at"]]
        tok_solved = [sum((a["out_tok"] or 0) + ((a["reasoning_tok"] or 0) if s.startswith("gemini") else 0)
                          for a in r["attempts"]) for r in solved]
        ms_solved = [sum(a["ms"] for a in r["attempts"]) for r in solved]
        speed[s].update({"mean_output_tokens_per_solved_item": round(statistics.fmean(tok_solved)) if tok_solved else None,
                         "mean_wall_s_per_solved_item": round(statistics.fmean(ms_solved) / 1000, 1) if ms_solved else None})
        trs = [r for r in tool if r["system"] == s]
        u = {"calls": len(calls) + len(trs),
             "in_tok": sum((a["in_tok"] or 0) for a in calls) + sum((r.get("in_tok") or 0) for r in trs),
             "out_tok": sum((a["out_tok"] or 0) for a in calls) + sum((r.get("out_tok") or 0) for r in trs),
             "reasoning_tok": sum((a["reasoning_tok"] or 0) for a in calls) + sum((r.get("reasoning_tok") or 0) for r in trs)}
        cost = [x.get("cost_usd") for x in calls + trs if x.get("cost_usd") is not None]
        if cost:  # OpenRouter reports usage.cost in USD
            u["cost_usd_reported"] = round(sum(cost), 4)
        if s.startswith("sarvam-105b"):  # completion_tokens already include reasoning tokens on Sarvam
            u["est_cost_inr_list_price"] = round(u["in_tok"] * 15 / 1e6 + u["out_tok"] * 60 / 1e6, 2)
        usage[s] = u
    metrics += [m1, m3]
    m_pen = {"name": "language penalty, pass@1 (English minus language; avg over hi/ta/hinglish)", "higher_is_better": False,
             "unit": "fraction", "values": {}}
    for s in systems:
        vals = [penalty["pass@1"][l][s]["mean"] for l in LANGS[1:] if s in penalty.get("pass@1", {}).get(l, {})]
        if vals:
            m_pen["values"][s] = {"mean": statistics.fmean(vals), "lo": None, "hi": None, "n": len(vals)}
    metrics.append(m_pen)

    # tool calling
    from tools import HARD
    mt = {"name": "tool calling: correct tool + exact args (all 50)", "higher_is_better": True, "unit": "fraction of 50 commands", "values": {}}
    mtb = {"name": "tool calling exact: base 30", "higher_is_better": True, "unit": "fraction", "values": {}}
    mth = {"name": "tool calling exact: hard 20 (fractional amounts, regional terms)", "higher_is_better": True, "unit": "fraction", "values": {}}
    mtn = {"name": "tool calling: correct tool name (all 50)", "higher_is_better": True, "unit": "fraction of 50 commands", "values": {}}
    tool_modes = {}
    for s in systems:
        trs = [r for r in tool if r["system"] == s]
        if not trs:
            continue
        mt["values"][s] = bootstrap_ci([1.0 if r["exact"] else 0.0 for r in trs])
        mtn["values"][s] = bootstrap_ci([1.0 if r["tool_ok"] else 0.0 for r in trs])
        mtb["values"][s] = bootstrap_ci([1.0 if r["exact"] else 0.0 for r in trs if r["id"] not in HARD])
        mth["values"][s] = bootstrap_ci([1.0 if r["exact"] else 0.0 for r in trs if r["id"] in HARD])
        tool_modes[s] = sorted({r["mode"] for r in trs})
        for lang in TOOL_LANGS:
            lr = [r for r in trs if r["lang"] == lang]
            per_lang.setdefault("tool exact", {}).setdefault(lang, {})[s] = bootstrap_ci([1.0 if r["exact"] else 0.0 for r in lr])
    metrics += [mt, mtb, mth, mtn]

    # like-for-like: every system on the 20-task subset (odd ids) that local and frontier tiers share
    odd = {t for t in TASKS if t % 2 == 1}
    subset20 = {}
    for s in systems:
        rs = [r for r in by[s] if r["task"] in odd]
        if rs:
            subset20[s] = {"pass@1": bootstrap_ci(pass_at(rs, 1)),
                           "pass@3": None if s in ("sarvam-30b-local", "qwen3-30b-local") else bootstrap_ci(pass_at(rs, 3))}

    # hardest tasks
    hard = {}
    for t in TASKS:
        rs = [r for r in code if r["task"] == t]
        if rs:
            hard[TASKS[t]["func"]] = round(statistics.fmean(pass_at(rs, 1)), 3)
    hardest = dict(sorted(hard.items(), key=lambda kv: kv[1])[:10])

    result = {"metrics": metrics, "per_language": per_lang, "language_penalty": penalty, "repair_curve": cum,
              "speed": speed, "usage": usage, "systems": systems}
    try:
        import narrative  # hand-written interpretation; numbers are computed from raw, not typed in
        nar = narrative.make(code, tool, result)
    except ImportError:
        nar = {}
    write_result(UC, {
        "uc": UC, "title": "Bharat Code: coding agents for Indian business logic, prompted in Indian languages",
        "business_question": "Can these models act as coding agents for Indian business logic when the developer writes the "
                             "task in their own language (Hindi, Tamil, Hinglish) instead of English? And can they drive "
                             "a payments-app tool schema from Indian-language voice commands?",
        "dataset": {"name": "uc11 Bharat Code (40 tasks x 4 prompt languages) + 50 tool-calling commands",
                    "source": "authored for this benchmark: 40 India-specific Python tasks (Verhoeff/Aadhaar, PAN, GSTIN, "
                              "IFSC, GST split/invoice, Indian digit grouping, lakh/crore words in English and Hindi, FY/quarter, "
                              "TDS/income tax with stated slabs, EMI, UPI, Indic digits, PIN, railway status, IST, Luhn/RuPay, "
                              "mobile normalisation, vehicle plates, HRA, gratuity, EPF, FD, CIN, bank holidays, etc.) each with "
                              "a reference solution and 8-14 hidden asserts (all references verified passing). Specs hand-translated "
                              "to Hindi, Tamil and Hinglish with identifiers/literals verbatim; every translation back-translated "
                              "blind by Gemini and diffed against the English (3 ambiguities found and fixed, then 0 flagged).",
                    "license": "CC-BY-4.0 (authored here)", "n": len(TASKS) * len(LANGS),
                    "languages": LANGS + ["bn (tool test only)"], "synthetic": True,
                    "synthetic_note": "All IDs (Aadhaar-format, PAN, GSTIN, CIN, cards, phones, UPI IDs) are synthetic test values."},
        "systems": systems, "metrics": metrics, "per_language": per_lang,
        "language_penalty": penalty, "repair_curve": cum, "subset20_odd_tasks": subset20, "hardest_tasks_pass@1_all_systems": hardest,
        "tool_calling_modes": tool_modes, "speed": speed, "usage": usage,
        "harness": {"sandbox": "macOS sandbox-exec: network denied, file writes only in a fresh temp dir, reads under $HOME "
                               "denied (except Python stdlib), python -I, 10 s timeout; self-test in suites/uc11_bharat_code/sandbox.py",
                    "repair_loop": "up to 3 attempts; after a failure the model sees up to 5 failing asserts (call, expected, got) "
                                   "or the traceback, truncated, like a coding-agent test runner",
                    "system_prompt": "English (as in real coding tools); task text and output instruction in the prompt language",
                    "temperature": 0},
        **nar,
    })


if __name__ == "__main__":
    build()
    print("written")
