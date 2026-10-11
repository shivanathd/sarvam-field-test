"""40 India-specific coding tasks: English spec, signature, reference solution, hidden tests.

Tests are (call_expression, expected_expression) pairs evaluated after the candidate code.
`_dt` is the datetime module; expected 'RAISES:ValueError' means the call must raise ValueError.
All IDs (Aadhaar-format, PAN, GSTIN, CIN, card numbers) are synthetic test values, not real people/companies.
"""

T = []


def task(id, func, signature, spec, ref, tests):
    T.append(dict(id=id, func=func, signature=signature, spec=spec.strip(), ref=ref.strip() + "\n", tests=tests))


VERHOEFF_REF = '''
_D = [[0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],
      [4,0,1,2,3,9,5,6,7,8],[5,9,8,7,6,0,4,3,2,1],[6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],
      [8,7,6,5,9,3,2,1,0,4],[9,8,7,6,5,4,3,2,1,0]]
_P = [[0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],[8,9,1,6,0,4,3,5,2,7],
      [9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],[2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]]
_INV = [0,4,3,2,1,5,6,7,8,9]
def _verhoeff_ok(num):
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0
'''

task(1, "is_valid_aadhaar", "def is_valid_aadhaar(number: str) -> bool:", """
Write a function that checks whether a string is a valid Aadhaar-format number.
Rules: remove all spaces first. The result must be exactly 12 ASCII digits. The first digit must not be 0 or 1.
The last digit is a Verhoeff checksum digit: the whole 12-digit number must pass the standard Verhoeff check.
Return True if all rules hold, otherwise False (never raise an exception).
""", VERHOEFF_REF + '''
def is_valid_aadhaar(number):
    s = number.replace(" ", "")
    return len(s) == 12 and s.isascii() and s.isdigit() and s[0] not in "01" and _verhoeff_ok(s)
''', [
    ("is_valid_aadhaar('999900001231')", "True"),
    ("is_valid_aadhaar('9999 0000 1231')", "True"),
    ("is_valid_aadhaar('999900001232')", "False"),
    ("is_valid_aadhaar('234567890124')", "True"),
    ("is_valid_aadhaar('134567890123')", "False"),
    ("is_valid_aadhaar('099900001231')", "False"),
    ("is_valid_aadhaar('99990000123')", "False"),
    ("is_valid_aadhaar('9999000012310')", "False"),
    ("is_valid_aadhaar('9999-0000-1231')", "False"),
    ("is_valid_aadhaar('')", "False"),
    ("is_valid_aadhaar('99990000123a')", "False"),
    ("is_valid_aadhaar('२३४५६७८९०१२४')", "False"),
])

task(2, "verhoeff_check_digit", "def verhoeff_check_digit(partial: str) -> int:", """
Write a function that takes a string of ASCII digits (any length >= 1) and returns the Verhoeff check digit (an int 0-9)
that must be appended to it so that the full number passes the Verhoeff checksum. This is how the 12th digit of an
Aadhaar-format number is generated from the first 11 digits. If the input is empty or contains anything other than
digits, raise ValueError.
""", VERHOEFF_REF + '''
def verhoeff_check_digit(partial):
    if not partial or not (partial.isascii() and partial.isdigit()):
        raise ValueError(partial)
    c = 0
    for i, ch in enumerate(reversed(partial)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return _INV[c]
''', [
    ("verhoeff_check_digit('236')", "3"),
    ("verhoeff_check_digit('12345')", "1"),
    ("verhoeff_check_digit('99990000123')", "1"),
    ("verhoeff_check_digit('23456789012')", "4"),
    ("verhoeff_check_digit('0')", "4"),
    ("verhoeff_check_digit('142857')", "0"),
    ("verhoeff_check_digit('75872')", "2"),
    ("verhoeff_check_digit('')", "RAISES:ValueError"),
    ("verhoeff_check_digit('12a4')", "RAISES:ValueError"),
    ("verhoeff_check_digit('12 4')", "RAISES:ValueError"),
])

task(3, "pan_entity_type", "def pan_entity_type(pan: str) -> str | None:", """
Write a function that validates an Indian PAN (Permanent Account Number) and returns the holder type.
First strip surrounding whitespace and convert to uppercase. A valid PAN is 10 characters: 5 letters, 4 digits, 1 letter.
The 4th character gives the holder type: P = "Individual", C = "Company", H = "HUF", F = "Firm", A = "AOP",
T = "Trust", B = "BOI", L = "Local Authority", J = "Artificial Juridical Person", G = "Government".
Return the holder type string exactly as written above. If the format is wrong or the 4th character is not one of
these letters, return None.
""", '''
import re
_TYPES = {"P": "Individual", "C": "Company", "H": "HUF", "F": "Firm", "A": "AOP", "T": "Trust", "B": "BOI",
          "L": "Local Authority", "J": "Artificial Juridical Person", "G": "Government"}
def pan_entity_type(pan):
    s = pan.strip().upper()
    if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", s):
        return None
    return _TYPES.get(s[3])
''', [
    ("pan_entity_type('ABCPE1234F')", "'Individual'"),
    ("pan_entity_type('  abccd1234k ')", "'Company'"),
    ("pan_entity_type('XYZHA0001Q')", "'HUF'"),
    ("pan_entity_type('PQRFS9999Z')", "'Firm'"),
    ("pan_entity_type('LMNTB4321C')", "'Trust'"),
    ("pan_entity_type('AAAJA1111A')", "'Artificial Juridical Person'"),
    ("pan_entity_type('AAALA1111A')", "'Local Authority'"),
    ("pan_entity_type('ABCXE1234F')", "None"),
    ("pan_entity_type('ABCPE12345')", "None"),
    ("pan_entity_type('ABCPE123F')", "None"),
    ("pan_entity_type('1BCPE1234F')", "None"),
    ("pan_entity_type('ABC PE1234F')", "None"),
])

GSTIN_REF = '''
_CH = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
def gstin_check_char(first14):
    if len(first14) != 14 or any(c not in _CH for c in first14):
        raise ValueError(first14)
    s = 0
    for i, c in enumerate(first14):
        p = _CH.index(c) * (2 if i % 2 else 1)
        s += p // 36 + p % 36
    return _CH[(36 - s % 36) % 36]
'''

task(4, "gstin_check_char", "def gstin_check_char(first14: str) -> str:", """
A GSTIN is 15 characters; the 15th is a check character computed from the first 14 characters.
Write a function that returns that check character. Algorithm: use the alphabet "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
where each character's value is its index (0-35). For each of the 14 characters at position i (0-based), multiply its
value by 1 if i is even and by 2 if i is odd; add (product // 36) + (product % 36) to a running sum.
The check value is (36 - sum % 36) % 36, and the result is the alphabet character with that index.
If the input is not exactly 14 characters from that alphabet (uppercase only), raise ValueError.
""", GSTIN_REF, [
    ("gstin_check_char('27AAPFU0939F1Z')", "'V'"),
    ("gstin_check_char('29ABCDE1234F1Z')", "'W'"),
    ("gstin_check_char('07AAACZ1234B1Z')", "'V'"),
    ("gstin_check_char('33ABCPE1234F2Z')", "'H'"),
    ("gstin_check_char('09ZZZZZ9999Z9Z')", "'Y'"),
    ("gstin_check_char('00000000000000')", "'0'"),
    ("gstin_check_char('27aapfu0939f1z')", "RAISES:ValueError"),
    ("gstin_check_char('27AAPFU0939F1')", "RAISES:ValueError"),
    ("gstin_check_char('27AAPFU0939F1Z9')", "RAISES:ValueError"),
    ("gstin_check_char('27AAPFU0939F-Z')", "RAISES:ValueError"),
])

task(5, "parse_gstin", "def parse_gstin(gstin: str) -> dict | None:", """
Write a function that validates and parses a GSTIN. Strip whitespace and uppercase it first. A valid GSTIN is 15 chars:
2-digit state code (must be 01 to 38, or 97), then a 10-character PAN (5 letters, 4 digits, 1 letter), then the entity
number (one character, 1-9 or A-Z), then the letter "Z", then a check character.
The check character is computed from the first 14 characters: alphabet "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", value = index;
at 0-based position i multiply the value by 1 if i is even, 2 if odd; add (product // 36) + (product % 36) to a sum;
check = alphabet[(36 - sum % 36) % 36].
Return {"state_code": "27", "pan": "AAPFU0939F", "entity_number": "1"} for a valid GSTIN, otherwise None.
""", GSTIN_REF + '''
import re
def parse_gstin(gstin):
    s = gstin.strip().upper()
    m = re.fullmatch(r"(\\d{2})([A-Z]{5}\\d{4}[A-Z])([1-9A-Z])Z([0-9A-Z])", s)
    if not m:
        return None
    sc = int(m.group(1))
    if not (1 <= sc <= 38 or sc == 97) or gstin_check_char(s[:14]) != s[14]:
        return None
    return {"state_code": m.group(1), "pan": m.group(2), "entity_number": m.group(3)}
''', [
    ("parse_gstin('27AAPFU0939F1ZV')", "{'state_code': '27', 'pan': 'AAPFU0939F', 'entity_number': '1'}"),
    ("parse_gstin(' 29abcde1234f1zw ')", "{'state_code': '29', 'pan': 'ABCDE1234F', 'entity_number': '1'}"),
    ("parse_gstin('33ABCPE1234F2ZH')", "{'state_code': '33', 'pan': 'ABCPE1234F', 'entity_number': '2'}"),
    ("parse_gstin('97AAACZ1234B1ZM')", "{'state_code': '97', 'pan': 'AAACZ1234B', 'entity_number': '1'}"),
    ("parse_gstin('27AAPFU0939F1ZW')", "None"),
    ("parse_gstin('39AAPFU0939F1ZV')", "None"),
    ("parse_gstin('00AAPFU0939F1Z0')", "None"),
    ("parse_gstin('27AAPFU0939F1YV')", "None"),
    ("parse_gstin('27AAPFU0939F0ZV')", "None"),
    ("parse_gstin('27AAPFU0939F1Z')", "None"),
    ("parse_gstin('27AAP1U0939F1ZV')", "None"),
])

