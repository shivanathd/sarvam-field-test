"""Transcribe Indian-language audio with Saaras v4, then turn number words into digits.

Usage (from the repo root, after `cp .env.example .env`):

    python skills/indic-stt-with-digits/transcribe.py path/to/call.wav --lang hi-IN
    python skills/indic-stt-with-digits/transcribe.py path/to/call.wav --lang hi-IN --no-keyterms

Reads `SARVAM_API_KEY` from the environment (or a repo-root `.env`). Does not
print or log the key. This script calls a paid API — do not import it from tests.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from common.bench import sarvam_post  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalize_digits import normalize  # noqa: E402

# Same rule as uc01: one fixed product/brand list a bank would configure once.
# v4 accepts at most 50 strings, each at most 64 characters, as a JSON array.
# v3 rejects keyterms with HTTP 400. Never put per-utterance gold values here.
KEYTERMS = [
    "UPI", "UPI PIN", "EMI", "KYC", "IFSC", "NEFT", "RTGS", "IMPS", "OTP", "ATM",
    "debit card", "credit card", "card ending", "last four digits", "reference number",
    "UTR", "transaction", "bounce charge", "cheque", "auto debit", "due amount",
    "installment", "loan", "account", "balance", "salary", "PhonePe", "Google Pay",
    "GPay", "Paytm", "Airtel", "Jio", "Vi", "BSNL", "postpaid", "prepaid",
    "recharge", "plan", "data", "port", "UPC code", "international roaming",
    "add-on", "health insurance", "claim number", "premium", "policy",
    "surveyor", "settle", "approve",
]
assert len(KEYTERMS) <= 50 and all(len(k) <= 64 for k in KEYTERMS)


def transcribe(path: Path, language_code: str, model: str = "saaras:v4",
               mode: str = "codemix", keyterms: list[str] | None = None) -> dict:
    """Call `/speech-to-text` the same way uc01 does, then run ITN on the transcript."""
    if not os.environ.get("SARVAM_API_KEY"):
        raise SystemExit("SARVAM_API_KEY is not set. Copy .env.example to .env or export it.")
    t = time.time()
    with path.open("rb") as fh:
        data = {"model": model, "mode": mode, "language_code": language_code}
        if keyterms:
            data["keyterms"] = json.dumps(keyterms)
        raw = sarvam_post("/speech-to-text", files={"file": (path.name, fh, "audio/wav")}, data=data)
    ms = (time.time() - t) * 1000
    if raw.get("_error"):
        raise SystemExit(f"Saaras HTTP {raw['_error']}: {raw.get('_body', '')[:300]}")
    hyp = raw.get("transcript") or ""
    return {
        "transcript": hyp,
        "transcript_digits": normalize(hyp),
        "language_code": raw.get("language_code") or language_code,
        "model": model,
        "mode": mode,
        "keyterms": bool(keyterms),
        "ms": round(ms, 1),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("audio", type=Path, help="WAV/MP3/file path (no default local path)")
    p.add_argument("--lang", default="hi-IN", help="Sarvam language_code, e.g. hi-IN, ta-IN, od-IN")
    p.add_argument("--model", default="saaras:v4")
    p.add_argument("--mode", default="codemix", choices=("codemix", "transcribe"))
    p.add_argument("--no-keyterms", action="store_true",
                   help="Omit the 50-term product list (v4 only; v3 cannot take keyterms)")
    args = p.parse_args(argv)
    if not args.audio.is_file():
        raise SystemExit(f"audio file not found: {args.audio}")
    kt = None if args.no_keyterms else KEYTERMS
    result = transcribe(args.audio, args.lang, model=args.model, mode=args.mode, keyterms=kt)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
