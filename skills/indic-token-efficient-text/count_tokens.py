"""Count tokens and estimate Sarvam-105B INR cost for Indian-language text (uc12).

Two modes, neither calls a paid API by default:

1. Local HuggingFace `tokenizer.json` (byte-identical for sarvam-30b and
   sarvam-105b). Pass `--tokenizer path` or set `SARVAM_TOKENIZER`.
2. Published uc12 table: tokens ≈ characters × (tokens/char for that language).
   Clearly labelled as an estimate.

    python skills/indic-token-efficient-text/count_tokens.py --text "नमस्ते भारत" --lang Hindi
    python skills/indic-token-efficient-text/count_tokens.py --file notes.txt --lang Tamil --cost
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# List prices used in this repo (October 2026). API prompt_tokens = HF count + 14.
SARVAM_IN_INR = 15 / 1e6
SARVAM_OUT_INR = 60 / 1e6
CHAT_OVERHEAD_TOKENS = 14

# uc12 table: mean characters and Sarvam tokens per sentence (n=100 FLEURS ids).
# tax = tokens / tokens for the same sentence in English.
UC12 = {
    "English":   {"chars": 118.9, "tok": 24.2, "tax": 1.00, "inr_1k_in": 0.3633},
    "Hindi":     {"chars": 117.2, "tok": 31.3, "tax": 1.29, "inr_1k_in": 0.4701},
    "Bengali":   {"chars": 117.6, "tok": 29.9, "tax": 1.23, "inr_1k_in": 0.4485},
    "Marathi":   {"chars": 120.5, "tok": 33.9, "tax": 1.42, "inr_1k_in": 0.5088},
    "Telugu":    {"chars": 121.0, "tok": 35.5, "tax": 1.48, "inr_1k_in": 0.5323},
    "Tamil":     {"chars": 138.4, "tok": 35.3, "tax": 1.49, "inr_1k_in": 0.5297},
    "Gujarati":  {"chars": 116.4, "tok": 36.9, "tax": 1.54, "inr_1k_in": 0.5538},
    "Kannada":   {"chars": 125.6, "tok": 37.0, "tax": 1.54, "inr_1k_in": 0.5556},
    "Malayalam": {"chars": 133.3, "tok": 39.2, "tax": 1.63, "inr_1k_in": 0.5887},
    "Punjabi":   {"chars": 120.3, "tok": 37.4, "tax": 1.54, "inr_1k_in": 0.5616},
    "Odia":      {"chars": 121.2, "tok": 34.1, "tax": 1.42, "inr_1k_in": 0.5118},
    "Assamese":  {"chars": 111.9, "tok": 48.5, "tax": 2.04, "inr_1k_in": 0.7275},
    "Urdu":      {"chars": 117.2, "tok": 36.7, "tax": 1.52, "inr_1k_in": 0.5510},
    "Nepali":    {"chars": 114.2, "tok": 37.4, "tax": 1.55, "inr_1k_in": 0.5605},
    "Sindhi":    {"chars": 106.0, "tok": 49.0, "tax": 2.03, "inr_1k_in": 0.7356},
}

# Average Indic token tax vs English (14 languages), from the uc12 verdict.
MACRO_TAX = {
    "sarvam": 1.55,
    "gemini": 1.89,
    "openai": 2.10,
    "claude": 3.44,
    "qwen3": 5.89,
}

ALIASES = {
    "en": "English", "english": "English",
    "hi": "Hindi", "hindi": "Hindi",
    "bn": "Bengali", "bengali": "Bengali", "bangla": "Bengali",
    "mr": "Marathi", "marathi": "Marathi",
    "te": "Telugu", "telugu": "Telugu",
    "ta": "Tamil", "tamil": "Tamil",
    "gu": "Gujarati", "gujarati": "Gujarati",
    "kn": "Kannada", "kannada": "Kannada",
    "ml": "Malayalam", "malayalam": "Malayalam",
    "pa": "Punjabi", "punjabi": "Punjabi",
    "or": "Odia", "od": "Odia", "odia": "Odia", "oriya": "Odia",
    "as": "Assamese", "assamese": "Assamese",
    "ur": "Urdu", "urdu": "Urdu",
    "ne": "Nepali", "nepali": "Nepali",
    "sd": "Sindhi", "sindhi": "Sindhi",
}


def canonical_lang(name: str) -> str:
    key = name.strip()
    if key in UC12:
        return key
    return ALIASES.get(key.casefold(), key)


def estimate_tokens(text: str, lang: str) -> dict:
    """Character-rate estimate from the uc12 per-language means. Offline."""
    lang = canonical_lang(lang)
    row = UC12.get(lang)
    if not row:
        known = ", ".join(UC12)
        raise SystemExit(f"unknown language {lang!r}. Use one of: {known}")
    n_chars = len(text)
    rate = row["tok"] / row["chars"]
    tokens = n_chars * rate
    return {
        "method": "uc12_char_rate",
        "language": lang,
        "characters": n_chars,
        "tokens": round(tokens, 2),
        "tokens_per_char": round(rate, 4),
        "tax_vs_english": row["tax"],
        "note": "Estimate from uc12 mean tokens/char on FLEURS prose. Not a tokenizer.",
    }


def hf_tokens(text: str, tokenizer_path: Path) -> dict:
    from tokenizers import Tokenizer
    tok = Tokenizer.from_file(str(tokenizer_path))
    n = len(tok.encode(text).ids)
    return {
        "method": "huggingface_tokenizer",
        "tokenizer": str(tokenizer_path),
        "tokens": n,
        "characters": len(text),
        "note": "Open Sarvam 30B/105B tokenizer. API prompt_tokens is this plus 14.",
    }


def cost_inr(tokens: float, direction: str = "in", sentences: int = 1) -> dict:
    price = SARVAM_IN_INR if direction == "in" else SARVAM_OUT_INR
    billed = tokens + CHAT_OVERHEAD_TOKENS
    return {
        "direction": "input" if direction == "in" else "output",
        "list_price_inr_per_million": 15 if direction == "in" else 60,
        "chat_overhead_tokens": CHAT_OVERHEAD_TOKENS,
        "billed_tokens": round(billed, 2),
        "inr": round(billed * price, 6),
        "inr_per_1k_similar": round(billed * price * 1000 / max(1, sentences), 4),
    }


def compare_macro(tokens_sarvam: float) -> dict:
    """What the same Indic text would cost in tokens on other tokenizers (macro tax)."""
    out = {}
    for name, tax in MACRO_TAX.items():
        out[name] = round(tokens_sarvam * (tax / MACRO_TAX["sarvam"]), 2)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--text", help="Literal text (not a file path)")
    src.add_argument("--file", type=Path, help="UTF-8 text file")
    p.add_argument("--lang", default="Hindi")
    p.add_argument("--tokenizer", type=Path, default=None,
                   help="Path to sarvamai tokenizer.json (or $SARVAM_TOKENIZER)")
    p.add_argument("--cost", action="store_true", help="Add Sarvam-105B list-price INR")
    args = p.parse_args(argv)
    text = args.text if args.text is not None else args.file.read_text(encoding="utf-8")
    tok_path = args.tokenizer or (Path(os.environ["SARVAM_TOKENIZER"]) if os.environ.get("SARVAM_TOKENIZER") else None)
    if tok_path and tok_path.is_file():
        counted = hf_tokens(text, tok_path)
        counted["language"] = canonical_lang(args.lang)
        row = UC12.get(counted["language"])
        if row:
            counted["tax_vs_english"] = row["tax"]
    else:
        counted = estimate_tokens(text, args.lang)
    counted["macro_token_tax_vs_english"] = MACRO_TAX
    counted["same_text_tokens_if_taxed_like"] = compare_macro(float(counted["tokens"]))
    if args.cost:
        counted["cost"] = {
            "input": cost_inr(float(counted["tokens"]), "in"),
            "output": cost_inr(float(counted["tokens"]), "out"),
        }
    json.dump(counted, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
