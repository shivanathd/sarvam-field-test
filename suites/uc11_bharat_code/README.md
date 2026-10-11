# UC11 Bharat Code: coding agents for Indian business logic, prompted in Indian languages

**Question.** An Indian developer asks an AI model to write business logic, in their own language: "GSTIN ka check
character nikalne wala function likho", or the same in Tamil. Does the model write correct code? Does it fix the code
when the tests fail? Does it do as well as when the task is written in English?

**Second question (sub-test).** Can the model drive a payments-app tool schema (recharge, pay_bill, check_balance,
book_cylinder, transfer_upi) from voice-assistant commands like "mera 299 wala recharge kar do", "கரண்ட் பில் கட்டுங்க"
or "dipak@paytm-এ দেড় হাজার টাকা পাঠাও"?

## Why this test is realistic

- The 40 tasks are logic Indian fintech, GST, HR and logistics software has to get right: Verhoeff checks for
  Aadhaar-format numbers, PAN holder type, GSTIN check characters, IFSC, lakh/crore digit grouping, amounts in words
  (English for cheques, Hindi), financial year and quarter, CGST/SGST vs IGST, an income-tax slab calculation with the
  rules given in the prompt, EMI, UPI IDs and deep links, Indic digits, PIN-to-state, IRCTC booking status, IST to UTC,
  Luhn plus RuPay prefixes, mobile normalisation, vehicle plates including BH series, GST invoices with round-off,
  Aadhaar masking for data protection, "1.5 crore"/"3.25L" parsing, HRA, gratuity, EPF, FD maturity, CIN, bank
  holidays (2nd and 4th Saturdays), compact "1.25 Cr" formatting, invoice numbering per FY, MSME class, advance tax.
- Every rule is stated in the prompt. The test measures whether the model follows a precise Indian spec. It does not
  test whether the model remembers this year's tax law.
- Scoring uses hidden unit tests (8-14 asserts per task, including edge cases: exact halves in paise rounding, FY
  boundaries, 12 AM/PM, `9999999 -> "100 L"`, Bengali/Arabic digits). Each reference solution passes all of its own
  tests. No AI judge is involved.
- Each prompt exists in English, Hindi, Tamil and Hinglish (romanised code-mixed). Identifiers, signatures and literals
  are verbatim in every language. The system prompt stays in English, as it does in real coding tools.
- **Repair mode** works like a coding agent. When a test fails, the model sees up to 5 failing asserts (call, expected,
  got) or the traceback, truncated, and gets up to 3 attempts. This reveals the expected values for the asserts it is
  shown, which is what pytest output does too. So pass@3 measures "can it converge with test feedback". It is not a
  blind score.

## Data

- `tasks.py`: specs, signatures, reference solutions and tests (English). `spec_hi.py`, `spec_ta.py` and
  `spec_hinglish.py` hold the hand-written translations.
- Translation QA (`backtranslate.py`): Gemini back-translates each translation into English without seeing the
  original. A second call lists any difference in meaning that would change the correct code. The first pass flagged
  3 ambiguities ("remove whitespace" vs "strip"). They were fixed and the re-check flagged 0. Results are in
  `data/uc11_bharat_code/backtranslation.json`. `prompts.py` also checks that every quoted literal and number in the
  English spec appears verbatim in each translation.
- `tools.py`: 50 commands with gold tool + arguments. 30 base commands (8 Hindi, 8 Hinglish, 7 Tamil, 7 Bengali)
  include spoken Indian amounts ("ढाई हज़ार" = 2500, "sava sau" = 125, "দেড় হাজার" = 1500), Bengali digits and colloquial
  terms ("கரண்ட் பில்" = electricity bill). 20 harder commands were added after every API system scored 100% on the base
  set. They cover fractional amounts ("पौने दो हज़ार" = 1750, "paune teen sau" = 275, "সাড়ে তিনশো" = 350), regional or
  brand terms ("ஈபி பில்" = electricity, "Tata Play" = DTH), postpaid bills and "1,250"-style grouping.
- All IDs, numbers and UPI handles are synthetic. Licence: CC-BY-4.0.

