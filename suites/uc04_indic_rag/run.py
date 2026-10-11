"""uc04_indic_rag: question answering over company documents written in Indian languages.

Pipeline: gemini-embedding-2 retrieval (top-5 over all 6 docs) -> generator answers from the retrieved chunks.
Also an "oracle" condition (gold chunk handed to the generator) to separate retrieval errors from generation errors.

Usage:
  .venv/bin/python suites/uc04_indic_rag/run.py                       # API systems
  .venv/bin/python suites/uc04_indic_rag/run.py --systems sarvam-30b-local qwen3-30b-local
  .venv/bin/python suites/uc04_indic_rag/run.py --score-only           # recompute results/uc04_indic_rag.json from raw
Resumable: (qid, condition, system) already in results/raw/uc04_indic_rag.jsonl are skipped.
"""
import argparse, hashlib, json, re, sys, threading, unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from common.bench import (DATA, GEMINI_CHAT, bootstrap_ci, chat, dominant_script, log, pctl, raw_append, raw_load,
                          wait_for_local, write_result)

UC = "uc04_indic_rag"
D = DATA / UC
EMB_MODEL, TOPK = "gemini-embedding-2", 5
API_SYSTEMS = ["sarvam-105b", "sarvam-105b-think", "sarvam-105b-conversations", GEMINI_CHAT,
               "openai:gpt-5.4-mini", "or:anthropic/claude-haiku-5.5"]  # price-matched tier, full set
FRONTIER = ["gemini-pro-latest-think", "openai:gpt-5.5-think", "or:anthropic/claude-sonnet-5.5-think"]  # 38-question subset
LOCAL_SYSTEMS = ["sarvam-30b-local", "qwen3-30b-local"]
SEM = {"sarvam": threading.Semaphore(3), "gemini": threading.Semaphore(4), "local": threading.Semaphore(1),
       "openai": threading.Semaphore(4), "openrouter": threading.Semaphore(4)}
LOCK = threading.Lock()
DEAD = set()  # API kinds that returned 402 (out of credit): stop calling them

SYSTEM_PROMPT = """You are the help-desk assistant for an Indian organisation. Answer the user's question using ONLY the document excerpts provided.
Rules:
- Reply in the same language and script the user wrote in. If the user writes an Indian language in Latin letters (e.g. Hinglish, Tanglish), reply the same way in Latin letters.
- Be brief: one or two sentences with the exact figure, date, name or code from the excerpts.
- If the excerpts do not contain the answer, say so in the user's language and add the tag [NOT_FOUND]. Never guess or use outside knowledge."""


# ---------- data ----------
def load():
    chunks, questions = [], []
    for p in sorted((D / "docs").glob("*.json")):
        doc = json.loads(p.read_text())
        for s in doc["sections"]:
            chunks.append({"chunk_id": f"{doc['doc_id']}#{s['sec_id']}", "doc_id": doc["doc_id"], "lang": doc["lang"],
                           "heading": s["heading"], "text": s["text"], "title": doc["title"]})
    langs = {c["doc_id"]: c["lang"] for c in chunks}
    for p in sorted((D / "questions").glob("*.jsonl")):
        for line in p.read_text().splitlines():
            q = json.loads(line)
            q["lang"] = langs[q["doc_id"]]
            q["gold_chunk"] = f"{q['doc_id']}#{q['sec_id']}" if q["answerable"] else None
            questions.append(q)
    return chunks, questions


def chunk_text(c):
    return f"{c['title']} — {c['heading']}\n{c['text']}"