task(6, "parse_ifsc", "def parse_ifsc(code: str) -> tuple[str, str] | None:", """
Write a function that validates an Indian bank IFSC code and splits it. Strip whitespace and uppercase first.
A valid IFSC is exactly 11 characters: 4 letters (bank code), then the digit 0, then 6 letters or digits (branch code).
Return a tuple (bank_code, branch_code), e.g. "SBIN0001234" -> ("SBIN", "001234"). Return None if invalid.
""", '''
import re
def parse_ifsc(code):
    s = code.strip().upper()
    m = re.fullmatch(r"([A-Z]{4})0([A-Z0-9]{6})", s)
    return (m.group(1), m.group(2)) if m else None
''', [
    ("parse_ifsc('SBIN0001234')", "('SBIN', '001234')"),
    ("parse_ifsc(' hdfc0abc123 ')", "('HDFC', 'ABC123')"),
    ("parse_ifsc('ICIC0000001')", "('ICIC', '000001')"),
    ("parse_ifsc('SBIN1001234')", "None"),
    ("parse_ifsc('SBI00001234')", "None"),
    ("parse_ifsc('SBIN000123')", "None"),
    ("parse_ifsc('SBIN00012345')", "None"),
    ("parse_ifsc('SBIN0-01234')", "None"),
    ("parse_ifsc('')", "None"),
])

task(7, "format_inr", "def format_inr(paise: int) -> str:", """
Write a function that formats an amount given in paise (integer, 100 paise = 1 rupee) as an Indian rupee string
with Indian digit grouping: the last 3 digits of the rupee part form one group, and every 2 digits before that form a group.
Always show exactly 2 decimal places and prefix the rupee sign "₹". Negative amounts get a leading "-" before "₹".
Examples: 123456789 -> "₹12,34,567.89", 100000 -> "₹1,000.00", -5050 -> "-₹50.50", 0 -> "₹0.00".
""", '''
def format_inr(paise):
    sign = "-" if paise < 0 else ""
    r, p = divmod(abs(paise), 100)
    s = str(r)
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:]); head = head[:-2]
    if head:
        groups.insert(0, head)
    return f"{sign}₹{','.join(groups + [tail])}.{p:02d}"
''', [
    ("format_inr(123456789)", "'₹12,34,567.89'"),
    ("format_inr(100000)", "'₹1,000.00'"),
    ("format_inr(-5050)", "'-₹50.50'"),
    ("format_inr(0)", "'₹0.00'"),
    ("format_inr(5)", "'₹0.05'"),
    ("format_inr(99999)", "'₹999.99'"),
    ("format_inr(10000000)", "'₹1,00,000.00'"),
    ("format_inr(1000000000)", "'₹1,00,00,000.00'"),
    ("format_inr(123456789012345)", "'₹12,34,56,78,90,123.45'"),
    ("format_inr(-100000000)", "'-₹10,00,000.00'"),
])

WORDS_EN_REF = '''
_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
         "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
def _two(n):
    if n < 20:
        return _ONES[n]
    return _TENS[n // 10] + ("-" + _ONES[n % 10] if n % 10 else "")
def _words(n):
    if n == 0:
        return "zero"
    parts = []
    for div, name in ((10**7, "crore"), (10**5, "lakh"), (1000, "thousand"), (100, "hundred")):
        q, n = divmod(n, div)
        if q:
            parts.append(_words(q) + " " + name)
    if n:
        parts.append(_two(n))
    return " ".join(parts)
'''

task(8, "inr_words_en", "def inr_words_en(n: int) -> str:", """
Write a function that converts a non-negative integer (0 <= n < 1,000,000,000) into English words using the Indian
numbering system (thousand, lakh, crore — never million or billion). Rules: all lowercase; numbers 21-99 that are not
multiples of ten are written with a hyphen ("forty-two"); no "and"; single spaces between words; 0 -> "zero".
Example: 12345678 -> "one crore twenty-three lakh forty-five thousand six hundred seventy-eight".
Raise ValueError if n is negative or >= 1,000,000,000.
""", WORDS_EN_REF + '''
def inr_words_en(n):
    if n < 0 or n >= 10**9:
        raise ValueError(n)
    return _words(n)
''', [
    ("inr_words_en(0)", "'zero'"),
    ("inr_words_en(7)", "'seven'"),
    ("inr_words_en(19)", "'nineteen'"),
    ("inr_words_en(42)", "'forty-two'"),
    ("inr_words_en(105)", "'one hundred five'"),
    ("inr_words_en(1000)", "'one thousand'"),
    ("inr_words_en(100000)", "'one lakh'"),
    ("inr_words_en(12345678)", "'one crore twenty-three lakh forty-five thousand six hundred seventy-eight'"),
    ("inr_words_en(250000)", "'two lakh fifty thousand'"),
    ("inr_words_en(999999999)", "'ninety-nine crore ninety-nine lakh ninety-nine thousand nine hundred ninety-nine'"),
    ("inr_words_en(10000001)", "'one crore one'"),
    ("inr_words_en(1000000000)", "RAISES:ValueError"),
    ("inr_words_en(-1)", "RAISES:ValueError"),
])

task(9, "inr_words_hi", "def inr_words_hi(n: int) -> str:", """
Write a function that converts a non-negative integer (0 <= n < 1,000,000,000) into Hindi words in Devanagari using the
Indian system. Split n into: crore part (n // 10^7), lakh part (two digits), thousand part (two digits), hundreds digit,
and the last two digits. Each non-zero part is written as its number word followed by the unit word:
करोड़, लाख, हज़ार, सौ (the last two digits have no unit). Join with single spaces; skip zero parts; 0 -> "शून्य".
Use exactly these number words: 1 एक, 2 दो, 3 तीन, 4 चार, 5 पाँच, 6 छह, 7 सात, 8 आठ, 9 नौ, 10 दस, 20 बीस, 30 तीस,
40 चालीस, 50 पचास, 60 साठ, 70 सत्तर, 80 अस्सी, 90 नब्बे. Every two-digit part in the inputs will be one of these values.
Example: 30405060 -> "तीन करोड़ चार लाख पाँच हज़ार साठ".
""", '''
_W = {1: "एक", 2: "दो", 3: "तीन", 4: "चार", 5: "पाँच", 6: "छह", 7: "सात", 8: "आठ", 9: "नौ", 10: "दस", 20: "बीस",
      30: "तीस", 40: "चालीस", 50: "पचास", 60: "साठ", 70: "सत्तर", 80: "अस्सी", 90: "नब्बे"}
def inr_words_hi(n):
    if n == 0:
        return "शून्य"
    parts = []
    for div, name in ((10**7, "करोड़"), (10**5, "लाख"), (1000, "हज़ार"), (100, "सौ")):
        q, n = divmod(n, div)
        if q:
            parts.append(_W[q] + " " + name)
    if n:
        parts.append(_W[n])
    return " ".join(parts)
''', [
    ("_nfc(inr_words_hi(0))", "_nfc('शून्य')"),
    ("_nfc(inr_words_hi(5))", "_nfc('पाँच')"),
    ("_nfc(inr_words_hi(90))", "_nfc('नब्बे')"),
    ("_nfc(inr_words_hi(100))", "_nfc('एक सौ')"),
    ("_nfc(inr_words_hi(610))", "_nfc('छह सौ दस')"),
    ("_nfc(inr_words_hi(2000))", "_nfc('दो हज़ार')"),
    ("_nfc(inr_words_hi(4000000))", "_nfc('चालीस लाख')"),
    ("_nfc(inr_words_hi(30405060))", "_nfc('तीन करोड़ चार लाख पाँच हज़ार साठ')"),
    ("_nfc(inr_words_hi(900000009))", "_nfc('नब्बे करोड़ नौ')"),
    ("_nfc(inr_words_hi(708090))", "_nfc('सात लाख आठ हज़ार नब्बे')"),
    ("_nfc(inr_words_hi(10010101))", "_nfc('एक करोड़ दस हज़ार एक सौ एक')"),
])

FY_REF = '''
def fy_label(d):
    start = d.year if d.month >= 4 else d.year - 1
    return f"FY{start}-{(start + 1) % 100:02d}"
'''

task(10, "fy_quarter", "def fy_quarter(d: datetime.date) -> tuple[str, str]:", """
The Indian financial year runs from 1 April to 31 March. Write a function that returns the financial year label and the
quarter for a date. Label format: "FY" + start year + "-" + last two digits of the end year, e.g. "FY2024-25".
Quarters: Q1 = April-June, Q2 = July-September, Q3 = October-December, Q4 = January-March.
Example: datetime.date(2025, 2, 10) -> ("FY2024-25", "Q4").
""", "import datetime\n" + FY_REF + '''
def fy_quarter(d):
    q = {4: 1, 5: 1, 6: 1, 7: 2, 8: 2, 9: 2, 10: 3, 11: 3, 12: 3}.get(d.month, 4)
    return (fy_label(d), f"Q{q}")
''', [
    ("tuple(fy_quarter(_dt.date(2025, 2, 10)))", "('FY2024-25', 'Q4')"),
    ("tuple(fy_quarter(_dt.date(2024, 4, 1)))", "('FY2024-25', 'Q1')"),
    ("tuple(fy_quarter(_dt.date(2024, 3, 31)))", "('FY2023-24', 'Q4')"),
    ("tuple(fy_quarter(_dt.date(2024, 6, 30)))", "('FY2024-25', 'Q1')"),
    ("tuple(fy_quarter(_dt.date(2024, 7, 1)))", "('FY2024-25', 'Q2')"),
    ("tuple(fy_quarter(_dt.date(2023, 12, 31)))", "('FY2023-24', 'Q3')"),
    ("tuple(fy_quarter(_dt.date(2023, 10, 1)))", "('FY2023-24', 'Q3')"),
    ("tuple(fy_quarter(_dt.date(1999, 12, 31)))", "('FY1999-00', 'Q3')"),
    ("tuple(fy_quarter(_dt.date(2000, 1, 1)))", "('FY1999-00', 'Q4')"),
    ("tuple(fy_quarter(_dt.date(2009, 5, 5)))", "('FY2009-10', 'Q1')"),
])

HALF_UP = '''
from decimal import Decimal, ROUND_HALF_UP
def _r(x, q="1"):
    return Decimal(x).quantize(Decimal(q), rounding=ROUND_HALF_UP)
'''

