"""Shared plumbing for every use-case suite: keys, model clients, scoring helpers, result files.

Import from a suite with:  sys.path.insert(0, str(ROOT)); from common.bench import *
"""
import base64, json, os, random, re, statistics, time, unicodedata
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RESULTS, RAW, LOGS, DATA = ROOT / "results", ROOT / "results" / "raw", ROOT / "logs", ROOT / "data"
for d in (RESULTS, RAW, LOGS, DATA):
    d.mkdir(parents=True, exist_ok=True)


def _load_env():
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        k, _, v = line.partition("=")
        if k and v and not os.environ.get(k.strip()):  # empty shell vars must not mask .env
            os.environ[k.strip()] = v.strip()


_load_env()
SARVAM = "https://api.sarvam.ai"
GEMINI_CHAT = "gemini-3.8-flash"
GEMINI_TTS = "gemini-3.8-flash-tts"
# models that cannot disable thinking: think=False runs them at their minimum instead (report this)
ALWAYS_THINK = {"gemini-pro-latest", "anthropic/claude-sonnet-5.5", "anthropic/claude-opus-5.5"}
LOCAL_PORTS = {"sarvam-30b-local": 8101, "qwen3-30b-local": 8102}


def log(uc, *msg):
    line = time.strftime("%H:%M:%S ") + " ".join(str(m) for m in msg)
    print(line, flush=True)
    with open(LOGS / f"{uc}.log", "a") as f:
        f.write(line + "\n")


def _retry(fn, tries=6):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # 429s, 5xx and timeouts all retry with backoff
            if i == tries - 1:
                raise
            time.sleep(min(60, 2 ** i + random.random()))


# ---------- Sarvam ----------
def sarvam_post(path, json_body=None, files=None, data=None, timeout=180):
    h = {"api-subscription-key": os.environ["SARVAM_API_KEY"]}
    # read file handles into bytes once, so a retry after 429/5xx doesn't re-send an exhausted (empty) stream
    if files:
        def _bytes(v):
            if hasattr(v, "read"):
                return (os.path.basename(getattr(v, "name", "file")), v.read())
            if isinstance(v, tuple) and len(v) > 1 and hasattr(v[1], "read"):
                return (v[0], v[1].read(), *v[2:])
            return v
        files = {k: _bytes(v) for k, v in files.items()}

    def go():
        r = requests.post(SARVAM + path, headers=h, json=json_body, files=files, data=data, timeout=timeout)
        if r.status_code == 429 or r.status_code >= 500:
            raise RuntimeError(f"{r.status_code} {r.text[:200]}")
        if r.status_code >= 400:  # client errors are not retried
            # credit exhaustion arrives as 402 on chat but 400 "Insufficient credits" on Vision: flag both
            return {"_error": r.status_code, "_body": r.text[:500],
                    "_credits": r.status_code == 402 or bool(re.search(r"credit|quota", r.text, re.I))}
        return r.json()

    return _retry(go)


