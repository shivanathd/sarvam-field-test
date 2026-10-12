"""Offline tests for inverse text normalisation. No API calls."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalize_digits import fold_indic_digits, normalize  # noqa: E402


class FoldDigits(unittest.TestCase):
    def test_devanagari(self):
        self.assertEqual(fold_indic_digits("कुल ₹१,२५०"), "कुल ₹1,250")

    def test_tamil_kannada_bengali(self):
        self.assertEqual(fold_indic_digits("௨௦௨௪"), "2024")
        self.assertEqual(fold_indic_digits("ಪಿನ್ ೫೬೦೦೦೧"), "ಪಿನ್ 560001")
        self.assertEqual(fold_indic_digits("৩৪৫ টাকা"), "345 টাকা")

    def test_ascii_unchanged(self):
        self.assertEqual(fold_indic_digits("card 4821"), "card 4821")


class HindiAmounts(unittest.TestCase):
    def test_uc01_hi02_amount(self):
        # README / uc01 example: v4 wrote the amount as words
        self.assertEqual(normalize("बारह हज़ार चार सौ निन्यानवे"), "12499")

    def test_uc01_digit_spelling(self):
        self.assertEqual(normalize("सेवन थ्री ज़ीरो सिक्स"), "7306")

    def test_lakh_and_thousand(self):
        self.assertEqual(normalize("एक लाख पच्चीस हज़ार"), "125000")

    def test_four_hundred(self):
        self.assertIn("400", normalize("चार सौ रुपये"))


class HinglishAndEnglish(unittest.TestCase):
    def test_barah_hazaar(self):
        self.assertEqual(normalize("barah hazar"), "12000")

    def test_english_place_value(self):
        self.assertEqual(normalize("twelve thousand four hundred"), "12400")

    def test_digit_spelling_english(self):
        self.assertEqual(normalize("seven three zero six"), "7306")


class Fractions(unittest.TestCase):
    # uc11v spoken fractions: keep the words and let a later step resolve them,
    # but once they are in the transcript we should land on the gold amount.
    def test_paune_do_hazaar(self):
        self.assertEqual(normalize("पौने दो हज़ार"), "1750")

    def test_sadhe_char_hazaar(self):
        self.assertEqual(normalize("साढ़े चार हज़ार"), "4500")

    def test_dhai_hazaar(self):
        self.assertEqual(normalize("ढाई हज़ार"), "2500")

    def test_sava_sau(self):
        self.assertEqual(normalize("sava sau"), "125")


class OtherLanguages(unittest.TestCase):
    def test_malayalam_18000(self):
        # uc01: '₹18,000' came back as പതിനെണ്ണായിരം രൂപ
        self.assertIn("18000", normalize("പതിനെണ്ണായിരം രൂപ"))

    def test_tamil_472(self):
        self.assertEqual(normalize("நானூற்றி எழுபத்தி ரெண்டு"), "472")

    def test_bengali_thousand(self):
        self.assertEqual(normalize("আঠারো হাজার"), "18000")


class Passthrough(unittest.TestCase):
    def test_already_digits(self):
        self.assertIn("12499", normalize("मेरा EMI 12,499 रुपये है"))

    def test_empty(self):
        self.assertEqual(normalize(""), "")

    def test_no_numbers(self):
        self.assertIn("debit card", normalize("mera debit card block kar do"))


if __name__ == "__main__":
    unittest.main()
