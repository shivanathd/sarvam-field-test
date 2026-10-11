# UC06v: Spoken farmer questions (voice-in crop advisory)

**Question:** farmers ask by voice, often over a phone line. How much does speech recognition cost the advice they get,
and which STT front-end should a voice crop-advisory line use?

This suite is uc06 with a microphone in front: same 70 questions, same advisory sheet, same scorer.

## Data (synthetic)
- **Text:** the 70 uc06 questions in Hindi, Marathi, Kannada, Telugu, Tamil and Punjabi (60 answerable from the
  sheet, 10 out of scope).
- **Voices:** native-script items are spoken by the macOS Indian voice for that language where one exists (Lekha hi,
  Soumya kn, Geeta te, Vani ta). Romanised items are spoken from their native-script twin by a `gemini-3.8-flash-tts`
  voice, so each fact is heard from two speakers. Marathi and Punjabi have no macOS voice, so both of their forms use
  Gemini voices. Sarvam's own TTS is never used.
- **Phone line:** uc01's `phone_line()`: 8 kHz, 300-3400 Hz band-pass, G.711 mu-law, about 20 dB SNR noise.
- **Native versions for 4 items:** the out-of-scope questions that existed only romanised got hand-written native
  versions (`OOS_NATIVE` in run.py).
- **Output:** audio in `data/uc06v_offline_agri_voice/audio/{clean,phone}/`, voice per clip in `synth.json`.

## Pipelines
| Pipeline | What it isolates |
|---|---|
| `text -> gemini-3.8-flash` | upper bound: the exact spoken text |
| `<stt> -> gemini-3.8-flash` for stt in saaras:v4, saaras:v3 (transcribe mode), gemini-3.8-flash (audio in), gpt-4o-transcribe | STT quality only; the answering model and prompt are identical |
| `saaras:v4 -> sarvam-105b` | all-Sarvam stack |
| `audio -> gemini-3.8-flash` | Gemini answering straight from audio, with the sheet as the system prompt |

All answering uses thinking off, temperature 0 and uc06's prompt. Each STT system is told the language.

## Metrics
uc06's scorer: `grounded_correct`, `oos_refusal` (strict code / lenient helpline redirect), `false_refusal`,
`reply_language_correct` (native script expected, since speech has no script) and `overall_pass`. The suite adds
per-system `cer_<stt>` against the spoken text, by condition and per language.

## Run
```
.venv/bin/python suites/uc06v_offline_agri_voice/run.py            # synth stt answer score; resumable
.venv/bin/python suites/uc06v_offline_agri_voice/run.py score      # recompute results only
```
Failed calls (429, 402) are not recorded as done and are retried on rerun. A Sarvam credit error stops all Sarvam calls.
