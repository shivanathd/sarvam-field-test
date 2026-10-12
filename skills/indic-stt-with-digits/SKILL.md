---
name: indic-stt-with-digits
description: Transcribe Indian-language and Hinglish speech with Sarvam Saaras v4, then convert number-words to ASCII digits. Use when an agent must capture amounts, card last-4, phones, OTPs or dates from Indic audio. Includes keyterms usage. Grounded in uc01 and uc02 of this repo.
---

# Indic STT with digits (Saaras v4 + ITN)

Sarvam's Saaras is a strong speech recogniser for India's languages. Use it when
the job is a transcript. Add this skill's inverse-text-normalisation (ITN) step
when the transcript has to feed a bank, wallet or collections system that needs
**digits**, not "बारह हज़ार".

## When to use

- Support, collections, helpline or WhatsApp voice notes in Hindi, Hinglish,
  Tamil, Malayalam, Bengali, Kannada and the other Saaras languages.
- Downstream tools that match amounts, PANs, phones or OTPs as digits.

Prefer Gemini 3.8 Flash **on the audio** only when you need raw entity accuracy
and cannot add ITN (uc01: 94% of gold entities). For a multi-language helpline
transcript, Saaras v4 is the better default (uc02).

## What this repo measured

Numbers are from [`results/uc01_voice_support.json`](../../results/uc01_voice_support.json)
and [`results/uc02_helpline_stt.json`](../../results/uc02_helpline_stt.json),
run 11 October 2026. Audio in uc01 is synthetic (macOS `say` + Gemini TTS, never
Bulbul), so real-call error rates will be higher.

**Digits on code-mixed collections calls (uc01, 80 clips, 100 gold entities)**

| System | Entity accuracy, phone | Notes |
|---|---|---|
| Gemini 3.8 Flash | **94%** | Writes numbers as digits |
| Saaras v3 codemix | **81%** [73–88] | Best Sarvam number capture |
| Saaras v4 transcribe | 64% | Better digits than v4 codemix |
| Saaras v4 codemix + keyterms | **56%** [47–66] | Up from 39% without keyterms |
| Saaras v4 codemix | 39% | Writes amounts as words |

v4 is not a worse listener. Most misses are **formatting**: 15 of 26 clean
codemix misses had no digits at all (`बारह हज़ार चार सौ निन्यानवे`,
`सेवन थ्री ज़ीरो सिक्स`). The README's "API quirks" section records the same
behaviour. A perfect ITN ceiling on the phone line was **0.95–0.96** for v4 —
that is an upper bound, not a measured parser. This skill ships a practical
parser, not that ceiling.

**Word error rate on read speech (uc02, 13 languages, FLEURS)**

Saaras v4 transcribe **0.149** vs v3 0.170, Gemini 0.21, GPT-4o transcribe 0.27.
Lowest WER in 11 of 13 languages. Sindhi is Devanagari-only.

**Keyterms (v4 only)**

- One fixed list of at most **50** strings, each at most **64** characters, sent
  as a **JSON array**. A comma-separated string returns HTTP 400.
- v3 rejects `keyterms` entirely (HTTP 400).
- On uc01 phone audio, the bank-style list lifted entity accuracy 0.39 → 0.56
  and gave the lowest phone CER of any system (0.19). Gains were uneven
  (Manglish/Kanglish large, Benglish none). Latency rose: p50 **1.78 s** /
  p95 **6.0 s**.
- On WhatsApp voice orders (uc08v, phone), the same idea moved exact-order
  accuracy 89.5% → **91.9%**, at a similar latency cost.

Do not put per-utterance gold values in the list. Configure products and brands
once, the way a bank would.

## How to run

```bash
cp .env.example .env          # SARVAM_API_KEY only
python skills/indic-stt-with-digits/transcribe.py path/to/call.wav --lang hi-IN
python skills/indic-stt-with-digits/test_normalize.py   # no API
```

`transcribe.py` calls `/speech-to-text` the same way
[`suites/uc01_voice_support/run.py`](../../suites/uc01_voice_support/run.py)
does (`sarvam_post`, `model=saaras:v4`, `mode=codemix`, `keyterms=json.dumps(...)`),
then runs [`normalize_digits.py`](normalize_digits.py).

Odia is `od-IN`. There is a 30 s cap per REST call (uc02).

## Agent checklist

1. Use `saaras:v4` + `mode=codemix` for Hinglish / Tanglish / code-mix; `transcribe`
   for a single Indian language on a helpline.
2. Pass a JSON-encoded `keyterms` array (≤50). Skip it on v3.
3. Run ITN before any tool that compares amounts or IDs.
4. Confirm card digits and payout amounts with the caller. ITN is not 100%.
5. Read keys only from `SARVAM_API_KEY` (see `.env.example`).

## Caveats

- The parser covers Hindi 0–99 and scales, Hinglish/English spelling, spoken
  English digits in Devanagari, common fractions (पौने, साढ़े, ढाई, सवा, डेढ़),
  and frequent Bengali / Tamil / Malayalam / Kannada thousands. Agglutinated
  Dravidian forms outside that list will pass through as words.
- uc01 did not ship ITN; treat production digit accuracy as unmeasured.
- Saaras v4 is faster at p50 (~0.5 s) than v3 but has a heavier tail
  (p95 2.8–5.3 s in that run, under a shared rate-limited account).
