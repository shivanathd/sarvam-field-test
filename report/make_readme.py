"""Writes README.md from results/*.json, using the same scorecard as the report. Run after build_report.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_report as b  # noqa: E402

b.body()
STATE = {"lead": "Sarvam leads", "level": "Level", "behind": "Sarvam behind"}
rows = "\n".join(
    f"| [{x['label']}](#{x['uc'].replace('_', '-')}) | {b.pretty(x['s'][0])} **{b.fmt(x['s'][1]['mean'], x['kind'])}** "
    f"| {b.pretty(x['r'][0])} **{b.fmt(x['r'][1]['mean'], x['kind'])}** | {STATE[x['state']]} |" for x in b.SC)
tally = {k: sum(x["state"] == k for x in b.SC) for k in STATE}

uc_blocks = []
for i, (uc, d) in enumerate(b.R.items(), 1):
    ds = d.get("dataset", {})
    finds = "\n".join(f"- {f}" for f in d.get("findings", [])[:6])
    uc_blocks.append(f"""### {uc.replace('_', '-')}

**{i}. {d.get('title', uc)}.** {d.get('business_question', '')}

- Data: {ds.get('name', '')} (n={ds.get('n', '')}; {'synthetic, written for this benchmark' if ds.get('synthetic') else 'public'}; licence {ds.get('license', '')})
- Code: [`suites/{uc}/`](suites/{uc}/) · results: [`results/{uc}.json`](results/{uc}.json) · every output: `results/raw/{uc}.jsonl`

**Verdict.** {d.get('verdict', '')}

{finds}
""")

readme = f"""# Sarvam Field Test

An open, reproducible benchmark of **Sarvam AI**'s speech, translation, document and chat models against **Google Gemini**,
**OpenAI**, **Anthropic Claude** and **self-hosted open weights** (Sarvam-30B and Qwen3-30B on llama.cpp), on twelve jobs
Indian businesses and developers actually do. Every test has known answers, so scoring is automatic and no model grades another.

**Read the full interactive report:** [`report/index.html`](report/index.html) (open it in a browser; it has every chart, the
per-language tables, API quirks, costs, and the source of every script).

Run on 11 October 2026 on one Apple M5 Max (128 GB). Sarvam leads **{tally['lead']}**, is level on **{tally['level']}** and behind on
**{tally['behind']}** of {len(b.SC)} head-to-heads.

## Results at a glance

Best Sarvam system against the best rival that ran on the same full test set. **Level** means the 95% bootstrap confidence
intervals overlap or the scores are under 2% apart. Frontier models (Gemini Pro, GPT-5.5, Claude Sonnet 5.5) ran on fixed
30-item subsets and are reported inside each suite, not here.

| Test | Best Sarvam | Best rival | Result |
|---|---|---|---|
{rows}

## What to use for which job

- **Speech recognition in Indian languages:** Saaras v3 (lowest word error rate in 12 of 13 languages, about 4x faster). For calls where amounts and account digits matter, Gemini 3.8 Flash captured them exactly more often, because Saaras often writes numbers as words.
- **Real-time voice bot:** the all-Sarvam stack (Saaras, Sarvam-105B, Bulbul): about 1.5 s to first audio, replies in the caller's language, ₹1.56 per conversation-minute.
- **Text-to-speech:** Bulbul v3, as intelligible as Gemini and OpenAI voices and the fastest to start.
- **Translating into Indian languages:** Sarvam-Translate. Avoid Mayura for text with numbers (it garbled every decimal crore amount). **Into English:** Gemini 3.8 Flash, Claude Haiku 5.5 or GPT-5.4 mini.
- **KYC, invoices, land records:** Gemini 3.8 Flash or Claude Sonnet 5.5 on the image. On poor photos Sarvam Vision invented text that was not on the page.
- **Chat, Q&A, business text, clinical notes, coding:** a price-matched Gemini, OpenAI or Claude model. Sarvam-105B gets close only with thinking on, which is slow and sometimes returns nothing.
- **Data must stay on your servers:** Qwen3-30B over Sarvam-30B for accuracy; Sarvam-30B is faster and its tokenizer is much cheaper for Indian text, but it ignores format instructions.
- **Token cost of Indian text:** Sarvam's tokenizer is cheapest (1.55x the English count on average), then Gemini (1.89x), OpenAI (2.10x), Claude (3.44x), Qwen3 (5.89x).

