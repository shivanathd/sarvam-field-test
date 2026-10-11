# UC09 Courts and legal: translating and summarising judgments without losing facts

**Business question.** Legal-aid groups, law firms, court e-services and legal-tech apps want to give litigants
orders in their own language. A translation or summary that drops or changes an amount, a deadline, a section
number or a party name is worse than none. Which system keeps the facts intact?

## Why the test is realistic
- **The documents a litigant actually receives:**
  - s.138 NI Act cheque-bounce conviction, and an appeal allowed on limitation (s.142).
  - Regular bail with conditions, and anticipatory bail rejected.
  - Consumer commission orders: a builder refund, and an insurance repudiation appeal.
  - Rent-suit eviction with arrears and mesne profits.
  - A land partition decree.
  - An RTI fee reply, and an RTI penalty order (s.20(1), ₹250 per day, capped at ₹25,000).
  - Motor accident tribunal awards for a death (with multiplier) and an injury.
- **Each 550–700 character passage packs in 12–17 checkable facts:** case and FIR numbers, sections and Act years,
  dates, amounts in Indian notation (₹4,75,000 / ₹12.5 lakh / ₹3.2 crore), interest rates, deadlines in days,
  and party and place names.
- **Derived amounts are internally consistent,** so a careless model can't hide behind an inconsistent source.
  The deposit is 20% of the cheque, the RTI fee is ₹2 × pages, the penalty is min(₹250 × days, ₹25,000), and the
  MACT award follows the multiplier.
- **No AI judge.** Every fact is a typed entity, checked by deterministic code (`score.py`).

## Data (synthetic)
`make_data.py` fills 12 hand-written templates with invented parties, courts, places and numbers to make 40
passages, written to `data/uc09_legal/passages.jsonl`.
- **566 entities**, plus 6 `key_facts` per passage for the summary task.
- **Passages stay at or under 1,000 characters,** which is mayura:v1's input limit, so each passage is one API call.
- **No real case or person** is reproduced. Licence CC0.

## Tasks and systems
- **Task A, translation (English to target language).**
  - Hindi and Tamil: all 40 passages. Marathi and Bengali: the first 20. That gives 120 items per system.
  - Systems: `sarvam-translate:v1`, `mayura:v1` (both via `/translate`, default formal mode and international
    numerals), `sarvam-105b` (think off) and `gemini-3.8-flash`.
  - The two LLMs get one instruction to keep numbers, dates, amounts and sections exactly and to write names in
    the target script. The translate APIs take no instructions.
- **Task B, plain-language summary for a litigant.**
  - All 40 passages, into Hindi and Tamil: 80 items per system, each scored on its 6 key facts.
  - Systems: `sarvam-105b` with think off and with think on (reasoning_effort medium, max_tokens 6000), and
    `gemini-3.8-flash`.
  - Local `sarvam-30b-local` and `qwen3-30b-local` run on the first 5 passages per language only (sarvam-30b also has passages 6-10 in Hindi). Each summary
    took 4-8 minutes on the shared Mac.

- **Added cloud comparators.**
  - Price-matched tier: `openai:gpt-5.4-mini` and `or:anthropic/claude-haiku-5.5`, run on the full sets of both
    tasks.
  - Frontier tier, think on: `gemini-pro-latest`, `openai:gpt-5.5` and `or:anthropic/claude-sonnet-5.5`, on a fixed
    30 items per task (the first 15 passages in Hindi and Tamil).
  - Like-for-like metrics on that subset are reported for every system.
- **Think-on rerun.** The 16 think-on summaries that came back empty at max_tokens 6000 were rerun at 16000
  (`sarvam-105b-think-16k`). Both versions are reported.

## Run
```
.venv/bin/python suites/uc09_legal/make_data.py   # deterministic (seed 909)
.venv/bin/python suites/uc09_legal/score.py       # scorer self-test
.venv/bin/python suites/uc09_legal/run.py         # resumable; skips (task, id, lang, system) already in raw
```

## Metrics (all in `score.py`)
- **Entity preservation rate (Task A)** and **key-fact recall (Task B).** The share of source facts found in the
  output.
  - Numbers: Indic digits are folded to ASCII, and a number must stand alone.
  - Amounts: compared by value, so ₹12,50,000 equals "12.5 लाख" and "12 லட்சத்து 50 ஆயிரம்".
  - Dates: the day, the month (as a name in any of the five languages, or numeric) and the year must sit near
    each other. This accepts "2021 ஜனவரி 30".
  - Names: transliteration-tolerant consonant-skeleton matching, so Subrata Ghosh matches সুব্রত ঘোষ and சுப்ரதா கோஷ்,
    and Rajendra does not match ராஜசேகர.
  - Self-tests are in `score.py`. Known blind spots are listed in its docstring.
- **Facts dropped or altered per passage.** The count of source facts not found.
- **Distinct unsupported numbers.** Numbers in the output that the source does not contain: hallucinated or
  altered values, and also values the model computed itself, such as deadline dates and totals.
- **Output in target language.** The dominant script is the target script and at least 50% of letters are in it.
  An empty reply fails.
- **Latency** p50 / p95, and **usage:** translate characters, LLM tokens and reasoning tokens.

## What is *not* measured
Fluency, legal register, and meaning errors that keep the entities intact (for example swapping who is the
complainant and who is the accused) are not measured. Spot checks found such errors. See `examples` in the
result file.
