"""Known-answer checks for legal translation/summaries: are the facts of the English source still there?

Entity types (from make_data.py) and how each is found in a Hindi/Tamil/Marathi/Bengali output:
  number  standalone digit run (Indic digits are folded to ASCII first; "1,234" == "1234").
  amount  rupee value: a bare number equal to the value, or "N lakh"/"N crore" in any of the languages
          (12.5 लाख == ₹12,50,000), including Indian compounds ("19 லட்சத்து 51 ஆயிரத்து 500").
          Amounts written fully in words are NOT credited (counted as dropped).
  date    year present, with the day number and the month (name in en/hi/mr/ta/bn, or numeric d/m/y)
          within the 60 characters before the year or 25 after it (Tamil often writes "2021 ஜனவரி 30").
  name    transliteration-tolerant: each word of the name is reduced to a consonant skeleton
          (voicing/aspiration merged, s/c/j merged, v/w/b merged, vowels, h and y dropped, the flap
          ड़/ড় matched as d or r, Indic letters mapped through the shared ISCII-order Unicode layout), and
          must match some output word's skeleton (prefix, or difflib ratio >= 0.75, which tolerates Tamil's
          missing voiced letters and case suffixes). Words with a 1-letter skeleton are not checked.
          Known misses: Tamil spells h as க (சவுகான் for Chauhan), and renamed places (Bombay -> मुंबई)
          count as altered.
Unsupported numbers: distinct numbers in the output that the source does not support (not a source number, not an
amount in lakh/crore/thousand units, not a date part, not 1-10 which are used as list markers). Values the
model computed itself (a deadline date, a grand total) count too: they are not in the order, and a litigant
acting on a wrong computed date is harmed just the same.
Run `python score.py` for the self-test.
"""
import re, unicodedata
from datetime import date
from difflib import SequenceMatcher

LAKH = ["lakh", "lac", "लाख", "लक्ष", "லட்சம்", "இலட்சம்", "லட்ச", "লাখ", "লক্ষ"]
CRORE = ["crore", "करोड", "कोटी", "கோடி", "কোটি"]
THOUSAND = ["thousand", "हजार", "हज़ार", "ஆயிர", "হাজার"]
MONTHS = {
    "en": "january february march april may june july august september october november december",
    "hi": "जनवरी फरवरी मार्च अप्रैल मई जून जुलाई अगस्त सितंबर अक्टूबर नवंबर दिसंबर",
    "hi2": "जनवरी फ़रवरी मार्च अप्रेल मई जून जुलाई अगस्त सितम्बर अक्तूबर नवम्बर दिसम्बर",
    "mr": "जानेवारी फेब्रुवारी मार्च एप्रिल मे जून जुलै ऑगस्ट सप्टेंबर ऑक्टोबर नोव्हेंबर डिसेंबर",
    "ta": "ஜனவரி பிப்ரவரி மார்ச் ஏப்ரல் மே ஜூன் ஜூலை ஆகஸ்ட் செப்டம்பர் அக்டோபர் நவம்பர் டிசம்பர்",
    "bn": "জানুয়ারি ফেব্রুয়ারি মার্চ এপ্রিল মে জুন জুলাই আগস্ট সেপ্টেম্বর অক্টোবর নভেম্বর ডিসেম্বর",
}


