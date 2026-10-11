# UC10: Self-hosting Sarvam-30B for business text

**Question:** can an Indian business run Sarvam-30B on its own hardware instead of calling a cloud API? What does it
give up in accuracy and speed?

Sarvam deprecated Sarvam-30B on its API (calls are redirected to "use sarvam-105b"). The open weights, with an
official Q4_K_M GGUF, are now the only way to use it. A business choosing that route compares it with the
same-class open model, Qwen3-30B-A3B (also MoE, ~3B active parameters, also Q4_K_M), and with the cloud options.

## Tasks (150 items, all scored against known answers; no AI judge)
Five back-office tasks. Each has five scenarios, and each scenario is hand-written in Hindi, Marathi, Tamil, Telugu,
Bengali and Hinglish (Hindi typed in Latin letters).

| Task | Input | Model must produce | Scored on |
|---|---|---|---|
| triage | support ticket | JSON intent (8-way fixed list), urgency 1-3 (rule given), language | exact match on each field |
| crm | complaint | 2-3 sentence English CRM note | contains the order id, the amount, the date as YYYY-MM-DD, the issue (keyword regex); Latin script |
| reply | angry or demanding customer message | reply in the customer's language under a policy: state the N-day return window in digits, no compensation or money amount, no other dates or periods | right script (and Hindi vs Marathi vs Hinglish markers), N present, no number other than N and the order id |
| escalate | customer message | JSON sentiment + escalate flag (rule given) | exact match |
| extract | supplier invoice or email, with distractors (invoice date, previous bill, phone number) | JSON invoice_no, GSTIN, total (incl. GST), due date | exact match per field |

The main metric for each task is `<task>_all_correct`: every check on the item passes. `overall_all_correct` is the
same measure averaged over all 150 items.

**Why it is realistic.** These are the texts an Indian D2C or marketplace support desk actually gets: UPI money
debited but the order shows failed, wrong-colour saree, empty box, consumer-court threats, GST-deadline lockouts.
Dates use native month names, amounts use Indian digit grouping (₹1,33,222), and invoices carry checksum-valid
GSTINs (random and marked SAMPLE).

## Systems
- `sarvam-30b-local-nothink` / `-think`: official Sarvam-30B Q4_K_M GGUF, llama.cpp b11541, `-ngl 99 -c 32768 -np 4`, :8101
- `qwen3-30b-local-nothink` / `-think`: Qwen3-30B-A3B Q4_K_M, same settings, :8102
- `sarvam-105b` (reasoning off), `sarvam-105b-think` (reasoning_effort medium): Sarvam API
- `gemini-3.8-flash` (thinking off)
- Price-matched cloud tier, full set, thinking off: `openai:gpt-5.4-mini`, `or:anthropic/claude-haiku-5.5`
- Frontier tier, thinking on, fixed 30-item `SUBSET` defined in run.py (per task, one item per language): `gemini-pro-latest-think`, `openai:gpt-5.5-think`, `or:anthropic/claude-sonnet-5.5-think`. Compare these with `overall_all_correct_subset30`.

**Thinking control for local Sarvam-30B.** The chat template turns `enable_thinking=false` into a `<|nothink|>`
marker, but the GGUF still reasons for about 1k tokens with it. Prefilling an empty `<think></think>` assistant
turn does switch reasoning off. `localcall.py` does this. `common.bench.chat()` cannot, so it always thinks.

## Speed and hardware (`speed.py`)
The test machine is an Apple M5 Max with 128 GB, shared with other jobs (load average is recorded). Thinking is off,
the prompt is a fixed 22-ticket Indic business prompt (1,014 Sarvam tokens, 2,428 Qwen3 tokens), and each request
generates 256 tokens (`ignore_eos`, no prompt cache). For each server:
- prompt-processing and generation tok/s (llama-server timings)
- client-side time to first token
- aggregate generation tok/s at concurrency 1 and 4
- peak RSS of the server process, which includes the memory-mapped weights
- macOS phys_footprint, which excludes clean mapped weights

Each measurement runs on its own short-lived server, started for that one model, so requests from other suites on
the shared :8101 and :8102 servers do not queue ahead of it. It still shares the GPU and CPU with them; busy slots on
the shared servers are recorded. Results are appended per repeat to `data/uc10_selfhost_business/speed.json`.
```
LS=~/embed-bench/llamacpp/llama-b11541/llama-server
# GPU (:8112), one model at a time
$LS -m gguf/<model>.gguf --jinja -ngl 99 -c 32768 -np 4 --port 8112 &
.venv/bin/python suites/uc10_selfhost_business/speed.py sarvam-gpu      # or qwen-gpu; stop the server afterwards
# CPU-only (:8111), emulating a GPU-less office box
$LS -m gguf/<model>.gguf --jinja -ngl 0 -dev none --no-op-offload -c 32768 -np 4 --port 8111 &
.venv/bin/python suites/uc10_selfhost_business/speed.py sarvam-cpu      # or qwen-cpu; 64 generated tokens, fewer repeats
```

## Run
```
.venv/bin/python suites/uc10_selfhost_business/make_data.py      # regenerates data/uc10_selfhost_business/items.json (deterministic)
.venv/bin/python suites/uc10_selfhost_business/run.py            # all systems; resumable, skips done items
.venv/bin/python suites/uc10_selfhost_business/speed.py sarvam-gpu   # and qwen-gpu, sarvam-cpu, qwen-cpu
.venv/bin/python suites/uc10_selfhost_business/run.py --summarize
```
Raw outputs go to `results/raw/uc10_selfhost_business.jsonl`. Calls that fail with an API error (for example a 402
"no credits") are not counted as done, so they are retried on the next run and never scored as wrong answers.

## Reading the results
`metrics` holds each check with a 95% bootstrap CI, `per_language` holds the all-correct rate by language and by
task, and `hardware` holds the `speed.py` measurements. Per-item latency (`speed`) for the local models was measured
on a busy shared machine with up to 8 queued requests. Use `hardware` for throughput, not `speed`.