task(11, "gst_split", "def gst_split(taxable_paise: int, rate_pct: float, supplier_state: str, place_of_supply: str) -> dict:", """
Write a function that computes GST on a taxable value (in paise). supplier_state and place_of_supply are 2-digit GST
state codes like "27" or "07". If they are equal the supply is intra-state: charge CGST and SGST, each at half the rate.
Otherwise it is inter-state: charge IGST at the full rate.
Each tax amount is rounded to the nearest paisa, with exact halves rounded up (round half up — do NOT use Python's round()).
For intra-state, compute CGST and SGST separately (each = taxable * rate/2 / 100, rounded); they are always equal.
Return a dict {"cgst": int, "sgst": int, "igst": int} in paise, with 0 for taxes that do not apply.
rate_pct can be fractional, e.g. 0.25 or 1.5.
""", HALF_UP + '''
def gst_split(taxable_paise, rate_pct, supplier_state, place_of_supply):
    r = Decimal(str(rate_pct))
    if supplier_state == place_of_supply:
        h = int(_r(Decimal(taxable_paise) * r / 200))
        return {"cgst": h, "sgst": h, "igst": 0}
    return {"cgst": 0, "sgst": 0, "igst": int(_r(Decimal(taxable_paise) * r / 100))}
''', [
    ("gst_split(100000, 18, '27', '27')", "{'cgst': 9000, 'sgst': 9000, 'igst': 0}"),
    ("gst_split(100000, 18, '27', '29')", "{'cgst': 0, 'sgst': 0, 'igst': 18000}"),
    ("gst_split(12345, 5, '07', '07')", "{'cgst': 309, 'sgst': 309, 'igst': 0}"),
    ("gst_split(12345, 5, '07', '09')", "{'cgst': 0, 'sgst': 0, 'igst': 617}"),
    ("gst_split(250, 12, '33', '33')", "{'cgst': 15, 'sgst': 15, 'igst': 0}"),
    ("gst_split(1050, 28, '24', '27')", "{'cgst': 0, 'sgst': 0, 'igst': 294}"),
    ("gst_split(250, 1, '33', '32')", "{'cgst': 0, 'sgst': 0, 'igst': 3}"),
    ("gst_split(1000, 0.25, '27', '27')", "{'cgst': 1, 'sgst': 1, 'igst': 0}"),
    ("gst_split(99999, 1.5, '06', '07')", "{'cgst': 0, 'sgst': 0, 'igst': 1500}"),
    ("gst_split(0, 18, '27', '27')", "{'cgst': 0, 'sgst': 0, 'igst': 0}"),
    ("gst_split(100, 3, '10', '10')", "{'cgst': 2, 'sgst': 2, 'igst': 0}"),
])

task(12, "income_tax_new_regime", "def income_tax_new_regime(gross_salary: int) -> int:", """
Write a function that computes annual income tax for a salaried individual under these rules (rupees, integers in):
1. Taxable income = gross_salary - 75,000 standard deduction (not below 0).
2. Slab tax on taxable income: up to 4,00,000 nil; 4,00,001-8,00,000 at 5%; 8,00,001-12,00,000 at 10%;
   12,00,001-16,00,000 at 15%; 16,00,001-20,00,000 at 20%; 20,00,001-24,00,000 at 25%; above 24,00,000 at 30%.
   Each rate applies only to the portion of income inside that band.
3. Rebate: if taxable income is 12,00,000 or less, the tax is 0. (Ignore marginal relief and surcharge.)
4. Add 4% health and education cess on the tax.
5. Round the final amount to the nearest rupee, exact halves rounded up. Return an int.
""", HALF_UP + '''
_SLABS = [(400000, 0), (800000, 5), (1200000, 10), (1600000, 15), (2000000, 20), (2400000, 25), (None, 30)]
def income_tax_new_regime(gross_salary):
    ti = max(0, gross_salary - 75000)
    if ti <= 1200000:
        return 0
    tax, lo = Decimal(0), 0
    for hi, rate in _SLABS:
        top = ti if hi is None else min(ti, hi)
        if top > lo:
            tax += Decimal(top - lo) * rate / 100
        if hi is None or ti <= hi:
            break
        lo = hi
    return int(_r(tax * Decimal("1.04")))
''', [
    ("income_tax_new_regime(0)", "0"),
    ("income_tax_new_regime(1000000)", "0"),
    ("income_tax_new_regime(1275000)", "0"),
    ("income_tax_new_regime(1275001)", "62400"),
    ("income_tax_new_regime(1575000)", "109200"),
    ("income_tax_new_regime(2075000)", "208000"),
    ("income_tax_new_regime(2475000)", "312000"),
    ("income_tax_new_regime(3075000)", "499200"),
    ("income_tax_new_regime(5075000)", "1123200"),
    ("income_tax_new_regime(1300003)", "66300"),
    ("income_tax_new_regime(50000)", "0"),
])

task(13, "emi", "def emi(principal: int, annual_rate_pct: float, months: int) -> float:", """
Write a function that computes the monthly EMI for a loan (Indian bank reducing-balance method).
r = annual_rate_pct / 12 / 100. EMI = P * r * (1 + r)^n / ((1 + r)^n - 1), where P is the principal in rupees and n the
number of months. If the rate is 0, EMI = P / n. Round the result to 2 decimal places (paise) and return a float.
Raise ValueError if months <= 0 or principal < 0 or the rate is negative.
""", '''
def emi(principal, annual_rate_pct, months):
    if months <= 0 or principal < 0 or annual_rate_pct < 0:
        raise ValueError
    if annual_rate_pct == 0:
        return round(principal / months, 2)
    r = annual_rate_pct / 1200
    f = (1 + r) ** months
    return round(principal * r * f / (f - 1), 2)
''', [
    ("emi(1000000, 8.5, 240)", "8678.23"),
    ("emi(500000, 10.5, 60)", "10746.95"),
    ("emi(100000, 12, 12)", "8884.88"),
    ("emi(2500000, 9.15, 180)", "25580.23"),
    ("emi(120000, 0, 12)", "10000.0"),
    ("emi(100000, 0, 3)", "33333.33"),
    ("emi(50000, 15, 1)", "50625.0"),
    ("emi(0, 10, 12)", "0.0"),
    ("emi(100000, 10, 0)", "RAISES:ValueError"),
    ("emi(100000, -1, 12)", "RAISES:ValueError"),
])

task(14, "is_valid_upi_id", "def is_valid_upi_id(vpa: str) -> bool:", """
Write a function that validates a UPI ID (VPA) like "ramesh.kumar@okaxis". Strip surrounding whitespace first.
Rules: exactly one "@". The part before "@" is 2 to 64 characters, using only letters, digits, ".", "_" and "-";
it must start and end with a letter or digit, and must not contain two consecutive dots.
The part after "@" (the handle) is 3 to 32 characters, letters and digits only, and must start with a letter.
Letters may be upper or lower case. Return True or False (never raise).
""", '''
import re
def is_valid_upi_id(vpa):
    s = vpa.strip()
    if s.count("@") != 1:
        return False
    local, handle = s.split("@")
    if not (2 <= len(local) <= 64 and re.fullmatch(r"[A-Za-z0-9._-]+", local)):
        return False
    if not (local[0].isascii() and local[0].isalnum() and local[-1].isascii() and local[-1].isalnum()) or ".." in local:
        return False
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9]{2,31}", handle))
''', [
    ("is_valid_upi_id('ramesh.kumar@okaxis')", "True"),
    ("is_valid_upi_id(' 9876543210@ybl ')", "True"),
    ("is_valid_upi_id('Shop_42-Pune@HDFCBank')", "True"),
    ("is_valid_upi_id('ab@upi')", "True"),
    ("is_valid_upi_id('a@upi')", "False"),
    ("is_valid_upi_id('.ramesh@okaxis')", "False"),
    ("is_valid_upi_id('ramesh.@okaxis')", "False"),
    ("is_valid_upi_id('ram..esh@okaxis')", "False"),
    ("is_valid_upi_id('ramesh@ok')", "False"),
    ("is_valid_upi_id('ramesh@1bank')", "False"),
    ("is_valid_upi_id('ramesh@ok.axis')", "False"),
    ("is_valid_upi_id('ramesh@@okaxis')", "False"),
    ("is_valid_upi_id('ram esh@okaxis')", "False"),
    ("is_valid_upi_id('ramesh')", "False"),
])

task(15, "indic_digits_to_ascii", "def indic_digits_to_ascii(text: str) -> str:", """
Write a function that replaces every native digit of these Indian scripts with the matching ASCII digit 0-9:
Devanagari, Bengali, Gurmukhi, Gujarati, Odia, Tamil, Telugu, Kannada, Malayalam. Every other character (letters,
ASCII digits, punctuation, digits of non-Indian scripts such as Arabic-Indic digits) stays unchanged.
Example: "कुल ₹१,२५०" -> "कुल ₹1,250", "௨௦௨௪" -> "2024".
""", '''
_ZEROS = [0x966, 0x9E6, 0xA66, 0xAE6, 0xB66, 0xBE6, 0xC66, 0xCE6, 0xD66]
_MAP = {z + i: str(i) for z in _ZEROS for i in range(10)}
def indic_digits_to_ascii(text):
    return text.translate(_MAP)
''', [
    ("indic_digits_to_ascii('कुल ₹१,२५०')", "'कुल ₹1,250'"),
    ("indic_digits_to_ascii('௨௦௨௪')", "'2024'"),
    ("indic_digits_to_ascii('৩৪৫ টাকা')", "'345 টাকা'"),
    ("indic_digits_to_ascii('౧౨-౦౮-౨౦౨౫')", "'12-08-2025'"),
    ("indic_digits_to_ascii('ಪಿನ್ ೫೬೦೦೦೧')", "'ಪಿನ್ 560001'"),
    ("indic_digits_to_ascii('൯൮')", "'98'"),
    ("indic_digits_to_ascii('੧੦ ૨૦ ୩୦')", "'10 20 30'"),
    ("indic_digits_to_ascii('abc 123')", "'abc 123'"),
    ("indic_digits_to_ascii('٣٤')", "'٣٤'"),
    ("indic_digits_to_ascii('')", "''"),
])

task(16, "ascii_to_indic_digits", "def ascii_to_indic_digits(text: str, script: str) -> str:", """
Write a function that replaces every ASCII digit 0-9 in text with the native digit of the given script. script is one of
(case-insensitive): "devanagari", "bengali", "gurmukhi", "gujarati", "odia", "tamil", "telugu", "kannada", "malayalam".
All other characters stay unchanged. Raise ValueError for any other script name.
Example: ascii_to_indic_digits("₹1,250", "devanagari") -> "₹१,२५०".
""", '''
_Z = {"devanagari": 0x966, "bengali": 0x9E6, "gurmukhi": 0xA66, "gujarati": 0xAE6, "odia": 0xB66, "tamil": 0xBE6,
      "telugu": 0xC66, "kannada": 0xCE6, "malayalam": 0xD66}
def ascii_to_indic_digits(text, script):
    z = _Z.get(script.lower())
    if z is None:
        raise ValueError(script)
    return text.translate({ord("0") + i: chr(z + i) for i in range(10)})
''', [
    ("ascii_to_indic_digits('₹1,250', 'devanagari')", "'₹१,२५०'"),
    ("ascii_to_indic_digits('2024', 'Tamil')", "'௨௦௨௪'"),
    ("ascii_to_indic_digits('PIN 560001', 'kannada')", "'PIN ೫೬೦೦೦೧'"),
    ("ascii_to_indic_digits('12-08', 'TELUGU')", "'౧౨-౦౮'"),
    ("ascii_to_indic_digits('345', 'bengali')", "'৩৪৫'"),
    ("ascii_to_indic_digits('7', 'gujarati')", "'૭'"),
    ("ascii_to_indic_digits('90', 'malayalam')", "'൯൦'"),
    ("ascii_to_indic_digits('no digits', 'odia')", "'no digits'"),
    ("ascii_to_indic_digits('1', 'urdu')", "RAISES:ValueError"),
    ("ascii_to_indic_digits('१२', 'gurmukhi')", "'१२'"),
])

