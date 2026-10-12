"""Builds report/index.html from results/*.json (no API calls). Run: .venv/bin/python report/build_report.py"""
import glob, html, json, math, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R = {Path(f).stem: json.loads(Path(f).read_text()) for f in sorted(glob.glob(str(ROOT / "results" / "uc*.json")))}
NOTES = {p.parent.name: json.loads(p.read_text()) for p in ROOT.glob("suites/*/notes.json")}
for uc, d in R.items():  # some suites keep findings/verdict in notes.json
    n = NOTES.get(uc, {})
    for k in ("findings", "caveats", "verdict"):
        if not d.get(k) and n.get(k):
            d[k] = n[k]
E = html.escape

# ---------- naming ----------
def vendor(s):
    s = s.lower()
    if "->" in s:  # voice-input pipelines (A -> B): attributed to the speech front end A, the part being compared
        return vendor(s.split("->")[0])
    if "+" in s:  # mixed pipelines (e.g. Sarvam Vision + Gemini) belong to neither side
        parts = {vendor(x) for x in s.split("+")}
        return parts.pop() if len(parts) == 1 else "other"
    if re.search(r"sarvam|saaras|bulbul|mayura", s): return "sarvam"
    if "qwen" in s: return "open"
    if re.search(r"anthropic|claude|haiku|sonnet", s): return "anthropic"
    if re.search(r"openai|gpt|whisper", s): return "openai"
    if re.search(r"gemini|gemma|google", s): return "google"
    return "other"

def is_local(s):
    return bool(re.search(r"local|whisper-large|qwen3|sarvam-30b", s.lower()))

PRETTY = [
    (r"^audio:", ""), (r"^agent-", "stack: "),
    (r"or:anthropic/claude-haiku-5\.5", "Claude Haiku 5.5"), (r"or:anthropic/claude-sonnet-5\.5", "Claude Sonnet 5.5"),
    (r"(or:)?anthropic/", ""), (r"openai:", ""),
    (r"claude-haiku-5\.5", "Claude Haiku 5.5"), (r"claude-sonnet-5\.5", "Claude Sonnet 5.5"), (r"^gemini-pro(?=$| )", "Gemini Pro"),
    (r"gpt-5\.4-mini", "GPT-5.4 mini"), (r"gpt-5\.5", "GPT-5.5"), (r"gpt-4o-mini-tts", "GPT-4o mini TTS"),
    (r"gpt-4o-transcribe", "GPT-4o transcribe"), (r"whisper-1", "Whisper (OpenAI API)"),
    (r"whisper-large-v3-turbo", "Whisper large-v3-turbo (local)"),
    (r"gemini-3\.8-flash-audio\b", "Gemini 3.8 Flash transcript"), (r"gemini-3\.8-flash audio-direct", "Gemini 3.8 Flash, audio in"), (r"gemini-3\.8-flash-tts", "Gemini 3.8 Flash TTS"), (r"gemini-3\.8-flash", "Gemini 3.8 Flash"),
    (r"gemini-pro-latest", "Gemini Pro"), (r"gemini-embedding-2", "Gemini Embedding 2"),
    (r"sarvam-105b-conversations", "Sarvam-105B conversations"), (r"sarvam-105b", "Sarvam-105B"),
    (r"sarvam-30b-local", "Sarvam-30B (self-hosted)"), (r"sarvam-30b-cpu", "Sarvam-30B (self-hosted, CPU only)"), (r"qwen3-30b-local", "Qwen3-30B (self-hosted)"),
    (r"sarvam-translate:v1", "Sarvam-Translate"), (r"mayura:v1", "Mayura"), (r"saaras[:-]v3", "Saaras v3"), (r"saaras[:-]v4", "Saaras v4"),
    (r"bulbul:v3", "Bulbul v3"), (r"bulbul:v4-flash", "Bulbul v4-flash"), (r"sarvam-vision", "Sarvam Vision (legacy)"), (r"sarvam-docai-extract", "Sarvam Document AI Extract"), (r"gemini-direct-audio", "Gemini 3.8 Flash, audio in"), (r"all-sarvam", "all-Sarvam (Saaras v4 → Sarvam-105B)"), (r"sarvam-transliterate", "Sarvam Transliterate API"),
    (r"\s*->\s*", " → "), (r"-nothink\b", ""), (r"-think\b", " · thinking"), (r"^audio → Gemini 3\.8 Flash", "Gemini 3.8 Flash, audio in"), (r"^text → ", "typed text → "), (r"-codemix-kt\b", " codemix + keyterms"), (r"-codemix", " codemix mode"), (r"-keyterms\b", " + keyterms"), (r"-transcribe\b", " transcribe mode"),
]

def pretty(s):
    out = s
    for a, b in PRETTY:
        out = re.sub(a, b, out)
    return out

VENDOR_NAME = {"sarvam": "Sarvam", "google": "Google", "openai": "OpenAI", "anthropic": "Anthropic", "open": "Open weights (Qwen)", "other": "Other"}

# ---------- formatting ----------
def fmt(v, kind):
    if v is None or (isinstance(v, float) and math.isnan(v)): return "–"
    if kind == "pct": return f"{v * 100:.0f}%" if v * 100 >= 10 or v == 0 else f"{v * 100:.1f}%"
    if kind == "ms": return f"{v / 1000:.2f} s" if v >= 1000 else f"{v:.0f} ms"
    if kind == "num1": return f"{v:.1f}"
    if kind == "x": return f"{v:.2f}×"
    return f"{v:.2f}"

def metric(uc, name):
    for m in R[uc]["metrics"]:
        if m["name"] == name:
            return m
    raise KeyError(f"{uc}: {name}")

# ---------- charts ----------
def nice_top(v):
    """Smallest of 1, 1.2, 1.6, 2, 4, 6, 8 x 10^k at or above v, so the four axis ticks land on round numbers."""
    k = 10 ** math.floor(math.log10(v))
    return next(m * k for m in (1, 1.2, 1.6, 2, 4, 6, 8, 10) if m * k >= v - 1e-12)

