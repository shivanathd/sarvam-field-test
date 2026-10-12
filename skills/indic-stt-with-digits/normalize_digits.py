"""Inverse text normalisation: Indian-language number words -> ASCII digits.

Saaras v4 often writes amounts as words (uc01). This module is a practical ITN
layer for Hindi, Hinglish, English digit-spelling, and common Bengali / Tamil /
Malayalam / Kannada / Marathi forms. It is not a perfect ceiling parser — see
SKILL.md for what the benchmark measured.

No network. Safe to import from tests.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

# Scales. Value is the multiplier applied to the current group.
SCALES: dict[str, int] = {
    "hundred": 100, "sau": 100, "so": 100,
    "सौ": 100, "सवे": 100, "शंभर": 100, "শো": 100, "শত": 100,
    "நூறு": 100, "னூறு": 100, "நூற்றி": 100,
    "നൂറ്": 100, "നൂറു": 100,
    "ನೂರು": 100, "ನೂರ": 100,
    "thousand": 1_000, "hazar": 1_000, "hazaar": 1_000, "hazār": 1_000,
    "हजार": 1_000, "हज़ार": 1_000, "हज़ार": 1_000,
    "হাজার": 1_000, "ஆயிரம்": 1_000, "ஆயிரத்து": 1_000,
    "ആയിരം": 1_000, "ആയിരത്തി": 1_000, "ಸಾವಿರ": 1_000, "ಸಾವಿರದ": 1_000,
    "lakh": 100_000, "lac": 100_000, "lakhs": 100_000,
    "लाख": 100_000, "লক্ষ": 100_000, "লাখ": 100_000,
    "லட்சம்": 100_000, "ലക്ഷം": 100_000, "ಲಕ್ಷ": 100_000,
    "crore": 10_000_000, "cr": 10_000_000, "crores": 10_000_000,
    "करोड़": 10_000_000, "करोड": 10_000_000, "कोटी": 10_000_000,
    "কোটি": 10_000_000, "கோடி": 10_000_000, "കോടി": 10_000_000, "ಕೋಟಿ": 10_000_000,
}

# Fractional prefixes used in spoken Indian amounts (uc11v).
FRACTIONS = {
    "सवा", "sava", "डेढ़", "देढ़", "dedh", "deidh",
    "ढाई", "dhai", "पौने", "paune", "साढ़े", "sadhe", "saadhe",
}

# Skip tokens inside a number run (English "and"). Currency is left in the text.
SKIPS = {"and", "और", "एंड"}
CURRENCY = {"रुपये", "रुपए", "रुपया", "rupees", "rupee", "rs", "inr",
            "টাকা", "ரூபாய்", "രൂപ", "ರೂಪಾಯಿ"}

ONES: dict[str, int] = {}


def _add(words: Iterable[str], value: int) -> None:
    for w in words:
        if w:
            ONES[w] = value


# English + common Hinglish romanisation of Hindi digits (PIN / OTP / last-4 style).
_add("zero sunna shoonya shunya".split(), 0)
_add("one ek".split(), 1)
_add("two do".split(), 2)
_add("three teen tin".split(), 3)
_add("four char chaar".split(), 4)
_add("five paanch panch".split(), 5)
_add("six chhe cheh".split(), 6)
_add("seven saat".split(), 7)
_add("eight aath ath".split(), 8)
_add("nine nau".split(), 9)
_add("ten das".split(), 10)
_add("eleven gyarah gyaarah".split(), 11)
_add("twelve barah baarah".split(), 12)
_add("thirteen terah".split(), 13)
_add("fourteen chaudah".split(), 14)
_add("fifteen pandrah".split(), 15)
_add("sixteen solah".split(), 16)
_add("seventeen satrah".split(), 17)
_add("eighteen atharah".split(), 18)
_add("nineteen unnees unnis".split(), 19)
_add("twenty bees".split(), 20)
_add("thirty tees".split(), 30)
_add("forty chalis chaalis".split(), 40)
_add("fifty pachas".split(), 50)
_add("sixty saath".split(), 60)
_add("seventy sattar".split(), 70)
_add("eighty assi".split(), 80)
_add("ninety nabbe".split(), 90)

# Spoken English digits as Saaras sometimes writes them in Devanagari (uc01 hi02).
_add("ज़ीरो जिरो ज़ीरो".split(), 0)
_add("वन वान".split(), 1)
_add("टू टूू".split(), 2)
_add("थ्री थरी".split(), 3)
_add("फोर फ़ोर फोर".split(), 4)
_add("फाइव फ़ाइव".split(), 5)
_add("सिक्स".split(), 6)
_add("सेवन सेवेन".split(), 7)
_add("एट एइट".split(), 8)
_add("नाइन".split(), 9)

# Hindi 0–99 (standard forms + frequent spelling variants).
_HI = {
    0: "शून्य सुन्ना",
    1: "एक", 2: "दो", 3: "तीन", 4: "चार",
    5: "पाँच पांच पान्च", 6: "छह छः छै", 7: "सात", 8: "आठ", 9: "नौ",
    10: "दस", 11: "ग्यारह ग्यारा", 12: "बारह बारा", 13: "तेरह", 14: "चौदह",
    15: "पंद्रह पन्द्रह", 16: "सोलह", 17: "सत्रह", 18: "अठारह अठारा", 19: "उन्नीस उननीस",
    20: "बीस", 21: "इक्कीस इकीस", 22: "बाईस बाइस", 23: "तेईस तेइस", 24: "चौबीस",
    25: "पच्चीस", 26: "छब्बीस", 27: "सत्ताईस सत्ताइस", 28: "अट्ठाईस अट्ठाइस अठाईस", 29: "उनतीस उनतीस",
    30: "तीस", 31: "इकतीस इकत्तीस", 32: "बत्तीस", 33: "तैंतीस तेतीस", 34: "चौंतीस चोंतीस",
    35: "पैंतीस पेतीस", 36: "छत्तीस", 37: "सैंतीस", 38: "अड़तीस अडतीस", 39: "उनतालीस उनचालिस",
    40: "चालीस", 41: "इकतालीस इकतालीस", 42: "बयालीस", 43: "तैंतालीस तेतालीस", 44: "चवालीस चौवालीस",
    45: "पैंतालीस", 46: "छियालीस", 47: "सैंतालीस", 48: "अड़तालीस अडतालीस", 49: "उनचास उनचास",
    50: "पचास", 51: "इक्यावन इक्यावन", 52: "बावन", 53: "तिरपन तिरेपन", 54: "चौवन चौवन",
    55: "पचपन", 56: "छप्पन", 57: "सत्तावन", 58: "अट्ठावन अठावन", 59: "उनसठ",
    60: "साठ", 61: "इकसठ", 62: "बासठ", 63: "तिरसठ तिरसठ", 64: "चौंसठ",
    65: "पैंसठ", 66: "छियासठ", 67: "सड़सठ सडसठ", 68: "अड़सठ अडसठ", 69: "उनहत्तर उनहतर",
    70: "सत्तर", 71: "इकहत्तर इकहतर", 72: "बहत्तर", 73: "तिहत्तर", 74: "चौहत्तर",
    75: "पचहत्तर", 76: "छिहत्तर", 77: "सतहत्तर", 78: "अठहत्तर", 79: "उनासी उनहत्तर",
    80: "अस्सी", 81: "इक्यासी", 82: "बयासी", 83: "तिरासी", 84: "चौरासी",
    85: "पचासी पचासी", 86: "छियासी", 87: "सतासी", 88: "अठासी", 89: "नवासी नब्बासी",
    90: "नब्बे", 91: "इक्यानवे इक्यानबे इक्यान्नवे", 92: "बानवे बानबे",
    93: "तिरानवे तिरानबे", 94: "चौरानवे चौरानबे", 95: "पचानवे पचानबे",
    96: "छियानवे छियानबे", 97: "सत्तानवे सत्तानबे", 98: "अट्ठानवे अट्ठानबे",
    99: "निन्यानवे निन्यान्नवे निन्यानबे",
}
for _n, _ws in _HI.items():
    _add(_ws.split(), _n)

# Bengali 0–20 + tens (enough for amounts; agglutinated thousands listed below).
_BN = {
    0: "শূন্য", 1: "এক", 2: "দুই দুটো", 3: "তিন", 4: "চার", 5: "পাঁচ",
    6: "ছয় ছয়", 7: "সাত", 8: "আট", 9: "নয় নয়", 10: "দশ",
    11: "এগারো", 12: "বারো", 13: "তেরো", 14: "চোদ্দ", 15: "পনেরো",
    16: "ষোল", 17: "সতেরো", 18: "আঠারো", 19: "উনিশ", 20: "বিশ",
    30: "ত্রিশ", 40: "চল্লিশ", 50: "পঞ্চাশ", 60: "ষাট", 70: "সত্তর",
    80: "আশি", 90: "নব্বই", 100: "একশ একশো",
}
for _n, _ws in _BN.items():
    _add(_ws.split(), _n)

# Tamil 0–20 + tens + common hundreds (uc01 example: நானூற்றி எழுபத்தி ரெண்டு = 472).
_TA = {
    1: "ஒன்று ஒரு", 2: "இரண்டு ரெண்டு", 3: "மூன்று", 4: "நான்கு நாலு",
    5: "ஐந்து", 6: "ஆறு", 7: "ஏழு", 8: "எட்டு", 9: "ஒன்பது", 10: "பத்து",
    11: "பதினொன்று", 12: "பன்னிரண்டு", 13: "பதிமூன்று", 14: "பதினான்கு",
    15: "பதினைந்து", 16: "பதினாறு", 17: "பதினேழு", 18: "பதினெட்டு பதினெண்",
    19: "பத்தொன்பது", 20: "இருபது இருபத்தி", 30: "முப்பது முப்பத்தி",
    40: "நாற்பது நாற்பத்தி", 50: "ஐம்பது ஐம்பத்தி", 60: "அறுபது அறுபத்தி",
    70: "எழுபது எழுபத்தி", 80: "எண்பது எண்பத்தி", 90: "தொண்ணூறு தொண்ணூற்றி",
    100: "நூறு", 200: "இருநூறு இருநூற்றி", 300: "முந்நூறு", 400: "நானூறு நானூற்றி",
    500: "ஐநூறு", 600: "அறுநூறு", 700: "எழுநூறு", 800: "எண்ணூறு", 900: "தொள்ளாயிரம்",
}
for _n, _ws in _TA.items():
    _add(_ws.split(), _n)

# Malayalam (uc01: പതിനെണ്ണായിരം രൂപ = ₹18,000).
_ML = {
    1: "ഒന്ന് ഒരു", 2: "രണ്ട് രണ്ടു", 3: "മൂന്ന്", 4: "നാല്", 5: "അഞ്ച്",
    6: "ആറ്", 7: "ഏഴ്", 8: "എട്ട്", 9: "ഒമ്പത് ഒൻപത്", 10: "പത്ത്",
    11: "പതിനൊന്ന്", 12: "പന്ത്രണ്ട്", 18: "പതിനെട്ട് പതിനെൺ",
    20: "ഇരുപത് ഇരുപത്തി", 100: "നൂറ്", 1000: "ആയിരം",
}
for _n, _ws in _ML.items():
    _add(_ws.split(), _n)

# Kannada 0–10 + scales already in SCALES.
_KN = {
    1: "ಒಂದು", 2: "ಎರಡು", 3: "ಮೂರು", 4: "ನಾಲ್ಕು", 5: "ಐದು",
    6: "ಆರು", 7: "ಏಳು", 8: "ಎಂಟು", 9: "ಒಂಬತ್ತು", 10: "ಹತ್ತು",
    18: "ಹದಿನೆಂಟು", 100: "ನೂರು",
}
for _n, _ws in _KN.items():
    _add(_ws.split(), _n)

# Agglutinated thousands that do not split on spaces (the forms uc01 actually saw).
AGGLUTINATED: dict[str, int] = {
    "പതിനെണ്ണായിരം": 18_000, "പതിനെട്ടായിരം": 18_000,
    "പതിനാറായിരം": 16_000, "പതിനായിരം": 10_000,
    "இரண்டாயிரம்": 2_000, "மூன்றாயிரம்": 3_000, "நான்காயிரம்": 4_000,
    "ஐந்தாயிரம்": 5_000, "பத்தாயிரம்": 10_000, "பதினெண்ணாயிரம்": 18_000,
    "பதினாறாயிரம்": 16_000, "லட்சம்": 100_000,
    "ಹದಿನೆಂಟುಸಾವಿರ": 18_000, "ಹತ್ತುಸಾವಿರ": 10_000,
    "আঠারোহাজার": 18_000,
}


def fold_indic_digits(text: str) -> str:
    """Map Unicode decimal digits (Nd) to ASCII. Leaves Arabic-Indic Eastern digits too."""
    return "".join(str(unicodedata.digit(c)) if unicodedata.category(c) == "Nd" else c for c in text or "")


def _norm_token(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "")
    s = s.replace("\u200c", "").replace("\u200d", "")
    return s.casefold().strip(".,!?;:\"'()[]{}।॥")


def _lexicon() -> dict[str, tuple[str, int]]:
    """kind is 'num' | 'scale' | 'frac' | 'skip' | 'agg'."""
    lex: dict[str, tuple[str, int]] = {}
    for w, n in ONES.items():
        lex[_norm_token(w)] = ("num", n)
    for w, n in SCALES.items():
        lex[_norm_token(w)] = ("scale", n)
    for w in FRACTIONS:
        lex[_norm_token(w)] = ("frac", 0)
    for w in SKIPS:
        lex[_norm_token(w)] = ("skip", 0)
    for w, n in AGGLUTINATED.items():
        lex[_norm_token(w)] = ("agg", n)
    return lex


_LEX = _lexicon()
_LEX_KEYS = sorted(_LEX, key=len, reverse=True)
# Split on whitespace and a small punctuation set only. Do NOT use \w/\W —
# Devanagari matras, nuktas and virama are "non-word" and would shatter बारह.
_WORD_RE = re.compile(r"₹|\d+(?:[,.]\d+)*|[^\s₹.,!?;:\"'()\[\]{}।॥]+|[.,!?;:।॥]")


def _tokens(text: str) -> list[str]:
    return [m.group(0) for m in _WORD_RE.finditer(text)]


def _classify(tok: str) -> tuple[str, int] | None:
    raw = tok.strip()
    if re.fullmatch(r"\d+(?:,\d+)*", raw or ""):
        return ("num", int(raw.replace(",", "")))
    key = _norm_token(raw)
    if key in _LEX:
        return _LEX[key]
    for k in _LEX_KEYS:
        if len(k) >= 4 and key.startswith(k) and _LEX[k][0] in {"agg", "num", "scale"}:
            return _LEX[k]
    return None


def _apply_frac(name: str, number: int, scale: int) -> int:
    """Spoken Indian fractions (uc11v): पौने दो हज़ार = 1750, साढ़े चार हज़ार = 4500."""
    key = _norm_token(name)
    if key in {"पौने", "paune"}:
        return int((number - 0.25) * scale)
    if key in {"साढ़े", "sadhe", "saadhe"}:
        return int((number + 0.5) * scale)
    if key in {"सवा", "sava"}:
        return int(1.25 * (number or 1) * scale)
    if key in {"डेढ़", "देढ़", "dedh", "deidh"}:
        return int(1.5 * scale)
    if key in {"ढाई", "dhai"}:
        return int(2.5 * scale)
    return number * scale


def _place_value(items: list[tuple[str, int, str]]) -> int | None:
    """Indian/English place-value over a run of (kind, value, original)."""
    total = 0
    current = 0
    frac_name: str | None = None
    saw = False
    for kind, val, orig in items:
        if kind == "skip":
            continue
        if kind == "frac":
            frac_name = orig
            saw = True
            continue
        if kind == "agg":
            group = _apply_frac(frac_name, 1, val) if frac_name else val
            frac_name = None
            total += current + group
            current = 0
            saw = True
            continue
        if kind == "num":
            current += val
            saw = True
            continue
        if kind == "scale":
            if frac_name:
                group = _apply_frac(frac_name, current, val)
                frac_name = None
                current = 0
            else:
                group = (current or 1) * val
                current = 0
            if val >= 1000:
                total += group
            else:
                current = group
            saw = True
    if frac_name and current:
        current = _apply_frac(frac_name, current, 1)
    total += current
    return total if saw else None


def _digit_spell(items: list[tuple[str, int, str]]) -> int | None:
    """Concatenate single digits: 'seven three zero six' / 'सेवन थ्री ज़ीरो सिक्स' -> 7306."""
    digits = []
    for kind, val, _ in items:
        if kind == "skip":
            continue
        if kind != "num" or val > 9:
            return None
        digits.append(str(val))
    if len(digits) < 2:
        return None
    return int("".join(digits))


def _run_value(items: list[tuple[str, int, str]]) -> int | None:
    if not items:
        return None
    kinds = {k for k, _, _ in items if k != "skip"}
    nums = [v for k, v, _ in items if k == "num"]
    if kinds <= {"num", "skip"} and nums and all(v <= 9 for v in nums) and len(nums) >= 2:
        return _digit_spell(items)
    return _place_value(items)


def normalize_number_words(text: str) -> str:
    """Replace spoken number runs with ASCII digits. Leaves the rest of the text."""
    if not text:
        return text
    text = fold_indic_digits(unicodedata.normalize("NFC", text))
    toks = _tokens(text)
    out: list[str] = []
    i = 0
    while i < len(toks):
        cls = _classify(toks[i])
        if cls is None or cls[0] == "skip":
            out.append(toks[i])
            i += 1
            continue
        run: list[tuple[str, int, str]] = []
        j = i
        while j < len(toks):
            t = toks[j]
            if t.isspace():
                run.append(("skip", 0, t))
                j += 1
                continue
            if _norm_token(t) in {_norm_token(c) for c in CURRENCY}:
                break
            c = _classify(t)
            if c is None:
                break
            run.append((c[0], c[1], t))
            j += 1
            if c[0] == "skip" and len([x for x in run if x[0] != "skip"]) == 0:
                break
        useful = [(k, v, o) for k, v, o in run if k != "skip" or _norm_token(o) in {_norm_token(s) for s in SKIPS}]
        # require at least one real number token
        if not any(k in {"num", "agg", "scale", "frac"} for k, _, _ in useful):
            out.append(toks[i])
            i += 1
            continue
        # a single scale word with no number ("हज़ार") is left alone
        if all(k in {"scale", "skip"} for k, _, _ in useful) and not any(k == "agg" for k, _, _ in useful):
            out.append(toks[i])
            i += 1
            continue
        value = _run_value(useful)
        if value is None:
            out.append(toks[i])
            i += 1
            continue
        # preserve a leading rupee sign if it sat immediately before the run
        prefix = ""
        if out and out[-1] == "₹":
            prefix = out.pop()
        out.append(prefix + str(value))
        i = j
    # re-join: tokens already include punctuation; glue digits to following punctuation
    return _rejoin(out)


def _rejoin(parts: list[str]) -> str:
    s = ""
    for p in parts:
        if not s:
            s = p
            continue
        if p in {".", ",", "!", "?", ";", ":", "।", "॥"} or p.startswith("'"):
            s += p
        elif s[-1].isspace() or p[:1].isspace():
            s += p
        elif p.isdigit() or s[-1].isdigit() or p[0] in {"₹"}:
            s += " " + p
        elif re.match(r"\W", p):
            s += p
        else:
            s += " " + p
    return re.sub(r" {2,}", " ", s).strip()


def normalize(text: str) -> str:
    """Public entry: Indic digits then number words."""
    return normalize_number_words(text)