task(17, "pincode_state", "def pincode_state(pincode: str, table: dict[str, str]) -> str | None:", """
Write a function that finds the state for an Indian PIN code using a supplied prefix table, e.g.
{"11": "Delhi", "40": "Maharashtra", "403": "Goa", "56": "Karnataka"}. Remove spaces from the PIN first.
A valid PIN is exactly 6 ASCII digits and does not start with 0; for an invalid PIN return None.
Among all table keys that the PIN starts with, use the longest one. Return its state, or None if no key matches.
""", '''
def pincode_state(pincode, table):
    s = pincode.replace(" ", "")
    if len(s) != 6 or not (s.isascii() and s.isdigit()) or s[0] == "0":
        return None
    best = max((k for k in table if s.startswith(k)), key=len, default=None)
    return table[best] if best is not None else None
''', [
    ("pincode_state('110001', {'11': 'Delhi', '40': 'Maharashtra', '403': 'Goa'})", "'Delhi'"),
    ("pincode_state('403001', {'11': 'Delhi', '40': 'Maharashtra', '403': 'Goa'})", "'Goa'"),
    ("pincode_state('400050', {'11': 'Delhi', '40': 'Maharashtra', '403': 'Goa'})", "'Maharashtra'"),
    ("pincode_state('403001', {'403': 'Goa', '40': 'Maharashtra'})", "'Goa'"),
    ("pincode_state('560 001', {'56': 'Karnataka'})", "'Karnataka'"),
    ("pincode_state('600001', {'11': 'Delhi'})", "None"),
    ("pincode_state('011001', {'01': 'X', '011': 'Y'})", "None"),
    ("pincode_state('11001', {'11': 'Delhi'})", "None"),
    ("pincode_state('1100011', {'11': 'Delhi'})", "None"),
    ("pincode_state('11000A', {'11': 'Delhi'})", "None"),
    ("pincode_state('682001', {'6': 'South', '68': 'Kerala', '682': 'Ernakulam'})", "'Ernakulam'"),
])

task(18, "parse_booking_status", "def parse_booking_status(status: str) -> dict | None:", """
Write a function that parses an Indian Railways ticket booking status string. Ignore case and surrounding whitespace;
parts may be separated by "/" or spaces (one or more). Supported forms:
- Confirmed: "CNF/B2/45" or "CNF/B2/45/LB" -> {"status": "CNF", "coach": "B2", "berth": 45, "berth_type": "LB"}
  (berth_type is None when absent; coach and berth_type are returned uppercase; berth is an int).
- RAC: "RAC 12" or "RAC/12" -> {"status": "RAC", "number": 12}
- Waitlist: "WL 34", "GNWL 34", "RLWL/5", "PQWL 2", "TQWL 9" -> {"status": "WL", "list": "GNWL", "number": 34}
  where list is the waitlist code as written in uppercase ("WL", "GNWL", "RLWL", "PQWL" or "TQWL").
Return None for anything else (including non-numeric berth/number).
""", '''
import re
def parse_booking_status(status):
    t = [x for x in re.split(r"[\\s/]+", status.strip().upper()) if x]
    if not t:
        return None
    if t[0] == "CNF" and len(t) in (3, 4) and t[2].isdigit():
        return {"status": "CNF", "coach": t[1], "berth": int(t[2]), "berth_type": t[3] if len(t) == 4 else None}
    if t[0] == "RAC" and len(t) == 2 and t[1].isdigit():
        return {"status": "RAC", "number": int(t[1])}
    if t[0] in ("WL", "GNWL", "RLWL", "PQWL", "TQWL") and len(t) == 2 and t[1].isdigit():
        return {"status": "WL", "list": t[0], "number": int(t[1])}
    return None
''', [
    ("parse_booking_status('CNF/B2/45/LB')", "{'status': 'CNF', 'coach': 'B2', 'berth': 45, 'berth_type': 'LB'}"),
    ("parse_booking_status('cnf/s5/7')", "{'status': 'CNF', 'coach': 'S5', 'berth': 7, 'berth_type': None}"),
    ("parse_booking_status(' CNF  A1 12 sub ')", "{'status': 'CNF', 'coach': 'A1', 'berth': 12, 'berth_type': 'SUB'}"),
    ("parse_booking_status('RAC 12')", "{'status': 'RAC', 'number': 12}"),
    ("parse_booking_status('rac/3')", "{'status': 'RAC', 'number': 3}"),
    ("parse_booking_status('GNWL 34')", "{'status': 'WL', 'list': 'GNWL', 'number': 34}"),
    ("parse_booking_status('rlwl/5')", "{'status': 'WL', 'list': 'RLWL', 'number': 5}"),
    ("parse_booking_status('WL 1')", "{'status': 'WL', 'list': 'WL', 'number': 1}"),
    ("parse_booking_status('TQWL  9')", "{'status': 'WL', 'list': 'TQWL', 'number': 9}"),
    ("parse_booking_status('XYWL 9')", "None"),
    ("parse_booking_status('RAC')", "None"),
    ("parse_booking_status('CNF/B2/xx')", "None"),
    ("parse_booking_status('')", "None"),
])

task(19, "ist_to_utc", "def ist_to_utc(s: str) -> str:", """
Write a function that converts an Indian-format local time string in IST (UTC+05:30) to UTC.
Input format: "DD/MM/YYYY hh:mm AM" or "... PM" (12-hour clock; AM/PM case-insensitive; day and month always 2 digits,
hour 1 or 2 digits). 12:xx AM is just after midnight, 12:xx PM is just after noon.
Return UTC in ISO format "YYYY-MM-DDTHH:MM:00Z". Raise ValueError if the string or the date/time is invalid.
Example: "01/04/2025 12:15 AM" -> "2025-03-31T18:45:00Z".
""", '''
import datetime, re
def ist_to_utc(s):
    m = re.fullmatch(r"(\\d{2})/(\\d{2})/(\\d{4}) (\\d{1,2}):(\\d{2}) ([AaPp][Mm])", s.strip())
    if not m:
        raise ValueError(s)
    d, mo, y, h, mi, ap = m.groups()
    h, mi = int(h), int(mi)
    if not (1 <= h <= 12) or mi > 59:
        raise ValueError(s)
    h = h % 12 + (12 if ap.upper() == "PM" else 0)
    t = datetime.datetime(int(y), int(mo), int(d), h, mi) - datetime.timedelta(hours=5, minutes=30)
    return t.strftime("%Y-%m-%dT%H:%M:00Z")
''', [
    ("ist_to_utc('01/04/2025 12:15 AM')", "'2025-03-31T18:45:00Z'"),
    ("ist_to_utc('15/08/2024 09:00 AM')", "'2024-08-15T03:30:00Z'"),
    ("ist_to_utc('15/08/2024 12:00 PM')", "'2024-08-15T06:30:00Z'"),
    ("ist_to_utc('31/12/2024 11:59 pm')", "'2024-12-31T18:29:00Z'"),
    ("ist_to_utc('01/01/2025 05:29 AM')", "'2024-12-31T23:59:00Z'"),
    ("ist_to_utc('01/01/2025 5:30 AM')", "'2025-01-01T00:00:00Z'"),
    ("ist_to_utc('29/02/2024 06:45 PM')", "'2024-02-29T13:15:00Z'"),
    ("ist_to_utc('29/02/2023 06:45 PM')", "RAISES:ValueError"),
    ("ist_to_utc('15/08/2024 13:00 PM')", "RAISES:ValueError"),
    ("ist_to_utc('2024-08-15 09:00')", "RAISES:ValueError"),
])

task(20, "card_info", "def card_info(number: str) -> tuple[str, bool] | None:", """
Write a function that identifies a payment card number's network and checks its Luhn checksum.
Remove spaces and hyphens first. If what remains is not 12-19 ASCII digits, return None.
Network by prefix: "Amex" if it starts with 34 or 37; "Visa" if it starts with 4; "Mastercard" if the first two digits
are 51-55 or the first four digits are 2221-2720; "RuPay" if it starts with 60, 65, 81, 82 or 508; otherwise "Unknown".
Return (network, luhn_ok) where luhn_ok is True if the number passes the Luhn check.
""", '''
def card_info(number):
    s = number.replace(" ", "").replace("-", "")
    if not (12 <= len(s) <= 19 and s.isascii() and s.isdigit()):
        return None
    if s[:2] in ("34", "37"): net = "Amex"
    elif s[0] == "4": net = "Visa"
    elif 51 <= int(s[:2]) <= 55 or 2221 <= int(s[:4]) <= 2720: net = "Mastercard"
    elif s[:2] in ("60", "65", "81", "82") or s[:3] == "508": net = "RuPay"
    else: net = "Unknown"
    tot = 0
    for i, ch in enumerate(reversed(s)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        tot += d
    return (net, tot % 10 == 0)
''', [
    ("tuple(card_info('4111 1111 1111 1111'))", "('Visa', True)"),
    ("tuple(card_info('4111-1111-1111-1112'))", "('Visa', False)"),
    ("tuple(card_info('5500 0000 0000 0004'))", "('Mastercard', True)"),
    ("tuple(card_info('2221000000000009'))", "('Mastercard', True)"),
    ("tuple(card_info('2720990000000007'))", "('Mastercard', True)"),
    ("tuple(card_info('378282246310005'))", "('Amex', True)"),
    ("tuple(card_info('6521 0000 0000 0007'))", "('RuPay', True)"),
    ("tuple(card_info('5085000000000007'))", "('RuPay', True)"),
    ("tuple(card_info('8100000000000000'))", "('RuPay', False)"),
    ("tuple(card_info('9999 0000 0000 0000'))", "('Unknown', False)"),
    ("card_info('4111 1111 111')", "None"),
    ("card_info('4111x11111111111')", "None"),
])