## How to read the metrics

- **Accuracy / exact match / recall** (higher is better): share of items fully right against the gold answer, checked by code.
- **WER / CER** (lower is better): word or character error rate of a transcript against the reference; 0.20 means one word in five is wrong.
- **chrF++** (higher is better, 0–100): character and word n-gram overlap between a translation and a human reference.
- **Entity accuracy / entity preservation**: numbers, amounts, dates, section numbers and names carried over exactly.
- **pass@1 / pass@3**: share of coding tasks whose hidden unit tests pass on the first try, or within three tries with failing tests fed back.
- **95% CI**: bootstrap confidence interval over items. When two systems' intervals overlap, treat them as level.
- **Token tax**: tokens for a sentence in an Indian language divided by tokens for the same sentence in English.

Every results file (`results/<suite>.json`) holds: `metrics` (each with per-system mean, lo, hi, n), `per_language`,
`speed` (p50/p95 ms), `usage` (tokens, audio seconds, pages, characters), `examples`, `findings`, `caveats` and `verdict`.
`results/raw/<suite>.jsonl` has every model output with its score, so any number can be audited.

## Reproduce

```bash
git clone https://github.com/shivanathd/sarvam-field-test && cd sarvam-field-test
cp .env.example .env            # SARVAM_API_KEY, GOOGLE_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Rebuild the report and README from the committed results (no API keys needed)
.venv/bin/python report/build_report.py && .venv/bin/python report/make_readme.py

# Re-run a suite (resumable: only missing items call an API; delete results/raw/<suite>.jsonl to start fresh)
.venv/bin/python suites/uc08_quick_commerce/run.py api

# Optional: self-hosted models (downloads ~38 GB of GGUF files into gguf/, needs llama.cpp's llama-server)
LLAMA_SERVER=/path/to/llama-server scripts/serve_local.sh
```

Each suite folder has its own README with exact steps. Audio (synthesised test calls and dubbing output), FLEURS recordings
and tokenizer files are not committed; the suites regenerate or download them. Synthesising the test audio uses Gemini TTS
and macOS `say` voices. Expect roughly ₹1,200 of Sarvam credit, a few US dollars of OpenAI, US$4 of OpenRouter and a few million
Gemini tokens for a full run at the committed sizes.

## Repository layout

```
common/bench.py          shared clients (Sarvam, Gemini, OpenAI, OpenRouter, local llama.cpp), scoring helpers, result writer
suites/<suite>/          run.py (resumable), README.md, data builders, scorers
data/<suite>/            test inputs (authored text, document images, gold answers)
results/<suite>.json     scored results; results/raw/<suite>.jsonl every output
report/                  build_report.py, template.html, index.html (the report), make_readme.py
logs/                    run logs
scripts/serve_local.sh   starts self-hosted Sarvam-30B (:8101) and Qwen3-30B (:8102)
```

## Method and caveats

- Test sets for orders, KYC, invoices, policies, consultations, legal passages, farming and business text were written for
  this benchmark with fake people and clearly marked sample IDs. No native speaker reviewed them; treat absolute scores as
  indicative and the comparisons as the result.
- Public data: FLEURS / FLORES sentences (CC-BY 4.0) for speech recognition, translation and the token tax.
- Sarvam-105B ran with thinking off (`reasoning_effort: null`) and on. Sarvam-30B is no longer offered on Sarvam's API, so it
  was self-hosted from the official Q4_K_M GGUF; its thinking can only be disabled by pre-filling an empty think block.
- Model-written code ran only inside a macOS `sandbox-exec` profile with no network, no home-folder reads and no writes outside a temp folder.
- Speed figures were measured on a shared, often heavily loaded Mac; treat them as floors.
- Prices are list prices in October 2026.

## Use cases

{chr(10).join(uc_blocks)}

## Licence

Code: MIT. Authored test data and results: CC-BY 4.0. FLEURS/FLORES-derived text: CC-BY 4.0 (Google). Model outputs are
included for auditability.
"""
(b.ROOT / "README.md").write_text(readme)
print("README.md", len(readme) // 1024, "KB", tally)