# ---------- retrieval ----------
def embed(texts):
    """gemini-embedding-2 has no task_type; the task prefix goes in the text. Cached on disk by text hash."""
    from google import genai
    from google.genai import types
    cache_p = D / "embedding_cache.json"
    cache = json.loads(cache_p.read_text()) if cache_p.exists() else {}
    key = lambda t: hashlib.sha1(f"{EMB_MODEL}|{t}".encode()).hexdigest()
    todo = [t for t in dict.fromkeys(texts) if key(t) not in cache]
    if todo:
        c = genai.Client()
        for i in range(0, len(todo), 50):
            part = todo[i:i + 50]  # one Content per text, else the API merges them into ONE embedding
            r = c.models.embed_content(model=EMB_MODEL, contents=[types.Content(parts=[types.Part(text=t)]) for t in part])
            for t, e in zip(part, r.embeddings):
                cache[key(t)] = e.values
        cache_p.write_text(json.dumps(cache))
    v = np.array([cache[key(t)] for t in texts], dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True), len(todo), sum(len(t) for t in todo)


def retrieve(chunks, questions):
    C, n1, ch1 = embed([f"title: {c['heading']} | text: {chunk_text(c)}" for c in chunks])
    Q, n2, ch2 = embed([f"task: search result | query: {q['question']}" for q in questions])
    top = np.argsort(-(Q @ C.T), axis=1)[:, :TOPK]
    for q, row in zip(questions, top):
        q["retrieved"] = [chunks[i]["chunk_id"] for i in row]
    return {"calls_new": n1 + n2, "chars_new": ch1 + ch2}


# ---------- scoring ----------
def norm(s):
    s = unicodedata.normalize("NFC", s or "")
    s = "".join(str(unicodedata.digit(ch)) if ch.isdigit() and unicodedata.digit(ch, None) is not None else ch for ch in s)
    s = re.sub(r"(?<=\d),(?=\d)", "", s)
    return s.casefold()


def numbers(s):
    return {float(x) for x in re.findall(r"\d+(?:\.\d+)?", norm(s))}


def has_gold(reply, gold):
    r = norm(reply)
    for g in gold:
        if re.fullmatch(r"\d+(?:\.\d+)?", norm(g)):
            if float(norm(g)) in numbers(r):
                return True
        elif norm(g) in r:
            return True
    return False


def strip_tag(t):
    return t.replace("[NOT_FOUND]", "").strip()


def hallucinated_numbers(reply, context, question):
    """Numbers in the reply that appear in neither the context nor the question.
    1-12 and 2026 are ignored: they are usually months/years re-rendered from a date written in words."""
    extra = numbers(strip_tag(reply)) - numbers(context) - numbers(question)
    return sorted(x for x in extra if not (1 <= x <= 12 or x == 2026))


def score(q, rec, by_id):
    t = rec.get("text") or ""
    refused = "NOT_FOUND" in t.upper()
    body = strip_tag(t)
    # a bare "[NOT_FOUND]" has no language; it is left out of the language metric (None) rather than failed
    lang = dominant_script(body) if body else None
    s = {"refused": refused, "lang_match": None if lang is None else lang == dominant_script(q["question"]),
         "halluc_nums": hallucinated_numbers(t, build_context(rec["chunks"], by_id), q["question"])}
    if q["answerable"]:
        s["gold_present"] = has_gold(body, q["gold"])  # lenient: ignores a wrongly added [NOT_FOUND] tag
        s["correct"] = (not refused) and s["gold_present"]
    return s


# ---------- running ----------
def sys_call(system):
    base = system.replace("-think", "")
    think = system.endswith("-think")
    kind = ("sarvam" if base.startswith("sarvam-105b") else "gemini" if base.startswith("gemini") else
            "openai" if base.startswith("openai:") else "openrouter" if base.startswith("or:") else "local")
    return base, think, kind


def build_context(chunk_ids, by_id):
    return "\n\n".join(f"[Excerpt {i + 1}] {chunk_text(by_id[c])}" for i, c in enumerate(chunk_ids))


