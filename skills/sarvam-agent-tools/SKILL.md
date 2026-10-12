---
name: sarvam-agent-tools
description: Python MCP server that exposes Sarvam transcribe, translate and speak tools to an agent. Use when wiring Saaras, Sarvam-Translate and Bulbul into Cursor, Claude Desktop or any MCP host. Grounded in uc01, uc02 and uc07.
---

# Sarvam agent tools (MCP)

A small stdio MCP server so an agent can call the three Sarvam endpoints this
benchmark found most useful: **hear**, **translate into an Indian language**,
**speak**. It is JSON-RPC 2.0 on stdin/stdout. No extra SDK.

## Tools

| Tool | Endpoint | Why this repo recommends it |
|---|---|---|
| `transcribe` | `POST /speech-to-text` (`saaras:v4`) | Lowest Indic WER on uc02 (0.149). Runs the digits ITN from `indic-stt-with-digits` because v4 writes amounts as words (uc01). |
| `translate` | `POST /translate` (`sarvam-translate:v1`) | Best **into** Indian languages on uc07 (chrF++ **51.8**, 8 of 10 languages). Into English, Gemini 3.8 Flash led at **64.3** vs Sarvam-105B 57.8. **Never Mayura** for decimal crore amounts — it garbled every one (uc07 / uc09). |
| `speak` | `POST /text-to-speech/stream` | Bulbul v3 matched Gemini/OpenAI intelligibility across 10 languages; v4-flash starts ~50 ms sooner. Stream, not REST (`audios[]` is ~3× slower). |

## What this repo measured (honest bits)

- **Speech:** Saaras v4 is the transcriber to start with. Add ITN or Gemini-on-audio when the digits themselves are the product (uc01 phone: Gemini 94%, v3 81%, v4+keyterms 56%).
- **Dubbing first audio (uc07):** Bulbul v3 **430 ms** vs GPT-4o mini TTS **1.04 s**.
- **Voice bot (uc01):** all-Sarvam first audio ~1.1 s at ₹1.42 / conversation-minute. Pair this MCP with `indic-voice-bot-pipeline` if you need the LLM in the middle.
- Odia is `od-IN`. Mayura accepts at most 1,000 characters. Saaras REST clips are capped at 30 s.

## Run and connect

```bash
cp .env.example .env          # SARVAM_API_KEY
python skills/sarvam-agent-tools/server.py
python skills/sarvam-agent-tools/test_server.py   # no API
```

Cursor / Claude Desktop snippet (also in [`example_mcp.json`](example_mcp.json)):

```json
{
  "mcpServers": {
    "sarvam": {
      "command": "python",
      "args": ["skills/sarvam-agent-tools/server.py"],
      "env": { "SARVAM_API_KEY": "${SARVAM_API_KEY}" }
    }
  }
}
```

Run the command from the repo root so `common.bench` and the sibling STT skill
import cleanly. Do not put a key in the JSON file.

`initialize` and `tools/list` never touch the network. `tools/call` reads
`SARVAM_API_KEY` and fails closed if it is missing.

## Agent checklist

1. Prefer `sarvam-translate:v1` for en→Indic. For Indic→en, call a cloud LLM
   instead (or add one — this server does not wrap Gemini).
2. After `transcribe`, use `transcript_digits` for amounts and IDs.
3. Confirm payouts and card digits. ITN is practical, not the 0.96 ceiling.
4. Write `speak` output to a path the user asked for. No hardcoded home paths.
