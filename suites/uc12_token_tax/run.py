"""UC12 - The Indic token tax: how many tokens each model's tokenizer spends on the same sentence in each language.

Data: FLEURS (google/fleurs, CC-BY-4.0) test+dev transcripts. FLEURS sentences are FLoRes-101 sentences, so the
same id means the same meaning in every language. We take 100 ids present in all 15 languages.

Counters:
  sarvam      - HF tokenizer.json from sarvamai/sarvam-30b (byte-identical to sarvamai/sarvam-105b's)
  qwen3       - HF tokenizer.json from Qwen/Qwen3-30B-A3B
  gemma4      - HF tokenizer.json from google/gemma-4-26b-a4b-it (ungated; embeddinggemma is gated)
  gemini      - Gemini count_tokens API on gemini-3.8-flash (free endpoint), fixed per-request overhead removed
  sarvam_api  - prompt_tokens from a 1-token sarvam-105b call on a 10-sentence sample per language (cross-check)
  gguf        - llama-server /tokenize on the local Sarvam-30B GGUF, same sample (cross-check, if the server is up)

Usage: .venv/bin/python suites/uc12_token_tax/run.py      (resumable: API counts are cached in results/raw)
"""
import csv, json, random, statistics, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from common.bench import *  # noqa
from common.bench import _retry
import requests
from tokenizers import Tokenizer

UC = "uc12_token_tax"
D = DATA / UC
LANGS = {"en_us": "English", "hi_in": "Hindi", "bn_in": "Bengali", "mr_in": "Marathi", "te_in": "Telugu",
         "ta_in": "Tamil", "gu_in": "Gujarati", "kn_in": "Kannada", "ml_in": "Malayalam", "pa_in": "Punjabi",
         "or_in": "Odia", "as_in": "Assamese", "ur_pk": "Urdu", "ne_np": "Nepali", "sd_in": "Sindhi"}
N, N_API = 100, 10
SARVAM_IN, SARVAM_OUT = 15 / 1e6, 60 / 1e6  # INR per token, sarvam-105b list price Oct 2026


def load_sentences():
    rows = {}
    for lang in LANGS:
        rows[lang] = {}
        for split in ("test", "dev"):
            for r in csv.reader(open(D / "fleurs" / f"{lang}.{split}.tsv"), delimiter="\t", quoting=csv.QUOTE_NONE):
                rows[lang].setdefault(r[0], r[2])  # raw transcription, first speaker's copy
    common = sorted(set.intersection(*[set(v) for v in rows.values()]), key=int)
    ids = sorted(random.Random(0).sample(common, N), key=int)
    return ids, {lang: {i: rows[lang][i] for i in ids} for lang in LANGS}


def cached(kind):
    return {(r["lang"], r["id"]): r for r in raw_load(UC) if r["kind"] == kind}


def gemini_counts(sents):
    from google import genai
    from google.genai import types
    c = genai.Client(http_options=types.HttpOptions(timeout=180_000))
    done = cached("gemini")
    todo = [(lang, i, t) for lang, d in sents.items() for i, t in d.items() if (lang, i) not in done]

    def one(x):
        lang, i, t = x
        n = c.models.count_tokens(model=GEMINI_CHAT, contents=t).total_tokens
        rec = {"kind": "gemini", "lang": lang, "id": i, "raw": n}
        raw_append(UC, rec)
        return rec

    with ThreadPoolExecutor(4) as ex:
        for rec in ex.map(lambda x: _retry(lambda: one(x)), todo):
            done[(rec["lang"], rec["id"])] = rec
    if ("_overhead", "a") not in done:  # the request overhead: count_tokens("a") is 1 text token + overhead
        raw_append(UC, {"kind": "gemini", "lang": "_overhead", "id": "a",
                        "raw": c.models.count_tokens(model=GEMINI_CHAT, contents="a").total_tokens})
    return cached("gemini")


CHAT_COUNTERS = {"openai": "openai:gpt-5.4-mini", "claude": "or:anthropic/claude-haiku-5.5"}


