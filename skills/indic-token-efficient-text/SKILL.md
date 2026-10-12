---
name: indic-token-efficient-text
description: Count tokens and estimate INR cost for Indian-language text on Sarvam-105B (and compare the Indic token tax vs Gemini, OpenAI, Claude, Qwen3). Use when budgeting context windows or choosing a model for Hindi, Tamil, Odia, and other Indic workloads. Grounded in uc12.
---

# Indic token-efficient text

Sarvam's tokenizer is built for Indian scripts. The same sentence that Gemini,
OpenAI or Claude split into many byte pieces stays closer to the English token
count. That is the "Indic token tax" measured in uc12 — not a quality score,
just what you pay in tokens, latency and context.

## What this repo measured

[`results/uc12_token_tax.json`](../../results/uc12_token_tax.json): 100 FLEURS /
FLoRes sentences, 15 languages. Sarvam's `tokenizer.json` is byte-identical
on `sarvamai/sarvam-30b` and `sarvamai/sarvam-105b`.

**Average tax vs the same sentence in English (14 Indic languages)**

| Tokenizer | Tax |
|---|---|
| Sarvam 30B/105B | **1.55×** |
| Gemini 3.8 Flash / Gemma 4 | 1.89× |
| OpenAI gpt-5.4-mini | 2.10× |
| Claude Haiku 5.5 | 3.44× |
| Qwen3-30B-A3B | 5.89× |

Sarvam is cheapest on 12 of 14 Indic languages. OpenAI is cheaper only on
Assamese and Sindhi. For Hindi, Bengali, Marathi, Tamil, Urdu and Nepali,
Sarvam and Gemini tokenize the same, so **list price** is the only lever. For
Telugu, Kannada, Malayalam, Gujarati, Punjabi and especially Odia, Sarvam
needs **18–60% fewer tokens** than Gemini.

Qwen3 vs Sarvam on the same sentence: Odia **7.1×**, Telugu 5.0×, Hindi 3.5×.
That is 3–10× the self-hosted generation time and 3–10× less Indic text in a
context window.

**Sarvam-105B list cost per 1,000 FLEURS sentences as input** (₹15 / 1M):
English ₹0.36, Hindi ₹0.47, Tamil ₹0.53, Odia ₹0.51, Assamese ₹0.73,
Sindhi ₹0.74. Output (₹60 / 1M) is 4×.

**API cross-check:** `prompt_tokens` minus the open tokenizer is a constant
**+14** on every sampled sentence (chat-template overhead). This skill adds
those 14 when estimating a billed chat turn.

## How to run

```bash
python skills/indic-token-efficient-text/count_tokens.py \
    --text "कृषि ऋण माफ नहीं हुआ है" --lang Hindi --cost
python skills/indic-token-efficient-text/test_cost.py    # no API
```

Default counting is **offline**: characters × the uc12 tokens/char rate for
that language. For an exact count, pass the open tokenizer (not committed;
download `tokenizer.json` from `sarvamai/sarvam-30b` or `sarvamai/sarvam-105b`):

```bash
python skills/indic-token-efficient-text/count_tokens.py \
    --file notes.txt --lang Odia --tokenizer /path/to/tokenizer.json --cost
```

Do not call the chat API from tests or CI; this script stays offline unless you
point it at a local `tokenizer.json`.

## When to pick Sarvam for tokens

- Long Indian-language context (policies, judgments, catalogues).
- Self-hosting: Sarvam-30B was faster and much cheaper to *feed* Indic text
  than Qwen3-30B, even though Qwen3 was more accurate on business tasks
  (uc10: 84% vs 63%). Use Qwen3 when accuracy wins, Sarvam-30B when the
  token tax and speed matter more.
- Budgeting: apply the tax multiplier to any per-token price.

## Caveats

- FLEURS is encyclopaedic prose. Chatty Hinglish, code and number-heavy
  invoices may tokenize differently.
- Gemini prices are not applied in uc12; only token counts.
- Sindhi FLEURS is Perso-Arabic; Saaras writes Sindhi in Devanagari (different
  skill). Urdu sentences are `ur_pk`.
- The char-rate fallback is an estimate. Prefer `tokenizer.json` for billing.
