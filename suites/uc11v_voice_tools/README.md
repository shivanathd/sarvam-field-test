# UC11v: spoken voice-assistant commands → tool calls

**Question.** A user *says* "mera 299 wala recharge kar do" (or "கரண்ட் பில் கட்டுங்க", or "আড়াই হাজার টাকা rina@ybl-এ
পাঠাও") into a payments app. Which speech stack ends up calling the right tool with the right arguments?

This is the voice-input version of the uc11 tool-calling sub-test. It uses the same 50 commands (Hindi, Hinglish, Tamil,
Bengali; 20 hard ones), the same 5-tool schema (recharge, pay_bill, check_balance, book_cylinder, transfer_upi) and the
same exact-match scorer (`suites/uc11_bharat_code/tools.py`).

## Design

1. **Audio.** Each command is spoken by a macOS `say` Indian voice (Lekha hi, Vani ta, Piya bn) or a
   gemini-3.8-flash-tts voice. Sarvam TTS is never used, so Sarvam's ASR is not tested on its own voice. The spoken form
   reads phone numbers digit by digit and UPI IDs the way Indians say them ("priya dot s at the rate oksbi"). Gold
   arguments stay those of the typed command.
2. **Two conditions.** `clean` (16 kHz) and `phone`: 8 kHz band-limited 300-3400 Hz, ~20 dB SNR noise and G.711 mu-law,
   the same recipe as uc01.
3. **ASR comparison with a fixed brain.** saaras:v4 and saaras:v3 (transcribe mode, language code given),
   gemini-3.8-flash (audio in, verbatim-transcript prompt) and gpt-4o-transcribe (language code). **Every transcript goes
   to the same tool model**, gemini-3.8-flash with thinking off and the same schema, so differences come only from
   speech recognition.
4. **Stacks.** All-Sarvam (saaras:v4 → sarvam-105b native tools); gemini-3.8-flash direct audio function calling (no
   transcript step); and a typed-text oracle (the original command → gemini-3.8-flash).

**Metrics.** Correct tool AND exact arguments, using the uc11 normaliser (case, Indic digits, phone suffix, default
`quantity=1`). Reported separately for the 10 commands with **spoken fractional amounts** (dhai/paune/saadhe/dedh/sava,
e.g. "पौने दो हज़ार" = 1750) and the other 40, plus the hard 20. A secondary metric tolerates vowel spelling in a UPI
name (dipak/deepak), because no stack can recover the spelling from speech.

**Audio audit.** Every clean clip was checked against its intended words using the 4 transcripts. In 5 clips the TTS
itself was wrong (a `say` voice reordered or dropped phone digits, or could not pronounce an English UPI ID), and all
ASR systems agreed on the wrong words. Those clips were reworded or re-voiced and re-run; see `SPOKEN_OVERRIDE` /
`VOICE_OVERRIDE` in `run.py` and the caveats in the results file.

## Run

```bash
.venv/bin/python suites/uc11v_voice_tools/run.py          # synth, stt, tools, score (resumable; never re-spends)
.venv/bin/python suites/uc11v_voice_tools/run.py score    # rebuild results/uc11v_voice_tools.json from raw
```

Audio goes to `data/uc11v_voice_tools/audio/{clean,phone}/<id>.wav`, with voices and spoken text in `synth.json`.
Raw records go to `results/raw/uc11v_voice_tools.jsonl` (kind `stt` / `tool`). Any Sarvam/OpenAI credit or quota error
is a hard stop, and failed calls are never recorded.

## Reading the results

`metrics` holds one entry per (subset, condition), and each pipeline's value has a bootstrap CI over the 50 (or 10/40/20)
commands. `empty_transcripts_of_100` counts ASR outputs that came back empty (they lead to invented tool calls).
`examples` shows the fractional-amount commands on phone audio, with every pipeline's transcript and call side by side.
Cost: Saaras is billed by audio seconds (`usage`, ₹30/hour list); the test audio is ~340 s per condition.