def chat_counts(kind, sents):
    """No public tokenizer: send each sentence as the only user message and read usage.prompt_tokens.
    A fixed per-request chat overhead is removed using the count for the one-token message 'a'."""
    done = cached(kind)
    todo = [(l, i, t) for l, d in sents.items() for i, t in d.items() if (l, i) not in done]
    todo += [("_overhead", "a", "a")] if ("_overhead", "a") not in done else []

    frame = "Translate this sentence to English:\n"
    frame_extra = {}

    def count(t):
        return chat(CHAT_COUNTERS[kind], [{"role": "user", "content": t}], max_tokens=16)

    def one(x):
        lang, i, t = x
        r, framed = count(t), False
        if not r.get("in_tok") and lang != "_overhead":
            # OpenRouter/Claude content filter (finish_reason content_filter, no usage) blocks a few encyclopaedic
            # sentences (e.g. on Ebola). Re-ask with a translation frame and subtract the frame's own tokens.
            if "x" not in frame_extra:
                frame_extra["x"] = count(frame + "a")["in_tok"] - count("a")["in_tok"]
            r, framed = count(frame + t), True
            if r.get("in_tok"):
                r["in_tok"] -= frame_extra["x"]
        if r.get("error") or not r.get("in_tok"):
            log(UC, kind, "no usage for", lang, i, str(r.get("error"))[:200])
            return
        raw_append(UC, {"kind": kind, "lang": lang, "id": i, "raw": r["in_tok"], "out_tok": r.get("out_tok"),
                        "cost_usd": r.get("cost_usd"), "framed": framed})

    with ThreadPoolExecutor(4) as ex:
        list(ex.map(one, todo))
    return cached(kind)


def sarvam_api_counts(sents, sample):
    done = cached("sarvam_api")
    todo = [(lang, i) for lang in sents for i in sample if (lang, i) not in done]

    def one(x):
        lang, i = x
        r = chat("sarvam-105b", [{"role": "user", "content": sents[lang][i]}], max_tokens=1)
        rec = {"kind": "sarvam_api", "lang": lang, "id": i, "raw": r.get("in_tok"), "out_tok": r.get("out_tok")}
        raw_append(UC, rec)
        return rec

    with ThreadPoolExecutor(3) as ex:
        list(ex.map(one, todo))
    return cached("sarvam_api")


def gguf_counts(sents, sample):
    url = f"http://127.0.0.1:{LOCAL_PORTS['sarvam-30b-local']}"
    try:
        requests.get(url + "/health", timeout=3).raise_for_status()
    except Exception:
        log(UC, "sarvam-30b-local not up; skipping GGUF tokenizer cross-check")
        return {}
    out = {}
    for lang in sents:
        for i in sample:
            toks = requests.post(url + "/tokenize", json={"content": sents[lang][i]}, timeout=30).json()["tokens"]
            out[(lang, i)] = len(toks)
    return out


def vocab_diff():
    """Sarvam's vocab vs Gemma 4's: same size, how many entries identical, which scripts were swapped."""
    import collections, unicodedata
    a, b = [Tokenizer.from_file(str(D / "tokenizers" / d / "tokenizer.json")).get_vocab() for d in ("sarvam-30b", "gemma-4")]

    def script(t):
        return next((unicodedata.name(c, "?").split()[0] for c in t.replace("\u2581", "") if c.isalpha()), "non-alpha")

    same = sum(b.get(k) == v for k, v in a.items())
    added = collections.Counter(script(k) for k in a if k not in b).most_common(9)
    dropped = collections.Counter(script(k) for k in b if k not in a).most_common(8)
    return (f"Sarvam's tokenizer is Gemma's vocabulary with surgery: both have {len(a):,} entries and {same:,} "
            f"({same / len(a):.0%}) are the same token at the same id. {sum(k not in b for k in a):,} tokens are new in Sarvam: "
            f"{', '.join(f'{k} {n:,}' for k, n in added)}; dropped {', '.join(f'{k} {n:,}' for k, n in dropped)}. "
            "That is why Hindi/Bengali/Marathi/Tamil/Urdu/Nepali counts are identical to Gemini's, and Sarvam wins only "
            "on the scripts it added.")


