"""Build the per-language user prompts. The system prompt stays English (as in real coding tools);
the task itself and the output instruction are in the developer's language."""
import re
from tasks import T
from spec_hi import HI
from spec_ta import TA
from spec_hinglish import HINGLISH

LANGS = ["en", "hi", "ta", "hinglish"]
SYSTEM = "You are an expert Python developer working on Indian business software. Follow the specification exactly."
INSTR = {
    "en": "Write the complete Python function (with any imports it needs). Use only the standard library. "
          "Reply with a single ```python code block.",
    "hi": "पूरा Python फ़ंक्शन लिखिए (ज़रूरी imports के साथ)। सिर्फ़ standard library इस्तेमाल कीजिए। "
          "जवाब में केवल एक ```python code block दीजिए।",
    "ta": "முழு Python function-ஐ எழுதுங்கள் (தேவையான imports உடன்). Standard library-ஐ மட்டும் பயன்படுத்துங்கள். "
          "பதிலில் ஒரே ஒரு ```python code block மட்டும் தாருங்கள்.",
    "hinglish": "Poora Python function likho (jo imports chahiye unke saath). Sirf standard library use karna. "
                "Reply mein bas ek ```python code block do.",
}
SPECS = {"en": {t["id"]: t["spec"] for t in T}, "hi": HI, "ta": TA, "hinglish": HINGLISH}
TASKS = {t["id"]: t for t in T}


def user_prompt(tid, lang):
    t = TASKS[tid]
    return f"{SPECS[lang][tid].strip()}\n\n```python\n{t['signature']}\n```\n\n{INSTR[lang]}"


def literals(spec):
    """Tokens that must survive translation verbatim: quoted strings, numbers, code-ish identifiers."""
    toks = set(re.findall(r'"[^"]*"', spec))
    toks |= set(re.findall(r"\d[\d,.]*\d|\d", spec))
    toks |= set(re.findall(r"\b[A-Za-z_]+_[A-Za-z_]+\b|\b[A-Za-z]+\([^)]*\)", spec))
    return {x.rstrip(".,") for x in toks}


if __name__ == "__main__":
    bad = 0
    for lang in LANGS[1:]:
        assert sorted(SPECS[lang]) == list(range(1, 41)), lang
        for tid in TASKS:
            miss = [x for x in literals(TASKS[tid]["spec"]) if x not in SPECS[lang][tid]]
            if miss:
                bad += 1
                print(lang, tid, miss)
    print("literal check:", "OK" if not bad else f"{bad} specs missing literals")
