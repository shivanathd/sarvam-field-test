"""Calls to the self-hosted llama-server models with explicit thinking control (shared by uc10 and uc06).

common.bench.chat() ignores think=False for sarvam-30b-local (it always follows the chat template default, which
thinks). Sarvam-30B's template renders enable_thinking=false as a <|nothink|> marker, but the official Q4_K_M GGUF
still reasons for ~1k tokens with it (measured). What does switch thinking off is prefilling the assistant turn with an
empty "<think></think>" (the same thing the template writes for past assistant turns), so we do that.

Names: <model>-<where>[-think|-nothink]
  model: sarvam-30b | qwen3-30b     where: local (GPU, :8101/:8102) | cpu (CPU-only server, :8111)
  default thinking: sarvam-30b thinks, qwen3-30b does not (matching common.bench.chat)
"""
import re, time
import requests

PORTS = {("sarvam-30b", "local"): 8101, ("qwen3-30b", "local"): 8102, ("sarvam-30b", "cpu"): 8111, ("qwen3-30b", "cpu"): 8111}


def parse(system):
    m = re.fullmatch(r"(sarvam-30b|qwen3-30b)-(local|cpu)(?:-(think|nothink))?", system)
    model, where, mode = m.groups()
    think = mode == "think" if mode else model == "sarvam-30b"
    return model, where, think


def is_local(system):
    return re.fullmatch(r"(sarvam-30b|qwen3-30b)-(local|cpu)(-think|-nothink)?", system) is not None


def url(system):
    model, where, _ = parse(system)
    return f"http://127.0.0.1:{PORTS[(model, where)]}"


def healthy(system):
    try:
        return requests.get(url(system) + "/health", timeout=5).json().get("status") == "ok"
    except Exception:
        return False


def local_chat(system, messages, max_tokens=2000, temperature=0.0):
    model, where, think = parse(system)
    body = {"messages": messages, "max_tokens": max_tokens, "temperature": temperature,
            "chat_template_kwargs": {"enable_thinking": think}}
    if model == "sarvam-30b" and not think:
        body["messages"] = messages + [{"role": "assistant", "content": "<think></think>"}]
    if model == "qwen3-30b" and not think:  # same switch common.bench.chat uses
        body["messages"] = messages[:-1] + [{**messages[-1], "content": messages[-1]["content"] + " /no_think"}]
    t = time.time()
    d = None
    for i in range(4):
        try:
            d = requests.post(url(system) + "/v1/chat/completions", json=body, timeout=1800).json()
            break
        except Exception:
            if i == 3:
                raise
            time.sleep(5 * (i + 1))
    u = d.get("usage") or {}
    msg = d["choices"][0]["message"]
    text = re.sub(r"<think>.*?</think>", "", msg.get("content") or "", flags=re.S).strip()  # also drops the prefill echo
    return {"text": text, "ms": (time.time() - t) * 1000, "in_tok": u.get("prompt_tokens"),
            "out_tok": u.get("completion_tokens"), "reasoning_chars": len(msg.get("reasoning_content") or ""),
            "timings": d.get("timings")}