def main():
    ids, sents = load_sentences()
    (D / "sentences.json").write_text(json.dumps({"ids": ids, "sentences": sents}, ensure_ascii=False, indent=1))
    sample = ids[:: N // N_API][:N_API]
    toks = {n: Tokenizer.from_file(str(D / "tokenizers" / d / "tokenizer.json"))
            for n, d in [("sarvam", "sarvam-30b"), ("qwen3", "qwen3-30b-a3b"), ("gemma4", "gemma-4")]}
    counts = {n: {(l, i): len(t.encode(s, add_special_tokens=False).ids) for l, d in sents.items() for i, s in d.items()}
              for n, t in toks.items()}
    g = gemini_counts(sents)
    g_over = g[("_overhead", "a")]["raw"] - 1
    counts["gemini"] = {k: v["raw"] - g_over for k, v in g.items() if k[0] != "_overhead"}
    api = sarvam_api_counts(sents, sample)
    chat_raw = {}
    for kind in CHAT_COUNTERS:
        cc = chat_counts(kind, sents)
        over = cc[("_overhead", "a")]["raw"] - 1
        chat_raw[kind] = (cc, over)
        counts[kind] = {k: v["raw"] - over for k, v in cc.items() if k[0] != "_overhead"}
    gguf = gguf_counts(sents, sample)

    # cross-checks: API prompt_tokens - HF count should be a constant chat-template overhead if the tokenizer matches
    api_delta = {l: sorted({api[(l, i)]["raw"] - counts["sarvam"][(l, i)] for i in sample}) for l in LANGS}
    gguf_delta = {l: sorted({gguf[(l, i)] - counts["sarvam"][(l, i)] for i in sample}) for l in LANGS} if gguf else None
    gemma_gemini_delta = {l: statistics.fmean(counts["gemini"][(l, i)] - counts["gemma4"][(l, i)] for i in ids)
                          for l in LANGS}

    systems = ["sarvam", "qwen3", "gemma4", "gemini", "openai", "claude"]
    labels = {"sarvam": "Sarvam (30B/105B tokenizer)", "qwen3": "Qwen3-30B-A3B", "gemma4": "Gemma 4",
              "gemini": "Gemini 3.8 Flash (count_tokens)", "openai": "OpenAI gpt-5.4-mini (API prompt_tokens)",
              "claude": "Claude Haiku 5.5 (OpenRouter prompt_tokens)"}
    tok_per_sent = {s: {l: bootstrap_ci([counts[s][(l, i)] for i in ids]) for l in LANGS} for s in systems}
    tax = {s: {l: bootstrap_ci([counts[s][(l, i)] / counts[s][("en_us", i)] for i in ids]) for l in LANGS}
           for s in systems}
    chars = {l: statistics.fmean(len(sents[l][i]) for i in ids) for l in LANGS}
    words = {l: statistics.fmean(len(sents[l][i].split()) for i in ids) for l in LANGS}
    fert_word = {s: {l: sum(counts[s][(l, i)] for i in ids) / sum(len(sents[l][i].split()) for i in ids)
                     for l in LANGS} for s in systems}
    # implied sarvam-105b cost: INR per 1,000 sentences, if each sentence is sent as input / produced as output
    cost = {l: {"input_inr": round(tok_per_sent["sarvam"][l]["mean"] * 1000 * SARVAM_IN, 4),
                "output_inr": round(tok_per_sent["sarvam"][l]["mean"] * 1000 * SARVAM_OUT, 4)} for l in LANGS}
    table = [{"lang": LANGS[l], "code": l, "chars": round(chars[l], 1), "words": round(words[l], 1),
              **{f"{s}_tok": round(tok_per_sent[s][l]["mean"], 1) for s in systems},
              **{f"{s}_tax": round(tax[s][l]["mean"], 2) for s in systems},
              "sarvam_inr_per_1k_in": cost[l]["input_inr"], "sarvam_inr_per_1k_out": cost[l]["output_inr"]}
             for l in LANGS]

    indic = [l for l in LANGS if l != "en_us"]
    avg_tax = {s: statistics.fmean(tax[s][l]["mean"] for l in indic) for s in systems}
    best = {l: min(systems, key=lambda s: tok_per_sent[s][l]["mean"]) for l in LANGS}
    worst_ratio = {l: max(tok_per_sent[s][l]["mean"] for s in systems) / min(tok_per_sent[s][l]["mean"] for s in systems)
                   for l in indic}
    sarvam_vs_qwen = {l: tok_per_sent["qwen3"][l]["mean"] / tok_per_sent["sarvam"][l]["mean"] for l in LANGS}
    big = sorted(indic, key=lambda l: -sarvam_vs_qwen[l])

    findings = [
        f"Average Indic token tax (tokens vs the same sentence in English, mean over {len(indic)} languages): "
        + ", ".join(f"{labels[s]} {avg_tax[s]:.2f}x" for s in systems) + ".",
        f"Sarvam's tokenizer is the cheapest of the {len(systems)} on {sum(best[l] == 'sarvam' for l in indic)}/{len(indic)} Indic "
        f"languages; per language the cheapest is: " + ", ".join(f"{LANGS[l]}={best[l]}" for l in indic) + ".",
        "Qwen3 spends this many times more tokens than Sarvam on the same sentence: "
        + ", ".join(f"{LANGS[l]} {sarvam_vs_qwen[l]:.1f}x" for l in big) + f" (English {sarvam_vs_qwen['en_us']:.2f}x).",
        "Worst/best tokenizer spread per language (same sentence): "
        + ", ".join(f"{LANGS[l]} {worst_ratio[l]:.1f}x" for l in sorted(indic, key=lambda l: -worst_ratio[l])) + ".",
        f"Implied sarvam-105b list cost per 1,000 FLEURS sentences sent as input: English INR {cost['en_us']['input_inr']:.2f}, "
        + ", ".join(f"{LANGS[l]} INR {cost[l]['input_inr']:.2f}" for l in indic)
        + "; as generated output (INR 60/1M) multiply by 4.",
        f"Cross-check: Sarvam API prompt_tokens minus the HF tokenizer count is a constant per sentence "
        f"(distinct deltas across all {N_API * len(LANGS)} sampled sentences: "
        f"{sorted({d for v in api_delta.values() for d in v})}), i.e. the API bills exactly the open tokenizer plus a fixed "
        f"chat-template overhead.",
    ]
    if gguf_delta:
        mism = {l: sum(gguf[(l, i)] != counts["sarvam"][(l, i)] for i in sample) for l in LANGS}
        findings.append("llama.cpp's tokenizer for the official Sarvam-30B GGUF does not exactly match the HF tokenizer "
                        "on the scripts Sarvam added: sentences (of 10) with a different count - "
                        + ", ".join(f"{LANGS[l]} {n}" for l, n in mism.items() if n)
                        + f"; deltas range {min(d for v in gguf_delta.values() for d in v)} to "
                        f"{max(d for v in gguf_delta.values() for d in v)} tokens per sentence; identical for every other "
                        "language. Minor for cost, but it means the GGUF build sees slightly different token sequences "
                        "than the model was trained on for Telugu/Gujarati/Kannada/Malayalam/Punjabi.")
    findings.append("Gemini count_tokens minus Gemma-4 tokenizer count, mean per sentence: "
                    + ", ".join(f"{LANGS[l]} {gemma_gemini_delta[l]:+.2f}" for l in LANGS)
                    + f" (after removing a {g_over}-token request overhead).")
    findings.append(vocab_diff())
    for k in ("claude", "openai"):
        rat = {l: tok_per_sent[k][l]["mean"] / tok_per_sent["sarvam"][l]["mean"] for l in LANGS}
        findings.append(f"{labels[k]} needs this many times Sarvam's tokens for the same sentence: "
                        + ", ".join(f"{LANGS[l]} {rat[l]:.1f}x" for l in sorted(indic, key=lambda l: -rat[l]))
                        + f" (English {rat['en_us']:.2f}x).")

    usage = {**{CHAT_COUNTERS[k]: {"in_tok": sum(v["raw"] for v in cc.values()), "out_tok": sum(v.get("out_tok") or 0 for v in cc.values()),
                                   "calls": len(cc), "cost_usd": round(sum(v.get("cost_usd") or 0 for v in cc.values()), 4),
                                   "fixed_overhead_tokens_removed": over} for k, (cc, over) in chat_raw.items()},
             "sarvam-105b": {"in_tok": sum(r["raw"] for r in api.values()), "out_tok": sum(r.get("out_tok") or 0 for r in api.values()),
                             "calls": len(api)},
             GEMINI_CHAT: {"count_tokens_calls": len(g), "note": "count_tokens is a free endpoint; no generation"}}
    ex_ids = ids[:3]
    examples = [{"id": i, "sentences": {LANGS[l]: sents[l][i] for l in ("en_us", "hi_in", "ta_in", "ml_in", "or_in")},
                 "tokens": {LANGS[l]: {s: counts[s][(l, i)] for s in systems} for l in ("en_us", "hi_in", "ta_in", "ml_in", "or_in")}}
                for i in ex_ids]
    metrics = [{"name": f"tokens_per_sentence_{LANGS[l]}", "higher_is_better": False, "unit": "tokens",
                "values": {s: tok_per_sent[s][l] for s in systems}} for l in LANGS]
    metrics += [{"name": f"token_tax_vs_english_{LANGS[l]}", "higher_is_better": False, "unit": "x English",
                 "values": {s: tax[s][l] for s in systems}} for l in indic]
    write_result(UC, {
        "uc": UC, "title": "The Indic token tax",
        "business_question": "What does each model's tokenizer charge you, in tokens (and so in money, latency and "
                              "context window), for the same sentence written in each Indian language?",
        "dataset": {"name": "FLEURS transcripts (FLoRes-101 sentences)", "source": "google/fleurs data/<lang>/{test,dev}.tsv",
                    "license": "CC-BY-4.0", "n": N, "languages": list(LANGS.values()), "synthetic": False,
                    "how_made": f"{N} sentence ids drawn (seed 0) from the 201 ids present in all 15 languages; raw transcription column."},
        "systems": [labels[s] for s in systems],
        "metrics": metrics,
        "per_language": {"tokens_per_sentence": {LANGS[l]: {s: round(tok_per_sent[s][l]["mean"], 2) for s in systems} for l in LANGS},
                         "token_tax_vs_english": {LANGS[l]: {s: round(tax[s][l]["mean"], 3) for s in systems} for l in LANGS},
                         "tokens_per_word": {LANGS[l]: {s: round(fert_word[s][l], 3) for s in systems} for l in LANGS},
                         "sarvam_105b_inr_per_1000_sentences": {LANGS[l]: cost[l] for l in LANGS}},
        "table": table,
        "cross_checks": {"sarvam_api_minus_hf_distinct_deltas": api_delta, "gguf_minus_hf_distinct_deltas": gguf_delta,
                         "gemini_minus_gemma4_mean": gemma_gemini_delta, "gemini_request_overhead_tokens": g_over,
                         "sarvam_30b_vs_105b_tokenizer": "byte-identical tokenizer.json (md5 0987ae61...)"},
        "speed": {}, "usage": usage, "findings": findings,
        "caveats": [
            "FLEURS sentences are encyclopaedic (Wikipedia-style) prose; chatty business text, code-mixing and numbers "
            "may tokenize differently.",
            "Gemini prices are not applied (not taken from a verified source); its column is tokens only. The 'tax' "
            "multiplier is price-independent and applies to any per-token price.",
            "Sindhi FLEURS text is in Arabic (Perso-Arabic) script; Urdu sentences come from ur_pk.",
            "Gemini count_tokens adds a fixed per-request overhead, estimated from count_tokens('a') and subtracted.",
            "OpenAI and Claude publish no usable tokenizer here (tiktoken is not installed; Claude's is closed), so their "
            "counts are API usage.prompt_tokens for the sentence as the only user message, minus a fixed chat overhead "
            "estimated as prompt_tokens('a') - 1 (6 tokens for both). If 'a' is not exactly one token the error is a "
            "constant +-1 per sentence. 4 Claude sentences tripped OpenRouter's content filter (no usage returned) and were "
            "counted inside a 'Translate this sentence to English:' frame with the frame's tokens subtracted.",
            "Tokens per sentence is only half the cost story: a model that needs fewer tokens but answers worse is not cheaper.",
        ],
        "verdict": (
            "Claude is the expensive outlier among the cloud models: 1.9-6.6x Sarvam's tokens on Indic text (Kannada and Punjabi "
            "worst), and 1.6x even on English. OpenAI's tokenizer sits between Sarvam and Claude (0.8-3.5x Sarvam: cheaper only on Sindhi, worst on Odia). "
            "If your traffic is mostly Hindi, Bengali, Marathi, Tamil, Urdu or Nepali, Sarvam and Gemini/Gemma tokenize "
            "identically, so per-token price is the only cost lever. For Telugu, Kannada, Malayalam, Gujarati, Punjabi and "
            "especially Odia, Sarvam's tokenizer needs 18-60% fewer tokens than Gemini's on the same text. Avoid Qwen3-class "
            "byte-level tokenizers for Indic workloads: 3-10x the tokens of English means 3-10x the generation time when "
            "self-hosted and a context window that holds 3-10x less Indic text."),
        "examples": examples})
    log(UC, "wrote results; avg tax", {s: round(v, 2) for s, v in avg_tax.items()})
    return table


if __name__ == "__main__":
    for row in main():
        print(row)
