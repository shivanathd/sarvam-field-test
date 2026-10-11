"""UC08: code-mixed shopping orders and search (WhatsApp / quick-commerce).

Task A  order extraction: message -> JSON {items[{name,brand,qty,unit}], pincode, payment, slot}
Task B  transliteration: romanised name -> native script (hi, ta, bn, mr)

Resumable: raw calls live in results/raw/uc08_quick_commerce.jsonl keyed by `key`.
Usage:  run.py [api|local|score]   (default: api then score).  Build data first: build_data.py
"""
import json, sys, unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from common.bench import *  # noqa
from common.bench import _retry
import requests

UC = "uc08_quick_commerce"
D = DATA / UC
OD = json.loads((D / "orders.json").read_text())
TD = json.loads((D / "translit.json").read_text())
ORDERS, ITEMS = OD["orders"], TD["items"]
LANG = {"hi": ("Hindi", "Devanagari"), "ta": ("Tamil", "Tamil"), "bn": ("Bengali", "Bengali"),
        "mr": ("Marathi", "Devanagari")}
# (label, chat system, think)
A_SYSTEMS = [("sarvam-105b", "sarvam-105b", False), ("sarvam-105b-think", "sarvam-105b", True),
             (GEMINI_CHAT, GEMINI_CHAT, False)]
A_CHEAP = [("openai:gpt-5.4-mini", "openai:gpt-5.4-mini", False),
           ("or:anthropic/claude-haiku-5.5", "or:anthropic/claude-haiku-5.5", False)]  # price-matched, full set
FRONTIER = ["gemini-pro-latest", "openai:gpt-5.5", "or:anthropic/claude-sonnet-5.5"]  # ceiling, think on, subset
A_FRONTIER = [(f, f, True) for f in FRONTIER]
A_LOCAL = [("sarvam-30b-local", "sarvam-30b-local", False), ("qwen3-30b-local", "qwen3-30b-local", False)]
B_SYSTEMS = ["sarvam-transliterate", "sarvam-105b", GEMINI_CHAT]
B_LOCAL = ["sarvam-30b-local", "qwen3-30b-local"]
B_CHEAP = ["openai:gpt-5.4-mini", "or:anthropic/claude-haiku-5.5"]
LOCAL_ITEMS = ITEMS[::2]  # same reason: 50 of the 100 names (12-13 per language)
FRONTIER_ORDERS = [o for o in ORDERS if (o["id"] - 1) % 10 in (0, 3, 6)]  # ids 1,4,7,11,... = 30, all groups
FRONTIER_ITEMS = [it for i, it in enumerate(ITEMS) if i % 10 in (0, 3, 6)]  # 30 names, 7-8 per language
CAP_RETRY = "sarvam-105b-think-16k"  # rerun of think replies that hit the 6000-token cap with nothing out
LOCAL_ORDERS = ORDERS[::2]  # local models share a saturated llama-server (~2 min per order): every other message
SARVAM_SYSTEMS = {"sarvam-105b", "sarvam-105b-think", "sarvam-transliterate"}

PROMPT = f"""You are the order-taking assistant of an Indian quick-commerce grocery app. Current time: {OD['clock']}.
Convert the customer's WhatsApp message (any Indian language, script or spelling) into JSON, and output ONLY the JSON:
{{"items": [{{"name": str, "brand": str|null, "qty": number|null, "unit": str|null}}],
  "pincode": "6-digit string"|null, "payment": "COD"|"UPI"|"card"|null, "slot": str|null}}
Rules:
- name: the closest entry from this catalog, copied exactly: {", ".join(OD['catalog'])}.
- brand: only a brand/company name the customer mentions (e.g. Amul, Tata); varieties such as ponni,
  sona masoori or alphonso are not brands. null if none or if the customer says any brand is fine.
- qty/unit: unit is one of {", ".join(OD['units'])}. If the customer gives a count of packs/bottles/pieces,
  use that count; if only a weight or volume, use it (e.g. "aadha kilo" -> 0.5 kg). "darjan" = dozen.
  Include only what the customer wants now (respect corrections like "nahi" and "don't want").
- payment: cash / COD -> "COD"; GPay, PhonePe, Paytm, any UPI app -> "UPI"; card -> "card".
- slot: "today_" or "tomorrow_" + one of morning (6-12), afternoon (12-16), evening (16-20), night (20-23);
  "asap" if they want it immediately; null if not stated.
- Convert native-script digits (e.g. ৭০০০৬৪, ४११०३८) to ASCII digits in the pincode."""


