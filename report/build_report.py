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
    (r"gpt-5\.4-mini", "GPT-5.4 mini"), (r"gpt-5\.5", "GPT-5.5"), (r"gpt-4o-mini-tts", "GPT-4o mini TTS"),
    (r"gpt-4o-transcribe", "GPT-4o transcribe"), (r"whisper-1", "Whisper (OpenAI API)"),
    (r"whisper-large-v3-turbo", "Whisper large-v3-turbo (local)"),
    (r"gemini-3\.8-flash-tts", "Gemini 3.8 Flash TTS"), (r"gemini-3\.8-flash", "Gemini 3.8 Flash"),
    (r"gemini-pro-latest", "Gemini Pro"), (r"gemini-embedding-2", "Gemini Embedding 2"),
    (r"sarvam-105b-conversations", "Sarvam-105B conversations"), (r"sarvam-105b", "Sarvam-105B"),
    (r"sarvam-30b-local", "Sarvam-30B (self-hosted)"), (r"qwen3-30b-local", "Qwen3-30B (self-hosted)"),
    (r"sarvam-translate:v1", "Sarvam-Translate"), (r"mayura:v1", "Mayura"), (r"saaras:v3", "Saaras v3"),
    (r"bulbul:v3", "Bulbul v3"), (r"sarvam-vision", "Sarvam Vision"), (r"sarvam-transliterate", "Sarvam Transliterate API"),
    (r"-nothink\b", ""), (r"-think\b", " · thinking"), (r"-codemix", " codemix mode"), (r"-transcribe\b", " transcribe mode"),
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
def bar_chart(uc, name, kind="pct", title=None, note=None, include=None):
    m = metric(uc, name)
    hib = m.get("higher_is_better", True)
    rows = [(s, v) for s, v in m["values"].items() if isinstance(v, dict) and v.get("mean") is not None]
    if include: rows = [r for r in rows if include(r[0])]
    rows.sort(key=lambda r: r[1]["mean"], reverse=hib)
    maxn = max((v.get("n") or 0) for _, v in rows)
    sub = lambda v: bool(v.get("n")) and v["n"] < 0.8 * maxn
    vmax = max(max(v["mean"], v.get("hi") or v["mean"]) for _, v in rows)
    top = 1.0 if kind == "pct" and vmax <= 1 else vmax * 1.08
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
            '<p class="note">All-Sarvam stack costs ₹1.56 per conversation-minute at list prices (speech ₹0.23, model ₹0.015, voice ₹1.32).</p></figure>')


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
        verdict_row("uc01_voice_support", "Entity accuracy (digits/amounts/dates exactly captured) [phone]", "pct", "Hinglish support calls: numbers captured"),
        verdict_row("uc02_helpline_stt", "WER, macro-average over languages", "num2", "Helpline speech in 13 languages: word error rate"),
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
        bar_chart("uc02_helpline_stt", "WER, macro-average over languages", "num2", "Word error rate, average of 13 languages (Sindhi excluded)"),
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


if __name__ == "__main__":
    sc_rows, tally, sections = body()
    tpl = (ROOT / "report" / "template.html").read_text()
    out = (tpl.replace("{{SCORECARD}}", sc_rows).replace("{{SECTIONS}}", sections)
           .replace("{{LEAD}}", str(tally["lead"])).replace("{{LEVEL}}", str(tally["level"])).replace("{{BEHIND}}", str(tally["behind"]))
           .replace("{{NROWS}}", str(len(SC))))
    extra = ROOT / "report" / "extra.html"
    out = out.replace("{{EXTRA}}", extra.read_text() if extra.exists() else "")
    files = files_json()
    json.loads(files.replace("<\\/", "</"))  # the embedded file data must stay valid JSON
    out = out.replace("{{FILES}}", files)  # last: the files contain the other placeholders as text
    (ROOT / "report" / "index.html").write_text(out)
    print("wrote report/index.html", len(out) // 1024, "KB;", tally)