task(21, "normalize_mobile", "def normalize_mobile(s: str) -> str | None:", """
Write a function that normalises an Indian mobile number to the form "+91XXXXXXXXXX".
First remove spaces, hyphens, dots and parentheses. Then strip one country/trunk prefix: a leading "+91", or a leading
"0091", or a leading "91" if exactly 12 digits remain, or a leading "0" if exactly 11 digits remain.
What is left must be exactly 10 ASCII digits starting with 6, 7, 8 or 9; return "+91" + those 10 digits, otherwise None.
""", '''
import re
def normalize_mobile(s):
    t = re.sub(r"[\\s\\-.()]", "", s)
    if t.startswith("+91"): t = t[3:]
    elif t.startswith("0091"): t = t[4:]
    elif len(t) == 12 and t.startswith("91"): t = t[2:]
    elif len(t) == 11 and t.startswith("0"): t = t[1:]
    if len(t) == 10 and t.isascii() and t.isdigit() and t[0] in "6789":
        return "+91" + t
    return None
''', [
    ("normalize_mobile('+91 98765 43210')", "'+919876543210'"),
    ("normalize_mobile('09876543210')", "'+919876543210'"),
    ("normalize_mobile('919876543210')", "'+919876543210'"),
    ("normalize_mobile('0091-98765-43210')", "'+919876543210'"),
    ("normalize_mobile('(+91) 70123.45678')", "'+917012345678'"),
    ("normalize_mobile('6000000000')", "'+916000000000'"),
    ("normalize_mobile('5876543210')", "None"),
    ("normalize_mobile('+91 98765 4321')", "None"),
    ("normalize_mobile('+1 415 555 0100')", "None"),
    ("normalize_mobile('98765432101')", "None"),
    ("normalize_mobile('022 2345 6789')", "None"),
    ("normalize_mobile('')", "None"),
])

task(22, "parse_vehicle_reg", "def parse_vehicle_reg(plate: str) -> dict | None:", """
Write a function that parses an Indian vehicle registration number. Uppercase it and remove spaces and hyphens first.
Two formats are valid:
1. Regular: state code (2 letters), RTO code (1 or 2 digits), series (1 to 3 letters), number (1 to 4 digits).
   The state code must be one of: AN AP AR AS BR CH CG DD DL GA GJ HP HR JH JK KA KL LA LD MH ML MN MP MZ NL OD PB PY RJ SK TN TR TS UK UP WB.
   Return {"type": "regular", "state": "MH", "rto": "02", "series": "AB", "number": "0042"} with rto zero-padded to
   2 digits and number zero-padded to 4 digits.
2. Bharat series: 2-digit year, "BH", 4 digits, 1 or 2 letters, e.g. "22 BH 1234 AA".
   Return {"type": "BH", "year": 2022, "number": "1234", "series": "AA"}.
Return None if neither format matches.
""", '''
import re
_STATES = set("AN AP AR AS BR CH CG DD DL GA GJ HP HR JH JK KA KL LA LD MH ML MN MP MZ NL OD PB PY RJ SK TN TR TS UK UP WB".split())
def parse_vehicle_reg(plate):
    s = re.sub(r"[\\s-]", "", plate.upper())
    m = re.fullmatch(r"(\\d{2})BH(\\d{4})([A-Z]{1,2})", s)
    if m:
        return {"type": "BH", "year": 2000 + int(m.group(1)), "number": m.group(2), "series": m.group(3)}
    m = re.fullmatch(r"([A-Z]{2})(\\d{1,2})([A-Z]{1,3})(\\d{1,4})", s)
    if m and m.group(1) in _STATES:
        return {"type": "regular", "state": m.group(1), "rto": m.group(2).zfill(2), "series": m.group(3),
                "number": m.group(4).zfill(4)}
    return None
''', [
    ("parse_vehicle_reg('MH 12 AB 1234')", "{'type': 'regular', 'state': 'MH', 'rto': '12', 'series': 'AB', 'number': '1234'}"),
    ("parse_vehicle_reg('ka-03-mn-42')", "{'type': 'regular', 'state': 'KA', 'rto': '03', 'series': 'MN', 'number': '0042'}"),
    ("parse_vehicle_reg('DL 3 CAF 7')", "{'type': 'regular', 'state': 'DL', 'rto': '03', 'series': 'CAF', 'number': '0007'}"),
    ("parse_vehicle_reg('TN09B9999')", "{'type': 'regular', 'state': 'TN', 'rto': '09', 'series': 'B', 'number': '9999'}"),
    ("parse_vehicle_reg('22 BH 1234 AA')", "{'type': 'BH', 'year': 2022, 'number': '1234', 'series': 'AA'}"),
    ("parse_vehicle_reg('25bh0001c')", "{'type': 'BH', 'year': 2025, 'number': '0001', 'series': 'C'}"),
    ("parse_vehicle_reg('XX 12 AB 1234')", "None"),
    ("parse_vehicle_reg('MH 12 1234')", "None"),
    ("parse_vehicle_reg('MH 12 ABCD 1234')", "None"),
    ("parse_vehicle_reg('MH 12 AB 12345')", "None"),
    ("parse_vehicle_reg('MH 123 AB 1234')", "None"),
    ("parse_vehicle_reg('22 BH 123 AA')", "None"),
])

task(23, "gst_invoice_total", "def gst_invoice_total(items: list[tuple[int, int, float]], intra_state: bool) -> dict:", """
Write a function that totals a GST invoice. items is a list of (quantity, unit_price_paise, gst_rate_pct).
1. Taxable value = sum of quantity * unit_price over all lines (paise).
2. Group lines by GST rate. For each rate, tax is computed on that rate group's total taxable value:
   intra-state: CGST = SGST = group_taxable * rate / 2 / 100 each; inter-state: IGST = group_taxable * rate / 100.
   Round every tax amount (per rate group, per tax) to the nearest paisa, exact halves up.
3. Total before rounding = taxable + all taxes. The grand total is rounded to the nearest whole rupee (100 paise),
   exact halves (50 paise) up. round_off = grand_total - total before rounding (may be negative).
Return {"taxable", "cgst", "sgst", "igst", "round_off", "grand_total"} — all int paise.
""", HALF_UP + '''
def gst_invoice_total(items, intra_state):
    groups = {}
    for q, p, rate in items:
        k = Decimal(str(rate))
        groups[k] = groups.get(k, 0) + q * p
    taxable = sum(groups.values())
    c = s = i = 0
    for rate, val in groups.items():
        if intra_state:
            h = int(_r(Decimal(val) * rate / 200)); c += h; s += h
        else:
            i += int(_r(Decimal(val) * rate / 100))
    before = taxable + c + s + i
    grand = int(_r(Decimal(before) / 100)) * 100
    return {"taxable": taxable, "cgst": c, "sgst": s, "igst": i, "round_off": grand - before, "grand_total": grand}
''', [
    ("gst_invoice_total([(2, 49900, 18)], True)", "{'taxable': 99800, 'cgst': 8982, 'sgst': 8982, 'igst': 0, 'round_off': 36, 'grand_total': 117800}"),
    ("gst_invoice_total([(2, 49900, 18)], False)", "{'taxable': 99800, 'cgst': 0, 'sgst': 0, 'igst': 17964, 'round_off': 36, 'grand_total': 117800}"),
    ("gst_invoice_total([(1, 1999, 5), (3, 2999, 12), (1, 12345, 5)], True)", "{'taxable': 23341, 'cgst': 899, 'sgst': 899, 'igst': 0, 'round_off': -39, 'grand_total': 25100}"),
    ("gst_invoice_total([(1, 1999, 5), (3, 2999, 12), (1, 12345, 5)], False)", "{'taxable': 23341, 'cgst': 0, 'sgst': 0, 'igst': 1797, 'round_off': -38, 'grand_total': 25100}"),
    ("gst_invoice_total([(1, 10000, 0)], True)", "{'taxable': 10000, 'cgst': 0, 'sgst': 0, 'igst': 0, 'round_off': 0, 'grand_total': 10000}"),
    ("gst_invoice_total([(1, 150, 0)], False)", "{'taxable': 150, 'cgst': 0, 'sgst': 0, 'igst': 0, 'round_off': 50, 'grand_total': 200}"),
    ("gst_invoice_total([(1, 149, 0)], False)", "{'taxable': 149, 'cgst': 0, 'sgst': 0, 'igst': 0, 'round_off': -49, 'grand_total': 100}"),
    ("gst_invoice_total([(1, 333, 18), (1, 333, 18)], True)", "{'taxable': 666, 'cgst': 60, 'sgst': 60, 'igst': 0, 'round_off': 14, 'grand_total': 800}"),
    ("gst_invoice_total([(5, 1000, 28), (1, 1000, 3)], False)", "{'taxable': 6000, 'cgst': 0, 'sgst': 0, 'igst': 1430, 'round_off': -30, 'grand_total': 7400}"),
    ("gst_invoice_total([], True)", "{'taxable': 0, 'cgst': 0, 'sgst': 0, 'igst': 0, 'round_off': 0, 'grand_total': 0}"),
])

task(24, "mask_aadhaar", "def mask_aadhaar(text: str) -> str:", """
To comply with Indian data-protection rules, write a function that masks Aadhaar numbers inside free text.
A candidate is 12 digits written either contiguously or as three groups of 4 digits, where each gap between groups is
a single space or a single hyphen; it must not be immediately preceded or followed by another digit.
Mask a candidate only if it is a valid Aadhaar-format number: first digit is not 0 or 1, and the 12 digits pass the
Verhoeff checksum. Replace each valid one with "XXXX XXXX " followed by its last 4 digits. Leave everything else unchanged.
""", VERHOEFF_REF + '''
import re
def mask_aadhaar(text):
    def sub(m):
        d = m.group(1) + m.group(2) + m.group(3)
        return "XXXX XXXX " + d[-4:] if d[0] not in "01" and _verhoeff_ok(d) else m.group(0)
    return re.sub(r"(?<!\\d)(\\d{4})[ -]?(\\d{4})[ -]?(\\d{4})(?!\\d)", sub, text)
''', [
    ("mask_aadhaar('Aadhaar: 9999 0000 1231, name Ravi')", "'Aadhaar: XXXX XXXX 1231, name Ravi'"),
    ("mask_aadhaar('id=999900001231;')", "'id=XXXX XXXX 1231;'"),
    ("mask_aadhaar('UID 2345-6789-0124 ok')", "'UID XXXX XXXX 0124 ok'"),
    ("mask_aadhaar('bad 9999 0000 1232 here')", "'bad 9999 0000 1232 here'"),
    ("mask_aadhaar('order 1234567890123 shipped')", "'order 1234567890123 shipped'"),
    ("mask_aadhaar('ref 99990000123100')", "'ref 99990000123100'"),
    ("mask_aadhaar('a 999900001231 b 234567890124')", "'a XXXX XXXX 1231 b XXXX XXXX 0124'"),
    ("mask_aadhaar('phone 9876543210')", "'phone 9876543210'"),
    ("mask_aadhaar('no numbers here')", "'no numbers here'"),
    ("mask_aadhaar('9999  0000 1231')", "'9999  0000 1231'"),
])

