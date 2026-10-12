"""Minimal stdio MCP server: transcribe, translate, speak via the Sarvam API.

Protocol: JSON-RPC 2.0 on stdin/stdout (MCP 2024-11-05). No third-party MCP
SDK — stdlib + `requests` / `common.bench` only.

    python skills/sarvam-agent-tools/server.py

Tool handlers call paid endpoints. `initialize` and `tools/list` do not.
Keys come from `SARVAM_API_KEY` only (see `.env.example`).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "skills" / "indic-stt-with-digits"))

from common.bench import SARVAM, sarvam_post  # noqa: E402
from normalize_digits import normalize  # noqa: E402
from transcribe import KEYTERMS  # noqa: E402

SERVER_NAME = "sarvam-agent-tools"
SERVER_VERSION = "1.0.0"
PROTOCOL = "2024-11-05"

LANG_CODES = (
    "hi-IN", "bn-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN", "mr-IN",
    "gu-IN", "pa-IN", "od-IN", "en-IN", "as-IN",
)


def _key() -> str:
    k = os.environ.get("SARVAM_API_KEY")
    if not k:
        raise RuntimeError("SARVAM_API_KEY is not set. Copy .env.example to .env or export it.")
    return k


TOOLS = [
    {
        "name": "transcribe",
        "description": (
            "Transcribe Indian-language or Hinglish audio with Saaras v4 (codemix) "
            "and return both the raw transcript and a digits-normalised copy. "
            "Use a JSON keyterms list (max 50) for product/brand words."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Audio file path the user provided"},
                "language_code": {"type": "string", "enum": list(LANG_CODES), "default": "hi-IN"},
                "mode": {"type": "string", "enum": ["codemix", "transcribe"], "default": "codemix"},
                "keyterms": {"type": "boolean", "default": True},
            },
            "required": ["path"],
        },
    },
    {
        "name": "translate",
        "description": (
            "Translate with sarvam-translate:v1. Best into Indian languages "
            "(uc07: 8 of 10, chrF++ 51.8). Into English, Gemini/Claude/OpenAI "
            "led by 6–12 chrF++. Never use Mayura for decimal crore amounts."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "source_language_code": {"type": "string", "enum": list(LANG_CODES), "default": "en-IN"},
                "target_language_code": {"type": "string", "enum": list(LANG_CODES)},
            },
            "required": ["text", "target_language_code"],
        },
    },
    {
        "name": "speak",
        "description": (
            "Synthesize speech with Bulbul streaming TTS and write an MP3. "
            "v4-flash starts ~50 ms sooner than v3; no Malayalam/Odia v4 voice."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "target_language_code": {"type": "string", "enum": list(LANG_CODES), "default": "hi-IN"},
                "out": {"type": "string", "description": "Destination MP3 path"},
                "model": {"type": "string", "enum": ["bulbul:v4-flash", "bulbul:v3"], "default": "bulbul:v4-flash"},
            },
            "required": ["text", "out"],
        },
    },
]


def tool_transcribe(args: dict[str, Any]) -> dict[str, Any]:
    path = Path(args["path"])
    if not path.is_file():
        raise FileNotFoundError(f"audio file not found: {path}")
    language = args.get("language_code") or "hi-IN"
    mode = args.get("mode") or "codemix"
    use_kt = args.get("keyterms", True)
    with path.open("rb") as fh:
        data = {"model": "saaras:v4", "mode": mode, "language_code": language}
        if use_kt:
            data["keyterms"] = json.dumps(KEYTERMS)
        raw = sarvam_post("/speech-to-text", files={"file": (path.name, fh, "audio/wav")}, data=data)
    if raw.get("_error"):
        raise RuntimeError(f"Saaras HTTP {raw['_error']}: {raw.get('_body', '')[:300]}")
    hyp = raw.get("transcript") or ""
    return {"transcript": hyp, "transcript_digits": normalize(hyp),
            "language_code": raw.get("language_code") or language}


def tool_translate(args: dict[str, Any]) -> dict[str, Any]:
    body = {
        "input": args["text"],
        "source_language_code": args.get("source_language_code") or "en-IN",
        "target_language_code": args["target_language_code"],
        "model": "sarvam-translate:v1",
    }
    raw = sarvam_post("/translate", body)
    if raw.get("_error"):
        raise RuntimeError(f"Translate HTTP {raw['_error']}: {raw.get('_body', '')[:300]}")
    return {"translated_text": raw.get("translated_text") or "",
            "source_language_code": body["source_language_code"],
            "target_language_code": body["target_language_code"]}


def tool_speak(args: dict[str, Any]) -> dict[str, Any]:
    dest = Path(args["out"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    model = args.get("model") or "bulbul:v4-flash"
    language = args.get("target_language_code") or "hi-IN"
    speaker = None if model == "bulbul:v4-flash" else "shubh"
    body = {"text": args["text"], "target_language_code": language, "model": model,
            "output_audio_codec": "mp3"}
    if speaker:
        body["speaker"] = speaker
    r = requests.post(SARVAM + "/text-to-speech/stream",
                      headers={"api-subscription-key": _key()},
                      json=body, stream=True, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"Bulbul HTTP {r.status_code}: {r.text[:300]}")
    buf = b"".join(r.iter_content(4096))
    dest.write_bytes(buf)
    return {"path": str(dest), "bytes": len(buf), "model": model, "language_code": language}


HANDLERS = {"transcribe": tool_transcribe, "translate": tool_translate, "speak": tool_speak}


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    """Return a JSON-RPC response, or None for notifications."""
    mid = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}
    if method is None:
        return _err(mid, -32600, "Invalid Request")
    if method == "initialize":
        return _ok(mid, {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return _ok(mid, {})
    if method == "tools/list":
        return _ok(mid, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        fn = HANDLERS.get(name)
        if fn is None:
            return _err(mid, -32602, f"unknown tool: {name}")
        try:
            result = fn(params.get("arguments") or {})
        except Exception as exc:
            return _ok(mid, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
        return _ok(mid, {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                         "isError": False})
    return _err(mid, -32601, f"Method not found: {method}")


def _ok(mid: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _err(mid: Any, code: int, msg: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": msg}}


def serve() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            sys.stdout.write(json.dumps(_err(None, -32700, str(exc))) + "\n")
            sys.stdout.flush()
            continue
        reply = handle(message)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    serve()
