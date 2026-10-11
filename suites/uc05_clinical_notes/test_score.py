"""Scorer self-check: a note built from gold must score perfectly; a trap drug must be caught. Run with .venv/bin/python."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import run as R

for d in R.load():
    g, v = d["gold"], d["gold"]["vitals"]
    note = {"chief_complaint": g["chief_complaint"][0], "duration": f"{g['duration']['value']} {g['duration']['unit']}",
            "vitals": {"bp": v.get("bp"), "pulse": v.get("pulse"), "temperature_f": v.get("temp_f"), "spo2": v.get("spo2"),
                       "weight_kg": v.get("weight_kg"), "blood_sugar": v.get("blood_sugar")},
            "diagnosis": g["diagnosis"][0], "follow_up": g["follow_up"][0],
            "medications": [{"drug": m["drug"][0], "dose": m["dose"], "frequency": m["frequency"],
                             "duration_days": m["duration_days"]} for m in g["medications"]],
            "allergies": [a[0] for a in g["allergies"]], "red_flag_advice": [r[0] for r in g["red_flags"]]}
    s = R.score(d, note)
    for f in R.FIELDS + ["vitals", "red_flags", "med_found", "med_exact", "med_exact_with_duration"]:
        assert R.field_recall(s, f) in (None, 1.0), (d["id"], f)
    assert not R.halluc_count(s) and not s["false_allergy"], d["id"]
    if g["not_prescribed"]:
        note["medications"].append({"drug": g["not_prescribed"][0], "dose": "500 mg", "frequency": "BD", "duration_days": 5})
        assert R.score(d, note)["trap_meds"], d["id"]
assert R.canon_freq("twice daily") == "BD" and R.canon_freq("1-1-1") == "TDS"
assert R.dose_eq("1 g", "1000 mg") and R.duration_days("one week") == 7
print("ok")
