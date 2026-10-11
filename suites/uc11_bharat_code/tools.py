"""Tool-calling sub-test: 50 voice-assistant commands (30 base + 20 harder) in Hindi, Hinglish, Tamil and Bengali against a small payments-app
tool schema. Native tool calling everywhere it works (Sarvam /v1/chat/completions `tools`, Gemini function declarations,
llama-server --jinja); JSON-prompting fallback otherwise. Metric: correct tool AND exact arguments."""
import json, os, re, sys, threading, time, unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.bench import sarvam_post, log, raw_append, raw_load, _retry, GEMINI_CHAT, LOCAL_PORTS

UC = "uc11_bharat_code"
SYSTEM = ("You are the voice assistant inside an Indian payments app. Users speak in their own language. "
          "For every request call exactly one tool with the correct arguments. Amounts are whole rupees (integers). "
          "Mobile numbers are passed as 10 digits. Leave out optional arguments the user did not mention.")
TOOLS = [
    {"name": "recharge", "description": "Prepaid mobile recharge with a plan of the given price.",
     "parameters": {"type": "object", "properties": {
         "amount": {"type": "integer", "description": "Plan price in rupees"},
         "mobile": {"type": "string", "description": "10-digit number to recharge; omit to recharge the user's own number"}},
         "required": ["amount"]}},
    {"name": "pay_bill", "description": "Pay a utility or service bill.",
     "parameters": {"type": "object", "properties": {
         "biller": {"type": "string", "enum": ["electricity", "water", "piped_gas", "broadband", "dth", "mobile_postpaid"]},
         "amount": {"type": "integer", "description": "Rupees to pay; omit to pay the full amount due"}},
         "required": ["biller"]}},
    {"name": "check_balance", "description": "Check the balance of one of the user's accounts.",
     "parameters": {"type": "object", "properties": {
         "account": {"type": "string", "enum": ["bank", "credit_card", "wallet"]}}, "required": ["account"]}},
    {"name": "book_cylinder", "description": "Book LPG gas cylinder refills.",
     "parameters": {"type": "object", "properties": {
         "company": {"type": "string", "enum": ["indane", "hp_gas", "bharatgas"]},
         "quantity": {"type": "integer", "description": "Number of cylinders, default 1"}}, "required": ["company"]}},
    {"name": "transfer_upi", "description": "Send money by UPI.",
     "parameters": {"type": "object", "properties": {
         "payee": {"type": "string", "description": "UPI ID or 10-digit mobile number of the receiver"},
         "amount": {"type": "integer", "description": "Rupees"}}, "required": ["payee", "amount"]}},
]
DEFAULTS = {("book_cylinder", "quantity"): 1}

