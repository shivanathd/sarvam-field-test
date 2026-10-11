# UC08v: WhatsApp voice-note orders

**Business question.** Many kirana and quick-commerce orders arrive as WhatsApp voice notes rather than text.
Which speech-to-text should sit in front of the order extractor? How much accuracy is lost compared with typed
orders, and does a phone-quality line break it?

## Design

1. **Speech.** The 86 UC08 *order* messages (the searches are left out) are read by `gemini-3.8-flash-tts`
   exactly as written: romanised Hinglish/Tanglish, native script, English. The model infers the accent from the
   text, and the voices alternate between Kore and Puck. Sarvam TTS is deliberately not used, so the Sarvam ASR is
   not hearing its own voice.
2. **Conditions.** *clean* is the 24 kHz TTS output. *phone* is the same clip resampled to 8 kHz, band-passed to
   300–3400 Hz, with white noise added at 15 dB SNR (seeded per message, so it is reproducible).
3. **Speech recognition** (ASR), one setup per row:
   - `saaras:v4` codemix
   - `saaras:v4` codemix with `keyterms`: one fixed store-wide list of 50 brands, units and payment words, not per-item gold
   - `saaras:v3` codemix
   - `gemini-3.8-flash` (audio in, transcript out)
   - OpenAI `gpt-4o-transcribe`
4. **Extraction.** Every transcript goes to the *same* extractor, `gemini-3.8-flash` with thinking off and the
   UC08 order prompt, so any difference between rows comes from speech recognition only.
5. **End-to-end pipelines:**
   - *all-Sarvam*: `saaras:v4` codemix → `sarvam-105b` with thinking on (max_tokens 16k)
   - *direct audio*: `gemini-3.8-flash` given the audio plus the order prompt in one call
6. **Baselines.** UC08's typed-text results on the same 86 messages: gemini-3.8-flash and sarvam-105b-think.

Because of the Sarvam ₹30 budget, the saaras:v4-with-keyterms setup, saaras:v3 and the all-Sarvam pipeline run
on the **phone** condition only. saaras:v4 codemix, Gemini and OpenAI run on both conditions. The exact plan is
recorded in the result's `extra.plan`.

## Metrics

The UC08 order scorer is reused unchanged:
- exact whole-order accuracy
- item F1, strict (name + quantity/unit + brand) and catalog-name-only
- pincode, payment and slot accuracy, and JSON validity

95% bootstrap CIs; n = 86 per row.

## Run

```bash
.venv/bin/python suites/uc08v_voice_orders/run.py api     # TTS, phone simulation, ASR, extraction, score
.venv/bin/python suites/uc08v_voice_orders/run.py score
```

Raw calls are stored in `results/raw/uc08v_voice_orders.jsonl`, and audio in `data/uc08v_voice_orders/{clean,phone}/`.
A rerun skips finished calls.

## Caveats

TTS voices are cleaner and more regular than real customers: no background chatter, hesitations or regional
mispronunciation. The phone condition is a simple simulation, not a real GSM codec. The data is synthetic.
