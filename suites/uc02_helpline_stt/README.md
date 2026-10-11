# UC02 — Citizen helpline speech-to-text across India's languages

**Business question.** A state or national citizen helpline (grievances, schemes, health, police non-emergency)
takes calls in many Indian languages. Which speech-to-text works in all of them, and how bad is its weakest one?
A helpline is judged by the language it serves worst, so the **worst-language score** is a headline metric.

## Data
- **FLEURS** (`google/fleurs`, test split, CC-BY-4.0): real volunteers reading Wikipedia sentences.
  All 14 Indic configs FLEURS has: Hindi, Bengali, Tamil, Telugu, Malayalam, Kannada, Marathi, Gujarati, Punjabi,
  Odia, Assamese, Urdu (`ur_pk`), Nepali (`ne_np`), Sindhi.
- 25 clips per language = 350 clips (~73 min): the first 25 distinct sentences of at most 30 s in archive order.
  The 30 s cap exists because the saaras:v3 REST endpoint rejects longer audio ("use the batch API"); the same clips
  go to every system. The fetch streams each `test.tar.gz` and stops early, so it downloads a few MB per language
  instead of 400-800 MB (the HF dataset-server and parquet files are too large to sample cheaply).
- Not synthetic. Reference = FLEURS `raw_transcription`. `data/uc02/manifest.json` lists every clip.

## Systems
| system | how it is called |
|---|---|
| `saaras:v3-transcribe` | Sarvam `/speech-to-text`, `mode=transcribe`, `language_code` given (Odia = `od-IN`) |
| `gemini-3.8-flash` | audio inline, "Transcribe this {language} speech verbatim in {script} script", thinking off |
| `whisper-large-v3-turbo` | local, `transformers` on Apple MPS fp16, language forced; Whisper has no Odia, so Odia runs with auto-detect |
| `whisper-1` | OpenAI hosted Whisper, `language` given; the API rejects bn/te/gu/pa (and has no Odia), which then run on auto-detect |
| `gpt-4o-transcribe` | OpenAI, `language` given, "Transcribe this {language} speech verbatim in {script} script." as `prompt` |

## How to run
```
.venv/bin/python suites/uc02_helpline_stt/run.py           # fetch stt whisper score
.venv/bin/python suites/uc02_helpline_stt/run.py score     # recompute results only
```
Resumable: raw records in `results/raw/uc02_helpline_stt.jsonl`, keyed by (clip, system); failed calls are retried
on the next run, finished ones are never re-sent.

## Reading the metrics (`results/uc02_helpline_stt.json`)
- **WER / CER** per clip after NFC, ZWJ/ZWNJ removal, Malayalam chillu unification, Indic digits -> ASCII and
  Arabic short-vowel marks dropped, then the shared `norm_text`. Capped at 1.0 per clip so one hallucination loop
  cannot dominate a language mean. A clip with no transcript scores 1.0.
- `per_language` — WER (with bootstrap 95% CI), CER, and the share of outputs in the reference's script.
- **Worst language** — the language with the highest mean WER, per system. A second version excludes languages
  where the system writes a *different script* from the FLEURS reference (Saaras writes Sindhi in Devanagari, FLEURS
  uses Perso-Arabic; both are used in India and nothing is transliterated here).
- `cannot_handle` — languages where most output is in another script, or CER >= 0.5.
- **Clips with no transcript** — Gemini blocks some audio prompts outright (`block_reason OTHER`), even after
  three attempts.
- `speed` — p50/p95 latency per clip and real-time factor (processing time / audio time). Whisper ran on a shared
  Mac whose GPU was also serving a 30B llama.cpp model, so its timing is pessimistic.