def chat_any(system, messages, max_tokens, think=False):
    """bench.chat, except sarvam-30b-local: its GGUF ignores enable_thinking/<|nothink|> and spends the whole
    budget in reasoning_content, so we template via /apply-template, prefill an empty <think></think> and
    call /completion (thinking off, like every other system here)."""
    if system != "sarvam-30b-local" or think:
        return chat(system, messages, max_tokens=max_tokens, think=think)
    url, t = f"http://127.0.0.1:{LOCAL_PORTS[system]}", time.time()
    prompt = requests.post(url + "/apply-template", json={"messages": messages, "chat_template_kwargs": {
        "enable_thinking": False}}, timeout=120).json()["prompt"] + "<think></think>"
    d = _retry(lambda: requests.post(url + "/completion", json={"prompt": prompt, "n_predict": max_tokens,
                                                                "temperature": 0}, timeout=900).json())
    return {"text": d["content"].strip(), "ms": (time.time() - t) * 1000, "in_tok": d.get("tokens_evaluated"),
            "out_tok": d.get("tokens_predicted")}


def a_job(o, label, system, think, max_tokens=None):
    r = chat_any(system, [{"role": "system", "content": PROMPT}, {"role": "user", "content": o["message"]}],
                 max_tokens=max_tokens or (6000 if think else 1500), think=think)
    return {"key": f"A|{o['id']}|{label}", "task": "A", "id": o["id"], "system": label, "text": r["text"],
            "ms": r["ms"], "in_tok": r.get("in_tok"), "out_tok": r.get("out_tok"),
            "reasoning_tok": r.get("reasoning_tok"), "cost_usd": r.get("cost_usd"), "error": r.get("error")}


def b_job(it, system, think=False):
    name, script = LANG[it["lang"]]
    rec = {"key": f"B|{it['id']}|{system}", "task": "B", "id": it["id"], "system": system}
    if system == "sarvam-transliterate":
        t = time.time()
        d = sarvam_post("/transliterate", {"input": it["input"], "source_language_code": "en-IN",
                                           "target_language_code": f"{it['lang']}-IN"})
        rec.update(text=d.get("transliterated_text", ""), ms=(time.time() - t) * 1000, chars=len(it["input"]),
                   error=d.get("_body"))
    else:
        r = chat_any(system, [{"role": "user", "content": f"Transliterate this romanised name into {name} "
                                                      f"({script} script), spelled the way a native {name} "
                                                      f"speaker would write it. Output only the transliteration."
                                                      f"\n\n{it['input']}"}], max_tokens=4000 if think else 200,
                     think=think)
        rec.update(text=r["text"], ms=r["ms"], in_tok=r.get("in_tok"), out_tok=r.get("out_tok"), error=r.get("error"),
                   reasoning_tok=r.get("reasoning_tok"), cost_usd=r.get("cost_usd"))
    return rec


def ok(r):
    """A finished record: no API error (an empty reply is a legitimate failure and is scored, not retried)."""
    return not r.get("error")


NO_CREDIT = []  # set once Sarvam answers insufficient_quota_error; remaining Sarvam jobs are skipped