# (id, lang, utterance, gold_tool, gold_args). Synthetic numbers and UPI IDs.
CASES = [
    ("h1", "hi", "मेरा 299 वाला रिचार्ज कर दो", "recharge", {"amount": 299}),
    ("h2", "hi", "बिजली का बिल भर दो", "pay_bill", {"biller": "electricity"}),
    ("h3", "hi", "9876543210 पर पाँच सौ रुपये भेज दो", "transfer_upi", {"payee": "9876543210", "amount": 500}),
    ("h4", "hi", "मेरे बैंक खाते में कितना पैसा है?", "check_balance", {"account": "bank"}),
    ("h5", "hi", "इंडेन का गैस सिलेंडर बुक कर दो", "book_cylinder", {"company": "indane"}),
    ("h6", "hi", "मम्मी के नंबर 9123456780 पर 239 का रिचार्ज करो", "recharge", {"amount": 239, "mobile": "9123456780"}),
    ("h7", "hi", "डीटीएच का बिल 450 रुपये भर दो", "pay_bill", {"biller": "dth", "amount": 450}),
    ("h8", "hi", "ramesh@okaxis को ढाई हज़ार भेजो", "transfer_upi", {"payee": "ramesh@okaxis", "amount": 2500}),
    ("x1", "hinglish", "mera 299 wala recharge kar do", "recharge", {"amount": 299}),
    ("x2", "hinglish", "bhai dedh hazaar bhej do 9988776655 pe", "transfer_upi", {"payee": "9988776655", "amount": 1500}),
    ("x3", "hinglish", "credit card ka balance kitna bacha hai?", "check_balance", {"account": "credit_card"}),
    ("x4", "hinglish", "HP gas ke do cylinder book kar do", "book_cylinder", {"company": "hp_gas", "quantity": 2}),
    ("x5", "hinglish", "broadband ka bill pay karna hai, 799 ka", "pay_bill", {"biller": "broadband", "amount": 799}),
    ("x6", "hinglish", "wallet mein kitne paise hain", "check_balance", {"account": "wallet"}),
    ("x7", "hinglish", "sava sau rupaye bhejo shopkeeper@ybl ko", "transfer_upi", {"payee": "shopkeeper@ybl", "amount": 125}),
    ("x8", "hinglish", "piped gas ka bill bhar do, 612 rupaye", "pay_bill", {"biller": "piped_gas", "amount": 612}),
    ("t1", "ta", "என் நம்பருக்கு 349 ரூபாய் ரீசார்ஜ் பண்ணுங்க", "recharge", {"amount": 349}),
    ("t2", "ta", "கரண்ட் பில் கட்டுங்க", "pay_bill", {"biller": "electricity"}),
    ("t3", "ta", "9876501234-க்கு ஆயிரம் ரூபாய் அனுப்புங்க", "transfer_upi", {"payee": "9876501234", "amount": 1000}),
    ("t4", "ta", "பாரத் கேஸ் சிலிண்டர் புக் பண்ணுங்க", "book_cylinder", {"company": "bharatgas"}),
    ("t5", "ta", "என் பேங்க் அக்கவுண்ட்ல எவ்வளவு பேலன்ஸ் இருக்கு?", "check_balance", {"account": "bank"}),
    ("t6", "ta", "தண்ணி பில் 180 ரூபாய் கட்டிடு", "pay_bill", {"biller": "water", "amount": 180}),
    ("t7", "ta", "அம்மா நம்பர் 9445566778-க்கு 199 ரீசார்ஜ் பண்ணு", "recharge", {"amount": 199, "mobile": "9445566778"}),
    ("b1", "bn", "আমার নম্বরে ২৯৯ টাকার রিচার্জ করে দাও", "recharge", {"amount": 299}),
    ("b2", "bn", "ইলেকট্রিক বিল দিয়ে দাও", "pay_bill", {"biller": "electricity"}),
    ("b3", "bn", "৯৮৩০০১২৩৪৫ নম্বরে পাঁচশো টাকা পাঠাও", "transfer_upi", {"payee": "9830012345", "amount": 500}),
    ("b4", "bn", "ইন্ডেনের দুটো সিলিন্ডার বুক করো", "book_cylinder", {"company": "indane", "quantity": 2}),
    ("b5", "bn", "ক্রেডিট কার্ডে কত ব্যালান্স আছে?", "check_balance", {"account": "credit_card"}),
    ("b6", "bn", "ব্রডব্যান্ডের বিল ৬৯৯ টাকা দিয়ে দাও", "pay_bill", {"biller": "broadband", "amount": 699}),
    ("b7", "bn", "dipak@paytm-এ দেড় হাজার টাকা পাঠাও", "transfer_upi", {"payee": "dipak@paytm", "amount": 1500}),
    # harder set: fractional Indian amounts (paune/sava/saadhe/dhai), regional terms, brand -> category, 1,250 grouping
    ("h9", "hi", "पौने दो हज़ार रुपये 9812345670 पर ट्रांसफर करो", "transfer_upi", {"payee": "9812345670", "amount": 1750}),
    ("h10", "hi", "साढ़े तीन सौ वाला रिचार्ज मेरे भाई के 9090909090 पर कर दो", "recharge", {"amount": 350, "mobile": "9090909090"}),
    ("h11", "hi", "भारत गैस के तीन सिलेंडर चाहिए", "book_cylinder", {"company": "bharatgas", "quantity": 3}),
    ("h12", "hi", "पोस्टपेड बिल चुका दो", "pay_bill", {"biller": "mobile_postpaid"}),
    ("h13", "hi", "नल का बिल 1,250 रुपये भर दो", "pay_bill", {"biller": "water", "amount": 1250}),
    ("x9", "hinglish", "paune teen sau ka recharge karo", "recharge", {"amount": 275}),
    ("x10", "hinglish", "saadhe chaar hazaar bhej do priya.s@oksbi pe", "transfer_upi", {"payee": "priya.s@oksbi", "amount": 4500}),
    ("x11", "hinglish", "mobile ka postpaid bill bharna hai", "pay_bill", {"biller": "mobile_postpaid"}),
    ("x12", "hinglish", "Indane wala cylinder book karo, ek hi chahiye", "book_cylinder", {"company": "indane"}),
    ("x13", "hinglish", "Tata Play ka 350 ka bill bhar do", "pay_bill", {"biller": "dth", "amount": 350}),
    ("t8", "ta", "ஆயிரத்து ஐநூறு ரூபாய் 9840012345-க்கு அனுப்பு", "transfer_upi", {"payee": "9840012345", "amount": 1500}),
    ("t9", "ta", "இண்டேன் சிலிண்டர் ரெண்டு புக் பண்ணு", "book_cylinder", {"company": "indane", "quantity": 2}),
    ("t10", "ta", "வாலட்ல எவ்வளவு காசு இருக்கு?", "check_balance", {"account": "wallet"}),
    ("t11", "ta", "ஈபி பில் கட்டணும், 2,340 ரூபாய்", "pay_bill", {"biller": "electricity", "amount": 2340}),
    ("t12", "ta", "ஏர்டெல் போஸ்ட்பெய்ட் பில் கட்டு", "pay_bill", {"biller": "mobile_postpaid"}),
    ("b8", "bn", "সাড়ে তিনশো টাকার রিচার্জ করো", "recharge", {"amount": 350}),
    ("b9", "bn", "মায়ের নম্বর ৯৮৭৪৫৬৩২১০-এ ১৯৯ টাকার রিচার্জ করে দাও", "recharge", {"amount": 199, "mobile": "9874563210"}),
    ("b10", "bn", "জলের বিল মিটিয়ে দাও", "pay_bill", {"biller": "water"}),
    ("b11", "bn", "আড়াই হাজার টাকা rina@ybl-এ পাঠাও", "transfer_upi", {"payee": "rina@ybl", "amount": 2500}),
    ("b12", "bn", "এইচপি গ্যাসের একটা সিলিন্ডার বুক করো", "book_cylinder", {"company": "hp_gas"}),
]
HARD = {"h9", "h10", "h11", "h12", "h13", "x9", "x10", "x11", "x12", "x13", "t8", "t9", "t10", "t11", "t12",
        "b8", "b9", "b10", "b11", "b12"}