task(25, "parse_indian_amount", "def parse_indian_amount(s: str) -> int:", """
Write a function that parses an amount written the way Indians write it and returns whole rupees (int).
Steps: strip whitespace; remove a leading currency marker if present ("₹", "Rs.", "Rs", "INR", case-insensitive);
remove commas and spaces. The rest is a number (integer or decimal) optionally followed by a unit (case-insensitive):
"crore", "crores" or "cr" = 1,00,00,000; "lakh", "lakhs", "lac", "lacs" or "l" = 1,00,000; "k" or "thousand" = 1,000.
Multiply, then round to the nearest rupee (exact halves up). Raise ValueError if the text cannot be parsed.
Examples: "1.5 crore" -> 15000000, "₹2,50,000" -> 250000, "Rs. 12.5k" -> 12500, "3.25L" -> 325000.
""", HALF_UP + '''
import re
_U = {"crore": 10**7, "crores": 10**7, "cr": 10**7, "lakh": 10**5, "lakhs": 10**5, "lac": 10**5, "lacs": 10**5,
      "l": 10**5, "k": 1000, "thousand": 1000, "": 1}
def parse_indian_amount(s):
    t = s.strip()
    t = re.sub(r"^(₹|rs\\.?|inr)", "", t, flags=re.I)
    t = t.replace(",", "").replace(" ", "").lower()
    m = re.fullmatch(r"(\\d+(?:\\.\\d+)?|\\.\\d+)([a-z]*)", t)
    if not m or m.group(2) not in _U:
        raise ValueError(s)
    return int(_r(Decimal(m.group(1)) * _U[m.group(2)]))
''', [
    ("parse_indian_amount('1.5 crore')", "15000000"),
    ("parse_indian_amount('₹2,50,000')", "250000"),
    ("parse_indian_amount('Rs. 12.5k')", "12500"),
    ("parse_indian_amount('3.25L')", "325000"),
    ("parse_indian_amount('INR 7 lacs')", "700000"),
    ("parse_indian_amount('rs 1.2 Cr')", "12000000"),
    ("parse_indian_amount('  999 ')", "999"),
    ("parse_indian_amount('10.5')", "11"),
    ("parse_indian_amount('2 thousand')", "2000"),
    ("parse_indian_amount('0.000015 crore')", "150"),
    ("parse_indian_amount('12 million')", "RAISES:ValueError"),
    ("parse_indian_amount('abc')", "RAISES:ValueError"),
    ("parse_indian_amount('')", "RAISES:ValueError"),
])

task(26, "hra_exemption", "def hra_exemption(basic: int, hra_received: int, rent_paid: int, metro: bool) -> int:", """
Write a function that computes the HRA (house rent allowance) exemption under Indian income-tax rules. All inputs are
annual rupee amounts (basic salary includes DA). The exemption is the minimum of:
(a) actual HRA received; (b) rent paid minus 10% of basic (not below 0); (c) 50% of basic if the city is a metro,
otherwise 40% of basic. Round the result to the nearest rupee (exact halves up) and return an int.
""", HALF_UP + '''
def hra_exemption(basic, hra_received, rent_paid, metro):
    b = Decimal(basic)
    v = min(Decimal(hra_received), max(Decimal(0), Decimal(rent_paid) - b / 10), b * (Decimal("0.5") if metro else Decimal("0.4")))
    return int(_r(v))
''', [
    ("hra_exemption(600000, 240000, 300000, True)", "240000"),
    ("hra_exemption(600000, 300000, 300000, True)", "240000"),
    ("hra_exemption(600000, 300000, 400000, True)", "300000"),
    ("hra_exemption(600000, 300000, 400000, False)", "240000"),
    ("hra_exemption(600000, 300000, 50000, True)", "0"),
    ("hra_exemption(600000, 0, 300000, True)", "0"),
    ("hra_exemption(123455, 100000, 60000, False)", "47655"),
    ("hra_exemption(123455, 100000, 200000, True)", "61728"),
    ("hra_exemption(123455, 100000, 200000, False)", "49382"),
    ("hra_exemption(0, 50000, 60000, True)", "0"),
])

task(27, "gratuity", "def gratuity(monthly_salary: int, years: int, months: int) -> int:", """
Write a function that computes gratuity payable under these rules (Payment of Gratuity Act style).
monthly_salary is last drawn basic + DA in rupees; service is given as completed years plus extra months (0-11).
1. If completed years < 5, gratuity is 0.
2. Otherwise counted years = years, plus 1 if extra months is more than 6 (exactly 6 months does not count).
3. Gratuity = 15 * monthly_salary * counted_years / 26, rounded to the nearest rupee (exact halves up).
4. The amount is capped at 20,00,000. Return an int.
""", HALF_UP + '''
def gratuity(monthly_salary, years, months):
    if years < 5:
        return 0
    n = years + (1 if months > 6 else 0)
    return min(2000000, int(_r(Decimal(15 * monthly_salary * n) / 26)))
''', [
    ("gratuity(52000, 10, 0)", "300000"),
    ("gratuity(52000, 10, 6)", "300000"),
    ("gratuity(52000, 10, 7)", "330000"),
    ("gratuity(40000, 4, 11)", "0"),
    ("gratuity(40000, 5, 0)", "115385"),
    ("gratuity(35000, 7, 3)", "141346"),
    ("gratuity(26000, 1, 0)", "0"),
    ("gratuity(500000, 30, 0)", "2000000"),
    ("gratuity(100000, 34, 7)", "2000000"),
    ("gratuity(13, 6, 0)", "45"),
])

task(28, "epf_contribution", "def epf_contribution(basic_da: int) -> dict:", """
Write a function that computes monthly Employees' Provident Fund contributions in India for a monthly basic + DA (rupees).
- Employee contribution = 12% of basic_da.
- Employer's pension (EPS) share = 8.33% of the wage, where the wage is capped at 15,000 (use min(basic_da, 15000)).
- Employer's EPF share = (12% of basic_da) - EPS share, using the already-rounded values.
Round each percentage amount to the nearest rupee, exact halves up.
Return {"employee": int, "employer_eps": int, "employer_epf": int}.
""", HALF_UP + '''
def epf_contribution(basic_da):
    emp = int(_r(Decimal(basic_da) * 12 / 100))
    eps = int(_r(Decimal(min(basic_da, 15000)) * Decimal("8.33") / 100))
    return {"employee": emp, "employer_eps": eps, "employer_epf": emp - eps}
''', [
    ("epf_contribution(15000)", "{'employee': 1800, 'employer_eps': 1250, 'employer_epf': 550}"),
    ("epf_contribution(30000)", "{'employee': 3600, 'employer_eps': 1250, 'employer_epf': 2350}"),
    ("epf_contribution(10000)", "{'employee': 1200, 'employer_eps': 833, 'employer_epf': 367}"),
    ("epf_contribution(12345)", "{'employee': 1481, 'employer_eps': 1028, 'employer_epf': 453}"),
    ("epf_contribution(0)", "{'employee': 0, 'employer_eps': 0, 'employer_epf': 0}"),
    ("epf_contribution(14999)", "{'employee': 1800, 'employer_eps': 1249, 'employer_epf': 551}"),
    ("epf_contribution(7500)", "{'employee': 900, 'employer_eps': 625, 'employer_epf': 275}"),
    ("epf_contribution(1)", "{'employee': 0, 'employer_eps': 0, 'employer_epf': 0}"),
    ("epf_contribution(100000)", "{'employee': 12000, 'employer_eps': 1250, 'employer_epf': 10750}"),
])

task(29, "fd_maturity", "def fd_maturity(principal: int, annual_rate_pct: float, months: int) -> float:", """
Write a function that computes the maturity value of an Indian bank fixed deposit with quarterly compounding.
Maturity = principal * (1 + annual_rate_pct / 400) ** (months / 3). months must be a positive multiple of 3, otherwise
raise ValueError. Round the result to 2 decimal places and return a float.
""", '''
def fd_maturity(principal, annual_rate_pct, months):
    if months <= 0 or months % 3:
        raise ValueError(months)
    return round(principal * (1 + annual_rate_pct / 400) ** (months // 3), 2)
''', [
    ("fd_maturity(100000, 7.1, 12)", "107291.28"),
    ("fd_maturity(100000, 7, 60)", "141477.82"),
    ("fd_maturity(250000, 6.5, 36)", "303351.89"),
    ("fd_maturity(10000, 8, 3)", "10200.0"),
    ("fd_maturity(500000, 7.25, 24)", "577269.77"),
    ("fd_maturity(100000, 0, 12)", "100000.0"),
    ("fd_maturity(100000, 7, 10)", "RAISES:ValueError"),
    ("fd_maturity(100000, 7, 0)", "RAISES:ValueError"),
])

task(30, "gst_reverse", "def gst_reverse(inclusive_paise: int, rate_pct: float) -> tuple[int, int]:", """
Shops in India often quote GST-inclusive prices. Write a function that splits a GST-inclusive amount (paise) into the
taxable value and the GST amount. taxable = inclusive * 100 / (100 + rate_pct), rounded to the nearest paisa with exact
halves rounded up; gst = inclusive - taxable (so the two always add up exactly). Return (taxable, gst) as ints.
""", HALF_UP + '''
def gst_reverse(inclusive_paise, rate_pct):
    r = Decimal(str(rate_pct))
    t = int(_r(Decimal(inclusive_paise) * 100 / (100 + r)))
    return (t, inclusive_paise - t)
''', [
    ("tuple(gst_reverse(11800, 18))", "(10000, 1800)"),
    ("tuple(gst_reverse(10000, 18))", "(8475, 1525)"),
    ("tuple(gst_reverse(105, 5))", "(100, 5)"),
    ("tuple(gst_reverse(99900, 12))", "(89196, 10704)"),
    ("tuple(gst_reverse(12800, 28))", "(10000, 2800)"),
    ("tuple(gst_reverse(5000, 0))", "(5000, 0)"),
    ("tuple(gst_reverse(1, 18))", "(1, 0)"),
    ("tuple(gst_reverse(103, 3))", "(100, 3)"),
    ("tuple(gst_reverse(2050, 2.5))", "(2000, 50)"),
    ("tuple(gst_reverse(0, 18))", "(0, 0)"),
])

