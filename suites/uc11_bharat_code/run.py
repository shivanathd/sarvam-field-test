"""UC11 Bharat Code: can these models act as coding agents for Indian business logic, when the task is written in
the developer's own language?

  python suites/uc11_bharat_code/run.py            # everything: API systems, then local ones, then report
  python suites/uc11_bharat_code/run.py code --systems sarvam-105b gemini-3.8-flash
  python suites/uc11_bharat_code/run.py tools      # tool-calling sub-test
  python suites/uc11_bharat_code/run.py report     # recompute results/uc11_bharat_code.json from raw

Resumable: raw records are keyed by (kind, item id, system); finished items are never re-sent.
Model code only ever runs inside sandbox.run_sandboxed (sandbox-exec: no network, no writes outside a temp dir).
"""
import argparse, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1])); sys.path.insert(0, str(HERE))
import requests
from common.bench import chat, log, raw_append, raw_load, wait_for_local, GEMINI_CHAT, LOCAL_PORTS, _retry
from prompts import LANGS, SYSTEM, TASKS, user_prompt
from testrun import run_tests, feedback

UC = "uc11_bharat_code"
# label -> (chat() system name, think[, temperature])
SYSTEMS = {"sarvam-105b": ("sarvam-105b", False), "sarvam-105b-think": ("sarvam-105b", True, 0.5),  # Sarvam docs: thinking mode wants temperature >= 0.5
           "sarvam-105b-think-t0": ("sarvam-105b", True, 0.0),  # ablation: greedy decoding in thinking mode
           "sarvam-105b-t0.7": ("sarvam-105b", False, 0.7),  # ablation: does sampling unstick the repair loop?
           "gemini-3.8-flash": (GEMINI_CHAT, False), "gemini-3.8-flash-think": (GEMINI_CHAT, True),
           "sarvam-30b-local": ("sarvam-30b-local", False), "qwen3-30b-local": ("qwen3-30b-local", False),
           # addendum comparators: price-matched tier on the full set, frontier tier (think on) on tasks 1-30
           "gpt-5.4-mini": ("openai:gpt-5.4-mini", False), "gpt-5.4-mini-think": ("openai:gpt-5.4-mini", True),
           "claude-haiku-5.5": ("or:anthropic/claude-haiku-5.5", False),
           "claude-haiku-5.5-think": ("or:anthropic/claude-haiku-5.5", True),
           "gemini-pro-latest-think": ("gemini-pro-latest", True, 1.0),  # Google: keep Gemini 3 at temperature 1.0
           "gpt-5.5-think": ("openai:gpt-5.5", True), "claude-sonnet-5.5-think": ("or:anthropic/claude-sonnet-5.5", True)}
API = ["sarvam-105b", "sarvam-105b-think", "gemini-3.8-flash", "gemini-3.8-flash-think"]
LOCAL = ["sarvam-30b-local", "qwen3-30b-local"]
PRICE_MATCHED = ["gpt-5.4-mini", "gpt-5.4-mini-think", "claude-haiku-5.5", "claude-haiku-5.5-think"]
FRONTIER = ["gemini-pro-latest-think", "gpt-5.5-think", "claude-sonnet-5.5-think"]
POOL = {"sarvam": 3, "gemini": 4, "local": 2, "openai": 4, "openrouter": 4}  # brief: <=3 Sarvam, <=4 Gemini; 2 of 4 shared llama-server slots
MAX_ATTEMPTS = 3
# Local models run at ~6-20 tok/s on the shared Mac and Sarvam-30B fills its whole budget: single-shot on 20 tasks only.
LOCAL_TASKS = [t for t in TASKS if t % 2 == 1]
FRONTIER_TASKS = [t for t in TASKS if t <= 30 or t % 2 == 1]  # frontier: ids 1-30 (brief addendum) + the 20 odd ids (local subset)
REPAIR = ("Your code was run against hidden unit tests.\n{fb}\n\n"
          "Fix the function. Reply with the complete corrected code in a single ```python block.")
_lock = threading.Lock()
STOPPED = set()


def pool_of(label):
    s = SYSTEMS[label][0]
    return ("sarvam" if s.startswith("sarvam-105b") else "gemini" if s.startswith("gemini") else
            "openai" if s.startswith("openai:") else "openrouter" if s.startswith("or:") else "local")


def extract_code(text, func):
    """The last fenced block that defines the function; else the last block; else an unterminated fence; else raw."""
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", text, re.S)
    with_def = [b for b in blocks if f"def {func}" in b]
    if with_def or blocks:
        return (with_def or blocks)[-1]
    m = re.search(r"```(?:python|py)?[ \t]*\n(.*)", text, re.S)  # unterminated fence (ran out of tokens)
    return m.group(1) if m else text


