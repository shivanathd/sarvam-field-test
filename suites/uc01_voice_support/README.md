# UC01 — Code-mixed voice support & collections calls

**Business question.** A bank, telecom operator or insurer takes support and collections calls in Hinglish,
Tanglish, Manglish, Benglish and Kanglish. Which speech-to-text gets the caller's card digits, amounts, due dates,
phone and claim numbers right, and which voice-agent stack answers fast enough to feel like a phone call?

## Why the test is realistic
- 80 customer-side utterances written the way callers talk: lost/blocked cards, unrecognised card transactions,
  failed UPI payments, EMI promises-to-pay and bounce charges, recharges and number porting, insurance claim status.
  16 per code-mix, English nouns ("debit card", "EMI", "port") inside Indic grammar.
- Every utterance carries checkable gold entities (100 in total): card last-4, amounts, reference/claim numbers,
  10-digit phone numbers, dates. **Entity accuracy is the headline metric** — a transcript with a wrong digit is
  useless to a bank even if its WER looks fine.
- Two audio conditions: clean 16 kHz, and a phone line (8 kHz, 300-3400 Hz band-pass, G.711 mu-law, ~20 dB SNR
  noise, back to 16 kHz).
- An end-to-end voice-agent check: 20 turns through STT -> LLM reply -> TTS, timing each stage.

## Data (`data/uc01/`)
- `items.json` — id, code-mix, domain, `text` (code-mix reference: English in Latin script, Indic words in native
  script, numbers as digits — the saaras codemix convention), `native` (same sentence with English loanwords in native
  script), `ent` (gold entities; dates are `[day, month]`).
- `audio/clean/*.wav`, `audio/phone/*.wav` — synthesised; `synth.json` says which voice made each clip.
- Synthetic: written by hand for this benchmark; all phone/card/claim numbers are made up.
- Voices: macOS `say` (Lekha hi, Vani ta, Piya bn, Soumya kn) for half of each language, `gemini-3.8-flash-tts`
  (6 prebuilt voices) for the other half and all of Malayalam (macOS ships no Malayalam voice). Sarvam's own TTS is
  deliberately not used to make test audio.

## Systems
| system | how it is called |
|---|---|
| `saaras:v3-codemix` | Sarvam `/speech-to-text`, `mode=codemix`, `language_code` given |
| `saaras:v3-transcribe` | same, `mode=transcribe` |
| `saaras:v4-codemix`, `saaras:v4-transcribe` | same endpoint, `model=saaras:v4` (released 25 Sep 2026) |
| `saaras:v4-codemix+keyterms` | v4 codemix plus `keyterms` = one fixed 50-term product/brand list (`KEYTERMS` in run.py); no per-clip gold values |
| `gemini-3.8-flash` | audio inline, prompted for the same code-mix convention, thinking off |
| `whisper-large-v3-turbo` | local, `transformers` pipeline on Apple MPS fp16, language forced |
| `whisper-1` | OpenAI hosted Whisper, `language` given; the API rejects `bn` and `ml`, so those fall back to auto-detect |
| `gpt-4o-transcribe` | OpenAI, `language` given, the Gemini code-mix instruction passed as `prompt` |
| `agent-sarvam` | saaras codemix -> `sarvam-105b` (think off) -> `bulbul:v3` `/text-to-speech/stream` |
| `agent-gemini` | gemini STT -> `gemini-3.8-flash` (think off) -> `gemini-3.8-flash-tts` streaming |
| `agent-openai` | `gpt-4o-transcribe` -> `openai:gpt-5.4-mini` (reasoning none) -> `gpt-4o-mini-tts` streamed PCM |
| `agent-sarvam-speech+gpt-5.4-mini` | saaras codemix -> `openai:gpt-5.4-mini` -> bulbul:v3 (only the LLM swapped) |
| `agent-sarvam-v4` | saaras:v4 codemix -> `sarvam-105b` -> `bulbul:v4-flash` HTTP stream (per-language v4 voices; Malayalam has none, so the API default is used) |
| `agent-sarvam-speech+claude-haiku-5.5` | saaras codemix -> `or:anthropic/claude-haiku-5.5` (OpenRouter, reasoning off) -> bulbul:v3 |

## How to run
```
.venv/bin/python suites/uc01_voice_support/run.py            # all steps
.venv/bin/python suites/uc01_voice_support/run.py score      # recompute results only
```
Steps: `synth stt whisper agent score`. Every API result is appended to `results/raw/uc01_voice_support.jsonl`
keyed by (item, system, condition); reruns skip what is there (failed calls are retried) and never re-spend.
On a Sarvam HTTP 402 the run stops calling Sarvam. Needs `ffmpeg`/`ffprobe` and macOS `say`.

## Reading the metrics (`results/uc01_voice_support.json`)
- **Entity accuracy** — share of gold entities found exactly in the transcript after joining digit groups
  ("4 8 2 1", "12,499", "98450-12367") and mapping Indic digits to ASCII. Number words ("बारह हज़ार") do not count:
  this is raw API output, no inverse text normalisation. `entity_miss_types` splits misses into "no digits in
  output" (formatting) vs "digits wrong" (hearing).
- **Calls with every entity correct** — share of utterances where nothing numeric was lost.
- **WER/CER vs code-mix reference** — normalised (NFC, ZWJ removed, Malayalam chillus unified, currency words and
  the rupee sign dropped, digit groups joined), capped at 1.0 per clip.
- **WER, best of two references** — each output is scored against both the code-mix and the all-native-script
  reference and the lower WER is kept. Nothing is transliterated; this only stops a system being penalised for
  writing "डेबिट" instead of "debit". Spelling variants of loanwords still count as errors.
- `by_synthesis_source` — the same scores split by `say` vs Gemini-voiced audio, to check for a home advantage.
- `agent_pipeline` — per-stage p50/p95 ms; `time_to_first_audio` = STT + full LLM reply + TTS first byte;
  `reply_in_caller_language_script` = >=30% of the reply's letters in the caller's script (code-mixed replies are
  fine); `caller_entities_echoed_correctly` = the agent read the caller's numbers back correctly; cost per
  conversation-minute from usage (Sarvam list prices; Gemini tokens only).
