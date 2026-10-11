# UC07: Translation and dubbing of training content and product copy

**Business question.** An Indian company needs its training modules and product copy in Indian languages, as
text and as voice-over. Which translation system should it use, and which text-to-speech voice produces audio that
listeners can actually understand?

## What is tested

**A. Translation.** Short sentences (50–110 English characters, the length of a training-slide line or a product
blurb) are translated English → Indic and Indic → English in 10 languages: hi, bn, ta, te, kn, ml, mr, gu, pa, or.

| System | How it is called |
|---|---|
| `sarvam-translate:v1` | `POST /translate` (formal mode only) |
| `mayura:v1` | `POST /translate`, default formal mode. A 10-sentence subset is also run in `modern-colloquial` mode |
| `sarvam-105b` | chat, thinking off, plain "translate, output only the translation" prompt |
| `gemini-3.8-flash` | same prompt, thinking off |
| `openai:gpt-5.4-mini`, `or:anthropic/claude-haiku-5.5` | price-matched cloud tier, same prompt, thinking off, full set |
| `gemini-pro-latest`, `openai:gpt-5.5`, `or:anthropic/claude-sonnet-5.5` | frontier ceiling, thinking on, fixed subset: sentence ids 1669, 1672, 1701 × 10 languages × 2 directions |
| `sarvam-30b-local`, `qwen3-30b-local` | same prompt, llama.cpp Q4_K_M. Only the first 8 sentences (160 items), because the shared llama-server ran at ~3 calls/min. Sarvam-30B's GGUF ignores `enable_thinking=false`, so the suite prefills an empty `<think></think>` via `/completion` |

**B. Dubbing.** Each digit-free native-script reference sentence is synthesised with `bulbul:v3` (a voice chosen
per language, called through the HTTP stream endpoint with mp3 output), with `gemini-3.8-flash-tts` (voice
Kore, streaming) and with OpenAI `gpt-4o-mini-tts` (voice alloy, streaming mp3). `bulbul:v4-flash` (language-tagged voices, same stream endpoint) runs on the first 16 of those sentences, because its price is undocumented; compare it with v3 in the "matched subset" metrics. Three STT judges then transcribe the audio: `saaras:v3`, `gemini-3.8-flash` and the vendor-neutral OpenAI `gpt-4o-transcribe`. The score is
character error rate against the text that was sent to the TTS. Both judges are reported because each may favour
its own vendor's voice. The main set covers hi, bn, ta, te, mr, kn. A 3-sentence probe in ml, gu, pa, or checks
language coverage.

## Why this is realistic

The FLEURS/FLORES sentences are real-world prose: news, travel, science and health. Each reference is a human
native-speaker translation, not machine output. Round-trip intelligibility is a proxy for "can a learner follow
the voice-over". It does not measure naturalness or prosody.

## Data

`prepare.py` downloads the FLEURS test TSVs (`google/fleurs`, **CC-BY 4.0**, ungated) and keeps the sentence ids
present in all 11 languages. It filters them by English length and takes 32 with a fixed seed. The output is
`data/uc07_translation_dubbing/items.json`. The size was capped by the Sarvam translate price
(≈ ₹20 per 10k input characters).

## How to run

```bash
.venv/bin/python suites/uc07_translation_dubbing/prepare.py
.venv/bin/python suites/uc07_translation_dubbing/run.py api     # API systems, then score
.venv/bin/python suites/uc07_translation_dubbing/run.py local   # local llama.cpp models (waits for them)
.venv/bin/python suites/uc07_translation_dubbing/run.py score   # recompute results only
```

Every call is appended to `results/raw/uc07_translation_dubbing.jsonl`. A rerun skips keys that already
succeeded and retries only failed calls, so no successful call is paid for twice. Audio files go to
`data/uc07_translation_dubbing/audio/`.

## Reading the metrics

- Compare local models with API systems only in the "8-sentence subset" metrics, which score every system on the same sentences.
- **chrF++** (0–100, higher is better) is character n-gram F-score plus word bigrams, at sentence level. It is
  averaged over sentences, with a 95% bootstrap CI. It works for morphologically rich Indic languages, where BLEU
  is unreliable. Differences of 1–2 points sit inside the CI.
- **Mayura colloquial.** chrF++ is measured against the *formal* reference, so a lower score is expected and is not
  a defect. The "share of Latin letters" figure shows how much English the colloquial mode mixes in (for example
  "Shop 9 am-க்கு open ஆகும்").
- **Round-trip CER** (lower is better) is character edit distance between the TTS input and the judge's
  transcript, after lower-casing and stripping punctuation. A low CER from *both* judges means the audio is
  intelligible. A large gap between the judges points to judge bias, not TTS quality.
- **Latency.** TTFB is the time to the first audio byte, which matters for live playback. Total time is the time
  to the complete clip, which matters for batch dubbing.
- **Cost.** bulbul:v3 lists at ₹30 per 10k characters. For Gemini TTS the audio output tokens per 10k characters
  are recorded, and no price is assumed.