def chat(system, messages, max_tokens=2000, temperature=0.0, think=False):
    """One chat turn on any system. Returns dict(text, ms, in_tok, out_tok, reasoning_tok).

    system: 'sarvam-105b' | 'sarvam-105b-conversations' | 'sarvam-30b-local' | 'qwen3-30b-local' | GEMINI_CHAT
    think: Sarvam API -> reasoning_effort 'medium' vs null; Gemini -> thinking budget on/off;
           local models -> qwen3 '/no_think' toggle (sarvam-30b local follows its chat template).
    """
    t = time.time()
    if system.startswith("sarvam-105b"):
        body = {"model": system, "messages": messages, "max_tokens": max_tokens, "temperature": temperature,
                "reasoning_effort": "medium" if think else None}
        d = sarvam_post("/v1/chat/completions", body)
        if "_error" in d:
            return {"text": "", "error": d, "ms": (time.time() - t) * 1000}
        u = d.get("usage") or {}
        return {"text": d["choices"][0]["message"].get("content") or "", "ms": (time.time() - t) * 1000,
                "in_tok": u.get("prompt_tokens"), "out_tok": u.get("completion_tokens"),
                "reasoning_tok": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                "finish_reason": d["choices"][0].get("finish_reason")}  # "length" + empty text = budget ran out
    if system == "sarvam-30b-local" and not think:
        # llama-server ignores enable_thinking / reasoning_effort / <|nothink|> for this model, so prefill an
        # empty think block on the raw templated prompt (otherwise all max_tokens go to reasoning_content).
        base = f"http://127.0.0.1:{LOCAL_PORTS[system]}"
        prompt = _retry(lambda: requests.post(base + "/apply-template", json={"messages": messages}, timeout=60).json())["prompt"]
        body = {"prompt": prompt + "<think></think>", "n_predict": max_tokens, "temperature": temperature}
        d = _retry(lambda: requests.post(base + "/completion", json=body, timeout=900).json())
        return {"text": (d.get("content") or "").strip(), "ms": (time.time() - t) * 1000,
                "in_tok": d.get("tokens_evaluated"), "out_tok": d.get("tokens_predicted"), "timings": d.get("timings")}
    if system in LOCAL_PORTS:
        msgs = messages
        if system.startswith("qwen3") and not think:
            msgs = messages[:-1] + [{**messages[-1], "content": messages[-1]["content"] + " /no_think"}]
        body = {"messages": msgs, "max_tokens": max_tokens, "temperature": temperature}
        url = f"http://127.0.0.1:{LOCAL_PORTS[system]}/v1/chat/completions"
        d = _retry(lambda: requests.post(url, json=body, timeout=900).json())
        u = d.get("usage") or {}
        text = d["choices"][0]["message"].get("content") or ""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
        return {"text": text, "ms": (time.time() - t) * 1000, "in_tok": u.get("prompt_tokens"),
                "out_tok": u.get("completion_tokens"), "timings": d.get("timings")}
    if system.startswith(("openai:", "or:")):
        # OpenAI direct ("openai:gpt-5.4-mini") or OpenRouter ("or:anthropic/claude-haiku-5.5"); both OpenAI-compatible.
        prov, model = system.split(":", 1)
        url, key = (("https://api.openai.com/v1/chat/completions", "OPENAI_API_KEY") if prov == "openai"
                    else ("https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY"))
        body = {"model": model, "messages": messages, "max_completion_tokens" if prov == "openai" else "max_tokens": max_tokens}
        if prov == "openai":
            body["reasoning_effort"] = "medium" if think else "none"
        else:
            # some models (e.g. Claude Sonnet 5.5) refuse reasoning off; ALWAYS_THINK makes them run at low effort
            body["reasoning"] = {"effort": "low"} if (not think and model in ALWAYS_THINK) else {"enabled": bool(think)}
            body["temperature"] = temperature

        def go():
            r = requests.post(url, headers={"Authorization": "Bearer " + os.environ[key]}, json=body, timeout=300)
            if r.status_code == 429 or r.status_code >= 500:
                raise RuntimeError(f"{r.status_code} {r.text[:200]}")
            return r.json()

        d = _retry(go)
        if "error" in d:
            return {"text": "", "error": d["error"], "ms": (time.time() - t) * 1000}
        u = d.get("usage") or {}
        return {"text": (d["choices"][0]["message"].get("content") or "").strip(), "ms": (time.time() - t) * 1000,
                "in_tok": u.get("prompt_tokens"), "out_tok": u.get("completion_tokens"),
                "reasoning_tok": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                "cost_usd": u.get("cost"), "finish_reason": d["choices"][0].get("finish_reason")}
    if system.startswith("gemini"):
        from google import genai
        from google.genai import types
        c = genai.Client(http_options=types.HttpOptions(timeout=180_000))  # ms; calls can otherwise hang forever
        sys_txt = "\n".join(m["content"] for m in messages if m["role"] == "system") or None
        contents = [types.Content(role="model" if m["role"] == "assistant" else "user",
                                  parts=[types.Part(text=m["content"])]) for m in messages if m["role"] != "system"]
        cfg = types.GenerateContentConfig(system_instruction=sys_txt, temperature=temperature,
                                          max_output_tokens=max_tokens,
                                          thinking_config=types.ThinkingConfig(
                                              thinking_budget=-1 if think else (128 if system in ALWAYS_THINK else 0)))
        r = _retry(lambda: c.models.generate_content(model=system, contents=contents, config=cfg))
        u = r.usage_metadata
        return {"text": r.text or "", "ms": (time.time() - t) * 1000, "in_tok": u.prompt_token_count,
                "out_tok": u.candidates_token_count, "reasoning_tok": u.thoughts_token_count}
    raise ValueError(system)


