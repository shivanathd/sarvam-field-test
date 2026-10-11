"""Build the parallel test set from FLEURS (google/fleurs, CC-BY 4.0) transcription TSVs.

FLEURS sentences are FLORES-101 sentences; the same `id` is the same sentence in every language,
so the native-script transcription of each language is a human reference translation.
Output: data/uc07_translation_dubbing/items.json
"""
import csv, json, random, sys
from pathlib import Path
from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "uc07_translation_dubbing"
LANGS = ["en_us", "hi_in", "bn_in", "ta_in", "te_in", "kn_in", "ml_in", "mr_in", "gu_in", "pa_in", "or_in"]
N = 32  # budget-capped: Sarvam translate bills ~Rs20 per 10k input chars


def load(lang):
    p = hf_hub_download("google/fleurs", f"data/{lang}/test.tsv", repo_type="dataset", local_dir=D / "fleurs")
    out = {}
    with open(p) as f:
        for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            out.setdefault(row[0], row[2].strip())  # several speakers per id; text is identical
    return out


if __name__ == "__main__":
    t = {l: load(l) for l in LANGS}
    ids = sorted(set.intersection(*(set(v) for v in t.values())), key=int)
    ids = [i for i in ids if 50 <= len(t["en_us"][i]) <= 110]  # short, product/training-copy length
    random.Random(7).shuffle(ids)
    items = [{"id": i, **{l[:2]: t[l][i] for l in LANGS}} for i in sorted(ids[:N], key=int)]
    (D / "items.json").write_text(json.dumps(items, ensure_ascii=False, indent=1))
    print(len(ids), "candidates;", len(items), "written")
