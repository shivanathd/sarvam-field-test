"""Translation QA: blind back-translation to English (Gemini), then a second call compares the back-translation with the
original English spec and lists differences that would change correct code. Flagged items are reviewed by hand.
Output: data/uc11_bharat_code/backtranslation.json (cached; rerun is free)."""
import json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.bench import chat, GEMINI_CHAT, DATA
from prompts import SPECS, TASKS

OUT = DATA / "uc11_bharat_code" / "backtranslation.json"
OUT.parent.mkdir(parents=True, exist_ok=True)
done = json.loads(OUT.read_text()) if OUT.exists() else {}


def one(key):
    lang, tid = key.split(":")
    src = SPECS[lang][int(tid)]
    bt = chat(GEMINI_CHAT, [{"role": "user", "content": "Translate this programming task specification into English. "
              "Translate faithfully, do not fix or improve anything, keep code/literals as is. Output only the translation.\n\n" + src}],
              max_tokens=2000)["text"]
    cmp = chat(GEMINI_CHAT, [{"role": "user", "content":
               "Spec A is an original programming task. Spec B is a back-translation of a translated version of it.\n"
               "List every difference in meaning between A and B that could change what a correct implementation must do "
               "(rules, numbers, edge cases, return values, formats). Ignore wording/style. If there are none, reply exactly NONE.\n\n"
               f"=== A ===\n{TASKS[int(tid)]['spec']}\n\n=== B ===\n{bt}"}], max_tokens=1500)["text"].strip()
    return key, {"back_translation": bt, "diff": cmp}


keys = [f"{l}:{t}" for l in ("hi", "ta", "hinglish") for t in TASKS if f"{l}:{t}" not in done]
with ThreadPoolExecutor(4) as ex:
    for k, v in ex.map(one, keys):
        done[k] = v
        OUT.write_text(json.dumps(done, ensure_ascii=False, indent=1))
flag = {k: v["diff"] for k, v in done.items() if v["diff"] != "NONE"}
print(f"{len(done)} checked, {len(flag)} flagged")
for k, d in sorted(flag.items(), key=lambda kv: (kv[0].split(':')[0], int(kv[0].split(':')[1]))):
    print(f"--- {k}\n{d}\n")