task(31, "parse_indian_date", "def parse_indian_date(s: str) -> datetime.date:", """
Write a function that parses a date written in Indian day-first style and returns a datetime.date.
The order is always day, month, year. Separators may be "/", "-", "." or spaces. The month is a number (1 or 2 digits),
a 3-letter English abbreviation ("Aug") or a full English month name ("August"), case-insensitive. The year has 4 digits,
or 2 digits meaning 2000-2099. The day has 1 or 2 digits. Raise ValueError if the format or the date is invalid.
Examples: "15/08/2024", "15-Aug-2024", "5.9.24", "1 January 2025".
""", '''
import datetime, re
_M = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_F = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
def parse_indian_date(s):
    m = re.fullmatch(r"(\\d{1,2})[/\\-. ]+([A-Za-z]+|\\d{1,2})[/\\-. ]+(\\d{4}|\\d{2})", s.strip())
    if not m:
        raise ValueError(s)
    d, mo, y = m.groups()
    if mo.isdigit():
        mo = int(mo)
    elif mo.lower() in _M:
        mo = _M.index(mo.lower()) + 1
    elif mo.lower() in _F:
        mo = _F.index(mo.lower()) + 1
    else:
        raise ValueError(s)
    y = int(y) + (2000 if len(y) == 2 else 0)
    return datetime.date(y, mo, int(d))
''', [
    ("parse_indian_date('15/08/2024')", "_dt.date(2024, 8, 15)"),
    ("parse_indian_date('15-Aug-2024')", "_dt.date(2024, 8, 15)"),
    ("parse_indian_date('5.9.24')", "_dt.date(2024, 9, 5)"),
    ("parse_indian_date('1 January 2025')", "_dt.date(2025, 1, 1)"),
    ("parse_indian_date('03/04/2025')", "_dt.date(2025, 4, 3)"),
    ("parse_indian_date('29-FEB-2024')", "_dt.date(2024, 2, 29)"),
    ("parse_indian_date('7 dec 99')", "_dt.date(2099, 12, 7)"),
    ("parse_indian_date('31/02/2024')", "RAISES:ValueError"),
    ("parse_indian_date('13/13/2024')", "RAISES:ValueError"),
    ("parse_indian_date('15 Agust 2024')", "RAISES:ValueError"),
    ("parse_indian_date('2024-08-15')", "RAISES:ValueError"),
])

task(32, "parse_cin", "def parse_cin(cin: str) -> dict | None:", """
Write a function that validates and parses an Indian Corporate Identification Number (CIN). Strip and uppercase it first.
A CIN is 21 characters: 1 letter "L" (listed) or "U" (unlisted); 5 digits industry code; 2 letters state code;
4 digits year of incorporation (must be 1850-2100); 3 letters company type, which must be one of
PLC, PTC, GOI, SGC, FLC, GAP, NPL, ULL, ULT, OPC; 6 digits registration number.
Return {"listed": bool, "industry": "72200", "state": "MH", "year": 2010, "type": "PTC", "reg_no": "123456"}
(year as int, the rest as strings) or None if invalid.
""", '''
import re
_TYPES = {"PLC", "PTC", "GOI", "SGC", "FLC", "GAP", "NPL", "ULL", "ULT", "OPC"}
def parse_cin(cin):
    m = re.fullmatch(r"([LU])(\\d{5})([A-Z]{2})(\\d{4})([A-Z]{3})(\\d{6})", cin.strip().upper())
    if not m or m.group(5) not in _TYPES or not 1850 <= int(m.group(4)) <= 2100:
        return None
    return {"listed": m.group(1) == "L", "industry": m.group(2), "state": m.group(3), "year": int(m.group(4)),
            "type": m.group(5), "reg_no": m.group(6)}
''', [
    ("parse_cin('U72200MH2010PTC123456')", "{'listed': False, 'industry': '72200', 'state': 'MH', 'year': 2010, 'type': 'PTC', 'reg_no': '123456'}"),
    ("parse_cin(' l17110mh1973plc019786 ')", "{'listed': True, 'industry': '17110', 'state': 'MH', 'year': 1973, 'type': 'PLC', 'reg_no': '019786'}"),
    ("parse_cin('U74999KA2021OPC000001')", "{'listed': False, 'industry': '74999', 'state': 'KA', 'year': 2021, 'type': 'OPC', 'reg_no': '000001'}"),
    ("parse_cin('U85300DL2015NPL280000')", "{'listed': False, 'industry': '85300', 'state': 'DL', 'year': 2015, 'type': 'NPL', 'reg_no': '280000'}"),
    ("parse_cin('X72200MH2010PTC123456')", "None"),
    ("parse_cin('U72200MH2010XYZ123456')", "None"),
    ("parse_cin('U72200MH1800PTC123456')", "None"),
    ("parse_cin('U72200MH2010PTC12345')", "None"),
    ("parse_cin('U7220AMH2010PTC123456')", "None"),
    ("parse_cin('U722001H2010PTC123456')", "None"),
])

task(33, "upi_pay_link", "def upi_pay_link(vpa: str, name: str, amount_paise: int, note: str | None = None) -> str:", """
Write a function that builds a UPI deep link used for QR-code payments in India:
"upi://pay?pa=<vpa>&pn=<name>&am=<amount>&cu=INR" and, only if note is given and non-empty, "&tn=<note>" appended.
The amount is in rupees with exactly 2 decimals (amount_paise 12345 -> "123.45").
Every value (pa, pn, am, tn) is percent-encoded exactly as Python's urllib.parse.quote(value, safe="@") does
(so spaces become %20 and "@" is kept). Raise ValueError if amount_paise <= 0.
""", '''
from urllib.parse import quote
def upi_pay_link(vpa, name, amount_paise, note=None):
    if amount_paise <= 0:
        raise ValueError(amount_paise)
    q = lambda v: quote(v, safe="@")
    am = f"{amount_paise // 100}.{amount_paise % 100:02d}"
    s = f"upi://pay?pa={q(vpa)}&pn={q(name)}&am={q(am)}&cu=INR"
    return s + f"&tn={q(note)}" if note else s
''', [
    ("upi_pay_link('ramesh@okaxis', 'Ramesh Kumar', 12345)", "'upi://pay?pa=ramesh@okaxis&pn=Ramesh%20Kumar&am=123.45&cu=INR'"),
    ("upi_pay_link('shop@ybl', 'Sharma & Sons', 50000, 'Bill #42')", "'upi://pay?pa=shop@ybl&pn=Sharma%20%26%20Sons&am=500.00&cu=INR&tn=Bill%20%2342'"),
    ("upi_pay_link('a.b@upi', 'Ravi', 5)", "'upi://pay?pa=a.b@upi&pn=Ravi&am=0.05&cu=INR'"),
    ("upi_pay_link('x@upi', 'Kirana', 100, '')", "'upi://pay?pa=x@upi&pn=Kirana&am=1.00&cu=INR'"),
    ("upi_pay_link('x@upi', 'राम', 100)", "'upi://pay?pa=x@upi&pn=%E0%A4%B0%E0%A4%BE%E0%A4%AE&am=1.00&cu=INR'"),
    ("upi_pay_link('x@upi', 'A/B', 1000, 'rent=oct')", "'upi://pay?pa=x@upi&pn=A%2FB&am=10.00&cu=INR&tn=rent%3Doct'"),
    ("upi_pay_link('x@upi', 'Ravi', 1234567)", "'upi://pay?pa=x@upi&pn=Ravi&am=12345.67&cu=INR'"),
    ("upi_pay_link('x@upi', 'Ravi', 0)", "RAISES:ValueError"),
])

task(34, "bank_working_days", "def bank_working_days(start: datetime.date, end: datetime.date, holidays: list[datetime.date]) -> int:", """
Indian banks are closed on all Sundays and on the 2nd and 4th Saturdays of every month (1st, 3rd and 5th Saturdays are
working days). Write a function that counts bank working days from start to end, both inclusive, also excluding any
date listed in holidays. If start is after end return 0.
""", '''
import datetime
def bank_working_days(start, end, holidays):
    hs, n, d = set(holidays), 0, start
    while d <= end:
        closed = d.weekday() == 6 or (d.weekday() == 5 and (d.day - 1) // 7 + 1 in (2, 4)) or d in hs
        n += not closed
        d += datetime.timedelta(days=1)
    return n
''', [
    ("bank_working_days(_dt.date(2025, 3, 1), _dt.date(2025, 3, 31), [])", "24"),
    ("bank_working_days(_dt.date(2025, 3, 1), _dt.date(2025, 3, 31), [_dt.date(2025, 3, 14), _dt.date(2025, 3, 31)])", "22"),
    ("bank_working_days(_dt.date(2025, 3, 8), _dt.date(2025, 3, 8), [])", "0"),
    ("bank_working_days(_dt.date(2025, 3, 15), _dt.date(2025, 3, 15), [])", "1"),
    ("bank_working_days(_dt.date(2025, 3, 29), _dt.date(2025, 3, 29), [])", "1"),
    ("bank_working_days(_dt.date(2025, 3, 22), _dt.date(2025, 3, 22), [])", "0"),
    ("bank_working_days(_dt.date(2025, 3, 31), _dt.date(2025, 3, 1), [])", "0"),
    ("bank_working_days(_dt.date(2024, 8, 1), _dt.date(2024, 8, 31), [_dt.date(2024, 8, 15)])", "24"),
    ("bank_working_days(_dt.date(2025, 3, 2), _dt.date(2025, 3, 2), [])", "0"),
    ("bank_working_days(_dt.date(2025, 3, 3), _dt.date(2025, 3, 3), [_dt.date(2025, 3, 9)])", "1"),
    ("bank_working_days(_dt.date(2024, 12, 28), _dt.date(2025, 1, 11), [_dt.date(2025, 1, 1)])", "10"),
])

task(35, "cheque_amount_words", "def cheque_amount_words(paise: int) -> str:", """
Write a function that writes an amount (given in paise) in words for an Indian cheque, using the Indian system
(Thousand, Lakh, Crore). Rupees part n must be < 1,000,000,000. Format:
"Rupees <rupee words> Only" when paise part is 0, otherwise "Rupees <rupee words> and <paise words> Paise Only".
Words rules: every word starts with a capital letter; 21-99 non-multiples of ten use a hyphen with both parts capitalised
("Forty-Two"); no "and" inside the number; 0 is "Zero".
Example: 123456789 -> "Rupees Twelve Lakh Thirty-Four Thousand Five Hundred Sixty-Seven and Eighty-Nine Paise Only".
""", WORDS_EN_REF + '''
def _cap(s):
    return " ".join("-".join(p.capitalize() for p in w.split("-")) for w in s.split())
def cheque_amount_words(paise):
    r, p = divmod(paise, 100)
    out = "Rupees " + _cap(_words(r))
    if p:
        out += " and " + _cap(_words(p)) + " Paise"
    return out + " Only"
''', [
    ("cheque_amount_words(123456789)", "'Rupees Twelve Lakh Thirty-Four Thousand Five Hundred Sixty-Seven and Eighty-Nine Paise Only'"),
    ("cheque_amount_words(10000)", "'Rupees One Hundred Only'"),
    ("cheque_amount_words(50)", "'Rupees Zero and Fifty Paise Only'"),
    ("cheque_amount_words(0)", "'Rupees Zero Only'"),
    ("cheque_amount_words(100000000)", "'Rupees Ten Lakh Only'"),
    ("cheque_amount_words(1000000001)", "'Rupees One Crore and One Paise Only'"),
    ("cheque_amount_words(2500050)", "'Rupees Twenty-Five Thousand and Fifty Paise Only'"),
    ("cheque_amount_words(1111)", "'Rupees Eleven and Eleven Paise Only'"),
    ("cheque_amount_words(9999999999)", "'Rupees Nine Crore Ninety-Nine Lakh Ninety-Nine Thousand Nine Hundred Ninety-Nine and Ninety-Nine Paise Only'"),
])

