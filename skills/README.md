# Agent skills

Reusable workflows for plugging [Sarvam AI](https://www.sarvam.ai) into an
agent or product, grounded in the numbers in this repo. Each folder is a
skill: a `SKILL.md` (name + description in the YAML frontmatter) plus small
Python examples.

Sarvam is an Indian lab building models for India's languages. These skills
show where that work is already the right default — speech, voice bots,
translation *into* Indic languages, token cost of Indian text — and where you
should add a small extra step (digits, a stronger LLM, a confirm-the-amount
prompt).

API keys come only from environment variables listed in
[`.env.example`](../.env.example) (`SARVAM_API_KEY`, and the others if you
swap the LLM). No secrets and no machine-local paths are checked in.

| Skill | What it does | Benchmark |
|---|---|---|
| [indic-stt-with-digits](indic-stt-with-digits/SKILL.md) | Saaras v4 speech-to-text + number-words → digits + keyterms | [uc01](../suites/uc01_voice_support/), [uc02](../suites/uc02_helpline_stt/) |
| [indic-voice-bot-pipeline](indic-voice-bot-pipeline/SKILL.md) | Saaras → LLM → streaming Bulbul, with latency logs | [uc01](../suites/uc01_voice_support/) `agent_pipeline` |
| [indic-token-efficient-text](indic-token-efficient-text/SKILL.md) | Token count and ₹ cost for Indic text on Sarvam-105B | [uc12](../suites/uc12_token_tax/) |
| [sarvam-agent-tools](sarvam-agent-tools/SKILL.md) | MCP server: `transcribe` / `translate` / `speak` | uc01, uc02, [uc07](../suites/uc07_translation_dubbing/) |

Clients follow [`common/bench.py`](../common/bench.py) (`sarvam_post`, `chat`,
streaming TTS). Offline tests live next to each skill and must not call paid
APIs:

```bash
python skills/indic-stt-with-digits/test_normalize.py
python skills/indic-token-efficient-text/test_cost.py
python skills/sarvam-agent-tools/test_server.py
```