def run_one(q, cond, system, by_id):
    ids = q["retrieved"] if cond == "rag" else [q["gold_chunk"]]
    context = build_context(ids, by_id)
    base, think, kind = sys_call(system)
    if kind in DEAD:
        return {"id": q["qid"], "system": system, "skipped": True}
    msgs = [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Document excerpts:\n{context}\n\nUser question: {q['question']}"}]
    with SEM[kind]:
        try:
            r = chat(base, msgs, max_tokens=6000 if think else 1000 if kind == "local" else 800, think=think)
        except Exception as e:
            r = {"text": "", "error": repr(e)[:300]}
    rec = {"id": q["qid"], "cond": cond, "system": system, "chunks": ids, **r}  # context rebuilt from chunk ids
    if system == "sarvam-30b-local":
        rec["nothink_prefill"] = True
    if "402" in str(r.get("error")):
        DEAD.add(kind)
        log(UC, f"credit error on {system}, no more {kind} calls:", r["error"])
    with LOCK:
        raw_append(UC, rec)
    return rec


def local_subset(q, cond):
    """Local models run the RAG condition only (all 132 questions); the oracle condition was skipped for time."""
    return cond == "rag"


FRONTIER_QIDS = set()  # filled in main(): 30 evenly spaced over sorted qids + 8 unanswerable (38)


def frontier_subset(q, cond):
    return cond == "rag" and q["qid"] in FRONTIER_QIDS


def stale(r):
    """sarvam-30b-local records made before bench.chat learned to switch its reasoning off (all tokens went to
    reasoning) are not comparable; they lack the nothink_prefill flag and are ignored."""
    return r["system"] == "sarvam-30b-local" and not r.get("nothink_prefill")


def run(systems, questions, by_id):
    done = {(r["id"], r["cond"], r["system"]) for r in raw_load(UC) if not r.get("error") and not stale(r)}
    tasks = [(q, cond, s) for s in systems for cond in ("rag", "oracle") for q in questions
             if not (cond == "oracle" and not q["answerable"]) and (q["qid"], cond, s) not in done
             and (s not in LOCAL_SYSTEMS or local_subset(q, cond)) and (s not in FRONTIER or frontier_subset(q, cond))]
    log(UC, f"{len(tasks)} calls to make for {systems}")
    with ThreadPoolExecutor(10) as ex:
        for i, rec in enumerate(ex.map(lambda t: run_one(*t, by_id), tasks)):
            if i % 50 == 0 and not rec.get("skipped"):
                log(UC, i, rec["system"], rec["id"], rec["cond"], (rec.get("text") or rec.get("error", ""))[:80])


# ---------- results ----------
def summarise(questions, emb_usage, by_id):
    qby = {q["qid"]: q for q in questions}
    recs = {}
    for r in raw_load(UC):
        if not r.get("error") and r["id"] in qby and not stale(r):
            recs[(r["id"], r["cond"], r["system"])] = r  # last one wins
    systems = [s for s in API_SYSTEMS + FRONTIER + LOCAL_SYSTEMS if any(k[2] == s for k in recs)]
    ans = [q for q in questions if q["answerable"]]
    forms = ["native", "english", "romanised"]

    # retrieval
    rec5 = {f: bootstrap_ci([float(q["gold_chunk"] in q["retrieved"]) for q in ans if q["form"] == f]) for f in forms}
    rec5["all"] = bootstrap_ci([float(q["gold_chunk"] in q["retrieved"]) for q in ans])
    rec1 = {f: bootstrap_ci([float(q["gold_chunk"] == q["retrieved"][0]) for q in ans if q["form"] == f]) for f in forms}
    rec1["all"] = bootstrap_ci([float(q["gold_chunk"] == q["retrieved"][0]) for q in ans])

    S = {}
    for (qid, cond, s), r in recs.items():
        S[(qid, cond, s)] = score(qby[qid], r, by_id)

    def vals(cond, pred, field, sysname):
        return [(None if S[(q["qid"], cond, sysname)][field] is None else float(S[(q["qid"], cond, sysname)][field]))
                if not callable(field) else field(S[(q["qid"], cond, sysname)])
                for q in questions if pred(q) and (q["qid"], cond, sysname) in S]

    metric_defs = [
        ("answer_correct_rag", True, "rag", lambda q: q["answerable"], "correct"),
        ("answer_correct_oracle", True, "oracle", lambda q: q["answerable"], "correct"),
        ("gold_present_ignoring_tag_rag", True, "rag", lambda q: q["answerable"], "gold_present"),
        ("reply_in_user_language_rag", True, "rag", lambda q: True, "lang_match"),
        ("unanswerable_refused_rag", True, "rag", lambda q: not q["answerable"], "refused"),
        ("false_refusal_rag", False, "rag", lambda q: q["answerable"], "refused"),
        ("hallucinated_number_rate_rag", False, "rag", lambda q: True, lambda s: float(bool(s["halluc_nums"]))),
        ("hallucinated_number_rate_unanswerable", False, "rag", lambda q: not q["answerable"],
         lambda s: float(bool(s["halluc_nums"]))),
    ]
    metrics = [{"name": "retrieval_recall_at5", "higher_is_better": True, "unit": "fraction",
                "values": {EMB_MODEL: rec5["all"]}, "by_form": rec5},
               {"name": "retrieval_recall_at1", "higher_is_better": True, "unit": "fraction",
                "values": {EMB_MODEL: rec1["all"]}, "by_form": rec1}]
    for name, hib, cond, pred, field in metric_defs:
        m = {"name": name, "higher_is_better": hib, "unit": "fraction",
             "values": {s: bootstrap_ci(vals(cond, pred, field, s)) for s in systems}}
        if cond == "rag":  # same 60 questions the local models ran, for apples-to-apples comparison
            m["values_local_subset"] = {s: bootstrap_ci(vals(cond, lambda q: pred(q) and local_subset(q, cond), field, s))
                                        for s in systems}
            m["values_frontier_subset"] = {s: bootstrap_ci(vals(cond, lambda q: pred(q) and frontier_subset(q, cond), field, s))
                                           for s in systems}
        if name in ("answer_correct_rag", "answer_correct_oracle", "reply_in_user_language_rag"):
            m["by_form"] = {f: {s: bootstrap_ci(vals(cond, lambda q, f=f: pred(q) and q["form"] == f, field, s))["mean"]
                                for s in systems} for f in forms}
        metrics.append(m)

    langs = sorted({q["lang"] for q in questions})
    per_language = {
        "answer_correct_rag": {l: {s: bootstrap_ci(vals("rag", lambda q, l=l: q["answerable"] and q["lang"] == l, "correct", s))["mean"]
                                   for s in systems} for l in langs},
        "retrieval_recall_at5": {l: {EMB_MODEL: bootstrap_ci([float(q["gold_chunk"] in q["retrieved"]) for q in ans if q["lang"] == l])["mean"]}
                                 for l in langs},
        "reply_in_user_language_rag": {l: {s: bootstrap_ci(vals("rag", lambda q, l=l: q["lang"] == l, "lang_match", s))["mean"]
                                           for s in systems} for l in langs},
    }
    speed, usage = {}, {}
    for s in systems:
        rs = [r for k, r in recs.items() if k[2] == s]
        ms = [r["ms"] for r in rs if r["cond"] == "rag"]
        speed[s] = {"p50_ms": pctl(ms, .5), "p95_ms": pctl(ms, .95)}
        usage[s] = {"in_tok": sum(r.get("in_tok") or 0 for r in rs), "out_tok": sum(r.get("out_tok") or 0 for r in rs),
                    "reasoning_tok": sum(r.get("reasoning_tok") or 0 for r in rs), "calls": len(rs),
                    "cost_usd": round(sum(r.get("cost_usd") or 0 for r in rs), 4) or None}
    usage[EMB_MODEL] = emb_usage
    return systems, metrics, per_language, speed, usage, recs, S


def examples(questions, systems, recs, S, qids):
    out = []
    for qid in qids:
        q = next(q for q in questions if q["qid"] == qid)
        ex = {"qid": qid, "lang": q["lang"], "form": q["form"], "question": q["question"], "gold": q["gold"],
              "answerable": q["answerable"], "gold_chunk": q["gold_chunk"], "retrieved": q["retrieved"], "outputs": {}}
        for s in systems:
            r = recs.get((qid, "rag", s))
            if r:
                ex["outputs"][s] = {"text": r["text"], **{k: v for k, v in S[(qid, "rag", s)].items()}}
        out.append(ex)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", nargs="*", default=API_SYSTEMS)
    ap.add_argument("--score-only", action="store_true")
    a = ap.parse_args()
    chunks, questions = load()
    qids = sorted(q["qid"] for q in questions)
    FRONTIER_QIDS.update(qids[i * len(qids) // 30] for i in range(30))  # happens to be all answerable, so add
    unans = sorted(q["qid"] for q in questions if not q["answerable"])   # 8 evenly spaced unanswerable ones
    FRONTIER_QIDS.update(unans[i * len(unans) // 8] for i in range(8))
    by_id = {c["chunk_id"]: c for c in chunks}
    emb_usage = retrieve(chunks, questions)
    log(UC, f"{len(chunks)} chunks, {len(questions)} questions, embeddings new: {emb_usage}")
    if not a.score_only:
        api = [s for s in a.systems if s not in LOCAL_SYSTEMS]
        if api:
            run(api, questions, by_id)
        for s in [s for s in a.systems if s in LOCAL_SYSTEMS]:  # one local model at a time
            if wait_for_local(s):
                run([s], questions, by_id)
            else:
                log(UC, f"{s} not up, skipping")
    emb_usage = {"chars": sum(len(chunk_text(c)) for c in chunks) + sum(len(q["question"]) for q in questions),
                 "texts": len(chunks) + len(questions)}
    systems, metrics, per_language, speed, usage, recs, S = summarise(questions, emb_usage, by_id)
    summary_path = ROOT / "suites" / UC / "summary.json"
    extra = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    write_result(UC, {
        "uc": UC, "title": "Q&A over company documents in Indian languages (RAG)",
        "business_question": "Employees and customers ask questions (in their own language, in English, or in romanised "
                             "WhatsApp-style text) over company documents written in Indian languages. Which model "
                             "answers correctly, in the user's language, and says 'not in the documents' instead of guessing?",
        "dataset": {"name": "uc04 synthetic Indian-language policy documents", "source": "authored for this benchmark",
                    "license": "CC-BY-4.0 (this repo)", "n": len(questions),
                    "n_answerable": sum(q["answerable"] for q in questions),
                    "n_unanswerable": sum(not q["answerable"] for q in questions), "n_chunks": len(chunks),
                    "frontier_subset_qids": sorted(FRONTIER_QIDS),
                    "local_subset": "rag condition, all 132 questions (no oracle condition)",
                    "languages": sorted({q["lang"] for q in questions}), "synthetic": True,
                    "how_made": "6 fictional policy documents (HR/Hindi, health insurance/Tamil, bank charges/Malayalam, "
                                "telecom/Bengali, ration PDS/Marathi, hospital billing/Kannada) written by an LLM author "
                                "(Claude) with invented numbers, split into 150-250 word sections (= chunks). 36 "
                                "answerable facts x 3 question forms (native script, English, romanised code-mix) + 12 "
                                "unanswerable facts x 2 forms. Every gold answer was machine-checked to occur in exactly "
                                "its gold chunk and in no other chunk of that document."},
        "systems": [EMB_MODEL] + systems,
        "metrics": metrics, "per_language": per_language, "speed": speed, "usage": usage,
        "findings": extra.get("findings", []), "caveats": extra.get("caveats", []), "verdict": extra.get("verdict", ""),
        "examples": examples(questions, systems, recs, S, extra.get("example_qids", [q["qid"] for q in questions[:4]])),
    })
    for m in metrics:
        log(UC, m["name"], {s: (round(v["mean"], 3) if v["mean"] is not None else None, v["n"]) for s, v in m["values"].items()})


if __name__ == "__main__":
    main()