task(36, "electricity_bill", "def electricity_bill(units: int, sanctioned_load_kw: float) -> float:", """
Write a function that computes a domestic electricity bill with telescopic slab tariff (each rate applies only to the
units inside its slab):
units 1-100 at ₹3.00 per unit, 101-200 at ₹4.50, 201-500 at ₹6.00, above 500 at ₹7.50.
Fixed charge: ₹50 per kW of sanctioned load, with the load rounded UP to a whole kW (minimum 1 kW).
Electricity duty: 5% of the energy charge only (not of the fixed charge).
Total = energy charge + fixed charge + duty, rounded to 2 decimals (exact halves up). Return a float.
""", HALF_UP + '''
import math
def electricity_bill(units, sanctioned_load_kw):
    e, rem = Decimal(0), units
    for size, rate in ((100, "3.00"), (100, "4.50"), (300, "6.00"), (None, "7.50")):
        take = rem if size is None else min(rem, size)
        e += take * Decimal(rate); rem -= take
        if rem <= 0:
            break
    fixed = 50 * max(1, math.ceil(sanctioned_load_kw))
    return float(_r(e + fixed + e * Decimal("0.05"), "0.01"))
''', [
    ("electricity_bill(0, 1)", "50.0"),
    ("electricity_bill(100, 1)", "365.0"),
    ("electricity_bill(150, 2)", "651.25"),
    ("electricity_bill(200, 1.5)", "887.5"),
    ("electricity_bill(350, 3)", "1882.5"),
    ("electricity_bill(500, 5)", "2927.5"),
    ("electricity_bill(501, 5)", "2935.38"),
    ("electricity_bill(777, 0.5)", "4908.88"),
    ("electricity_bill(1, 0)", "53.15"),
    ("electricity_bill(101, 2.01)", "469.73"),
])

task(37, "format_compact_inr", "def format_compact_inr(rupees: int) -> str:", """
Write a function that formats a rupee amount compactly, the way Indian news and dashboards do.
- If abs(amount) >= 1,00,00,000: value in crores, rounded to 2 decimals (halves up), trailing zeros and a trailing
  "." removed, followed by " Cr" (12500000 -> "1.25 Cr", 10000000 -> "1 Cr").
- Else if abs(amount) >= 1,00,000: same in lakhs with " L" (150000 -> "1.5 L", 1234567 -> "12.35 L").
- Else: the integer with Indian digit grouping (99999 -> "99,999", 500 -> "500").
The unit is chosen from the value before rounding (9999999 -> "100 L"). Negative amounts get a leading "-".
""", HALF_UP + '''
def format_compact_inr(rupees):
    sign, a = ("-" if rupees < 0 else ""), abs(rupees)
    for div, unit in ((10**7, " Cr"), (10**5, " L")):
        if a >= div:
            v = str(_r(Decimal(a) / div, "0.01"))
            return sign + v.rstrip("0").rstrip(".") + unit
    s = str(a)
    head, groups = s[:-3], [s[-3:]]
    while head:
        groups.insert(0, head[-2:]); head = head[:-2]
    s = ",".join(groups)
    return sign + s
''', [
    ("format_compact_inr(12500000)", "'1.25 Cr'"),
    ("format_compact_inr(10000000)", "'1 Cr'"),
    ("format_compact_inr(150000)", "'1.5 L'"),
    ("format_compact_inr(1234567)", "'12.35 L'"),
    ("format_compact_inr(99999)", "'99,999'"),
    ("format_compact_inr(500)", "'500'"),
    ("format_compact_inr(0)", "'0'"),
    ("format_compact_inr(9999999)", "'100 L'"),
    ("format_compact_inr(-4560000000)", "'-456 Cr'"),
    ("format_compact_inr(100500)", "'1.01 L'"),
    ("format_compact_inr(-1000)", "'-1,000'"),
    ("format_compact_inr(1234567890123)", "'123456.79 Cr'"),
])

task(38, "next_invoice_number", "def next_invoice_number(prev: str | None, d: datetime.date) -> str:", """
GST invoice numbers must be sequential within a financial year (1 April - 31 March). Write a function that returns the
next invoice number in the format "INV/<FY>/<seq>", where FY is like "2024-25" (start year, "-", last 2 digits of end year)
and seq is zero-padded to at least 4 digits ("0001"; after "9999" comes "10000").
prev is the previous invoice number in the same format, or None. If prev is None or its FY differs from the FY of date d,
start at 0001; otherwise increment prev's sequence by one.
Example: next_invoice_number("INV/2024-25/0041", date(2025, 3, 31)) -> "INV/2024-25/0042".
""", "import datetime\n" + FY_REF + '''
def next_invoice_number(prev, d):
    fy = fy_label(d)[2:]
    n = 1
    if prev:
        _, pfy, seq = prev.split("/")
        if pfy == fy:
            n = int(seq) + 1
    return f"INV/{fy}/{n:04d}"
''', [
    ("next_invoice_number('INV/2024-25/0041', _dt.date(2025, 3, 31))", "'INV/2024-25/0042'"),
    ("next_invoice_number('INV/2024-25/0041', _dt.date(2025, 4, 1))", "'INV/2025-26/0001'"),
    ("next_invoice_number(None, _dt.date(2024, 4, 1))", "'INV/2024-25/0001'"),
    ("next_invoice_number(None, _dt.date(2024, 3, 31))", "'INV/2023-24/0001'"),
    ("next_invoice_number('INV/2024-25/9999', _dt.date(2024, 12, 1))", "'INV/2024-25/10000'"),
    ("next_invoice_number('INV/2024-25/0009', _dt.date(2024, 12, 1))", "'INV/2024-25/0010'"),
    ("next_invoice_number('INV/2099-00/0001', _dt.date(2100, 1, 5))", "'INV/2099-00/0002'"),
    ("next_invoice_number('INV/2023-24/0500', _dt.date(2024, 6, 1))", "'INV/2024-25/0001'"),
])

task(39, "msme_category", "def msme_category(investment_cr: float, turnover_cr: float) -> str:", """
Write a function that classifies an Indian enterprise under these MSME limits (both values in crore rupees; a limit
means "up to and including"):
Micro: investment <= 2.5 and turnover <= 10. Small: investment <= 25 and turnover <= 100.
Medium: investment <= 125 and turnover <= 500. Both conditions must hold for a category; check from Micro upwards and
return the first that fits: "Micro", "Small", "Medium", otherwise "Not MSME". Raise ValueError if either value is negative.
""", '''
def msme_category(investment_cr, turnover_cr):
    if investment_cr < 0 or turnover_cr < 0:
        raise ValueError
    for name, i, t in (("Micro", 2.5, 10), ("Small", 25, 100), ("Medium", 125, 500)):
        if investment_cr <= i and turnover_cr <= t:
            return name
    return "Not MSME"
''', [
    ("msme_category(1, 5)", "'Micro'"),
    ("msme_category(2.5, 10)", "'Micro'"),
    ("msme_category(2.5, 10.01)", "'Small'"),
    ("msme_category(2.6, 1)", "'Small'"),
    ("msme_category(25, 100)", "'Small'"),
    ("msme_category(0.5, 150)", "'Medium'"),
    ("msme_category(125, 500)", "'Medium'"),
    ("msme_category(125.01, 10)", "'Not MSME'"),
    ("msme_category(10, 501)", "'Not MSME'"),
    ("msme_category(0, 0)", "'Micro'"),
    ("msme_category(-1, 5)", "RAISES:ValueError"),
])

task(40, "advance_tax_due", "def advance_tax_due(total_tax: int, on_date: datetime.date) -> int:", """
Write a function that returns the cumulative advance tax that must have been paid by a given date in India.
total_tax is the estimated tax for the financial year (1 April - 31 March) that contains on_date.
If total_tax is less than 10,000, nothing is due (return 0). Otherwise the cumulative amount due is:
before 15 June: 0; from 15 June: 15%; from 15 September: 45%; from 15 December: 75%; from 15 March: 100%
(the instalment date itself counts, e.g. on 15 June 15% is due). Round to the nearest rupee, exact halves up. Return an int.
""", HALF_UP + '''
import datetime
def advance_tax_due(total_tax, on_date):
    if total_tax < 10000:
        return 0
    y = on_date.year if on_date.month >= 4 else on_date.year - 1
    pct = 0
    for d, p in ((datetime.date(y, 6, 15), 15), (datetime.date(y, 9, 15), 45), (datetime.date(y, 12, 15), 75),
                 (datetime.date(y + 1, 3, 15), 100)):
        if on_date >= d:
            pct = p
    return int(_r(Decimal(total_tax) * pct / 100))
''', [
    ("advance_tax_due(100000, _dt.date(2024, 6, 14))", "0"),
    ("advance_tax_due(100000, _dt.date(2024, 6, 15))", "15000"),
    ("advance_tax_due(100000, _dt.date(2024, 9, 14))", "15000"),
    ("advance_tax_due(100000, _dt.date(2024, 9, 15))", "45000"),
    ("advance_tax_due(100000, _dt.date(2024, 12, 31))", "75000"),
    ("advance_tax_due(100000, _dt.date(2025, 3, 14))", "75000"),
    ("advance_tax_due(100000, _dt.date(2025, 3, 15))", "100000"),
    ("advance_tax_due(100000, _dt.date(2025, 4, 1))", "0"),
    ("advance_tax_due(9999, _dt.date(2025, 3, 31))", "0"),
    ("advance_tax_due(12345, _dt.date(2024, 6, 20))", "1852"),
    ("advance_tax_due(10001, _dt.date(2025, 1, 10))", "7501"),
    ("advance_tax_due(250000, _dt.date(2025, 2, 1))", "187500"),
])

assert len(T) == 40 and [t["id"] for t in T] == list(range(1, 41))
