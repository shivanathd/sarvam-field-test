# UC12: The Indic token tax

**Question:** how many tokens does each model charge for the same sentence in each Indian language?

Every LLM bill, every self-hosted generation second and every context window is counted in tokens. A tokenizer
built mostly for English and Chinese breaks Odia or Telugu into many small byte pieces, so the same message costs
several times more. That multiplier is the token tax. This suite measures it directly, with no model quality involved.

## Data
- **FLEURS** (`google/fleurs`, CC-BY-4.0), the `data/<lang>/{test,dev}.tsv` transcript files only (no audio).
  FLEURS sentences are FLoRes-101 sentences, so one id carries the same meaning in every language.
- 15 languages: English (baseline), Hindi, Bengali, Marathi, Telugu, Tamil, Gujarati, Kannada, Malayalam, Punjabi,
  Odia, Assamese, Urdu, Nepali, Sindhi. 201 ids appear in all 15; we draw 100 of them (seed 0). The chosen sentences
  are saved to `data/uc12_token_tax/sentences.json`.

## Tokenizers
| Column | Source |
|---|---|
| Sarvam | `tokenizer.json` from `sarvamai/sarvam-30b`. Byte-identical to the one in `sarvamai/sarvam-105b`. |
| Qwen3 | `tokenizer.json` from `Qwen/Qwen3-30B-A3B` (the self-hosted comparator in UC10/UC06) |
| Gemma 4 | `tokenizer.json` from `google/gemma-4-26b-a4b-it` (ungated; `embeddinggemma` is gated) |
| Gemini | the Gemini `count_tokens` API on `gemini-3.8-flash` (free). `count_tokens("a")` returns 2, so we subtract a 1-token request overhead. |
| OpenAI | `usage.prompt_tokens` from `gpt-5.4-mini` (tiktoken isn't installed), with the sentence as the only user message, minus the fixed chat overhead `prompt_tokens("a") - 1` |
| Claude | `usage.prompt_tokens` from `anthropic/claude-haiku-5.5` via OpenRouter, same method. 4 sentences hit OpenRouter's content filter (no usage returned); those were counted inside a "Translate this sentence to English:" frame, with the frame's tokens subtracted. |

Cross-checks:
- **Sarvam API:** for 10 sentences per language, a 1-token `sarvam-105b` call. Its `prompt_tokens` minus the HF count
  is exactly the chat-template overhead, and it is constant.
- **llama.cpp:** `/tokenize` on the local Sarvam-30B GGUF server for the same sample, run only if that server is up.

## Run
```
.venv/bin/python suites/uc12_token_tax/run.py
```
The run is resumable. Gemini and Sarvam API counts are cached in `results/raw/uc12_token_tax.jsonl`, so a rerun
makes no new paid calls. The tokenizer files are in `data/uc12_token_tax/tokenizers/` (re-download them with
`huggingface_hub` if they are missing).

## Reading the results (`results/uc12_token_tax.json`)
- `table`: one row per language. Columns are characters, words, tokens per sentence for each tokenizer, the tax
  (tokens ÷ tokens for the same sentence in English), and Sarvam-105B list cost in INR per 1,000 sentences
  (₹15 per 1M input tokens, ₹60 per 1M output tokens).
- `metrics`: tokens per sentence and tax per language, with 95% bootstrap CIs over the 100 sentences.
- `per_language.tokens_per_word`: classic fertility, computed per whitespace word.
- `cross_checks`: the API and llama.cpp agreement checks described above.
- No Gemini price is applied. The tax multiplier works with any per-token price.