## Safety: the sandbox

Model-written code only runs through `sandbox.py`. It uses macOS `sandbox-exec` with a profile that denies all
network access, denies file writes outside a fresh temp dir, and denies reads under `$HOME` except the Python stdlib
(so `.env` keys cannot be read). The code runs under `python -I` with a 10 s timeout and a minimal environment. Run
`python suites/uc11_bharat_code/sandbox.py` to prove that a network call, a socket, writes to `~` and `/tmp`, a
subprocess write, reading `.env`, and an infinite loop all fail, while normal computation and writes inside the temp
dir work. `python suites/uc11_bharat_code/testrun.py` checks that all 40 reference solutions pass their tests inside
the sandbox.

## How to run

```bash
.venv/bin/python suites/uc11_bharat_code/sandbox.py        # sandbox self-test
.venv/bin/python suites/uc11_bharat_code/testrun.py        # references pass their tests
.venv/bin/python suites/uc11_bharat_code/run.py            # API systems, then local (waits for llama-servers), then report
.venv/bin/python suites/uc11_bharat_code/run.py code --systems sarvam-105b
.venv/bin/python suites/uc11_bharat_code/run.py tools --systems gemini-3.8-flash
.venv/bin/python suites/uc11_bharat_code/report.py         # recompute results/uc11_bharat_code.json from raw
```

Runs are resumable. A raw record is keyed by (kind, item, system), and finished items are never re-sent.
Concurrency: 3 Sarvam requests, 4 Gemini requests, and 2 slots per shared llama-server.

**Systems.** `sarvam-105b` (thinking off, temperature 0); `sarvam-105b-think` (reasoning_effort medium, temperature 0.5,
following Sarvam's docs for thinking mode); ablations `sarvam-105b-think-t0` (thinking at temperature 0) and
`sarvam-105b-t0.7` (thinking off, temperature 0.7, to test whether sampling unsticks the repair loop);
`gemini-3.8-flash` with thinking off and on (temperature 0). Thinking modes are capped at 16k output tokens.
Cloud comparators (addendum): price-matched `gpt-5.4-mini` and `claude-haiku-5.5` (OpenRouter), each with thinking
off and on, on the full set with repair; frontier `gemini-pro-latest-think` (temperature 1.0), `gpt-5.5-think` and
`claude-sonnet-5.5-think` on **task ids 1-30 × 4 languages**. OpenAI thinking-mode tool calls go through `/v1/responses`,
because chat completions rejects tools combined with `reasoning_effort`, with `strict: false`.
Local: `sarvam-30b-local` and `qwen3-30b-local` (official Q4_K_M GGUFs on llama-server `--jinja`) run **single-shot on
the 20 odd-numbered tasks × 4 languages**, with a 1500-token cap. The shared Mac ran them at ~6-20 tok/s per slot, so
the full repair protocol would have taken over a day. Sarvam-30B's reasoning cannot be switched off with the template's
`enable_thinking` flag or `reasoning_effort`; prefilling an empty `<think></think>` assistant turn does switch it off
(`run.local_chat`).

## Reading the metrics

- **pass@1**: share of the 160 task-language items solved on the first try, with a 95% bootstrap CI.
- **pass@3 with repair**: share solved within 3 attempts when the model is shown the failing tests. `repair_curve`
  gives the cumulative share after 1, 2 and 3 attempts.
- **language penalty**: English pass rate minus the pass rate in another language. It is paired by task (same 40
  tasks), and the CI comes from resampling tasks. A positive value means the model is worse when you write in that
  language. If a model scores near 100% in English, there is no room left to measure a penalty.
- **tokens / wall time per solved item**: summed over all attempts of solved items. For Sarvam, completion tokens
  already include reasoning tokens. For Gemini, thinking tokens are added separately.
- **tool calling exact**: right tool AND exact arguments after light normalisation (case, digits in any Indic script,
  10-digit phone suffix, and default `quantity=1` treated as absent). An argument the user never mentioned counts as
  wrong.
- `est_cost_inr_list_price` (Sarvam only) uses ₹15 per 1M input tokens and ₹60 per 1M output tokens.
