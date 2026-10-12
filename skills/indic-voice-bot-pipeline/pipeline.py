"""Saaras in → LLM → Bulbul out, with streaming TTS and per-stage latency logs.

Usage (from the repo root, after `cp .env.example .env`):

    python skills/indic-voice-bot-pipeline/pipeline.py path/to/turn.wav --lang hi-IN
    python skills/indic-voice-bot-pipeline/pipeline.py path/to/turn.wav --lang hi-IN --llm openai:gpt-5.4-mini

LLM ids match `common.bench.chat`: `sarvam-105b` (default), `openai:…`, `or:…`,
or `gemini-3.8-flash`. Speech ends stay on Sarvam (Saaras v4 + Bulbul stream).

Reads `SARVAM_API_KEY` and, if the LLM needs them, `OPENAI_API_KEY` /
`OPENROUTER_API_KEY` / `GOOGLE_API_KEY`. No secrets in flags. This script
calls paid APIs — do not import it from tests that should stay offline.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "skills" / "indic-stt-with-digits"))

from common.bench import SARVAM, chat, sarvam_post  # noqa: E402
from normalize_digits import normalize  # noqa: E402
from transcribe import KEYTERMS  # noqa: E402

AGENT_SYS = (
    "You are a phone support agent for an Indian bank, telecom and insurance helpline. "
    "Reply in the caller's language and the same English code-mixing style they use, "
    "in one or two short spoken sentences. Repeat back any number, amount or date "
    "the caller gave so they can confirm it. No markdown, no lists."
)

# bulbul:v4-flash rejects v3 voice names (API quirk). No Malayalam / Odia voice.
V4_SPEAKER = {
    "hi-IN": "shubh_hi_customer",
    "ta-IN": "gokul_ta_narration",
    "bn-IN": "arnab_bn_conversation",
    "kn-IN": "chetan_kn_conversation",
    "te-IN": "kavitha_te_narration",
    "mr-IN": "ritu_mr_narration",
    "gu-IN": "pooja_gu_conversational",
    "pa-IN": "harpreet_pa_narration",
}


def _need(key: str) -> None:
    if not os.environ.get(key):
        raise SystemExit(f"{key} is not set. Copy .env.example to .env or export it.")


def stt(path: Path, language_code: str, keyterms: bool = True) -> dict:
    _need("SARVAM_API_KEY")
    t = time.time()
    with path.open("rb") as fh:
        data = {"model": "saaras:v4", "mode": "codemix", "language_code": language_code}
        if keyterms:
            data["keyterms"] = json.dumps(KEYTERMS)
        raw = sarvam_post("/speech-to-text", files={"file": (path.name, fh, "audio/wav")}, data=data)
    ms = (time.time() - t) * 1000
    if raw.get("_error"):
        raise SystemExit(f"Saaras HTTP {raw['_error']}: {raw.get('_body', '')[:300]}")
    hyp = raw.get("transcript") or ""
    return {"hyp": hyp, "hyp_digits": normalize(hyp), "ms": ms}


def reply(llm: str, transcript: str) -> dict:
    if llm.startswith("openai:"):
        _need("OPENAI_API_KEY")
    elif llm.startswith("or:"):
        _need("OPENROUTER_API_KEY")
    elif llm.startswith("gemini"):
        _need("GOOGLE_API_KEY")
    else:
        _need("SARVAM_API_KEY")
    messages = [
        {"role": "system", "content": AGENT_SYS},
        {"role": "user", "content": transcript},
    ]
    out = chat(llm, messages, max_tokens=1000, think=False)
    if out.get("error"):
        raise SystemExit(f"LLM error: {out['error']}")
    return out


def tts_stream(text: str, language_code: str, model: str = "bulbul:v4-flash",
               dest: Path | None = None) -> dict:
    """POST /text-to-speech/stream (uc01). Time-to-first-byte is the first chunk."""
    _need("SARVAM_API_KEY")
    speaker = "shubh" if model == "bulbul:v3" else V4_SPEAKER.get(language_code)
    body = {"text": text, "target_language_code": language_code, "model": model,
            "output_audio_codec": "mp3"}
    if speaker:
        body["speaker"] = speaker
    t = time.time()
    r = requests.post(SARVAM + "/text-to-speech/stream",
                      headers={"api-subscription-key": os.environ["SARVAM_API_KEY"]},
                      json=body, stream=True, timeout=120)
    if r.status_code != 200:
        raise SystemExit(f"Bulbul HTTP {r.status_code}: {r.text[:300]}")
    first, buf = None, bytearray()
    for chunk in r.iter_content(4096):
        if first is None:
            first = (time.time() - t) * 1000
        buf += chunk
    total = (time.time() - t) * 1000
    if dest is not None:
        dest.write_bytes(buf)
    return {"ttfb_ms": first, "total_ms": total, "bytes": len(buf),
            "chars": len(text), "path": str(dest) if dest else None}


def run_turn(audio: Path, language_code: str, llm: str, tts_model: str,
             out_audio: Path | None, keyterms: bool) -> dict:
    s = stt(audio, language_code, keyterms=keyterms)
    user_text = s["hyp_digits"] or s["hyp"]
    llm_out = reply(llm, user_text)
    tts = tts_stream(llm_out.get("text") or "", language_code, model=tts_model, dest=out_audio)
    ttfa = s["ms"] + llm_out["ms"] + (tts["ttfb_ms"] or 0)
    return {
        "stt": {k: s[k] for k in ("hyp", "hyp_digits", "ms")},
        "llm": {"text": llm_out.get("text"), "ms": llm_out.get("ms"),
                "in_tok": llm_out.get("in_tok"), "out_tok": llm_out.get("out_tok"),
                "model": llm},
        "tts": tts,
        "time_to_first_audio_ms": ttfa,
        "language_code": language_code,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("audio", type=Path)
    p.add_argument("--lang", default="hi-IN")
    p.add_argument("--llm", default="sarvam-105b",
                   help="sarvam-105b | openai:gpt-5.4-mini | or:anthropic/claude-haiku-5.5 | gemini-3.8-flash")
    p.add_argument("--tts-model", default="bulbul:v4-flash", choices=("bulbul:v4-flash", "bulbul:v3"))
    p.add_argument("--out", type=Path, default=None, help="Optional MP3 path for the spoken reply")
    p.add_argument("--no-keyterms", action="store_true")
    args = p.parse_args(argv)
    if not args.audio.is_file():
        raise SystemExit(f"audio file not found: {args.audio}")
    rec = run_turn(args.audio, args.lang, args.llm, args.tts_model, args.out, not args.no_keyterms)
    json.dump(rec, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