def run(jobs, workers):
    done = {r["key"] for r in raw_load(UC) if ok(r)}
    todo = [j for j in jobs if j[0] not in done]
    if not todo:
        return
    log(UC, f"running {len(todo)} jobs ({todo[0][0]} ...)")

    def go(j):
        if NO_CREDIT and j[0].split("|")[-1] in SARVAM_SYSTEMS:
            return
        try:
            rec = j[1](*j[2])
            if "insufficient_quota" in str(rec.get("error")):
                NO_CREDIT.append(1)
                log(UC, "Sarvam: no credits; skipping remaining Sarvam jobs")
            raw_append(UC, rec)
        except Exception as e:  # retried on the next run
            log(UC, "FAIL", j[0], repr(e)[:300])
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(go, todo))


def workers_for(system):
    return 1 if system in LOCAL_PORTS else (4 if system.startswith(("gemini", "openai:", "or:")) else 3)


def jobs(a_systems, b_systems):
    for label, system, think in a_systems:
        orders = LOCAL_ORDERS if system in LOCAL_PORTS else FRONTIER_ORDERS if label in FRONTIER else ORDERS
        run([(f"A|{o['id']}|{label}", a_job, (o, label, system, think)) for o in orders], workers_for(system))
    for s in b_systems:
        items = LOCAL_ITEMS if s in LOCAL_PORTS else FRONTIER_ITEMS if s in FRONTIER else ITEMS
        run([(f"B|{it['id']}|{s}", b_job, (it, s, s in FRONTIER)) for it in items], workers_for(s))


def cap_retry():
    """Rerun 105b-think replies that came back empty at the 6000-token cap, with max_tokens 16000."""
    capped = [r["id"] for r in raw_load(UC) if r["key"].endswith("|sarvam-105b-think") and not r["text"].strip()
              and (r.get("out_tok") or 0) >= 5999]
    run([(f"A|{o['id']}|{CAP_RETRY}", a_job, (o, CAP_RETRY, "sarvam-105b", True, 16000)) for o in ORDERS
         if o["id"] in capped], 3)


# ---------------- scoring ----------------
def alnum(s):
    return "".join(c for c in (s or "").lower() if c.isalnum())


def brand_ok(gold, pred):
    if not gold:
        return not alnum(pred)
    p = alnum(pred)
    return bool(p) and any(g in p or p in g for g in map(alnum, gold.split("|")))


def qty_key(q, u):
    try:
        q = float(q)
    except (TypeError, ValueError):
        return None
    u = (u or "").lower().strip().rstrip("s")
    if u in ("kg", "kilo", "kilogram"):
        return ("w", q)
    if u in ("g", "gm", "gram"):
        return ("w", q / 1000)
    if u in ("l", "litre", "liter", "ltr"):
        return ("v", q)
    if u == "ml":
        return ("v", q / 1000)
    if u == "dozen":
        return ("c", q * 12)
    return ("c", q)  # packet, piece, bottle, bunch, box, can, loaf ...


def qty_ok(g, p):
    if g["qty"] is None:
        return p.get("qty") in (None, "", 0)
    pk = qty_key(p.get("qty"), p.get("unit"))
    if pk is None:
        return False
    for a in [g] + g.get("alt", []):
        qk = qty_key(a["qty"], a["unit"])
        if qk[0] == pk[0] and abs(qk[1] - pk[1]) < 1e-6:
            return True
    return False