def wait_for_local(system, minutes=120):
    """Block until the local llama-server for `system` is healthy (the orchestrator starts them)."""
    url = f"http://127.0.0.1:{LOCAL_PORTS[system]}/health"
    for _ in range(minutes * 6):
        try:
            if requests.get(url, timeout=5).json().get("status") == "ok":
                return True
        except Exception:
            pass
        time.sleep(10)
    return False


# ---------- scoring ----------
def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def norm_text(s):
    s = unicodedata.normalize("NFC", s.lower())
    s = re.sub(r"[।॥.,!?;:\"'()\[\]{}\-–—…।]", " ", s)
    return " ".join(s.split())


def wer(ref, hyp):
    r, h = norm_text(ref).split(), norm_text(hyp).split()
    return edit_distance(r, h) / max(1, len(r))


def cer(ref, hyp):
    r, h = norm_text(ref).replace(" ", ""), norm_text(hyp).replace(" ", "")
    return edit_distance(list(r), list(h)) / max(1, len(r))


def chrf(ref, hyp, n=6, beta=2, word_n=2):
    """chrF++ (character 1..6-grams + word 1..2-grams), sentence level, 0-100."""
    def grams(seq, k):
        return [tuple(seq[i:i + k]) for i in range(len(seq) - k + 1)]

    def f(rs, hs):
        from collections import Counter
        rc, hc = Counter(rs), Counter(hs)
        m = sum((rc & hc).values())
        p, r = m / max(1, sum(hc.values())), m / max(1, sum(rc.values()))
        return 0 if p + r == 0 else (1 + beta**2) * p * r / (beta**2 * p + r)

    rc, hc = ref.replace(" ", ""), hyp.replace(" ", "")
    scores = [f(grams(rc, k), grams(hc, k)) for k in range(1, n + 1)]
    rw, hw = ref.split(), hyp.split()
    scores += [f(grams(rw, k), grams(hw, k)) for k in range(1, word_n + 1)]
    return 100 * sum(scores) / len(scores)


SCRIPTS = {"Devanagari": (0x0900, 0x097F), "Bengali": (0x0980, 0x09FF), "Gurmukhi": (0x0A00, 0x0A7F),
           "Gujarati": (0x0A80, 0x0AFF), "Odia": (0x0B00, 0x0B7F), "Tamil": (0x0B80, 0x0BFF),
           "Telugu": (0x0C00, 0x0C7F), "Kannada": (0x0C80, 0x0CFF), "Malayalam": (0x0D00, 0x0D7F),
           "Arabic": (0x0600, 0x06FF), "Ol Chiki": (0x1C50, 0x1C7F), "Latin": (0x0041, 0x024F)}


def dominant_script(s):
    counts = {k: sum(lo <= ord(c) <= hi for c in s) for k, (lo, hi) in SCRIPTS.items()}
    return max(counts, key=counts.get) if any(counts.values()) else None


def extract_json(text):
    """First JSON object/array in a model reply (tolerates ```json fences and prose)."""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    s = m.group(1) if m else text
    for open_, close in (("{", "}"), ("[", "]")):
        i = s.find(open_)
        if i >= 0:
            j = s.rfind(close)
            try:
                return json.loads(s[i:j + 1])
            except Exception:
                pass
    return None


def bootstrap_ci(values, iters=2000, seed=0):
    vals = [v for v in values if v is not None]
    if not vals:
        return {"mean": None, "lo": None, "hi": None, "n": 0}
    rnd = random.Random(seed)
    means = sorted(statistics.fmean(rnd.choices(vals, k=len(vals))) for _ in range(iters))
    return {"mean": statistics.fmean(vals), "lo": means[int(0.025 * iters)], "hi": means[int(0.975 * iters)],
            "n": len(vals)}


def pctl(xs, p):
    xs = sorted(x for x in xs if x is not None)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None


# ---------- results ----------
def raw_append(uc, record):
    with open(RAW / f"{uc}.jsonl", "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def raw_load(uc):
    p = RAW / f"{uc}.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def write_result(uc, result):
    """result schema (keep it):
    {uc, title, business_question, dataset:{name, source, license, n, languages, synthetic:bool},
     systems:[...], metrics:[{name, higher_is_better, unit, values:{system:{mean,lo,hi,n}}}],
     per_language:{metric_name:{lang:{system:value}}} (optional),
     speed:{system:{p50_ms,p95_ms}}, usage:{system:{in_tok,out_tok,audio_s,pages,chars,calls}},
     findings:[str], caveats:[str], verdict:str, examples:[{...}]}
    """
    result["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    (RESULTS / f"{uc}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
