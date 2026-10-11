"""Turn raw UC03 records into results/uc03_documents.json (no API calls). Findings text lives in notes.json."""
import json
from collections import Counter, defaultdict
from pathlib import Path

from common.bench import bootstrap_ci, pctl
from run import (CHEAP_IMG, CONDS, FRONTIER_IMG, FRONTIER_SET, G_EXT, G_IMG, G_OCR, S_EXT, UC, VISION,
                 field_match, text_scores)

FIELD_SYS = [S_EXT, G_EXT, G_IMG] + CHEAP_IMG + FRONTIER_IMG
TEXT_SYS = [VISION, G_OCR]
NOTES = Path(__file__).with_name("notes.json")
INR_105B = (15 / 1e6, 60 / 1e6)  # list price per input / output token


def build(golds, raws):
    rec = {}
    for r in raws:
        if "error" not in r:
            rec[(r["id"], r["cond"], r["system"])] = r
    page = defaultdict(dict)  # (system, cond) -> id -> scores
    field_err = defaultdict(Counter)
    for g in golds:
        for c in CONDS:
            for s in FIELD_SYS:
                r = rec.get((g["id"], c, s))
                if not r:
                    continue
                pred = r.get("fields") if isinstance(r.get("fields"), dict) else {}
                hits = {k: field_match(v, pred.get(k)) for k, v in g["fields"].items()}
                page[(s, c)][g["id"]] = {"acc": sum(hits.values()) / len(hits), "all": all(hits.values()),
                                         "hits": hits}
                for k, ok in hits.items():
                    if not ok:
                        field_err[(s, c)][f"{g['doc_type']}.{k}"] += 1
            for s in TEXT_SYS:
                r = rec.get((g["id"], c, s))
                if r:
                    e, wr = text_scores(g["text"], r["text"])
                    page[(s, c)][g["id"]] = {"cer": e, "word_recall": wr}

    gid = {g["id"]: g for g in golds}
    metrics = []

    def metric(name, systems, key, hib, unit, cond):
        metrics.append({"name": f"{name} ({cond})", "higher_is_better": hib, "unit": unit, "values": {
            s: bootstrap_ci([float(v[key]) for v in page[(s, cond)].values()]) for s in systems}})

    for c in CONDS:
        metric("field exact-match accuracy", FIELD_SYS, "acc", True, "fraction of fields", c)
        metric("pages with every field correct", FIELD_SYS, "all", True, "fraction of pages", c)
        metric("character error rate vs gold text", TEXT_SYS, "cer", False, "CER (capped at 1)", c)
        metric("gold-word recall (order-free)", TEXT_SYS, "word_recall", True, "fraction of gold words", c)

    fset = set(FRONTIER_SET)  # like-for-like: every field system on the fixed 30 frontier images
    for key, name, unit in (("acc", "field exact-match accuracy", "fraction of fields"),
                            ("all", "pages with every field correct", "fraction of pages")):
        metrics.append({"name": f"{name} (frontier subset: 16 harsh + 14 phone photos)", "higher_is_better": True,
                        "unit": unit, "values": {s: bootstrap_ci([float(page[(s, c)][i][key]) for i, c in fset
                                                                  if i in page[(s, c)]]) for s in FIELD_SYS}})

    def breakdown(attr, key, systems):
        out = {}
        for c in CONDS:
            tab = defaultdict(dict)
            for s in systems:
                groups = defaultdict(list)
                for i, v in page[(s, c)].items():
                    groups[gid[i][attr]].append(float(v[key]))
                for grp, vals in groups.items():
                    tab[grp][s] = round(sum(vals) / len(vals), 4)
            out[c] = dict(tab)
        return out

    per_language = {f"field accuracy by script ({c})": v for c, v in breakdown("script", "acc", FIELD_SYS).items()}
    per_language.update({f"CER by script ({c})": v for c, v in breakdown("script", "cer", TEXT_SYS).items()})
    per_doc_type = {f"field accuracy by document type ({c})": v
                    for c, v in breakdown("doc_type", "acc", FIELD_SYS).items()}

    # latency: an extraction pipeline's page latency includes the Vision job it reads from
    lat = defaultdict(list)
    use = defaultdict(lambda: Counter())
    for (i, c, s), r in rec.items():
        ms = r.get("ms")
        if s in (S_EXT, G_EXT) and (i, c, VISION) in rec:
            ms = ms + rec[(i, c, VISION)]["ms"]
        lat[s].append(ms)
        u = use[s]
        u["calls"] += 1
        u["in_tok"] += r.get("in_tok") or 0
        u["out_tok"] += r.get("out_tok") or 0
        u["pages"] += r.get("pages") or 0
        u["reasoning_tok"] += r.get("reasoning_tok") or 0
        u["cost_usd"] += r.get("cost_usd") or 0
    speed = {s: {"p50_ms": round(pctl(v, 0.5)), "p95_ms": round(pctl(v, 0.95)), "n": len(v)} for s, v in lat.items()}
    usage = {s: dict(u) for s, u in use.items()}
    n_pages = max(1, use[VISION]["calls"])
    ext = use[S_EXT]
    inr_105b = (ext["in_tok"] * INR_105B[0] + ext["out_tok"] * INR_105B[1]) / max(1, ext["calls"])
    cost = {
        VISION: {"inr_per_1000_pages": 500.0, "basis": "₹0.50/page list price"},
        S_EXT: {"inr_per_1000_pages": round(500 + 1000 * inr_105b, 1),
                "basis": f"Vision ₹500 + sarvam-105b ₹{1000 * inr_105b:.1f} at ₹15/₹60 per 1M in/out tokens"},
        G_IMG: {"tokens_per_1000_pages": {k: round(1000 * use[G_IMG][k] / max(1, use[G_IMG]["calls"]))
                                          for k in ("in_tok", "out_tok")},
                "basis": "Gemini price not recorded here; multiply by your current Gemini rate"},
        G_EXT: {"inr_per_1000_pages_sarvam_part": 500.0,
                "gemini_tokens_per_1000_pages": {k: round(1000 * use[G_EXT][k] / max(1, use[G_EXT]["calls"]))
                                                 for k in ("in_tok", "out_tok")}},
    }
    for s_ in CHEAP_IMG + FRONTIER_IMG:
        n = max(1, use[s_]["calls"])
        cost[s_] = {"tokens_per_1000_pages": {k: round(1000 * use[s_][k] / n) for k in ("in_tok", "out_tok")}}
        if s_.startswith("or:"):
            cost[s_]["usd_per_1000_pages"] = round(1000 * use[s_]["cost_usd"] / n, 2)
    usage["_cost_per_1000_pages"] = cost
    usage["_openrouter_cost_usd"] = round(sum(use[s_]["cost_usd"] for s_ in CHEAP_IMG + FRONTIER_IMG), 4)
    usage["_sarvam_spend_inr_this_run"] = round(0.5 * use[VISION]["pages"] + ext["in_tok"] * INR_105B[0]
                                                + ext["out_tok"] * INR_105B[1], 2)

    # examples: pages where the pipelines disagree most on the harsh-photo condition
    examples = []
    xc = "harsh"
    cand = sorted((i for i in gid if i in page[(G_IMG, xc)]),
                  key=lambda i: -len({round(page[(s, xc)].get(i, {}).get("acc", -1), 2) for s in FIELD_SYS}))
    seen_types = set()
    for i in cand:
        g = gid[i]
        if g["doc_type"] in seen_types or len(examples) >= 5:
            continue
        seen_types.add(g["doc_type"])
        ex = {"id": i, "doc_type": g["doc_type"], "script": g["script"], "condition": xc,
              "image": f"data/{UC}/pages/{i}_{xc}.jpg", "gold_fields": g["fields"], "systems": {}}
        for s in FIELD_SYS:
            r = rec.get((i, xc, s), {})
            p = page[(s, xc)].get(i)
            pred = r.get("fields") if isinstance(r.get("fields"), dict) else {}
            ex["systems"][s] = {"field_accuracy": p and round(p["acc"], 3),
                                "wrong_fields": {k: pred.get(k) for k, ok in (p or {"hits": {}})["hits"].items()
                                                 if not ok}}
        for s in TEXT_SYS:
            p = page[(s, xc)].get(i)
            ex["systems"][s] = {"cer": p and round(p["cer"], 3)}
        examples.append(ex)

    notes = json.loads(NOTES.read_text()) if NOTES.exists() else {}
    top_err = {f"{s} ({c})": field_err[(s, c)].most_common(6) for s in FIELD_SYS for c in CONDS}
    return {
        "uc": UC, "title": "Documents: KYC, GST invoices, land records and bills in Indian scripts",
        "business_question": "Can I digitise Indian-language business documents (GST invoices, KYC forms, land "
                             "records, utility bills, ration cards) into correct structured fields, from clean "
                             "scans and from phone photos, and which stack should I use?",
        "dataset": {"name": "uc03-synthetic-indic-docs", "source": "authored for this benchmark "
                    "(suites/uc03_documents/make_data.py); rendered with macOS system fonts via CoreText",
                    "license": "CC0 (synthetic); fonts are macOS system fonts used only to render images",
                    "n": len(golds), "n_images": sum(len(page[(VISION, c)]) for c in CONDS), "conditions": list(CONDS),
                    "languages": sorted({g["lang"] for g in golds}),
                    "scripts": dict(Counter(g["script"] for g in golds)),
                    "doc_types": dict(Counter(g["doc_type"] for g in golds)),
                    "fields_scored": sum(len(g["fields"]) for g in golds), "synthetic": True},
        "systems": TEXT_SYS + FIELD_SYS, "metrics": metrics, "per_language": per_language,
        "per_doc_type": per_doc_type, "most_missed_fields": top_err, "speed": speed, "usage": usage,
        "examples": examples, "findings": notes.get("findings", []), "caveats": notes.get("caveats", []),
        "verdict": notes.get("verdict", ""),
    }