def score_order(gold, pred):
    """-> dict of per-message scores; pred is the parsed JSON or None."""
    if not isinstance(pred, dict) or not isinstance(pred.get("items"), list):
        n = len(gold["items"])
        return {"valid": 0, "name_tp": 0, "strict_tp": 0, "n_gold": n, "n_pred": 0, "pincode": 0, "payment": 0,
                "slot": 0, "exact": 0}
    items = [p for p in pred["items"] if isinstance(p, dict)]
    used, name_tp, strict_tp = set(), 0, 0
    for g in gold["items"]:
        cands = [i for i, p in enumerate(items) if i not in used and (p.get("name") or "").strip().lower() == g["name"]]
        best = next((i for i in cands if qty_ok(g, items[i]) and brand_ok(g["brand"], items[i].get("brand"))), None)
        if best is not None:
            strict_tp += 1
        pick = best if best is not None else (cands[0] if cands else None)
        if pick is not None:
            used.add(pick)
            name_tp += 1
    pin = "".join(c for c in str(pred.get("pincode") or "") if c.isdigit()) or None
    pay = {"cod": "COD", "upi": "UPI", "card": "card"}.get(str(pred.get("payment") or "").strip().lower())
    slot = (str(pred.get("slot")).strip().lower() or None) if pred.get("slot") not in (None, "null") else None
    s = {"valid": 1, "name_tp": name_tp, "strict_tp": strict_tp, "n_gold": len(gold["items"]), "n_pred": len(items),
         "pincode": int(pin == gold["pincode"]), "payment": int(pay == gold["payment"]), "slot": int(slot == gold["slot"])}
    s["exact"] = int(strict_tp == s["n_gold"] == s["n_pred"] and s["pincode"] and s["payment"] and s["slot"])
    return s


def f1(rows, tp):
    """micro F1 over all items plus a per-message F1 list for bootstrap."""
    per = []
    for r in rows:
        p, g, t = r["n_pred"], r["n_gold"], r[tp]
        per.append(1.0 if p == g == 0 else (2 * t / (p + g) if p + g else 0.0))
    return per


def tnorm(s):
    s = unicodedata.normalize("NFC", (s or "").strip().splitlines()[0] if (s or "").strip() else "")
    return s.replace("‌", "").replace("‍", "").strip(" .\"'`")