def fold(s):
    """NFD, drop nukta, Indic digits -> ASCII, lowercase."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if c not in "़়઼")
    s = "".join(str(unicodedata.digit(c)) if c.isdigit() and not c.isascii() else c for c in s)
    return unicodedata.normalize("NFC", s).lower()


def stem(w):
    return w[:3] if len(w) > 3 else w


MONTH_STEMS = {}  # stem -> month number
for names in MONTHS.values():
    for i, m in enumerate(fold(names).split(), 1):
        MONTH_STEMS[stem(m)] = i


def tokens(s):
    return [t for t in re.split(r"[\s,.;:()\"'“”‘’/\-–—।]+", s) if t]


# a number may follow "Rs." / "ரூ." directly, but not continue another number ("4.75" is one number)
NUM = re.compile(r"(?<!\d)(?<!\d[.,])\d+(?:,\d+)*(?:\.\d+)?(?!\d)")
NUM_DATE = re.compile(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{4})(?!\d)")


def numbers(s):
    """[(value, raw, start, end)] for every number in folded text; 14.07.2020 counts as 14, 7, 2020."""
    s = NUM_DATE.sub(r"\1 \2 \3", s)  # same length, so indices still point into the caller's string
    return [(float(m.group().replace(",", "")), m.group(), m.start(), m.end()) for m in NUM.finditer(s)]


def amount_groups(s):
    """[(rupee value, [indices into numbers(s)])]: each number scaled by a following lakh/crore/thousand word,
    plus compounds written the Indian way, e.g. "19 லட்சத்து 51 ஆயிரத்து 500" = 19,51,500."""
    nums = numbers(s)
    parts = []
    for v, raw, a, b in nums:
        mult = 1
        for words, k in ((LAKH, 1e5), (CRORE, 1e7), (THOUSAND, 1e3)):
            if any(s[b:b + 14].lstrip().startswith(fold(w)) for w in words):
                mult = k
        parts.append((v * mult, mult))
    out = [(v, [i]) for i, (v, _) in enumerate(parts)]
    for i in range(len(parts)):
        total, j = parts[i][0], i
        while (j + 1 < len(parts) and parts[j][1] > parts[j + 1][1] and parts[j][1] > 1
               and nums[j + 1][2] - nums[j][3] <= 25):
            j += 1
            total += parts[j][0]
            out.append((total, list(range(i, j + 1))))
    return out


def scaled_values(s):
    return [v for v, _ in amount_groups(s)]


def has_number(s, n):
    return re.search(rf"(?<!\d)(?<!\d[.,]){re.escape(str(n))}(?!\d|[.,]\d)", s.replace(",", "")) is not None


def has_amount(s, value):
    return any(abs(v - value) < 1 for v in scaled_values(s))


def has_date(s, iso):
    d = date.fromisoformat(iso)
    for m in re.finditer(rf"(?<!\d){d.year}(?!\d)", s):
        before = s[max(0, m.start() - 60):m.start()]
        if re.search(rf"(?<!\d)0?{d.day}[./-]0?{d.month}[./-]$", before.rstrip()):
            return True
        win = before + " " + s[m.end():m.end() + 25]  # Tamil often writes year-first: "2021 ஜனவரி 30"
        if not re.search(rf"(?<!\d)0?{d.day}(?!\d)", win):
            continue
        if any(MONTH_STEMS.get(stem(t)) == d.month and (len(t) > 2 or t in MONTH_STEMS) for t in tokens(win)):
            return True
    return False


# ---------- transliteration-tolerant names ----------
# Offsets inside any Indic block (Unicode keeps the ISCII order, so Tamil க and Bengali ক share क's offset).
# Classes merge voicing and aspiration (Tamil has one letter for k/g, t/d, p/b) and s with c/j (Tamil ச is
# both "s" and "ch"); v/w and b share a class because Bengali has one letter for both.
DEV_CLASS = {}
for offs, cls in (((0x15, 0x16, 0x17, 0x18, 0x58, 0x59, 0x5A), "K"),
                  ((0x1A, 0x1B, 0x1C, 0x1D, 0x5B, 0x36, 0x37, 0x38), "S"),
                  ((0x1F, 0x20, 0x21, 0x22, 0x24, 0x25, 0x26, 0x27), "T"), ((0x5C, 0x5D, 0x30, 0x31), "R"),
                  ((0x02, 0x19, 0x1E, 0x23, 0x28, 0x29), "N"), ((0x2A, 0x2B, 0x2C, 0x2D, 0x35, 0x5E), "P"),
                  ((0x2E,), "M"), ((0x32, 0x33, 0x34), "L")):
    for o in offs:
        DEV_CLASS[o] = cls
NUKTA = 0x3C
EN_DIGRAPH = [("chh", "S"), ("sh", "S"), ("ch", "S"), ("th", "T"), ("dh", "T"), ("bh", "P"), ("ph", "P"),
              ("kh", "K"), ("gh", "K"), ("jh", "S")]
EN_CLASS = dict(zip("kgqcjztdpbfvwsmnrlx", "KKKKSSTTPPPPPSMNRLX"))  # y and h dropped, like vowels


def skeleton(word):
    out = []
    if word.isascii():
        w = word.lower()
        for a, b in EN_DIGRAPH:
            w = w.replace(a, b)
        for c in w:
            out.append(c if c in "STPK" else EN_CLASS.get(c, ""))
        s = "".join(out).replace("X", "KS")
    else:
        offs = [(ord(c) - 0x0900) % 0x80 for c in unicodedata.normalize("NFD", word) if 0x0900 <= ord(c) < 0x0D80]
        for i, o in enumerate(offs):
            if o in (0x21, 0x22) and i + 1 < len(offs) and offs[i + 1] == NUKTA:
                out.append("D")  # ड़ ढ़ ড় ঢ় are a flap, written d or r in English: matched as either
            else:
                out.append(DEV_CLASS.get(o, ""))
        s = "".join(out)
    return re.sub(r"(.)\1+", r"\1", s)


def has_name(s, name):
    toks = [v for t in tokens(s) for v in {skeleton(t).replace("D", "T"), skeleton(t).replace("D", "R")}]
    for w in name.split():
        ws = skeleton(w)
        if len(ws) < 2:
            continue
        if not any(t.startswith(ws) or SequenceMatcher(None, ws, t).ratio() >= 0.75
                   or SequenceMatcher(None, ws, t[:len(ws)]).ratio() >= 0.75 for t in toks if t):
            return False
    return True


def entity_found(text, e):
    s = fold(text)
    t = e["type"]
    if t == "number":
        return has_number(s, e["value"])
    if t == "amount":
        return has_amount(s, e["value"])
    if t == "date":
        return has_date(s, e["value"])
    return has_name(text, e["value"])


def unsupported_numbers(text, source, entities):
    """Numbers in `text` the source cannot account for (hallucinated or altered values)."""
    ok = {n[0] for n in numbers(fold(source))}
    amounts = [e["value"] for e in entities if e["type"] == "amount"]
    for e in entities:
        if e["type"] == "date":
            d = date.fromisoformat(e["value"])
            ok |= {d.day, d.month, d.year}
    t = fold(text)
    covered = {i for v, idx in amount_groups(t) if any(abs(v - a) < 1 for a in amounts) for i in idx}
    bad = []
    for i, (v, raw, _, _) in enumerate(numbers(t)):
        if i in covered or v in ok or (v.is_integer() and 1 <= v <= 10):
            continue
        if raw not in bad:  # distinct values: a model stuck in a loop repeats one wrong number many times
            bad.append(raw)
    return bad


def script_share(text, script_range):
    lo, hi = script_range
    letters = [c for c in text if c.isalpha()]
    return sum(lo <= ord(c) <= hi for c in letters) / max(1, len(letters))


if __name__ == "__main__":
    hi = "रमेश कुलकर्णी ने 2 जून 2021 को ₹4,17,000 का चेक संख्या ८०६२८० दिया; धारा 138 के तहत 12.5 लाख रुपये।"
    assert entity_found(hi, {"type": "name", "value": "Ramesh Kulkarni"})
    assert entity_found(hi, {"type": "date", "value": "2021-06-02"})
    assert entity_found(hi, {"type": "amount", "value": 417000})
    assert entity_found(hi, {"type": "amount", "value": 1250000})
    assert entity_found(hi, {"type": "number", "value": 806280})
    assert entity_found(hi, {"type": "number", "value": "138"})
    assert not entity_found(hi, {"type": "number", "value": "13"})
    assert not entity_found(hi, {"type": "date", "value": "2021-07-02"})
    ta = "சுப்ரதா கோஷ் அவர்களுக்கு 30 ஆகஸ்ட் 2021 அன்று ₹8.34 லட்சம் வழங்க வேண்டும். ஹரிஷ் பட்டுக்கு 11 மாதங்கள்."
    assert entity_found(ta, {"type": "name", "value": "Subrata Ghosh"})
    assert entity_found(ta, {"type": "name", "value": "Harish Bhatt"})
    assert entity_found(ta, {"type": "date", "value": "2021-08-30"})
    assert entity_found(ta, {"type": "amount", "value": 834000})
    assert not entity_found(ta, {"type": "name", "value": "Sanjay Banerjee"})
    assert not has_name("ராஜசேகர பிரசாத் யாதவ்", "Rajendra Prasad Yadav")
    for en, native in (("Suresh Pawar", "சுரேஷ் பவார்"), ("Salem", "சேலம்"), ("Howrah", "हावड़ा"),
                       ("Nashik", "நாசிக்"), ("Sunita Joshi", "சுனிதா ஜோஷி"), ("Rajendra Prasad Yadav", "রাজেন্দ্র প্রসাদ যাদব"),
                       ("Shobha Gaikwad", "शोभा गायकवाड़"), ("Prakash Iyer", "பிரகாஷ் ஐயர்")):
        assert has_name(native, en), (en, native, skeleton(native))
    assert entity_found("நோட்டீஸ் 2021 ஜனவரி 30 அன்று", {"type": "date", "value": "2021-01-30"})
    bn = "মোহাম্মদ ইরফান শেখ ৬ নভেম্বর ২০২০ তারিখে গ্রেপ্তার হন; ৩৬ লক্ষ টাকা।"
    assert entity_found(bn, {"type": "name", "value": "Mohammed Irfan Shaikh"})
    assert entity_found(bn, {"type": "date", "value": "2020-11-06"})
    assert entity_found(bn, {"type": "amount", "value": 3600000})
    mr = "अर्जदार गायकवाड यांनी 06/11/2020 रोजी मे महिन्यात"
    assert entity_found(mr, {"type": "name", "value": "Shobha Gaikwad"}) is False  # Shobha missing
    assert entity_found(mr, {"type": "date", "value": "2020-11-06"})
    src = "pay ₹4,17,000 within 61 days on 2 June 2021"
    ents = [{"type": "amount", "value": 417000}, {"type": "date", "value": "2021-06-02"}]
    assert unsupported_numbers("₹4.17 लाख 61 दिन, 2 जून 2021, 3 सूची", src, ents) == []
    assert unsupported_numbers("₹4,71,000 और 90 दिन", src, ents) == ["4,71,000", "90"]
    assert has_amount(fold("ரூ.16,250 அபராதம்"), 16250) and has_amount(fold("ரூ.25.5 கோடியை"), 255000000)
    assert entity_found("ரூ.94,000 தனிப்பட்ட", {"type": "number", "value": 94000})
    assert unsupported_numbers("14.07.2020 முதல்", "14 July 2020", [{"type": "date", "value": "2020-07-14"}]) == []
    assert has_amount(fold("மொத்தம் 19 லட்சத்து 51 ஆயிரத்து 500 ரூபாயை"), 1951500)
    assert unsupported_numbers("2 லட்சத்து 99 ஆயிரத்து 500 ரூபாய்", "₹2,99,500", [{"type": "amount", "value": 299500}]) == []
    print("score.py self-test ok")