def bar_chart(uc, name, kind="pct", title=None, note=None, include=None):
    m = metric(uc, name)
    hib = m.get("higher_is_better", True)
    rows = [(s, v) for s, v in m["values"].items() if isinstance(v, dict) and v.get("mean") is not None]
    if include: rows = [r for r in rows if include(r[0])]
    rows.sort(key=lambda r: r[1]["mean"], reverse=hib)
    maxn = max((v.get("n") or 0) for _, v in rows)
    sub = lambda v: bool(v.get("n")) and v["n"] < 0.8 * maxn
    vmax = max(max(v["mean"], v.get("hi") or v["mean"]) for _, v in rows)
    top = 1.0 if kind == "pct" and vmax <= 1 else nice_top(vmax * 1.08)
    label_w, bar_w, row_h = 250, 420, 30
    h = row_h * len(rows) + 34
    g = []
    for i in range(5):
        x = label_w + bar_w * i / 4
        g.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="6" y2="{h - 24}" class="grid"/>'
                 f'<text x="{x:.1f}" y="{h - 8}" class="tick" text-anchor="middle">{E(fmt(top * i / 4, kind))}</text>')
    for i, (s, v) in enumerate(rows):
        y = 8 + i * row_h
        w = max(2, bar_w * v["mean"] / top)
        vd, loc = vendor(s), is_local(s)
        tip = f'{pretty(s)}: {fmt(v["mean"], kind)}'
        if v.get("lo") is not None and v.get("hi") is not None and v["lo"] != v["hi"]:
            tip += f' (95% CI {fmt(v["lo"], kind)}–{fmt(v["hi"], kind)})'
        if v.get("n"): tip += f' · n={v["n"]}'
        g.append(f'<g class="row" data-tip="{E(tip)}">'
                 f'<rect x="0" y="{y - 4}" width="{label_w + bar_w + 70}" height="{row_h}" class="hit"/>'
                 f'<text x="{label_w - 10}" y="{y + 13}" class="lab" text-anchor="end">{E(pretty(s))}{f" · n={v[chr(110)]}" if sub(v) else ""}</text>'
                 f'<rect x="{label_w}" y="{y + 2}" width="{w:.1f}" height="{row_h - 12}" rx="3" class="bar v-{vd}{" local" if loc else ""}{" sub" if sub(v) else ""}"/>')
        if v.get("lo") is not None and v.get("hi") is not None and v["hi"] > v["lo"]:
            x1, x2, cy = label_w + bar_w * v["lo"] / top, label_w + bar_w * v["hi"] / top, y + 2 + (row_h - 12) / 2
            g.append(f'<line x1="{x1:.1f}" x2="{x2:.1f}" y1="{cy:.1f}" y2="{cy:.1f}" class="ci"/>'
                     f'<line x1="{x1:.1f}" x2="{x1:.1f}" y1="{cy - 4:.1f}" y2="{cy + 4:.1f}" class="ci"/>'
                     f'<line x1="{x2:.1f}" x2="{x2:.1f}" y1="{cy - 4:.1f}" y2="{cy + 4:.1f}" class="ci"/>')
        lx = label_w + max(w, bar_w * (v.get("hi") or 0) / top) + 6
        g.append(f'<text x="{lx:.1f}" y="{y + 13}" class="val">{E(fmt(v["mean"], kind))}</text></g>')
    svg = (f'<svg viewBox="0 0 {label_w + bar_w + 70} {h}" role="img" aria-label="{E(title or name)}">'
           + "".join(g) + "</svg>")
    table = "".join(f"<tr><td>{E(pretty(s))}</td><td>{E(fmt(v['mean'], kind))}</td>"
                    f"<td>{E(fmt(v.get('lo'), kind))}–{E(fmt(v.get('hi'), kind))}</td><td>{v.get('n', '')}</td></tr>"
                    for s, v in rows)
    return (f'<figure class="chart"><figcaption><b>{E(title or name)}</b>'
            f'<span class="dir">{"higher is better" if hib else "lower is better"}</span></figcaption>'
            f'<div class="scroll">{svg}</div>'
            + (f'<p class="note">{E(note)}</p>' if note else "")
            + f'<details class="tbl"><summary>Table view</summary><div class="scroll"><table><thead><tr><th>System</th><th>Score</th>'
              f'<th>95% CI</th><th>n</th></tr></thead><tbody>{table}</tbody></table></div></details></figure>')


def heat_table(data, kind, hib=True, title="", systems=None, langs=None):
    """data {lang:{system:value}} or {system:{lang:value}}; shading is per row (per language)."""
    if not data: return ""
    first = next(iter(data.values()))
    if isinstance(first, dict) and any(re.search(r"sarvam|gemini|gpt|claude|qwen|whisper|saaras|mayura", k) for k in data):
        data = {l: {s: data[s].get(l) for s in data} for l in {l for s in data for l in data[s]}}
    langs = langs or list(data)
    systems = systems or sorted({s for l in langs for s in data[l] if isinstance(data[l].get(s), (int, float))},
                                key=lambda s: (vendor(s) != "sarvam", s))
    head = "".join(f'<th><span class="sw v-{vendor(s)}"></span>{E(pretty(s))}</th>' for s in systems)
    body = []
    for l in langs:
        vals = [data[l].get(s) for s in systems]
        nums = [v for v in vals if isinstance(v, (int, float))]
        if not nums: continue
        lo, hi = min(nums), max(nums)
        cells = []
        for v in vals:
            if not isinstance(v, (int, float)):
                cells.append('<td class="na">–</td>'); continue
            t = 0.5 if hi == lo else (v - lo) / (hi - lo)
            t = t if hib else 1 - t
            cells.append(f'<td style="--t:{t * 70:.0f}%">{E(fmt(v, kind))}</td>')
        body.append(f"<tr><th>{E(l)}</th>{''.join(cells)}</tr>")
    return (f'<figure class="heat"><figcaption><b>{E(title)}</b><span class="dir">darker = better within each row'
            f' ({"higher" if hib else "lower"} is better)</span></figcaption><div class="scroll"><table>'
            f"<thead><tr><th></th>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div></figure>")


# ---------- scorecard (Sarvam's best vs best rival, CI overlap = level) ----------
def verdict_row(uc, name, kind, label, include=None):
    m = metric(uc, name)
    hib = m.get("higher_is_better", True)
    vals = [(s, v) for s, v in m["values"].items() if isinstance(v, dict) and v.get("mean") is not None]
    if include: vals = [x for x in vals if include(x[0])]
    maxn = max((x[1].get("n") or 0) for x in vals)
    vals = [x for x in vals if not x[1].get("n") or x[1]["n"] >= 0.8 * maxn]  # compare like-for-like sample sizes
    key = (lambda x: x[1]["mean"]) if hib else (lambda x: -x[1]["mean"])
    sv = max([x for x in vals if vendor(x[0]) == "sarvam"], key=key)
    rv = max([x for x in vals if vendor(x[0]) != "sarvam"], key=key)
    lo = lambda v: v.get("lo") if v.get("lo") is not None else v["mean"]
    hi = lambda v: v.get("hi") if v.get("hi") is not None else v["mean"]
    overlap = lo(sv[1]) <= hi(rv[1]) and lo(rv[1]) <= hi(sv[1])
    better = (sv[1]["mean"] > rv[1]["mean"]) == hib
    small = abs(sv[1]["mean"] - rv[1]["mean"]) / max(abs(rv[1]["mean"]), 1e-9) < 0.02  # under 2% apart: no practical difference
    state = "level" if (overlap or small) else ("lead" if better else "behind")
    return {"uc": uc, "label": label, "metric": name, "kind": kind, "state": state,
            "s": sv, "r": rv}


def _macro_excl_sindhi():
    """13-language macro WER (Sindhi excluded: Saaras writes it in Devanagari, the reference is Arabic script).
    CI: 2,000 bootstrap resamples over languages."""
    import random
    pl = R["uc02_helpline_stt"]["per_language"]["WER"]
    langs = [l for l in pl if l != "Sindhi"]
    rng, vals = random.Random(0), {}
    for s in pl[langs[0]]:
        xs = [pl[l][s] for l in langs if pl[l].get(s) is not None]
        if len(xs) < len(langs): continue
        boots = sorted(sum(rng.choice(xs) for _ in xs) / len(xs) for _ in range(2000))
        vals[s] = {"mean": sum(xs) / len(xs), "lo": boots[50], "hi": boots[1949], "n": len(xs)}
    R["uc02_helpline_stt"]["metrics"].append({"name": "WER, macro-average over 13 languages (Sindhi excluded)",
                                             "higher_is_better": False, "unit": "fraction", "values": vals})
_macro_excl_sindhi()

SC = []  # filled in body()

# ---------- page sections ----------
def section(uc, num, charts, extra=""):
    d = R[uc]
    ds = d.get("dataset", {})
    finds = "".join(f"<li>{E(f)}</li>" for f in d.get("findings", []))
    cav = "".join(f"<li>{E(c)}</li>" for c in d.get("caveats", []))
    data_line = (f'{E(str(ds.get("name", "")))} · n={E(str(ds.get("n", "")))} · '
                 f'{"synthetic, written for this benchmark" if ds.get("synthetic") else "public data"} · licence: {E(str(ds.get("license", "")))}')
    sc = next((x for x in SC if x["uc"] == uc), None)
    pill = (f'<span class="pill {sc["state"]}">{ {"lead": "Sarvam leads", "level": "Level", "behind": "Sarvam behind"}[sc["state"]] }</span>'
            if sc else "")
    return f"""
<section id="{uc}" class="uc">
  <header><p class="eyebrow">Use case {num}{pill}</p><h2>{E(d.get("title", uc))}</h2>
  <p class="q">{E(d.get("business_question", ""))}</p><p class="meta">{data_line}</p></header>
  <div class="verdict"><h3>Verdict</h3><p>{E(d.get("verdict", ""))}</p></div>
  <div class="charts">{"".join(charts)}</div>
  {extra}
  <div class="cols"><div><h3>Findings</h3><ul>{finds}</ul></div>
  <div><h3>Caveats</h3><ul class="cav">{cav}</ul></div></div>
  <p class="src">Code: <code>suites/{uc}/</code> · results: <code>results/{uc}.json</code> · every output: <code>results/raw/{uc}.jsonl</code></p>
</section>"""