assert len(CASES) == 50 and len(HARD) == 20
OPENAI_TOOLS = [{"type": "function", "function": t} for t in TOOLS]
JSON_FALLBACK = (SYSTEM + "\nTools (JSON schema):\n" + json.dumps(TOOLS, ensure_ascii=False) +
                 '\nReply with only a JSON object: {"tool": "<name>", "arguments": {...}}')


def _digits(s):
    return "".join(str(unicodedata.digit(c)) for c in s if c.isdigit())


def norm_args(tool, args):
    out = {}
    for k, v in (args or {}).items():
        if v is None or (tool, k) in DEFAULTS and v == DEFAULTS[(tool, k)]:
            continue
        if k in ("amount", "quantity"):
            try:
                v = int(float(_digits(str(v)) if isinstance(v, str) and not re.fullmatch(r"[\d.]+", v) else v))
            except Exception:
                pass
        elif k in ("payee", "mobile"):
            v = str(v).strip().lower()
            d = _digits(v)
            if "@" not in v and len(d) >= 10:
                v = d[-10:]
        elif isinstance(v, str):
            v = v.strip().lower()
        out[k] = v
    return out


def score(case, call):
    _, _, _, gtool, gargs = case
    if not call:
        return {"tool_ok": False, "exact": False}
    tool_ok = call["name"] == gtool
    return {"tool_ok": tool_ok, "exact": tool_ok and norm_args(gtool, call.get("args")) == norm_args(gtool, gargs)}


def _openai_call(msg):
    tc = (msg.get("tool_calls") or [])
    if tc:
        f = tc[0]["function"]
        a = f.get("arguments")
        try:
            a = json.loads(a) if isinstance(a, str) else a
        except Exception:
            a = {"_unparsed": a}
        return {"name": f["name"], "args": a, "n_calls": len(tc)}
    return None


