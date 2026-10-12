"""Writes README.md from results/*.json and report/template.html, using the same scorecard as the report.
Run after build_report.py:  .venv/bin/python report/make_readme.py"""
import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_report as b  # noqa: E402

b.body()
REPO = "https://github.com/shivanathd/sarvam-field-test"
STATE = {"lead": "▲ Sarvam leads", "level": "= Level", "behind": "▼ Sarvam behind"}
tally = {k: sum(x["state"] == k for x in b.SC) for k in ("lead", "level", "behind")}


def md_from_html(fragment):
    """Template <li> HTML -> markdown text (code spans kept)."""
    t = re.sub(r"<code>(.*?)</code>", lambda m: "`" + html.unescape(m.group(1)) + "`", fragment)
    t = re.sub(r"<[^>]+>", "", t)
    return html.unescape(t).strip()


tpl = (b.ROOT / "report" / "template.html").read_text()
quirks = re.findall(r"<li>(.*?)</li>", tpl.split('<ul class="quirks"')[1].split("</ul>")[0], re.S)
quirks_md = "\n".join(f"- {md_from_html(q)}" for q in quirks)

scorecard = "\n".join(
    f"| [{x['label']}](#{x['uc'].replace('_', '-')}) | {b.pretty(x['s'][0])} **{b.fmt(x['s'][1]['mean'], x['kind'])}** "
    f"| {b.pretty(x['r'][0])} **{b.fmt(x['r'][1]['mean'], x['kind'])}** | {STATE[x['state']]} |" for x in b.SC)

datasets = []
for uc, d in b.R.items():
    ds = d.get("dataset", {})
    datasets.append(f"| [{d.get('title', uc)}](#{uc.replace('_', '-')}) | {ds.get('n', '')} | "
                    f"{'Authored for this benchmark' if ds.get('synthetic') else 'Public'} | {ds.get('license', '')} |")

sc_i, co_i = b.intelligence()
b.cost_section()
speech_md = "\n".join(f"| {b.pretty(p['c'])} | {p['idx']:.0%} | " + (f"₹{p['cost']:,.0f}" if p['cost'] else "self-hosted") + " |"
                      for p in sorted(b.cost_section.speech, key=lambda p: -p['idx']))
spoken_md = "\n".join(f"| {b.pretty(p['c'])} | {p['idx']:.0%} | ₹{p['cost']:,.0f} |"
                       for p in sorted(b.cost_section.spoken, key=lambda p: -p['idx']))
intel = []
for c, sc in sorted(sc_i.items(), key=lambda kv: -sum(v for v, _, _ in kv[1].values()) / len(kv[1])):
    if len(sc) < 5: continue
    idx = sum(v for v, _, _ in sc.values()) / len(sc)
    cs = [co_i.get(c, {}).get(uc) for uc in sc]; cs = [x for x in cs if x is not None]
    local = "local" in c
    sub = any(n < 0.8 * mx for _, n, mx in sc.values())
    intel.append(f"| {b.pretty(c)}{' (subsets)' if sub else ''} | {idx:.0%} | "
                 f"{'own hardware' if local else ('₹{:,.0f}'.format(sum(cs) / len(cs)) if cs else '–')} |")
usemap_md = "\n".join(f"| {job} | {who} | {use} | [{int(uc[2:4])}](#{uc.replace('_', '-')}) |" for job, who, use, uc, _ in b.USEMAP)

uc_blocks = []
for i, (uc, d) in enumerate(b.R.items(), 1):
    ds = d.get("dataset", {})
    finds = "\n".join(f"- {f}" for f in d.get("findings", [])[:6])
    cav = "\n".join(f"- {c}" for c in d.get("caveats", [])[:4])
    uc_blocks.append(f"""### {uc.replace('_', '-')}

#### {i}. {d.get('title', uc)}

> {d.get('business_question', '')}

**Verdict.** {d.get('verdict', '')}

<details><summary>Findings, caveats and files</summary>

**Findings**

{finds}

**Caveats**

{cav}

- Data: {ds.get('name', '')} (n={ds.get('n', '')}; {'authored for this benchmark' if ds.get('synthetic') else 'public'}; licence {ds.get('license', '')})
- Code: [`suites/{uc}/`](suites/{uc}/) · results: [`results/{uc}.json`](results/{uc}.json) · every output: [`results/raw/{uc}.jsonl`](results/raw/{uc}.jsonl)

</details>
""")