def voice_agent_table():
    ap = R["uc01_voice_support"]["agent_pipeline"]
    rows = []
    for k, v in sorted(ap.items(), key=lambda kv: kv[1]["time_to_first_audio_ms"]["p50"]):
        c = v.get("components", {})
        rows.append(f"<tr><th>{E(' → '.join(c.get(x, '') for x in ('stt', 'llm', 'tts')) or k)}</th>"
                    f"<td>{fmt(v['time_to_first_audio_ms']['p50'], 'ms')}</td><td>{fmt(v['time_to_first_audio_ms']['p95'], 'ms')}</td>"
                    f"<td>{fmt(v['stt_ms']['p50'], 'ms')}</td><td>{fmt(v['llm_ms']['p50'], 'ms')}</td><td>{fmt(v['tts_first_byte_ms']['p50'], 'ms')}</td>"
                    f"<td>{fmt(v['reply_in_caller_language_script']['mean'], 'pct')}</td>"
                    f"<td>{fmt(v['caller_entities_echoed_correctly']['mean'], 'pct')}</td></tr>")
    return ('<figure class="heat plain"><figcaption><b>Voice agent: time until the caller hears a reply (20 turns per stack)</b>'
            '<span class="dir">p50 and p95; LLM replies not streamed</span></figcaption><div class="scroll"><table><thead><tr>'
            '<th>Stack (speech-to-text → model → voice)</th><th>First audio p50</th><th>p95</th><th>STT p50</th><th>Model p50</th>'
            '<th>Voice first byte</th><th>Reply in caller\'s script</th><th>Numbers read back right</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>"
            '<p class="note">All-Sarvam cost per conversation-minute at list prices: v3 stack ₹1.56 (speech ₹0.23, model ₹0.015, voice ₹1.32); v4 stack about ₹1.42 (v4 models priced as v3, since Sarvam lists no separate v4 prices).</p></figure>')