def call_sarvam(utt, think):
    body = {"model": "sarvam-105b", "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": utt}],
            "tools": OPENAI_TOOLS, "tool_choice": "auto", "max_tokens": 4000 if think else 800,
            "temperature": 0.5 if think else 0,  # Sarvam docs recommend >= 0.5 in thinking mode
            "reasoning_effort": "medium" if think else None}
    t = time.time()
    d = sarvam_post("/v1/chat/completions", body)
    if "_error" in d:
        raise RuntimeError(d)
    m, u = d["choices"][0]["message"], d.get("usage") or {}
    return {"call": _openai_call(m), "text": m.get("content"), "ms": (time.time() - t) * 1000, "mode": "native",
            "in_tok": u.get("prompt_tokens"), "out_tok": u.get("completion_tokens"),
            "reasoning_tok": (u.get("completion_tokens_details") or {}).get("reasoning_tokens")}


def call_openai_compat(system, utt, think):
    """OpenAI direct ("openai:<model>") or OpenRouter ("or:<provider>/<model>"), both with native OpenAI `tools`."""
    from common.bench import ALWAYS_THINK
    prov, model = system.split(":", 1)
    url, key = (("https://api.openai.com/v1/chat/completions", "OPENAI_API_KEY") if prov == "openai"
                else ("https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY"))
    body = {"model": model, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": utt}],
            "tools": OPENAI_TOOLS, "tool_choice": "auto"}
    if prov == "openai":
        body.update({"max_completion_tokens": 4000, "reasoning_effort": "medium" if think else "none"})
    else:
        body.update({"max_tokens": 4000, "temperature": 0,
                     "reasoning": {"effort": "low"} if (not think and model in ALWAYS_THINK) else {"enabled": bool(think)}})
    mode = "native"
    if prov == "openai" and think:
        # OpenAI: "Function tools with reasoning_effort are not supported ... in /v1/chat/completions. Use /v1/responses"
        url, mode = "https://api.openai.com/v1/responses", "native (responses API)"
        body = {"model": model, "instructions": SYSTEM, "input": utt, "max_output_tokens": 4000,
                "reasoning": {"effort": "medium"}, "tool_choice": "auto",
                "tools": [{"type": "function", "name": t["name"], "description": t["description"],
                           "parameters": t["parameters"], "strict": False} for t in TOOLS]}
        # strict defaults to true on /v1/responses, which makes every property required: the model then sends
        # mobile="" and amount=0 for optional args (a measured 26% exact-match loss), so match chat-completions semantics
    t = time.time()

    def go():
        r = requests.post(url, headers={"Authorization": "Bearer " + os.environ[key]}, json=body, timeout=300)
        if r.status_code == 429 or r.status_code >= 500:
            raise RuntimeError(f"{r.status_code} {r.text[:200]}")
        return r.json()
    d = _retry(go)
    if d.get("error"):
        raise RuntimeError(d["error"])
    if mode != "native":
        fc = [o for o in d.get("output", []) if o.get("type") == "function_call"]
        u = d.get("usage") or {}
        call = {"name": fc[0]["name"], "args": json.loads(fc[0]["arguments"] or "{}"), "n_calls": len(fc)} if fc else None
        text = " ".join(c.get("text", "") for o in d.get("output", []) if o.get("type") == "message" for c in o.get("content", []))
        return {"call": call, "text": text or None, "ms": (time.time() - t) * 1000, "mode": mode,
                "in_tok": u.get("input_tokens"), "out_tok": u.get("output_tokens"),
                "reasoning_tok": (u.get("output_tokens_details") or {}).get("reasoning_tokens")}
    m, u = d["choices"][0]["message"], d.get("usage") or {}
    return {"call": _openai_call(m), "text": m.get("content"), "ms": (time.time() - t) * 1000, "mode": mode,
            "in_tok": u.get("prompt_tokens"), "out_tok": u.get("completion_tokens"),
            "reasoning_tok": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"), "cost_usd": u.get("cost")}


def call_gemini(utt, think, model=GEMINI_CHAT, temperature=0):
    from google import genai
    from google.genai import types
    c = genai.Client(http_options=types.HttpOptions(timeout=180_000))  # calls can otherwise hang forever
    decls = [types.FunctionDeclaration(name=t["name"], description=t["description"], parameters_json_schema=t["parameters"])
             for t in TOOLS]
    cfg = types.GenerateContentConfig(system_instruction=SYSTEM, temperature=temperature, max_output_tokens=4000 if think else 800,
                                      tools=[types.Tool(function_declarations=decls)],
                                      automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                                      thinking_config=types.ThinkingConfig(thinking_budget=-1 if think else 0))
    t = time.time()
    r = _retry(lambda: c.models.generate_content(model=model, contents=utt, config=cfg))
    fcs = r.function_calls or []
    call = {"name": fcs[0].name, "args": dict(fcs[0].args or {}), "n_calls": len(fcs)} if fcs else None
    u = r.usage_metadata
    text = None if fcs else (r.text or "")
    return {"call": call, "text": text, "ms": (time.time() - t) * 1000, "mode": "native",
            "in_tok": u.prompt_token_count, "out_tok": u.candidates_token_count, "reasoning_tok": u.thoughts_token_count}


def call_local(system, utt):
    url = f"http://127.0.0.1:{LOCAL_PORTS[system]}/v1/chat/completions"
    u2 = utt + (" /no_think" if system.startswith("qwen3") else "")
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": u2}]
    if system.startswith("sarvam"):  # no-think via empty <think></think> prefill, as in run.local_chat
        msgs.append({"role": "assistant", "content": "<think></think>"})
    t = time.time()
    r = _retry(lambda: requests.post(url, json={"messages": msgs, "tools": OPENAI_TOOLS, "max_tokens": 2000,
                                                "temperature": 0}, timeout=900))
    mode = "native"
    if r.status_code >= 400:  # template without tool support -> JSON prompting fallback
        mode = "json"
        msgs = [{"role": "system", "content": JSON_FALLBACK}, {"role": "user", "content": u2}]
        r = _retry(lambda: requests.post(url, json={"messages": msgs, "max_tokens": 2000, "temperature": 0}, timeout=900))
    d = r.json()
    m, u = d["choices"][0]["message"], d.get("usage") or {}
    call = _openai_call(m)
    text = re.sub(r"<think>.*?</think>", "", m.get("content") or "", flags=re.S).strip()
    if mode == "json":
        from common.bench import extract_json
        j = extract_json(text) or {}
        call = {"name": j.get("tool"), "args": j.get("arguments"), "n_calls": 1} if j.get("tool") else None
    return {"call": call, "text": text, "ms": (time.time() - t) * 1000, "mode": mode,
            "in_tok": u.get("prompt_tokens"), "out_tok": u.get("completion_tokens")}


def call_system(label, utt):
    from run import SYSTEMS
    system, think, temp = (SYSTEMS[label] + (0.0,))[:3]
    if system.startswith("sarvam-105b"):
        return call_sarvam(utt, think)
    if system.startswith("gemini"):
        return call_gemini(utt, think, system, temp)
    if system.startswith(("openai:", "or:")):
        return call_openai_compat(system, utt, think)
    return call_local(label, utt)


def run(labels):
    have = {(r["id"], r["system"]) for r in raw_load(UC) if r.get("kind") == "tool"}
    lock = threading.Lock()

    def work(job):
        case, label = job
        try:
            r = call_system(label, case[2])
        except Exception as e:
            log(UC, "TOOL ERROR", label, case[0], str(e)[:300]); return
        rec = {"kind": "tool", "id": case[0], "lang": case[1], "hard": case[0] in HARD, "system": label, "utterance": case[2],
               "gold": {"name": case[3], "args": case[4]}, **r, **score(case, r["call"])}
        with lock:
            raw_append(UC, rec)
        log(UC, "tool", label, case[0], "exact" if rec["exact"] else f"MISS {r['call']} {str(r.get('text'))[:80]}")

    for label in labels:
        jobs = [(c, label) for c in CASES if (c[0], label) not in have]
        n = 3 if label.startswith("sarvam-105b") else 2 if label in ("sarvam-30b-local", "qwen3-30b-local") else 4
        with ThreadPoolExecutor(n) as ex:
            list(ex.map(work, jobs))


if __name__ == "__main__":
    for c in CASES:  # gold must score as exact against itself
        assert score(c, {"name": c[3], "args": c[4]})["exact"], c
    assert score(CASES[23], {"name": "recharge", "args": {"amount": "২৯৯"}})["exact"]
    assert not score(CASES[0], {"name": "recharge", "args": {"amount": 299, "mobile": "9999999999"}})["exact"]
    assert score(CASES[4], {"name": "book_cylinder", "args": {"company": "Indane", "quantity": 1}})["exact"]
    print("tool gold self-check OK")