readme = f"""<h1 align="center">Sarvam Field Test</h1>

<p align="center">
An open, reproducible benchmark of <b>Sarvam AI</b> against <b>Google Gemini</b>, <b>OpenAI</b>, <b>Anthropic Claude</b> and
<b>self-hosted open weights</b> on fifteen jobs Indian businesses and developers actually do, three of them with spoken input.<br>
Every test has known answers, so scoring is automatic and no model grades another.
</p>

<p align="center">
<a href="report/index.html"><b>Interactive report</b></a> ·
<a href="#results-at-a-glance">Results</a> ·
<a href="#what-to-use-for-which-job">What to use</a> ·
<a href="#methodology">Methodology</a> ·
<a href="#biases-and-limitations">Biases</a> ·
<a href="#reproduce">Reproduce</a>
</p>

Run on 11 October 2026 on one Apple M5 Max (128 GB) in Kochi, India. Across **{len(b.SC)}** like-for-like head-to-heads,
Sarvam **leads {tally['lead']}**, is **level on {tally['level']}** and is **behind on {tally['behind']}**.

> **In one line:** use Sarvam for Indian-language speech, voice bots and translating *into* Indian languages; for reasoning over
> text, documents and code, a price-matched Gemini, OpenAI or Claude model was more accurate in every test we ran.

The interactive report (`report/index.html`, open it in a browser) has every chart with confidence intervals, per-language
tables, worked examples and the source of every script.

---

## Results at a glance

Best Sarvam system against the best rival that ran on the **same full test set**. *Level* means the two 95% bootstrap
confidence intervals overlap or the scores are under 2% apart. Frontier models (Gemini Pro, GPT-5.5, Claude Sonnet 5.5) ran
on fixed 30-item subsets and are reported inside each suite rather than here.

| Test | Best Sarvam | Best rival | Result |
|---|---|---|---|
{scorecard}

## What to use for which job

```mermaid
flowchart TD
    Q{{What is the job?}}
    Q -->|Speech in an Indian language| S1[Saaras for transcripts<br/>Gemini 3.8 Flash if exact amounts and digits matter]
    Q -->|Real-time voice bot| S2[All-Sarvam stack<br/>Saaras + Sarvam-105B + Bulbul]
    Q -->|Text-to-speech| S3[Bulbul]
    Q -->|Translate| T{{Direction?}}
    T -->|Into an Indian language| S4[Sarvam-Translate<br/>never Mayura for numbers]
    T -->|Into English| S5[Gemini 3.8 Flash, Claude Haiku 5.5 or GPT-5.4 mini]
    Q -->|Documents: KYC, invoices, land records| S6[Gemini 3.8 Flash or Claude Sonnet 5.5 on the image]
    Q -->|Q&A, business text, clinical notes, code| S7[Gemini 3.8 Flash, GPT-5.4 mini or Claude Haiku 5.5]
    Q -->|Data cannot leave your servers| S8[Qwen3-30B for accuracy<br/>Sarvam-30B for speed and token cost]
```

- **Speech recognition in Indian languages:** Saaras v4 had the lowest average word error rate over 13 languages (0.149, against 0.21 for Gemini and 0.27 for OpenAI) and was the most accurate transcriber of spoken farmer questions. It often writes numbers as words, so for amounts and account digits on phone calls Gemini 3.8 Flash (94%) and Saaras v3 (81%) beat Saaras v4 with keyterms (56%). Add a number-words-to-digits step.
- **Spoken input in front of an app:** with the same Gemini model behind it, a Saaras front end matched Gemini's own audio input on spoken farm questions, voice-note orders and spoken payment commands, and beat OpenAI's transcriber in all three.
- **Real-time voice bot:** the all-Sarvam stack (Saaras v4, Sarvam-105B, Bulbul v4-flash) reached first audio in about 1.1 s, replied in the caller's language 18 of 20 times and cost about ₹1.42 per conversation-minute. The all-Gemini stack read numbers back more accurately but took about 6.8 s.
- **Text-to-speech:** Bulbul v3 was as intelligible as Gemini and OpenAI voices across 10 languages; Bulbul v4-flash starts about 50 ms sooner but was slightly less clear.
- **Translation:** Sarvam-Translate was best into Indian languages (8 of 10). Mayura garbled every decimal crore amount. Into English, Gemini, Claude and OpenAI were 6–12 chrF++ points ahead.
- **Documents:** clean scans were a tie (~99.5%). On bad phone photos Sarvam's legacy Vision pipeline invented text that was not on the page; the newer Document AI Extract invents less but was no more accurate; OpenAI models misread Indian-script names.
- **Chat, Q&A, clinical notes, code:** price-matched cloud models were more accurate. Sarvam-105B closes part of the gap with thinking on, at 5–46 s per answer, and sometimes returns nothing.
- **Self-hosting:** Qwen3-30B was more accurate than Sarvam-30B (84% vs 63% on business tasks); Sarvam-30B was faster and much cheaper to feed Indian text.
- **Token cost of Indian text:** Sarvam's tokenizer is cheapest (1.55x the English count), then Gemini (1.89x), OpenAI (2.10x), Claude (3.44x), Qwen3 (5.89x).

---

## Cost and intelligence

Accuracy is the average of seven text tests (policy Q&A, clinical medications, crop advice, WhatsApp orders, legal summaries,
business text, coding). Cost is measured: tokens each model actually used, thinking and repair attempts included, times
October 2026 list prices at ₹{b.USD_INR}/US$.

| Model | Average accuracy | API cost per 1,000 tasks |
|---|---|---|
{chr(10).join(intel)}

Claude Haiku 5.5 was the best value; Sarvam-105B cost about the same but was about 10 points less accurate; Gemini 3.8 Flash
bought the last 9 points for about 4x the cost. Gemini 3.8 Flash prices are promotional until 31 Dec 2026 and double after.

Speech models have no text-test score, so they get their own comparisons.

**Speech recognition:** accuracy is 1 minus the word error rate over 13 Indian languages of real FLEURS speech (Sindhi left
out); cost is list price per audio hour (Saaras v4 priced as v3; Gemini from its measured tokens).

| Speech-to-text | Word accuracy | Cost per audio hour |
|---|---|---|
{speech_md}

**Spoken tasks, end to end:** accuracy is the average of two phone-audio tests (farmer questions answered right, WhatsApp
voice notes turned into exactly the right order); cost adds transcription and the answering step, per 1,000 spoken requests.

| Pipeline | Task accuracy | Cost per 1,000 spoken requests |
|---|---|---|
{spoken_md}

Saaras v4 is the most accurate standalone transcriber, but sending the audio straight to Gemini 3.8 Flash was slightly more
accurate and cheaper end to end. All six pipelines cost ₹114–155 per 1,000 requests, so accuracy should decide.

## Use-case map

| Job | Who needs it | Recommended | Evidence |
|---|---|---|---|
{usemap_md}

---

## Methodology

### How it ran

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/pipeline-dark.webp">
  <img alt="Pipeline: authored and public test data feed 15 suites run by 6 agents under a shared brief; identical prompts go to the Sarvam API, cloud rivals and self-hosted models; known-answer scoring with bootstrap confidence intervals writes raw outputs and result files, which build the report." src="docs/pipeline-light.webp">
</picture>

Six parallel agents built and ran the suites, all sharing one library ([`common/bench.py`](common/bench.py)) for API clients,
scoring and result files. Every model output is kept, so every number can be audited and every rerun is resumable.

### How one test item is scored

```mermaid
sequenceDiagram
    autonumber
    participant D as Test item (input + gold answer)
    participant S as Suite run.py
    participant M as System under test
    participant X as Sandbox (code only)
    participant C as Scorer
    D->>S: same input for every system
    S->>M: same prompt, temperature 0, thinking on/off as configured
    M-->>S: output (text, JSON, audio, tool call)
    opt coding tasks
        S->>X: run model code, no network, no home folder
        X-->>S: hidden unit-test results
    end
    S->>C: output + gold answer
    C-->>S: score (exact match, fact recall, WER, chrF++ ...)
    S->>S: append to results/raw/*.jsonl, bootstrap 95% CI per system
```

### Systems tested

| Vendor | Systems | Access | Settings |
|---|---|---|---|
| Sarvam | Sarvam-105B, Sarvam-105B conversations, Saaras v3/v4 (STT), Bulbul v3/v4-flash (TTS), Sarvam-Translate, Mayura, Transliterate, Sarvam Vision / Document AI | Sarvam API | 105B with `reasoning_effort: null` (thinking off) and `medium` (on) |
| Sarvam (open weights) | Sarvam-30B, official Q4_K_M GGUF | llama.cpp on the test Mac | thinking off via an empty `<think></think>` prefill |
| Google | Gemini 3.8 Flash (and Flash TTS), Gemini Pro, Gemini Embedding 2 | Gemini API | Flash thinking off, on where it mattered |
| OpenAI | GPT-5.4 mini, GPT-5.5, gpt-4o-transcribe, whisper-1, gpt-4o-mini-tts | OpenAI API | `reasoning_effort` none / medium |
| Anthropic | Claude Haiku 5.5, Claude Sonnet 5.5 | OpenRouter | reasoning off / low (Sonnet cannot turn it off) |
| Open weights | Qwen3-30B-A3B Q4_K_M, Whisper large-v3-turbo | llama.cpp / transformers on the test Mac | `/no_think` |

Price-matched tier (Sarvam-105B, Gemini 3.8 Flash, GPT-5.4 mini, Claude Haiku 5.5) ran on every item. The frontier tier
(Gemini Pro, GPT-5.5, Claude Sonnet 5.5) ran on fixed subsets to show the ceiling.

### Test data

| Use case | Items | Source | Licence |
|---|---|---|---|
{chr(10).join(datasets)}

Authored sets use fake people and IDs marked SAMPLE (valid checksum formats where a test needs them). Public data is FLEURS /
FLORES (CC-BY 4.0).

### Scoring and statistics

- **Known answers only.** Every item has a gold answer (number, code, label, fact list, reference text, unit tests) and is scored by code. No LLM-as-judge.
- **Speech and dubbing quality** use references (FLEURS) or round-trip transcription by two or three different vendors' transcribers, reported separately so a judge's home advantage is visible.
- **Uncertainty:** 95% bootstrap confidence intervals (2,000 resamples over items) on every score.
- **Head-to-head rule:** *level* if the intervals overlap or the gap is under 2%; otherwise lead or behind. Overlapping intervals is a conservative test: some *level* rows would separate under a paired test.
- **Like-for-like samples:** systems that ran on fewer than 80% of a metric's items are excluded from the scorecard and labelled with their sample size in charts.

### Fairness controls

- Identical inputs and prompts for every system; no per-vendor prompt tuning.
- Test audio was synthesised with Gemini TTS and macOS voices, **never with Sarvam's Bulbul**, so Saaras is not transcribing its sibling's voice.
- In voice-input variants, every transcript goes to the **same** downstream model, so differences come only from speech recognition.
- Keyterm lists for Saaras v4 are fixed and generic (product and brand terms), never the per-item answers.
- Thinking mode on and off reported separately; empty replies caused by the token budget are reported and also rerun with a larger budget.
- Model-written code runs only inside a macOS `sandbox-exec` profile: no network, no home-folder reads, no writes outside a temp folder, 10 s timeout.

---

## Biases and limitations

We tried to make this fair. These are the ways it may still not be, so you can weigh the results yourself.

- **Who built it.** The test sets, prompts, scorers and this README were written by AI agents running Anthropic's Claude, and Claude models are also contestants. We limited this by scoring only against known answers, but test items written by one model may suit that model family's style. Claude Haiku and Sonnet did not top the scorecard, which is weak evidence the effect is small.
- **What the requester expected.** The benchmark was commissioned with the hypothesis that Sarvam would win. We fixed the scoring rules before the runs and kept every output; where Sarvam loses, the outputs are in `results/raw/` to check.
- **Synthetic data.** Most test sets were written for this benchmark and **no native speaker reviewed them**. Phrasing may be unnatural in places, and gold answers in Indian languages could contain errors. Treat absolute scores as indicative; the comparisons are the result.
- **Synthetic speech.** Code-mixed calls, consultations and voice-input tests use text-to-speech, which is cleaner than real calls (no crosstalk, accents within one voice, no real phone codecs beyond our 8 kHz simulation). Gemini TTS voices may favour Gemini's own speech recognition; the voice suite checks this on macOS-voiced clips separately.
- **Geography and latency.** Runs were made from India. Sarvam's servers are in India; the other vendors' are likely further away, which favours Sarvam on latency. Accuracy is unaffected.
- **Model versions move.** Our first pass used Saaras v3 and Bulbul v3; Saaras v4 (25 Sep 2026), Bulbul v4-flash and Sarvam's Document AI Extract were added after we noticed them. Versions were checked against each API's model list on 11 October 2026. Rerun before relying on these numbers.
- **Self-hosted settings.** Only the official Q4_K_M quantisation of Sarvam-30B exists; we compared Qwen3-30B at the same quantisation. The test Mac was shared and often heavily loaded (load average up to 265), so local speed numbers are floors.
- **Thinking and temperature.** Temperature 0 throughout, except Sarvam-105B thinking runs at Sarvam's recommended 0.5. Gemini thinking ran at temperature 0 rather than Google's recommended 1.0, which may understate it slightly.
- **Scoring decisions made after seeing outputs.** Two were made and are disclosed in their suites: accepting native-script variants of four Bengali surnames (uc08), and stem/synonym and dose-format tolerance in clinical notes (uc05), applied to every system.
- **Saturation.** Several tests (business text, coding, legal translation) are near the ceiling for strong models, so they separate weak systems from strong ones but cannot rank the strongest.
- **Small subsets.** Frontier checks use 30-item subsets; local models in some suites ran on 8–50-item subsets because they were slow. Those numbers are indicative.

---

## How to read the metrics

| Metric | Meaning | Better |
|---|---|---|
| Accuracy / exact match | Share of items fully right against the gold answer | Higher |
| Fact recall | Share of gold facts present in a summary or note | Higher |
| Entity accuracy / preservation | Numbers, amounts, dates, section numbers, names carried over exactly | Higher |
| WER / CER | Word / character error rate of a transcript; 0.20 = one word in five wrong | Lower |
| chrF++ | Character and word n-gram overlap with a human translation, 0–100 | Higher |
| pass@1 / pass@3 | Coding tasks passing hidden unit tests first try / within three tries with failures fed back | Higher |
| Token tax | Tokens for a sentence in an Indian language ÷ tokens for the same English sentence | Lower |
| 95% CI | Bootstrap interval over items; overlapping intervals mean no clear winner | Narrower |

Every `results/<suite>.json` holds `metrics` (per-system `mean`, `lo`, `hi`, `n`), `per_language`, `speed` (p50/p95 ms),
`usage` (tokens, audio seconds, pages, characters), `examples`, `findings`, `caveats` and `verdict`.
`results/raw/<suite>.jsonl` has every model output with its score.

---

## Results by use case

{chr(10).join(uc_blocks)}

---

## API quirks we hit

{quirks_md}

---

## Cost of a full run

About ₹1,200 of Sarvam credit at list prices, a few US dollars of OpenAI usage, about US$3.75 on OpenRouter for Claude, and a
few million Gemini tokens. List prices used (October 2026): speech-to-text ₹30 per audio hour (₹45 with speaker labels),
Sarvam-105B ₹15 / ₹60 per million input / output tokens, Bulbul ₹3 per 1,000 characters, Document AI Extract ₹1 per page.
Sarvam's translation APIs were the largest single cost; Sarvam-105B translated the same legal text as faithfully for a
fraction of the price.

## Reproduce

```bash
git clone {REPO} && cd sarvam-field-test
cp .env.example .env            # SARVAM_API_KEY, GOOGLE_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Rebuild the report and this README from the committed results (no API keys needed)
.venv/bin/python report/build_report.py && .venv/bin/python report/make_readme.py

# Re-run one suite (resumable: only missing items call an API; delete results/raw/<suite>.jsonl to start fresh)
.venv/bin/python suites/uc08_quick_commerce/run.py api

# Optional: self-hosted models (downloads ~38 GB of GGUF files into gguf/; needs llama.cpp's llama-server)
LLAMA_SERVER=/path/to/llama-server scripts/serve_local.sh
```

Each suite folder has its own README with exact steps. Audio, FLEURS recordings and tokenizer files are not committed; the
suites regenerate or download them.

## Repository layout

```
common/bench.py            shared clients (Sarvam, Gemini, OpenAI, OpenRouter, local llama.cpp), scoring helpers, result writer
suites/<suite>/            run.py (resumable), README.md, data builders, scorers
data/<suite>/              test inputs (authored text, document images, gold answers)
results/<suite>.json       scored results;  results/raw/<suite>.jsonl  every output
report/                    build_report.py, template.html, index.html (the report), make_readme.py
docs/                      README images
logs/                      run logs
scripts/serve_local.sh     starts self-hosted Sarvam-30B (:8101) and Qwen3-30B (:8102)
scripts/export_public.sh   makes a publishable copy without secrets or local paths
```

## Licence and citation

Code: MIT. Authored test data and results: CC-BY 4.0. FLEURS / FLORES-derived text: CC-BY 4.0 (Google). Model outputs are
included for auditability. If you use this benchmark, please link to {REPO}.
"""
(b.ROOT / "README.md").write_text(readme)
print("README.md", len(readme) // 1024, "KB", tally)