def local_chat(system, msgs, max_tokens):
    """common.bench.chat() cannot switch Sarvam-30B's reasoning off (its <|nothink|> template flag is ignored by the
    GGUF; measured >4000 reasoning tokens on a 3-line IFSC task). Prefilling an empty <think></think> assistant turn
    does switch it off, so sarvam-30b-local is run in no-think mode, matching sarvam-105b and qwen3 defaults here."""
    t = time.time()
    body = {"messages": msgs + [{"role": "assistant", "content": "<think></think>"}], "max_tokens": max_tokens,
            "temperature": 0}

    def go():
        d = requests.post(f"http://127.0.0.1:{LOCAL_PORTS[system]}/v1/chat/completions", json=body, timeout=1800).json()
        if "choices" not in d:
            raise RuntimeError(str(d)[:300])
        return d
    d = _retry(go)
    u = d.get("usage") or {}
    text = re.sub(r"<think>.*?</think>", "", d["choices"][0]["message"].get("content") or "", flags=re.S).strip()
    return {"text": text, "ms": (time.time() - t) * 1000, "in_tok": u.get("prompt_tokens"), "out_tok": u.get("completion_tokens")}


def solve(tid, lang, label):
    system, think, temp = (SYSTEMS[label] + (0.0,))[:3]
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_prompt(tid, lang)}]
    attempts = []
    for k in range(1 if label in LOCAL else MAX_ATTEMPTS):
        if system == "sarvam-30b-local":
            r = local_chat(system, msgs, 1500)
        else:  # local models capped at 1500 tokens: ~16 tok/s per slot on the shared Mac
            r = chat(system, msgs, max_tokens=16000 if think else 1500 if label in LOCAL else 4000, think=think,
                     temperature=temp)
        if r.get("error"):
            raise RuntimeError(r["error"])
        code = extract_code(r["text"], TASKS[tid]["func"])
        res = run_tests(code, TASKS[tid]["tests"])
        fb = None if res["ok"] else feedback(res)
        attempts.append({"text": r["text"], "ok": res["ok"], "passed": res["passed"], "total": res["total"],
                         "error": (res["error"] or "")[-400:] or None, "feedback": fb, "ms": r["ms"],
                         "in_tok": r.get("in_tok"), "out_tok": r.get("out_tok"), "reasoning_tok": r.get("reasoning_tok"),
                         "finish_reason": r.get("finish_reason"), "cost_usd": r.get("cost_usd")})
        if res["ok"]:
            break
        msgs += [{"role": "assistant", "content": r["text"] or "(empty reply)"},
                 {"role": "user", "content": REPAIR.format(fb=fb)}]
    solved = next((i + 1 for i, a in enumerate(attempts) if a["ok"]), None)
    return {"kind": "code", "id": f"{tid}:{lang}", "task": tid, "func": TASKS[tid]["func"], "lang": lang,
            "system": label, "solved_at": solved, "attempts": attempts}


def run_code(labels):
    have = {(r["id"], r["system"]) for r in raw_load(UC) if r.get("kind") == "code"}
    jobs = {p: [] for p in POOL}
    for label in labels:
        for tid in (LOCAL_TASKS if label in LOCAL else FRONTIER_TASKS if label in FRONTIER else TASKS):
            for lang in LANGS:
                if (f"{tid}:{lang}", label) not in have:
                    jobs[pool_of(label)].append((tid, lang, label))

    def work(job):
        p = pool_of(job[2])
        if p in STOPPED:
            return
        try:
            rec = solve(*job)
        except Exception as e:  # not recorded -> retried on the next run
            if re.search(r"402|quota|credit|insufficient|billing", str(e), re.I):
                STOPPED.add(p)  # out of credits is a hard stop for that provider, not a per-item retry
                log(UC, "HARD STOP", p, str(e)[:300])
            log(UC, "ERROR", job, str(e)[:300])
            return
        with _lock:
            raw_append(UC, rec)
        log(UC, rec["system"], rec["id"], "solved_at", rec["solved_at"])

    threads = []
    for p, js in jobs.items():
        if js:
            log(UC, f"code: {len(js)} items on pool {p}")
            ex = ThreadPoolExecutor(POOL[p])
            threads.append(ex)
            for j in js:
                ex.submit(work, j)
    for ex in threads:
        ex.shutdown(wait=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", nargs="?", default="all", choices=["all", "code", "tools", "report"])
    ap.add_argument("--systems", nargs="*")
    a = ap.parse_args()
    import tools as toolsuite, report
    if a.what in ("code", "all"):
        run_code(a.systems or API)
    if a.what in ("tools", "all"):
        toolsuite.run(a.systems or API)
    if a.what == "all":
        for label in LOCAL:
            if wait_for_local(SYSTEMS[label][0]):
                run_code([label]); toolsuite.run([label])
            else:
                log(UC, f"{label} not up after waiting; skipped")
    report.build()


if __name__ == "__main__":
    main()
