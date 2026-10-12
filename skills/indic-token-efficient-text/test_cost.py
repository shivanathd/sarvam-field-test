"""Offline tests for token-tax math. No API calls, no tokenizer download."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from count_tokens import (  # noqa: E402
    CHAT_OVERHEAD_TOKENS,
    MACRO_TAX,
    canonical_lang,
    compare_macro,
    cost_inr,
    estimate_tokens,
)


class LangNames(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(canonical_lang("hi"), "Hindi")
        self.assertEqual(canonical_lang("od-IN".split("-")[0]), "Odia")
        self.assertEqual(canonical_lang("Tamil"), "Tamil")


class Estimate(unittest.TestCase):
    def test_empty_is_zero(self):
        rec = estimate_tokens("", "Hindi")
        self.assertEqual(rec["tokens"], 0)
        self.assertEqual(rec["method"], "uc12_char_rate")

    def test_hindi_rate_matches_uc12(self):
        # 117.2 chars -> 31.3 tokens in the published table
        rec = estimate_tokens("x" * 1172, "Hindi")
        self.assertAlmostEqual(rec["tokens"] / 10, 31.3, places=1)

    def test_unknown_language(self):
        with self.assertRaises(SystemExit):
            estimate_tokens("hi", "Klingon")


class Cost(unittest.TestCase):
    def test_overhead_and_price(self):
        c = cost_inr(1_000_000, "in")
        self.assertEqual(c["chat_overhead_tokens"], CHAT_OVERHEAD_TOKENS)
        self.assertAlmostEqual(c["inr"], (1_000_000 + 14) * 15 / 1e6, places=6)

    def test_output_is_4x_input(self):
        inp = cost_inr(10_000, "in")
        out = cost_inr(10_000, "out")
        self.assertAlmostEqual(out["inr"] / inp["inr"], 4.0, places=5)


class MacroTax(unittest.TestCase):
    def test_order(self):
        self.assertLess(MACRO_TAX["sarvam"], MACRO_TAX["gemini"])
        self.assertLess(MACRO_TAX["gemini"], MACRO_TAX["openai"])
        self.assertLess(MACRO_TAX["openai"], MACRO_TAX["claude"])
        self.assertLess(MACRO_TAX["claude"], MACRO_TAX["qwen3"])

    def test_compare_scales(self):
        other = compare_macro(155)
        self.assertAlmostEqual(other["sarvam"], 155)
        self.assertAlmostEqual(other["qwen3"], 155 * 5.89 / 1.55, places=2)


if __name__ == "__main__":
    unittest.main()
