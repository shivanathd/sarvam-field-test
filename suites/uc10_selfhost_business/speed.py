"""Hardware/speed measurement for the self-hosted models (writes data/uc10_selfhost_business/speed.json, merged per target).

For one llama-server target it measures, with thinking disabled and a fixed ~1k-token business prompt:
  prompt-processing tok/s and generation tok/s (llama-server timings), time-to-first-token (client side, streaming),
  aggregate generation tok/s at concurrency 1 and 4, peak RSS and macOS phys_footprint of the server process,
  system load average before/after, and whether other clients were using the server (slot busy) at start.

Usage: .venv/bin/python suites/uc10_selfhost_business/speed.py <target>
  target: sarvam-gpu | qwen-gpu (:8112, a dedicated GPU server you start) | sarvam-cpu | qwen-cpu (:8111, CPU-only)
"""
import json, os, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "uc10_selfhost_business" / "speed.json"
TARGETS = {"sarvam-gpu": 8112, "qwen-gpu": 8112, "sarvam-cpu": 8111, "qwen-cpu": 8111}
# :8112 / :8111 are dedicated measurement servers started for this script (see README), so requests from other suites
# on the shared :8101/:8102 servers do not queue in front of ours; they still share the GPU and CPU, which we record.
SHARED = {"sarvam": 8101, "qwen": 8102}
GEN = 256  # tokens generated per request; CPU targets use 64 and fewer runs (a 256-token CPU run takes minutes)


def prompt(nonce):
    items = json.loads((OUT.parent / "items.json").read_text())["items"]
    tickets = "\n".join(f"{k + 1}. {it['text']}" for k, it in enumerate(items[::6][:22]))
    return [{"role": "system", "content": f"[run {nonce}] You are a support analyst at an Indian online store."},
            {"role": "user", "content": "Summarise each ticket below in one English line, then list the three most "
                                        "urgent ones.\n\n" + tickets}]


def one(port, nonce, gen):
    """Streaming request; returns ttft_ms, wall_ms and llama-server timings."""
    body = {"messages": prompt(nonce), "max_tokens": gen, "temperature": 0, "stream": True, "ignore_eos": True,
            "cache_prompt": False, "chat_template_kwargs": {"enable_thinking": False}}
    t0, ttft, timings = time.time(), None, None
    with requests.post(f"http://127.0.0.1:{port}/v1/chat/completions", json=body, stream=True, timeout=3600) as r:
        for line in r.iter_lines():
            if not line.startswith(b"data: ") or line == b"data: [DONE]":
                continue
            d = json.loads(line[6:])
            delta = (d.get("choices") or [{}])[0].get("delta") or {}
            if ttft is None and (delta.get("content") or delta.get("reasoning_content")):
                ttft = (time.time() - t0) * 1000
            timings = d.get("timings") or timings
    return {"ttft_ms": ttft, "wall_ms": (time.time() - t0) * 1000, "timings": timings}


def sampler(pid, stop, peak):
    while not stop.is_set():
        try:
            rss = int(subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True).stdout) * 1024
            peak["rss_bytes"] = max(peak.get("rss_bytes", 0), rss)
        except ValueError:
            pass
        time.sleep(0.5)


def footprint(pid):
    out = subprocess.run(["footprint", "-p", str(pid)], capture_output=True, text=True).stdout
    m = re.search(r"Footprint:\s*([\d.]+)\s*(KB|MB|GB)", out)
    return float(m.group(1)) * {"KB": 1e-3, "MB": 1, "GB": 1e3}[m.group(2)] if m else None


def main(target):
    port = TARGETS[target]
    pid = int(subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"], capture_output=True, text=True).stdout.split()[0])
    cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    def busy_slots(p):
        try:
            return sum(s.get("is_processing", False) for s in requests.get(f"http://127.0.0.1:{p}/slots", timeout=10).json())
        except Exception:
            return None

    busy = {p: busy_slots(p) for p in SHARED.values()}
    load0 = os.getloadavg()
    stop, peak = threading.Event(), {}
    th = threading.Thread(target=sampler, args=(pid, stop, peak), daemon=True)
    th.start()
    cpu = target.endswith("cpu")
    gen, n1, n4 = (64, 2, 1) if cpu else (GEN, 3, 2)
    if not cpu:
        one(port, "warmup", gen)
    c1 = [one(port, f"c1-{k}", gen) for k in range(n1)]
    c4 = []
    for rnd in range(n4):
        t0 = time.time()
        with ThreadPoolExecutor(4) as ex:
            batch = list(ex.map(lambda k: one(port, f"c4-{rnd}-{k}", gen), range(4)))
        c4.append({"wall_ms": (time.time() - t0) * 1000, "requests": batch})
    stop.set()
    th.join()
    load1 = os.getloadavg()

    def med(xs):
        xs = sorted(x for x in xs if x is not None)
        return xs[len(xs) // 2] if xs else None

    res = {
        "target": target, "port": port, "server_cmd": cmd, "measured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "machine": "Apple M5 Max, 128 GB unified memory (shared Mac; other jobs running)",
        "prompt_tokens": c1[0]["timings"]["prompt_n"], "gen_tokens": gen, "thinking": "disabled",
        "c1": {"prompt_tok_per_s": med(r["timings"]["prompt_per_second"] for r in c1),
               "gen_tok_per_s": med(r["timings"]["predicted_per_second"] for r in c1),
               "ttft_ms": med(r["ttft_ms"] for r in c1), "wall_ms": med(r["wall_ms"] for r in c1), "runs": len(c1)},
        "c4": {"per_request_gen_tok_per_s": med(r["timings"]["predicted_per_second"] for b in c4 for r in b["requests"]),
               "per_request_prompt_tok_per_s": med(r["timings"]["prompt_per_second"] for b in c4 for r in b["requests"]),
               "aggregate_gen_tok_per_s": med(4 * gen / (b["wall_ms"] / 1000) for b in c4),
               "ttft_ms": med(r["ttft_ms"] for b in c4 for r in b["requests"]),
               "batch_wall_ms": med(b["wall_ms"] for b in c4), "rounds": len(c4)},
        "peak_rss_gb": round(peak.get("rss_bytes", 0) / 1e9, 2),
        "phys_footprint_mb_after": footprint(pid),
        "load_avg_before": [round(x, 1) for x in load0], "load_avg_after": [round(x, 1) for x in load1],
        "shared_server_busy_slots_at_start": busy,
        "shared_server_busy_slots_at_end": {p: busy_slots(p) for p in SHARED.values()},
        "raw": {"c1": c1, "c4": c4},
    }
    allr = json.loads(OUT.read_text()) if OUT.exists() else {}
    prev = allr.get(target, [])
    allr[target] = (prev if isinstance(prev, list) else [prev]) + [res]  # keep every repeat; the shared Mac is noisy
    OUT.write_text(json.dumps(allr, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "raw"}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