def selfhost_table():
    hw = R["uc10_selfhost_business"].get("hardware", {})
    rows = []
    for k, runs in hw.items():
        for r in runs if isinstance(runs, list) else [runs]:
            c1 = r.get("c1", {})
            c4 = r.get("c4", {})
            rows.append(f"<tr><th>{E(k)}</th><td>{c1.get('prompt_tok_per_s', 0):.0f}</td><td>{c1.get('gen_tok_per_s', 0):.1f}</td>"
                        f"<td>{fmt(c1.get('ttft_ms'), 'ms')}</td><td>{c4.get('aggregate_gen_tok_per_s', 0):.1f}</td>"
                        f"<td>{r.get('peak_rss_gb', '–')}</td><td>{E(str(r.get('measured_at', '')))}</td></tr>")
    return ('<figure class="heat plain"><figcaption><b>Self-hosting on an Apple M5 Max (128 GB): measured speed</b>'
            '<span class="dir">thinking off, same 1k-token prompt; the Mac was shared with other jobs, so these are floors</span></figcaption>'
            '<div class="scroll"><table><thead><tr><th>Server</th><th>Prompt tok/s</th><th>Gen tok/s</th><th>First token</th>'
            '<th>4 users, total tok/s</th><th>Peak memory GB</th><th>Measured</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div></figure>")


def token_tax_chart():
    d = R["uc12_token_tax"]
    tax = d["per_language"]["token_tax_vs_english"]
    langs = [l for l in tax if l != "English"]
    toks = ["sarvam", "gemini", "openai", "claude", "qwen3"]
    names = {"sarvam": "Sarvam", "gemini": "Gemini / Gemma 4", "openai": "OpenAI (GPT-5.4 mini)", "claude": "Claude Haiku 5.5", "qwen3": "Qwen3"}
    vend = {"sarvam": "sarvam", "gemini": "google", "openai": "openai", "claude": "anthropic", "qwen3": "open"}
    avg = {t: sum(tax[l][t] for l in langs if tax[l].get(t)) / len([l for l in langs if tax[l].get(t)]) for t in toks}
    rows = sorted(toks, key=lambda t: avg[t])
    label_w, bar_w, row_h, top = 200, 440, 34, 6.5
    h = row_h * len(rows) + 34
    g = [f'<line x1="{label_w + bar_w * i / top:.1f}" x2="{label_w + bar_w * i / top:.1f}" y1="6" y2="{h - 24}" class="grid"/>'
         f'<text x="{label_w + bar_w * i / top:.1f}" y="{h - 8}" class="tick" text-anchor="middle">{i}×</text>' for i in range(0, 7)]
    for i, t in enumerate(rows):
        y = 8 + i * row_h
        w = bar_w * avg[t] / top
        g.append(f'<g class="row" data-tip="{E(names[t])}: {avg[t]:.2f}× the tokens of the same English sentence (average of {len(langs)} languages)">'
                 f'<rect x="0" y="{y - 4}" width="{label_w + bar_w + 70}" height="{row_h}" class="hit"/>'
                 f'<text x="{label_w - 10}" y="{y + 15}" class="lab" text-anchor="end">{E(names[t])}</text>'
                 f'<rect x="{label_w}" y="{y + 3}" width="{w:.1f}" height="{row_h - 14}" rx="3" class="bar v-{vend[t]}"/>'
                 f'<text x="{label_w + w + 6:.1f}" y="{y + 15}" class="val">{avg[t]:.2f}×</text></g>')
    svg = f'<svg viewBox="0 0 {label_w + bar_w + 70} {h}" role="img" aria-label="Average token tax">{"".join(g)}</svg>'
    heat = heat_table({l: {names[t]: tax[l].get(t) for t in toks} for l in langs}, "x", hib=False,
                      title="Token tax by language (tokens for the sentence ÷ tokens for the same English sentence)",
                      systems=[names[t] for t in toks])
    heat = heat.replace('<span class="sw v-other"></span>', "")
    return (f'<figure class="chart"><figcaption><b>The Indic token tax: average across {len(langs)} Indian languages</b>'
            f'<span class="dir">lower is cheaper</span></figcaption><div class="scroll">{svg}</div>'
            '<p class="note">1.00× would mean an Indian-language sentence costs the same as its English translation. '
            'Gemini and Gemma 4 counts are identical; Sarvam\'s vocabulary is Gemma\'s with about 22,800 slots re-assigned to Indian scripts.</p></figure>' + heat)


FRONTIER = {"gemini-pro-latest", "openai:gpt-5.5", "or:anthropic/claude-sonnet-5.5"}
no_frontier = lambda s: s not in FRONTIER


def body():
    global SC
    SC = [
        verdict_row("uc01_voice_support", "Entity accuracy (digits/amounts/dates exactly captured) [phone]", "pct", "Hinglish support calls: numbers captured (v3 beat v4, which writes numbers as words: 56% with keyterms)"),
        verdict_row("uc02_helpline_stt", "WER, macro-average over 13 languages (Sindhi excluded)", "num2", "Helpline speech in 13 languages: word error rate"),
        verdict_row("uc03_documents", "field exact-match accuracy (frontier subset: 16 harsh + 14 phone photos)", "pct", "Documents from bad phone photos: fields right"),
        verdict_row("uc04_indic_rag", "answer_correct_rag", "pct", "Q&A over Indian-language policies: correct"),
        verdict_row("uc05_clinical_notes", "medication_exact_drug_dose_freq", "pct", "Clinical notes: drug + dose + frequency exact"),
        verdict_row("uc06_offline_agri", "overall_pass_subset30", "pct", "Crop advisory (incl. refusing out-of-scope)", include=no_frontier),
        verdict_row("uc07_translation_dubbing", "chrF++ English->Indic", "num1", "Translation into Indian languages (chrF++)"),
        verdict_row("uc07_translation_dubbing", "chrF++ Indic->English", "num1", "Translation into English (chrF++)"),
        verdict_row("uc07_translation_dubbing", "TTS time to first audio byte", "ms", "Dubbing: time to first audio"),
        verdict_row("uc08_quick_commerce", "A: exact whole-order accuracy", "pct", "WhatsApp orders: whole order exactly right", include=no_frontier),
        verdict_row("uc09_legal", "entity preservation rate (translation)", "pct", "Legal translation: facts kept"),
        verdict_row("uc09_legal", "key-fact recall (litigant summary)", "pct", "Legal summaries: key facts kept", include=no_frontier),
        verdict_row("uc10_selfhost_business", "overall_all_correct", "pct", "Business text tasks: fully correct"),
        verdict_row("uc11_bharat_code", "pass@1 (single shot)", "pct", "Coding Indian business logic: first try"),
        verdict_row("uc11_bharat_code", "tool calling: correct tool + exact args (all 50)", "pct", "Voice-assistant tool calls: exact"),
        verdict_row("uc06v_offline_agri_voice", "overall_pass", "pct", "Spoken farmer questions: answered right (speech front end)",
                    include=lambda s: s.endswith("[phone]")),
        verdict_row("uc08v_voice_orders", "Exact whole-order accuracy", "pct", "WhatsApp voice notes: order exactly right (speech front end)",
                    include=lambda s: s.startswith("phone:")),
        verdict_row("uc11v_voice_tools", "tool call exact (all 50), phone audio", "pct", "Spoken payment commands: exact (speech front end)"),
    ]
    sc_rows = "".join(
        f'<tr><th><a href="#{x["uc"]}">{E(x["label"])}</a></th>'
        f'<td><span class="sw v-sarvam"></span>{E(pretty(x["s"][0]))} <b>{fmt(x["s"][1]["mean"], x["kind"])}</b></td>'
        f'<td><span class="sw v-{vendor(x["r"][0])}"></span>{E(pretty(x["r"][0]))} <b>{fmt(x["r"][1]["mean"], x["kind"])}</b></td>'
        f'<td><span class="pill {x["state"]}">{ {"lead": "Sarvam leads", "level": "Level", "behind": "Sarvam behind"}[x["state"]] }</span></td></tr>'
        for x in SC)
    tally = {k: sum(x["state"] == k for x in SC) for k in ("lead", "level", "behind")}

    U = []
    U.append(section("uc01_voice_support", 1, [
        bar_chart("uc01_voice_support", "Entity accuracy (digits/amounts/dates exactly captured) [phone]", "pct",
                  "Phone-quality calls: amounts, account digits and dates captured exactly"),
        bar_chart("uc01_voice_support", "WER vs code-mix reference [phone]", "num2", "Phone-quality calls: word error rate vs code-mixed reference")],
        voice_agent_table()))
    U.append(section("uc02_helpline_stt", 2, [
        bar_chart("uc02_helpline_stt", "WER, macro-average over 13 languages (Sindhi excluded)", "num2", "Word error rate, average of 13 languages (Sindhi excluded; interval = bootstrap over languages)"),
        heat_table(R["uc02_helpline_stt"]["per_language"]["WER"], "num2", hib=False, title="Word error rate by language")]))
    U.append(section("uc03_documents", 3, [
        bar_chart("uc03_documents", "field exact-match accuracy (frontier subset: 16 harsh + 14 phone photos)", "pct",
                  "Hard photos (16 harsh + 14 phone): fields read exactly right"),
        bar_chart("uc03_documents", "field exact-match accuracy (clean)", "pct", "Clean scans: fields read exactly right"),
        heat_table(R["uc03_documents"]["per_language"]["field accuracy by script (harsh)"], "pct", title="Harsh photos: field accuracy by script")]))
    U.append(section("uc04_indic_rag", 4, [
        bar_chart("uc04_indic_rag", "answer_correct_rag", "pct", "Correct answers (retrieval + answer, 108 answerable questions)"),
        bar_chart("uc04_indic_rag", "reply_in_user_language_rag", "pct", "Replied in the language and script the question was asked in"),
        bar_chart("uc04_indic_rag", "unanswerable_refused_rag", "pct", "Unanswerable questions correctly refused")]))
    U.append(section("uc05_clinical_notes", 5, [
        bar_chart("uc05_clinical_notes", "medication_exact_drug_dose_freq", "pct", "Medications exactly right (drug + dose + frequency)"),
        bar_chart("uc05_clinical_notes", "fact_recall_overall", "pct", "Clinical facts captured"),
        bar_chart("uc05_clinical_notes", "note_fully_in_english", "pct", "Notes written fully in English")]))
    U.append(section("uc06_offline_agri", 6, [
        bar_chart("uc06_offline_agri", "overall_pass_subset30", "pct", "Fixed 30 questions (20 answerable + 10 out of scope): passed"),
        bar_chart("uc06_offline_agri", "oos_refusal", "pct", "Out-of-scope questions refused instead of invented"),
        bar_chart("uc06_offline_agri", "grounded_correct", "pct", "Answerable questions: correct numbers from the advisory sheet")]))
    U.append(section("uc07_translation_dubbing", 7, [
        bar_chart("uc07_translation_dubbing", "chrF++ English->Indic", "num1", "English → 10 Indian languages (chrF++)", include=no_frontier),
        bar_chart("uc07_translation_dubbing", "chrF++ Indic->English", "num1", "10 Indian languages → English (chrF++)", include=no_frontier),
        bar_chart("uc07_translation_dubbing", "chrF++ English->Indic, frontier subset: 30 sentence-language pairs (all systems)", "num1",
                  "Frontier check: English → Indian languages, 30 sentence-language pairs", note="Small subset; confidence intervals overlap."),
        bar_chart("uc07_translation_dubbing", "Dubbing intelligibility: round-trip CER, judge=openai:gpt-4o-transcribe", "pct",
                  "Dubbing intelligibility: character error rate when a neutral transcriber reads the audio back"),
        bar_chart("uc07_translation_dubbing", "TTS time to first audio byte", "ms", "Dubbing: time to first audio byte"),
        heat_table(R["uc07_translation_dubbing"]["per_language"]["chrF++ English->Indic"], "num1", title="English → Indian languages: chrF++ by language")]))
    U.append(section("uc08_quick_commerce", 8, [
        bar_chart("uc08_quick_commerce", "A: exact whole-order accuracy", "pct", "WhatsApp orders: whole order exactly right (100 messages)", include=no_frontier),
        bar_chart("uc08_quick_commerce", "A: exact whole-order accuracy, frontier 30-message subset (all systems)", "pct", "Frontier check: 30 fixed messages"),
        bar_chart("uc08_quick_commerce", "B: transliteration exact match", "pct", "Names written in native script exactly right (100 names)")]))
    U.append(section("uc09_legal", 9, [
        bar_chart("uc09_legal", "entity preservation rate (translation)", "pct", "Translation: sections, amounts, dates and names kept"),
        bar_chart("uc09_legal", "key-fact recall (litigant summary)", "pct", "Plain-language summaries for litigants: key facts kept", include=no_frontier),
        bar_chart("uc09_legal", "key-fact recall (litigant summary, frontier subset: first 15 passages x hi/ta)", "pct", "Frontier check: summaries, 30 fixed items")]))
    U.append(section("uc10_selfhost_business", 10, [
        bar_chart("uc10_selfhost_business", "overall_all_correct", "pct", "150 business-text tasks: every field correct"),
        heat_table(R["uc10_selfhost_business"]["per_language"]["overall_all_correct"], "pct", title="Fully correct by language")],
        selfhost_table()))
    U.append(section("uc11_bharat_code", 11, [
        bar_chart("uc11_bharat_code", "pass@1 (single shot)", "pct", "40 Indian business-logic tasks × 4 prompt languages: passed first try"),
        bar_chart("uc11_bharat_code", "pass@3 with repair loop", "pct", "Passed within 3 attempts, with failing tests fed back"),
        bar_chart("uc11_bharat_code", "tool calling: correct tool + exact args (all 50)", "pct", "Voice-assistant commands: right tool, exact arguments"),
        heat_table(R["uc11_bharat_code"]["per_language"]["pass@1"], "pct", title="Passed first try, by prompt language")]))
    U.append(section("uc12_token_tax", 12, [token_tax_chart()]))
    U.append(section("uc06v_offline_agri_voice", 13, [
        bar_chart("uc06v_offline_agri_voice", "overall_pass", "pct", "70 spoken questions: passed (same Gemini answering model unless named)",
                  note="Colour shows the speech front end. Clean and phone-line audio are separate bars."),
        bar_chart("uc06v_offline_agri_voice", "cer_saaras:v4", "pct", "Saaras v4 transcription error (CER)"),
        heat_table(R["uc06v_offline_agri_voice"]["per_language"]["cer"], "pct", hib=False, title="Transcription error (CER) by language")]))
    U.append(section("uc08v_voice_orders", 14, [
        bar_chart("uc08v_voice_orders", "Exact whole-order accuracy", "pct", "86 spoken orders: whole order exactly right",
                  note="Colour shows the speech front end; all transcripts go to the same Gemini 3.8 Flash extractor unless named."),
        bar_chart("uc08v_voice_orders", "pincode accuracy", "pct", "Pincode captured exactly")]))
    U.append(section("uc11v_voice_tools", 15, [
        bar_chart("uc11v_voice_tools", "tool call exact (all 50), phone audio", "pct", "50 spoken commands over a phone line: right tool, exact arguments",
                  note="Colour shows the speech front end; transcripts go to the same Gemini 3.8 Flash tool model unless named."),
        bar_chart("uc11v_voice_tools", "tool call exact: fractional spoken amounts (10), phone audio", "pct", "Spoken fractions (\"paune do hazaar\"): exact")]))
    return sc_rows, tally, "".join(U)


def scrub(t):
    t = t.replace(str(Path.home()), "~").replace(Path.home().name, "user")
    return re.sub(r"(sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{30,}|sk_[A-Za-z0-9]{30,})", "[REDACTED]", t)


def files_json():
    out = {}
    for p in [ROOT / "common" / "bench.py", ROOT / "report" / "build_report.py", ROOT / "scripts" / "serve_local.sh"] + sorted(
            q for q in (ROOT / "suites").rglob("*") if q.suffix in (".py", ".md", ".swift", ".sh") and "__pycache__" not in q.parts):
        if p.exists() and p.stat().st_size < 250_000:
            out[str(p.relative_to(ROOT))] = scrub(p.read_text(errors="replace"))
    for p in sorted((ROOT / "logs").glob("*.log")):
        lines = p.read_text(errors="replace").splitlines()
        out[f"logs/{p.name} (last {min(200, len(lines))} of {len(lines)} lines)"] = scrub("\n".join(lines[-200:]))
    return json.dumps(out, ensure_ascii=False).replace("</", "<\\/")


# ---------- cost & intelligence (list prices, October 2026) ----------
USD_INR = 96.61  # RBI reference rate, 9 Oct 2026
# INR per 1M tokens (input, output incl. thinking). Sources: Sarvam changelog 10 Oct 2026; OpenRouter list prices;
# Google Gemini API pricing page. gemini-pro-latest is priced as Gemini 3.1 Pro (the page does not say which it resolves to).
PRICE = {
    "sarvam-105b": (15, 60), "gemini-3.8-flash": (0.75 * USD_INR, 3.75 * USD_INR), "gpt-5.4-mini": (0.75 * USD_INR, 4.5 * USD_INR),
    "claude-haiku-5.5": (0.10 * USD_INR, 0.50 * USD_INR), "gemini-pro": (2 * USD_INR, 12 * USD_INR),
    "gpt-5.5": (5 * USD_INR, 30 * USD_INR), "claude-sonnet-5.5": (2 * USD_INR, 10 * USD_INR),
}
TEXT_TESTS = [  # (suite, metric) used for the intelligence index: all higher-is-better, full sets
    ("uc04_indic_rag", "answer_correct_rag"), ("uc05_clinical_notes", "medication_exact_drug_dose_freq"),
    ("uc06_offline_agri", "grounded_correct"), ("uc08_quick_commerce", "A: exact whole-order accuracy"),
    ("uc09_legal", "key-fact recall (litigant summary)"), ("uc10_selfhost_business", "overall_all_correct"),
    ("uc11_bharat_code", "pass@1 (single shot)")]


def canon(s):
    """Normalise system names across suites: 'A:or:anthropic/claude-haiku-5.5 [x]' -> 'claude-haiku-5.5'."""
    s = re.sub(r"^[AB]:", "", s)
    s = re.sub(r"\s*\[.*?\]$", "", s)
    s = re.sub(r"^(openai:|or:anthropic/|or:)", "", s).replace("-nothink", "")
    s = s.replace("gemini-pro-latest", "gemini-pro")
    if re.match(r"(gemini-pro|gpt-5\.5|claude-sonnet-5\.5)", s):
        s = re.sub(r"-think$", "", s)  # frontier models always ran with thinking
    return s


def price_key(c):
    base = re.sub(r"(-think.*|-t0.*|\(.*)$", "", c).strip()
    return base if base in PRICE else None


def cost_inr(c, u):
    k = price_key(c)
    if not k or not u: return None
    out = (u.get("out_tok") or 0) + ((u.get("reasoning_tok") or 0) if k.startswith("gemini") else 0)
    pin, pout = PRICE[k]
    return ((u.get("in_tok") or 0) * pin + out * pout) / 1e6


def intelligence():
    scores, costs = {}, {}
    for uc, name in TEXT_TESTS:
        m = metric(uc, name)
        maxn = max((v.get("n") or 0) for v in m["values"].values() if isinstance(v, dict))
        keep = {"uc08_quick_commerce": lambda k: k.startswith("A:"),  # order extraction, not transliteration
                "uc09_legal": lambda k: k.endswith("[litigant summary]")}.get(uc, lambda k: True)
        usage = {canon(k): v for k, v in (R[uc].get("usage") or {}).items() if isinstance(v, dict) and keep(k)}
        for s, v in m["values"].items():
            if not isinstance(v, dict) or v.get("mean") is None: continue
            c = canon(s)
            if c.endswith("(16k cap)") or "empties rerun" in c or c.endswith("-t0") or c.endswith("-t0.7"): continue
            scores.setdefault(c, {})[uc] = (v["mean"], v.get("n") or 0, maxn)
            u = usage.get(c)
            ci = cost_inr(c, u)
            if ci is not None and (v.get("n") or u.get("calls")):
                costs.setdefault(c, {})[uc] = ci / (v.get("n") or u.get("calls")) * 1000  # ₹ per 1,000 tasks
    return scores, costs



def scatter_svg(pts, xlabel, ymin):
    """Accuracy (y) against log cost (x). pts: dicts with c, idx, cost (None = self-hosted), local, sub, tip.
    Labels are placed greedily (right, left, above, below) to avoid dots and earlier labels."""
    W, H, L, T, B, R_ = 880, 440, 150, 24, 50, 170
    xs = [p["cost"] for p in pts if p["cost"]]
    linear = max(xs) / min(xs) < 3  # narrow cost range: a zoomed linear axis spreads the points out
    if linear:
        span = nice_top((max(xs) - min(xs)) * 1.6) / 4
        x0 = math.floor(min(xs) * 0.97 / span) * span; x1 = math.ceil(max(xs) * 1.03 / span) * span
        X = lambda v: L + (v - x0) / (x1 - x0) * (W - L - R_)
        xticks = [x0 + span * i for i in range(int(round((x1 - x0) / span)) + 1)]
        xlabel = xlabel.replace("log scale", "linear scale")
    else:
        lo, hi = math.floor(math.log10(min(xs))), math.ceil(math.log10(max(xs)))
        if hi == lo: hi += 1
        X = lambda v: L + (math.log10(v) - lo) / (hi - lo) * (W - L - R_)
        xticks = [10 ** e for e in range(lo, hi + 1)]
    Y = lambda v: T + (1 - (v - ymin) / (1 - ymin)) * (H - T - B)
    g = []
    step = 0.2 if ymin <= 0.4 else 0.1
    t_ = ymin
    while t_ <= 1.0001:
        g.append(f'<line x1="{L}" x2="{W - R_}" y1="{Y(t_):.1f}" y2="{Y(t_):.1f}" class="grid"/><text x="{L - 8}" y="{Y(t_) + 4:.1f}" class="tick" text-anchor="end">{t_:.0%}</text>')
        t_ += step
    for v in xticks:
        g.append(f'<line x1="{X(v):.1f}" x2="{X(v):.1f}" y1="{T}" y2="{H - B}" class="grid"/><text x="{X(v):.1f}" y="{H - B + 18}" class="tick" text-anchor="middle">₹{v:,.0f}</text>')
    if any(not p["cost"] for p in pts):
        g.append(f'<rect x="10" y="{T}" width="{L - 70}" height="{H - T - B}" class="strip"/><text x="{(L - 60) / 2 + 10:.0f}" y="{H - B + 18}" class="tick" text-anchor="middle">own hardware</text>')
    g.append(f'<text x="{(L + W - R_) / 2:.0f}" y="{H - 8}" class="tick" text-anchor="middle">{E(xlabel)}</text>')
    placed = []  # boxes (x0, y0, x1, y1) of dots and labels already drawn
    li = 0
    for p in pts:
        if p["cost"]: p["x"] = X(p["cost"])
        else: p["x"] = 30 + (li % 2) * 34; li += 1
        p["y"] = Y(p["idx"])
        placed.append((p["x"] - 8, p["y"] - 8, p["x"] + 8, p["y"] + 8))
    hit = lambda b: any(not (b[2] < q[0] or b[0] > q[2] or b[3] < q[1] or b[1] > q[3]) for q in placed)
    for p in sorted(pts, key=lambda p: -p["idx"]):
        lab = pretty(p["c"]); w = 7.2 * len(lab); x, y = p["x"], p["y"]
        cands = [(x + 11, y + 4, "start"), (x - 11, y + 4, "end"), (x - w / 2, y - 13, "start"), (x - w / 2, y + 21, "start"),
                 (x + 11, y - 14, "start"), (x + 11, y + 22, "start"), (x - 11, y - 14, "end"), (x - 11, y + 22, "end"),
                 (x + 11, y - 28, "start"), (x + 11, y + 36, "start"), (x - 11, y - 28, "end"), (x - 11, y + 36, "end")]
        def box(c):
            lx, ly, anc = c
            x0 = lx if anc == "start" else lx - w
            return (x0, ly - 11, x0 + w, ly + 3)
        left = (L + 2) if p["cost"] else 2  # priced points keep their labels inside the plot, clear of the y-axis ticks
        pick = next((c for c in cands if not hit(box(c)) and box(c)[2] < W - 4 and box(c)[0] > left and box(c)[1] > 2), cands[0])
        placed.append(box(pick))
        g.append(f'<g class="row" data-tip="{E(p["tip"])}"><circle cx="{x:.1f}" cy="{y:.1f}" r="12" class="hit"/>'
                 f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6.5" class="dot v-{vendor(p["c"])}{" local" if p["local"] else ""}{" sub" if p["sub"] else ""}"/>'
                 f'<text x="{pick[0]:.1f}" y="{pick[1]:.1f}" text-anchor="{pick[2]}" class="lab small">{E(pretty(p["c"]))}</text></g>')
    return "".join(g), W, H

def cost_section():
    scores, costs = intelligence()
    pts = []
    for c, sc in scores.items():
        if len(sc) < 5: continue  # needs most of the seven tests
        sub = any(n < 0.8 * mx for _, n, mx in sc.values())
        idx = sum(v for v, _, _ in sc.values()) / len(sc)
        cs = [costs.get(c, {}).get(uc) for uc in sc]
        cs = [x for x in cs if x is not None]
        local = "local" in c or "cpu" in c
        pts.append({"c": c, "idx": idx, "cost": (sum(cs) / len(cs)) if cs and not local else None, "local": local,
                    "sub": sub, "k": len(sc)})
    for p in pts:
        p["tip"] = (f'{pretty(p["c"])}: {p["idx"]:.0%} average across {p["k"]} text tests'
                    + (f', ₹{p["cost"]:,.1f} per 1,000 tasks' if p["cost"] else ", self-hosted") + (" (frontier: 30-item subsets)" if p["sub"] else ""))
    g, W, H = scatter_svg(pts, "API cost per 1,000 tasks (₹, log scale, measured tokens × list price)", 0.2)
    avg = {p["c"]: p for p in pts}
    def a(c): return avg[c]["idx"], avg[c]["cost"]
    hk, fl, sv = a("claude-haiku-5.5"), a("gemini-3.8-flash"), a("sarvam-105b")
    r = [a(c)[1] / fl[1] for c in ("gemini-pro", "gpt-5.5", "claude-sonnet-5.5") if c in avg and a(c)[1]]
    summary = (f'<p class="prose"><b>Best value:</b> Claude Haiku 5.5 averaged {hk[0]:.0%} at about ₹{hk[1]:,.0f} per 1,000 tasks. '
               f'Sarvam-105B cost about the same (₹{sv[1]:,.0f}) but averaged {sv[0]:.0%}. Gemini 3.8 Flash reached {fl[0]:.0%} for about '
               f'₹{fl[1]:,.0f}, {fl[1] / hk[1]:.1f}× Haiku\'s cost. Frontier models matched Flash on accuracy at '
               f'{min(r):.0f}–{max(r):.0f}× its cost.</p>')
    scatter = summary + (f'<figure class="chart"><figcaption><b>Intelligence against cost: average accuracy on seven text tests</b>'
               f'<span class="dir">up and to the left is better</span></figcaption><div class="scroll"><svg viewBox="0 0 {W} {H}" role="img" '
               f'aria-label="Accuracy against cost per 1,000 tasks">{g}</svg></div>'
               '<p class="note">Tests: policy Q&amp;A, clinical medications, crop advice, WhatsApp orders, legal summaries, business text, coding. '
               'Frontier models (faded) ran on 30-item subsets of some tests. Self-hosted models have no per-call price; their cost is the hardware.</p></figure>')

    # speech: word accuracy (1 - 13-language macro WER) against cost per audio hour
    u = R["uc02_helpline_stt"]["usage"]
    hrs = u["gemini-3.8-flash"]["audio_s"] / 3600
    per_hour = {  # ₹ per audio hour at list price
        "saaras:v3-transcribe": 30, "saaras:v4-transcribe": 30,  # Sarvam pricing page; v4 priced as v3 (no v4 price listed)
        "gemini-3.8-flash": (u["gemini-3.8-flash"]["in_tok"] * 0.75 + u["gemini-3.8-flash"]["out_tok"] * 3.75) / 1e6 * USD_INR / hrs,
        "gpt-4o-transcribe": 0.006 * 60 * USD_INR, "whisper-1": 0.006 * 60 * USD_INR,  # OpenAI $0.006/min
        "whisper-large-v3-turbo": None}
    wer = metric("uc02_helpline_stt", "WER, macro-average over 13 languages (Sindhi excluded)")["values"]
    spts = [{"c": s, "idx": 1 - wer[s]["mean"], "cost": per_hour[s], "local": per_hour[s] is None, "sub": False,
             "tip": f'{pretty(s)}: {1 - wer[s]["mean"]:.0%} word accuracy over 13 languages, '
                    + (f'₹{per_hour[s]:,.0f} per audio hour' if per_hour[s] else "self-hosted")} for s in per_hour if s in wer]
    sg, sW, sH = scatter_svg(spts, "Cost per audio hour (₹, log scale, list price)", 0.2)
    scatter += (f'<figure class="chart"><figcaption><b>Speech recognition: accuracy against cost</b>'
                f'<span class="dir">up and to the left is better</span></figcaption><div class="scroll"><svg viewBox="0 0 {sW} {sH}" role="img" '
                f'aria-label="Speech word accuracy against cost per audio hour">{sg}</svg></div>'
                '<p class="note">Accuracy is 1 − word error rate, averaged over 13 Indian languages of real FLEURS speech (Sindhi left out: Saaras writes it in another script). '
                'Saaras at ₹30 per hour (v4 assumed to cost the same as v3; Sarvam lists no separate v4 price); OpenAI at $0.006 per minute; '
                'Gemini from its measured audio and output tokens at list price. Speech models are not on the text chart above because they have no text-test score.</p></figure>')

    # spoken tasks: end-to-end accuracy against cost per 1,000 spoken requests (phone audio)
    stt_rate = {"saaras": 30, "gemini": per_hour["gemini-3.8-flash"], "gpt": per_hour["gpt-4o-transcribe"]}  # ₹ per audio hour
    tok = lambda m, i, o: (i * PRICE[m][0] + o * PRICE[m][1]) / 1e6  # ₹
    a6, a8 = R["uc06v_offline_agri_voice"], R["uc08v_voice_orders"]
    u6, u8 = a6["usage"], a8["usage"]
    sec6 = u6["saaras:v4"]["audio_s"] / u6["saaras:v4"]["calls"]          # audio seconds per question
    sec8 = u8["asr:saaras-v4-codemix"]["audio_s"] / u8["asr:saaras-v4-codemix"]["calls"]
    g6 = u6["gemini-3.8-flash (answering)"]; ans6_g = tok("gemini-3.8-flash", g6["in_tok"], g6["out_tok"]) / g6["calls"]
    ans6_s = u6["sarvam-105b (answering)"]["inr_list_price"] / u6["sarvam-105b (answering)"]["calls"]
    def ex8(k, m="gemini-3.8-flash"):
        x = u8["extract:" + k]; return tok(m, x["in_tok"], x["out_tok"]) / x["calls"]
    stt = lambda kind, sec: stt_rate[kind] * sec / 3600
    pipes = [  # (name, uc06v key, uc08v key, ₹ per uc06v task, ₹ per uc08v task)
        ("saaras:v4 -> gemini-3.8-flash", "saaras:v4 -> gemini-3.8-flash [phone]", "phone: saaras-v4-codemix",
         stt("saaras", sec6) + ans6_g, stt("saaras", sec8) + ex8("saaras-v4-codemix")),
        ("saaras:v3 -> gemini-3.8-flash", "saaras:v3 -> gemini-3.8-flash [phone]", "phone: saaras-v3-codemix",
         stt("saaras", sec6) + ans6_g, stt("saaras", sec8) + ex8("saaras-v3-codemix")),
        ("gemini-3.8-flash-audio -> gemini-3.8-flash", "gemini-3.8-flash -> gemini-3.8-flash [phone]", "phone: gemini-3.8-flash",
         stt("gemini", sec6) + ans6_g, stt("gemini", sec8) + ex8("gemini-3.8-flash")),
        ("gpt-4o-transcribe -> gemini-3.8-flash", "gpt-4o-transcribe -> gemini-3.8-flash [phone]", "phone: gpt-4o-transcribe",
         stt("gpt", sec6) + ans6_g, stt("gpt", sec8) + ex8("gpt-4o-transcribe")),
        ("gemini-3.8-flash audio-direct", "audio -> gemini-3.8-flash [phone]", "phone: gemini-direct-audio",
         stt("gemini", sec6) + ans6_g, ex8("gemini-direct-audio")),
        ("all-sarvam", "saaras:v4 -> sarvam-105b [phone]", "phone: all-sarvam",
         stt("saaras", sec6) + ans6_s, stt("saaras", sec8) + ex8("all-sarvam", "sarvam-105b")),
    ]
    m6 = metric("uc06v_offline_agri_voice", "overall_pass")["values"]; m8 = metric("uc08v_voice_orders", "Exact whole-order accuracy")["values"]
    vpts = []
    for name, k6, k8, c6, c8 in pipes:
        acc = (m6[k6]["mean"] + m8[k8]["mean"]) / 2; cost = (c6 + c8) / 2 * 1000
        vpts.append({"c": name, "idx": acc, "cost": cost, "local": False, "sub": False,
                     "tip": f'{pretty(name)}: {acc:.0%} average task accuracy on phone audio (farm questions {m6[k6]["mean"]:.0%}, voice-note orders {m8[k8]["mean"]:.0%}), ₹{cost:,.1f} per 1,000 spoken requests'})
    cost_section.speech, cost_section.spoken = spts, vpts  # reused by make_readme.py
    vg, vW, vH = scatter_svg(vpts, "Cost per 1,000 spoken requests (₹, log scale: transcription + answering step)", 0.6)
    scatter += (f'<figure class="chart"><figcaption><b>Spoken tasks: accuracy against cost, end to end</b>'
                f'<span class="dir">up and to the left is better</span></figcaption><div class="scroll"><svg viewBox="0 0 {vW} {vH}" role="img" '
                f'aria-label="Spoken-task accuracy against cost per 1,000 spoken requests">{vg}</svg></div>'
                '<p class="note">Accuracy is the average of two spoken tests on phone-line audio: farmer questions answered correctly and WhatsApp voice notes turned into exactly the right order. '
                'Cost adds transcription (per audio second, at the speech chart\'s rates) and the answering or extraction step (measured tokens at list price). '
                'Colour shows the speech front end; all pipelines except all-Sarvam use Gemini 3.8 Flash after transcription. '
                'The farm-question answering cost is an average over all of that test\'s Gemini answering calls (audio-in calls included), so it is approximate. '
                'The spoken-commands test is left out because its tool-call step did not log tokens.</p></figure>')

    # cost per 1,000 tasks table
    systems = sorted({c for c in costs if len(costs[c]) >= 3}, key=lambda c: (vendor(c) != "sarvam", sum(costs[c].values()) / len(costs[c])))
    head = "".join(f'<th><span class="sw v-{vendor(c)}"></span>{E(pretty(c))}</th>' for c in systems)
    rows = []
    for uc, name in TEXT_TESTS:
        vals = [costs.get(c, {}).get(uc) for c in systems]
        nums = [v for v in vals if v is not None]
        if not nums: continue
        lo2, hi2 = math.log10(min(nums)), math.log10(max(nums))
        cells = "".join('<td class="na">–</td>' if v is None else
                        f'<td style="--t:{(0 if hi2 == lo2 else (1 - (math.log10(v) - lo2) / (hi2 - lo2))) * 70:.0f}%">₹{v:,.1f}</td>' for v in vals)
        rows.append(f"<tr><th>{E(R[uc]['title'][:48])}</th>{cells}</tr>")
    costtab = (f'<figure class="heat"><figcaption><b>API cost per 1,000 tasks, by use case (₹)</b><span class="dir">darker = cheaper within each row; '
               f'includes thinking tokens and repair attempts</span></figcaption><div class="scroll"><table><thead><tr><th></th>{head}</tr></thead>'
               f'<tbody>{"".join(rows)}</tbody></table></div></figure>')

    # price per token and per lakh Indian-language sentences
    tax = R["uc12_token_tax"]["table"]
    indic = [r for r in tax if r["lang"] != "English"]
    tokcol = {"sarvam-105b": "sarvam_tok", "gemini-3.8-flash": "gemini_tok", "gpt-5.4-mini": "openai_tok", "claude-haiku-5.5": "claude_tok",
              "gemini-pro": "gemini_tok", "gpt-5.5": "openai_tok", "claude-sonnet-5.5": "claude_tok"}
    prow = []
    for k, (pin, pout) in sorted(PRICE.items(), key=lambda kv: kv[1][0]):
        toks = sum(r[tokcol[k]] for r in indic if r.get(tokcol[k])) / len([r for r in indic if r.get(tokcol[k])])
        lakh = toks * 1e5 * pin / 1e6
        prow.append(f'<tr><th><span class="sw v-{vendor(k)}"></span>{E(pretty(k))}</th><td>₹{pin:,.1f}</td><td>₹{pout:,.1f}</td>'
                    f'<td>{toks:.1f}</td><td>₹{lakh:,.2f}</td></tr>')
    ptab = ('<figure class="heat plain"><figcaption><b>Price per token, and what it costs to send Indian-language text</b>'
            f'<span class="dir">₹ per 1M tokens at ₹{USD_INR}/US$ (RBI, 9 Oct 2026)</span></figcaption><div class="scroll"><table><thead><tr><th>Model</th>'
            '<th>Input ₹/1M</th><th>Output ₹/1M</th><th>Tokens per Indian sentence</th><th>₹ to send 1 lakh sentences</th></tr></thead><tbody>'
            + "".join(prow) + '</tbody></table></div><p class="note">Tokens per sentence: average over 14 Indian languages of the same FLEURS sentences (use case 12). '
            'Gemini 3.8 Flash prices are promotional until 31 Dec 2026 and double from 1 Jan 2027. Gemini Pro priced as Gemini 3.1 Pro. '
            'Sarvam-105B: Sarvam changelog, 10 Oct 2026. Others: OpenRouter and Google list prices.</p></figure>')
    units = ('<figure class="heat plain"><figcaption><b>Speech, voice and document unit prices</b><span class="dir">list prices, October 2026</span></figcaption>'
             '<div class="scroll"><table><thead><tr><th>Job</th><th>Sarvam</th><th>Rival</th></tr></thead><tbody>'
             '<tr><th>Speech-to-text</th><td>Saaras ₹30 per audio hour (₹45 with speaker labels)</td><td>Gemini 3.8 Flash bills audio as input tokens at $0.75/1M</td></tr>'
             f'<tr><th>Text-to-speech</th><td>Bulbul ₹3 per 1,000 characters</td><td>Gemini Flash TTS $9 per 1M audio tokens; measured about 19,400 audio tokens per 10,000 characters ≈ ₹{19400 * 9 / 1e6 * USD_INR / 10:.1f} per 1,000 characters</td></tr>'
             '<tr><th>Documents</th><td>Document AI Extract ₹1 per page; Digitise ₹0.50 per page</td><td>Gemini / Claude bill the page image as input tokens</td></tr>'
             '<tr><th>Translation</th><td>Sarvam-Translate / Mayura by character: list price ₹5 per 1,000 characters (Sarvam pricing page, Oct 2026), about ₹2 per 1,000 as actually billed in this run; Sarvam-105B by token, 80–200× cheaper for the same legal text</td><td>LLM token prices above</td></tr>'
             '<tr><th>Voice bot, all-Sarvam</th><td>v3 stack ₹1.56 per conversation-minute (speech ₹0.23, model ₹0.015, voice ₹1.32); v4 stack about ₹1.42</td><td>–</td></tr>'
             '</tbody></table></div></figure>')
    return scatter + costtab + ptab + units


USEMAP = [  # (job, who, use, evidence suite, model whose measured cost to show)
    ("EMI and collections reminder calls", "Banks, NBFCs", "All-Sarvam voice stack; confirm amounts with a Gemini 3.8 Flash transcript", "uc01_voice_support", None),
    ("Inbound support calls in regional languages", "Telecom, D2C", "Saaras → GPT-5.4 mini or Claude Haiku 5.5 → Bulbul", "uc01_voice_support", None),
    ("Citizen grievance and scheme helplines", "Government", "Saaras for transcripts; check Sindhi and Assamese separately", "uc02_helpline_stt", None),
    ("Call-centre QA and analytics", "BPO, insurance", "Saaras batch with speaker labels", "uc02_helpline_stt", None),
    ("KYC and account-opening documents", "Banks, fintech", "Gemini 3.8 Flash or Claude Sonnet 5.5 on the image; human review for poor photos", "uc03_documents", None),
    ("GST invoice capture", "Accounts payable, SMEs", "Gemini 3.8 Flash on the image; Sarvam Document AI on clean scans", "uc03_documents", None),
    ("Land-record digitisation", "State governments", "Gemini or Claude on the image; reject fields the model cannot read", "uc03_documents", None),
    ("HR and policy assistant in Indian languages", "Enterprises", "Gemini Embedding 2 retrieval + Gemini 3.8 Flash answers", "uc04_indic_rag", "gemini-3.8-flash"),
    ("Insurance claim questions", "Insurers, TPAs", "Same RAG stack; test answers in the user's script", "uc04_indic_rag", "gpt-5.4-mini"),
    ("OPD doctor scribe", "Clinics, healthtech", "Gemini 3.8 Flash straight on the consultation audio", "uc05_clinical_notes", "gemini-3.8-flash"),
    ("Krishi advisory helpline", "Agritech, FPOs", "Cloud model that refuses out-of-scope questions; offline only with thinking on", "uc06_offline_agri", "gemini-3.8-flash"),
    ("Course and training localisation", "Edtech, L&D", "Sarvam-Translate into Indian languages + Bulbul voice-over", "uc07_translation_dubbing", None),
    ("Product catalogue translation", "E-commerce", "Sarvam-Translate into Indian languages; Gemini into English", "uc07_translation_dubbing", None),
    ("WhatsApp orders and voice notes", "Quick commerce, kirana", "Gemini 3.8 Flash for order extraction; Saaras v4 + keyterms or Gemini audio for voice notes", "uc08v_voice_orders", "gemini-3.8-flash"),
    ("Name and address transliteration", "Logistics", "Gemini 3.8 Flash; Sarvam's transliterate API is weak on Tamil", "uc08_quick_commerce", None),
    ("Judgment and order translation", "Courts, legal-tech", "Sarvam-105B or GPT-5.4 mini; never Mayura for amounts", "uc09_legal", None),
    ("Plain-language summaries for litigants", "Legal aid", "Gemini 3.8 Flash or GPT-5.4 mini", "uc09_legal", "gemini-3.8-flash"),
    ("Ticket triage and CRM notes", "SaaS support", "GPT-5.4 mini or Claude Haiku 5.5", "uc10_selfhost_business", "claude-haiku-5.5"),
    ("On-premise processing of regulated data", "Banks, hospitals", "Qwen3-30B self-hosted; Sarvam-30B if speed and token cost matter more", "uc10_selfhost_business", None),
    ("Coding copilot for Indian business logic", "Fintech, ERP vendors", "Gemini 3.8 Flash or Claude Haiku 5.5", "uc11_bharat_code", "claude-haiku-5.5"),
    ("Voice-assistant actions (recharge, bill pay)", "Wallets, telecom", "Saaras or Gemini audio in front of Gemini tool calling; confirm payee and amount before paying", "uc11v_voice_tools", None),
    ("Budgeting Indian-text-heavy workloads", "Any", "Sarvam's tokenizer is cheapest; Claude uses 3.4× the English token count", "uc12_token_tax", None),
]


def usemap():
    _, costs = intelligence()
    rows = []
    for job, who, use, uc, model in USEMAP:
        c = costs.get(model, {}).get(uc) if model else None
        rows.append(f'<tr><th>{E(job)}</th><td>{E(who)}</td><td>{E(use)}</td><td><a href="#{uc}">{int(uc[2:4])}</a></td>'
                    f'<td>{"₹%s per 1,000" % format(round(c, 1), ",") if c else "see section"}</td></tr>')
    return ('<div class="scroll"><table class="usemap"><thead><tr><th>Job</th><th>Who needs it</th><th>Recommended</th><th>Evidence</th>'
            '<th>Measured API cost</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")


if __name__ == "__main__":
    sc_rows, tally, sections = body()
    tpl = (ROOT / "report" / "template.html").read_text()
    out = (tpl.replace("{{SCORECARD}}", sc_rows).replace("{{SECTIONS}}", sections)
           .replace("{{LEAD}}", str(tally["lead"])).replace("{{LEVEL}}", str(tally["level"])).replace("{{BEHIND}}", str(tally["behind"]))
           .replace("{{NROWS}}", str(len(SC))).replace("{{COST}}", cost_section()).replace("{{USEMAP}}", usemap()))
    extra = ROOT / "report" / "extra.html"
    out = out.replace("{{EXTRA}}", extra.read_text() if extra.exists() else "")
    files = files_json()
    json.loads(files.replace("<\\/", "</"))  # the embedded file data must stay valid JSON
    out = out.replace("{{FILES}}", files)  # last: the files contain the other placeholders as text
    (ROOT / "report" / "index.html").write_text(out)
    print("wrote report/index.html", len(out) // 1024, "KB;", tally)