def score():
    raw = [r for r in {r["key"]: r for r in raw_load(UC)}.values() if ok(r)]
    gold = {o["id"]: o for o in ORDERS}
    A = [r for r in raw if r["task"] == "A"]
    for r in A:
        r["s"] = score_order(gold[r["id"]]["gold"], extract_json(r["text"] or ""))
    retry = {r["id"]: r for r in A if r["system"] == CAP_RETRY}
    A = [r for r in A if r["system"] != CAP_RETRY]
    A += [{**retry.get(r["id"], r), "system": "sarvam-105b-think(16k cap)", "key": r["key"] + "16k"}
          for r in A if r["system"] == "sarvam-105b-think"]  # same messages; capped ones replaced by the 16k rerun
    labels = [l for l, _, _ in A_SYSTEMS[:2]] + ["sarvam-105b-think(16k cap)"] + [l for l, _, _ in A_SYSTEMS[2:]]
    a_sys = [l for l in labels + [l for l, _, _ in A_CHEAP + A_FRONTIER + A_LOCAL] if any(r["system"] == l for r in A)]
    metrics, per_lang, speed, usage = [], {}, {}, {}

    def m(name, fn, systems, rows, hib=True, unit="fraction"):
        metrics.append({"name": name, "higher_is_better": hib, "unit": unit,
                        "values": {s: bootstrap_ci(fn([r for r in rows if r["system"] == s])) for s in systems}})
    m("A: item F1 (name+qty/unit+brand all correct)", lambda rs: f1([r["s"] for r in rs], "strict_tp"), a_sys, A)
    m("A: item F1 (catalog name only)", lambda rs: f1([r["s"] for r in rs], "name_tp"), a_sys, A)
    m("A: exact whole-order accuracy", lambda rs: [r["s"]["exact"] for r in rs], a_sys, A)
    fsub = {o["id"] for o in FRONTIER_ORDERS}
    m("A: item F1 strict, frontier 30-message subset (all systems)",
      lambda rs: f1([r["s"] for r in rs if r["id"] in fsub], "strict_tp"), a_sys, A)
    m("A: exact whole-order accuracy, frontier 30-message subset (all systems)",
      lambda rs: [r["s"]["exact"] for r in rs if r["id"] in fsub], a_sys, A)
    m("A: empty reply rate", lambda rs: [int(not (r["text"] or "").strip()) for r in rs], a_sys, A, hib=False)
    sub = {o["id"] for o in LOCAL_ORDERS}
    m("A: item F1 strict, 50-message subset (all systems)", lambda rs: f1([r["s"] for r in rs if r["id"] in sub],
                                                                         "strict_tp"), a_sys, A)
    m("A: exact whole-order accuracy, 50-message subset (all systems)",
      lambda rs: [r["s"]["exact"] for r in rs if r["id"] in sub], a_sys, A)
    for k in ("pincode", "payment", "slot", "valid"):
        m(f"A: {k} accuracy" if k != "valid" else "A: JSON validity rate", lambda rs, k=k: [r["s"][k] for r in rs],
          a_sys, A)
    groups = sorted({o["lang"] for o in ORDERS})
    per_lang["A: item F1 strict by message language"] = {g: {s: round(statistics.fmean(v), 3) if (v := f1(
        [r["s"] for r in A if r["system"] == s and gold[r["id"]]["lang"] == g], "strict_tp")) else None
        for s in a_sys} for g in groups}
    per_lang["A: exact order by message language"] = {g: {s: round(statistics.fmean(v), 3) if (v := [
        r["s"]["exact"] for r in A if r["system"] == s and gold[r["id"]]["lang"] == g]) else None
        for s in a_sys} for g in groups}
    for s in a_sys:
        rs = [r for r in A if r["system"] == s]
        speed[f"A:{s}"] = {"p50_ms": pctl([r["ms"] for r in rs], .5), "p95_ms": pctl([r["ms"] for r in rs], .95)}
        usage[f"A:{s}"] = {"calls": len(rs), "in_tok": sum(r.get("in_tok") or 0 for r in rs),
                           "out_tok": sum(r.get("out_tok") or 0 for r in rs),
                           "reasoning_tok": sum(r.get("reasoning_tok") or 0 for r in rs),
                           "cost_usd": round(sum(r.get("cost_usd") or 0 for r in rs), 4),
                           "errors": sum(1 for r in rs if r.get("error"))}

    B = [r for r in raw if r["task"] == "B"]
    bg = {it["id"]: it for it in ITEMS}
    for r in B:
        h, gs = tnorm(r["text"]), [unicodedata.normalize("NFC", g) for g in bg[r["id"]]["gold"]]
        r["exact"] = int(h in gs)
        r["cer"] = min(edit_distance(list(g), list(h)) / len(g) for g in gs)
    b_sys = [s for s in B_SYSTEMS + B_CHEAP + FRONTIER + B_LOCAL if any(r["system"] == s for r in B)]
    m("B: transliteration exact match", lambda rs: [r["exact"] for r in rs], b_sys, B)
    m("B: transliteration CER", lambda rs: [r["cer"] for r in rs], b_sys, B, hib=False, unit="CER")
    bsub = {it["id"] for it in LOCAL_ITEMS}
    m("B: transliteration exact match, 50-name subset (all systems)",
      lambda rs: [r["exact"] for r in rs if r["id"] in bsub], b_sys, B)
    bf = {it["id"] for it in FRONTIER_ITEMS}
    m("B: transliteration exact match, frontier 30-name subset (all systems)",
      lambda rs: [r["exact"] for r in rs if r["id"] in bf], b_sys, B)
    for k, label in (("exact", "B: exact match by language"), ("cer", "B: CER by language")):
        per_lang[label] = {l: {s: round(statistics.fmean(v), 3) if (v := [
            r[k] for r in B if r["system"] == s and bg[r["id"]]["lang"] == l]) else None for s in b_sys} for l in LANG}
    for s in b_sys:
        rs = [r for r in B if r["system"] == s]
        speed[f"B:{s}"] = {"p50_ms": pctl([r["ms"] for r in rs], .5), "p95_ms": pctl([r["ms"] for r in rs], .95)}
        usage[f"B:{s}"] = {"calls": len(rs), "chars": sum(r.get("chars") or 0 for r in rs),
                           "in_tok": sum(r.get("in_tok") or 0 for r in rs),
                           "out_tok": sum(r.get("out_tok") or 0 for r in rs),
                           "cost_usd": round(sum(r.get("cost_usd") or 0 for r in rs), 4)}
    inr = usage.get("B:sarvam-transliterate", {}).get("chars", 0) / 1e4 * 20
    retry_rs = list(retry.values())
    usage["A:sarvam-105b-think-16k-rerun"] = {"calls": len(retry_rs), "ids": sorted(retry),
                                              "in_tok": sum(r.get("in_tok") or 0 for r in retry_rs),
                                              "out_tok": sum(r.get("out_tok") or 0 for r in retry_rs)}
    for k in ("A:sarvam-105b", "A:sarvam-105b-think", "A:sarvam-105b-think-16k-rerun", "B:sarvam-105b"):
        inr += usage.get(k, {}).get("in_tok", 0) / 1e6 * 15 + usage.get(k, {}).get("out_tok", 0) / 1e6 * 60

    examples = []
    for oid in (25, 49, 73, 93):
        ex = {"task": "A order extraction", "input": gold[oid]["message"], "gold": gold[oid]["gold"], "outputs": {}}
        for r in A:
            if r["id"] == oid:
                ex["outputs"][r["system"]] = {"text": r["text"][:600], "score": r["s"]}
        examples.append(ex)
    for iid in ("mr-87", "ta-28"):
        if iid in bg:
            examples.append({"task": "B transliteration", "input": bg[iid]["input"], "gold": bg[iid]["gold"],
                             "outputs": {r["system"]: {"text": r["text"], "exact": r["exact"], "cer": round(r["cer"], 3)}
                                         for r in B if r["id"] == iid}})

    write_result(UC, {
        "uc": UC, "title": "Code-mixed quick-commerce orders and product/place-name transliteration",
        "business_question": "Can a model turn code-mixed WhatsApp/quick-commerce order and search messages into a "
                             "correct structured order, and write Indian names in native script correctly?",
        "dataset": {"name": "uc08 hand-authored orders (100) + transliteration names (100)",
                    "source": "authored for this benchmark (suites/uc08_quick_commerce/build_data.py)",
                    "license": "CC-BY 4.0", "n": len(ORDERS) + len(ITEMS),
                    "languages": groups + list(LANG), "synthetic": True,
                    "how_made": "Orders: 100 messages written to mimic how Indians type on WhatsApp (romanised and "
                                "native-script Hindi/Tamil/Bengali/Marathi/Kannada, English, native digits, typos, "
                                "corrections, negation, brands, local units), 86 orders + 14 searches, gold JSON "
                                "against an 80-item catalog. Translit: 25 well-known place/person/brand names per "
                                "language with standard native spellings (accepted variants listed)."},
        "systems": a_sys + [s for s in b_sys if s not in a_sys],
        "metrics": metrics, "per_language": per_lang, "speed": speed, "usage": usage,
        "extra": {"sarvam_spend_inr_estimate": round(inr, 2)},
        "examples": examples, "findings": FINDINGS, "caveats": CAVEATS, "verdict": VERDICT})
    log(UC, "scored; Sarvam spend estimate INR", round(inr, 2))


FINDINGS, CAVEATS, VERDICT = [], [], ""
_notes = Path(__file__).with_name("notes.json")
if _notes.exists():
    FINDINGS, CAVEATS, VERDICT = (json.loads(_notes.read_text())[k] for k in ("findings", "caveats", "verdict"))

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "api"
    if mode == "api":
        jobs(A_SYSTEMS, B_SYSTEMS)
        cap_retry()
        jobs(A_CHEAP + A_FRONTIER, B_CHEAP + FRONTIER)
    if mode == "local":
        for b in B_LOCAL:  # short transliteration calls first, then the slow order extraction
            jobs([], [b])
        for a in A_LOCAL:
            jobs([a], [])
    score()
