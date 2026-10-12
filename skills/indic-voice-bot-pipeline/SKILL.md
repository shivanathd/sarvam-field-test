---
name: indic-voice-bot-pipeline
description: Build a real-time Indic voice bot with Saaras speech-in, an OpenAI-compatible LLM (Sarvam-105B by default), and streaming Bulbul speech-out. Logs per-stage latency and time-to-first-audio. Grounded in uc01 agent_pipeline numbers.
---

# Indic voice-bot pipeline

The all-Sarvam stack is the fastest voice loop this benchmark ran. Use it when
the caller should hear a reply in about a second, in their own language. Swap
only the LLM when you need stricter number read-back.

## Pipeline

```
audio → Saaras v4 (codemix, optional keyterms, optional ITN)
      → LLM (sarvam-105b, or any OpenAI-compatible id `common.bench.chat` accepts)
      → Bulbul /text-to-speech/stream
```

Time-to-first-audio in this repo is **STT + full LLM reply + TTS first byte**.
The bot does not start speaking until the model has finished the sentence.
Streaming TTS still cuts perceived delay versus the REST `audios[]` body
(API quirks: the stream delivered complete audio about 3× faster than REST).

## What this repo measured (uc01, 20 clean turns)

From [`results/uc01_voice_support.json`](../../results/uc01_voice_support.json)
`agent_pipeline`. Runs were from Kochi; Sarvam is hosted in India, so latency
favours it. n=20, so treat p95 as a hint.

| Stack | TTFA p50 | Reply in caller script | Caller entities echoed | ₹ / conversation-minute |
|---|---|---|---|---|
| **Saaras v4 + Sarvam-105B + Bulbul v4-flash** | **1.14 s** | 18/20 (0.90) | 80% | **₹1.42** |
| Saaras v3 + Sarvam-105B + Bulbul v3 | 1.48 s | 19/20 (0.95) | 83% | ₹1.56 |
| Saaras + GPT-5.4 mini + Bulbul | ~3 s class (OpenAI stack 3.17 s) | lower than Sarvam | — | speech + OpenAI tokens |
| All-Gemini | **6.78 s** | 16/20 (0.80) | **97%** | Gemini tokens |

v4-flash first audio byte ~308 ms vs Bulbul v3 ~388 ms (about 50 ms sooner;
README: slightly less clear). Sarvam-105B reply p50 **374 ms**. Saaras v4 p50
**443 ms**, p95 **4.5 s** on this 20-turn sample.

uc11v (spoken payments, same ears, different LLM): Saaras v4 → Gemini tool
calls scored 96%/94% exact (clean/phone); the all-Sarvam stack 90%/88%. The
gap was the LLM (UPI-ID names, fractional amounts), not Saaras. Confirm payee
and amount before paying.

## How to run

```bash
cp .env.example .env
python skills/indic-voice-bot-pipeline/pipeline.py turn.wav --lang hi-IN
python skills/indic-voice-bot-pipeline/pipeline.py turn.wav --lang hi-IN \
    --llm openai:gpt-5.4-mini --out reply.mp3
```

`--llm` values: `sarvam-105b` (default), `openai:gpt-5.4-mini`,
`or:anthropic/claude-haiku-5.5`, `gemini-3.8-flash`. Keys come only from the
matching `.env.example` variables.

The script reuses `sarvam_post` / `chat` from [`common/bench.py`](../../common/bench.py)
and the streaming POST from uc01 `sarvam_tts_stream`. It also runs the ITN
step from `indic-stt-with-digits` so the LLM sees digits.

## Voice and language notes

- **Bulbul v4-flash** rejects v3 voice names (`shubh`). Voices are language-tied
  (`ritu_hi_edtech`, `gokul_ta_narration`, …). The list appears in the API
  error message, not the docs.
- No Malayalam or Odia v4 voice; Assamese needs beta access. Those languages
  fall back to the API default (or a Hindi voice in the uc07 probe).
- Odia language code is `od-IN`.
- Leave `reasoning_effort` **null** on Sarvam-105B for a voice turn.
  `"low"` still spent ~1,300 reasoning tokens on a one-line task.

## Agent checklist

1. Time each stage. Alert if TTFA p95 leaves a phone-call gap (>3 s).
2. Echo amounts back. Gemini echoed 97% of caller entities; Sarvam-105B 80%.
3. Empty Saaras transcripts must re-prompt, not guess (uc11v: an empty
   transcript made the tool-calling model invent a payment).
4. Do not synthesise test audio with Bulbul if you later score Saaras on it
   (this benchmark never did).
