"""Generate the synthetic UC09 legal passages: 40 English court/RTI texts dense with checkable facts.

12 hand-written templates (cheque bounce, bail, consumer, tenancy, land, RTI, motor accident) are filled
with invented parties, places, case numbers, dates and amounts. Every slot becomes a typed entity, so
scoring needs no AI judge. Parties are fictitious; no real case is reproduced.
Slots: [[P:k]] person  [[M:k]] male person  [[C:k]] / [[C:k:hc]] / [[C:k:vil]] place
       [[A:k]] rupees in digits (₹4,75,000)  [[L:k]] rupees in lakh (₹12.5 lakh)  [[K:k]] crore
       [[T:k]] date (keys t1<t2<t3 are chronological)  [[R=lo-hi:k]] random int  [[N=138]] fixed number
       [[Y:k]] / [[Y:k:t1]] case year (latest date's year / t1's year)   [[D:k]] value supplied by the template's derive() (amounts/numbers computed from others)
Output: data/uc09_legal/passages.jsonl  {id, type, text, entities:[{key,type,value,surface}], key_facts:[keys]}
"""
import json, random, re
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "uc09_legal"

MALE = ["Ramesh Kulkarni", "Suresh Pawar", "Anil Deshmukh", "Mohammed Irfan Shaikh", "Rajendra Prasad Yadav",
        "Sanjay Banerjee", "Prakash Iyer", "Venkatesh Murugan", "Dinesh Chauhan", "Subrata Ghosh",
        "Gopal Krishnan", "Imran Qureshi", "Harish Bhatt", "Manoj Tiwari", "Arvind Patil", "Selvam Rajan"]
FEMALE = ["Sunita Joshi", "Meena Raghavan", "Kavita Sharma", "Rekha Bose", "Lakshmi Narayanan",
          "Farzana Begum", "Anjali Mehta", "Shobha Gaikwad", "Priya Chatterjee", "Geetha Subramanian"]
PLACES = {"court": ["Pune", "Nagpur", "Nashik", "Madurai", "Coimbatore", "Kolkata", "Howrah", "Lucknow",
                    "Varanasi", "Patna", "Jaipur", "Indore", "Bhopal", "Salem"],
          "hc": ["Bombay", "Madras", "Calcutta", "Allahabad", "Patna"],
          "ps": ["Shivajinagar", "Kothrud", "Hadapsar", "Civil Lines", "Kotwali", "Anna Nagar", "Gandhi Bazar"],
          "vil": ["Shirur", "Kalyani", "Vadakkupatti", "Ambegaon", "Sonari", "Kothamangalam", "Bishnupur"]}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def inr(n):  # Indian digit grouping: 475000 -> 4,75,000
    s = str(int(n))
    head, tail = s[:-3], s[-3:]
    while len(head) > 2:
        tail = head[-2:] + "," + tail
        head = head[:-2]
    return (head + "," + tail) if head else tail


def lakh(v):  # rupee value -> "12.5 lakh"
    return f"{v / 1e5:.2f}".rstrip("0").rstrip(".") + " lakh"


T = []  # (type, template, key_facts, derive)


def tpl(kind, key_facts, derive=None):
    def deco(text):
        T.append((kind, " ".join(text.split()), key_facts, derive))
    return deco


tpl("cheque_bounce_conviction", ["a1", "chq", "m", "a2", "d", "p2"],
    lambda v, r: {"a2": ("A", v["a1"] * 2)})(
    """IN THE COURT OF THE JUDICIAL MAGISTRATE FIRST CLASS, [[C:c1]]. Criminal Complaint No. [[R=1000-4999:cc]]/[[Y:y1]].
    [[P:p1]] (Complainant) versus [[M:p2]] (Accused). The accused issued cheque No. [[R=100000-999999:chq]] dated
    [[T:t1]] for [[A:a1]] towards repayment of a hand loan. The cheque was returned unpaid on [[T:t2]] with the remark
    "funds insufficient". Despite a legal notice dated [[T:t3]], the accused failed to pay within [[N=15]] days. The
    accused is convicted under Section [[N=138]] of the Negotiable Instruments Act, [[N=1881]], sentenced to simple
    imprisonment for [[R=3-12:m]] months and directed to pay compensation of [[D:a2]] to the complainant under
    Section [[N=357]](3) of the Code of Criminal Procedure within [[R=30-90:d]] days.""")

tpl("cheque_bounce_appeal", ["l1", "dep", "t1", "t2", "d", "p1"],
    lambda v, r: {"dep": ("A", round(v["l1"] * 0.2))})(
    """IN THE COURT OF THE ADDITIONAL SESSIONS JUDGE, [[C:c1]]. Criminal Appeal No. [[R=10-399:ca]]/[[Y:y1]]. The
    appellant [[M:p1]] challenges the judgment dated [[T:t3]] convicting him under Section [[N=138]] of the
    Negotiable Instruments Act for dishonour of a cheque of [[L:l1]]. The appellant has deposited [[D:dep]], being
    20% of the cheque amount, under Section [[N=148]] of the Act. The statutory notice was served on [[T:t1]], but
    the complaint was filed only on [[T:t2]], beyond the one month allowed by Section [[N=142]], so the complaint was
    time-barred. The appeal is allowed, the conviction is set aside and the deposit of [[D:dep]] shall be refunded to
    the appellant within [[R=15-45:d]] days.""")

tpl("bail_granted", ["t1", "fir", "l1", "days", "a1", "p1"])(
    """IN THE COURT OF THE SESSIONS JUDGE, [[C:c1]]. Bail Application No. [[R=100-2999:ba]]/[[Y:y1]]. The applicant
    [[M:p1]], aged [[R=21-64:age]] years, was arrested on [[T:t1]] in FIR No. [[R=10-899:fir]]/[[Y:yf:t1]] registered at
    [[C:c2:ps]] police station under Sections [[N=420]] and [[N=406]] of the Indian Penal Code for allegedly cheating the
    complainant [[P:p2]] of [[L:l1]]. The charge-sheet was filed on [[T:t2]] and the applicant has been in custody for
    [[R=60-300:days]] days. Trial is unlikely to conclude soon. The applicant is released on bail on furnishing a
    personal bond of [[A:a1:10000-100000]] with one surety of the like amount. He shall report to the police station every Monday
    and shall not leave the district without permission.""")

tpl("anticipatory_bail_rejected", ["k1", "inv", "t3", "d", "crime", "p1"])(
    """HIGH COURT OF JUDICATURE AT [[C:c1:hc]]. Criminal Miscellaneous Application No. [[R=1000-9999:cma]] of
    [[Y:y1]]. The applicant [[M:p1]] seeks anticipatory bail under Section [[N=438]] of the Code of Criminal
    Procedure, [[N=1973]] in Crime No. [[R=10-999:crime]]/[[Y:yc:t1]], registered under Sections [[N=409]] and
    [[N=420]] of the Indian Penal Code, for misappropriating [[K:k1]] collected from [[R=40-400:inv]]
    investors between [[T:t1]] and [[T:t2]]. Custodial interrogation is necessary to trace the money. The
    application is rejected. The interim protection granted on [[T:t3]] stands vacated, and the applicant shall
    surrender before the investigating officer within [[R=3-14:d]] days.""")

tpl("consumer_builder_refund", ["l1", "t1", "int", "a1", "a2", "d"])(
    """BEFORE THE DISTRICT CONSUMER DISPUTES REDRESSAL COMMISSION, [[C:c1]]. Consumer Complaint No.
    [[R=50-899:cc]]/[[Y:y1]]. [[P:p1]] versus [[M:p2]], proprietor of a builder firm. The complainant paid [[L:l1]]
    on [[T:t1]] for a flat that was to be delivered by [[T:t2]]. Possession was never handed over. The opposite
    party is directed to refund [[L:l1]] with interest at [[R=7-11:int]]% per annum from [[T:t1]], to pay
    [[A:a1:25000-200000]] as compensation for mental agony and [[A:a2:5000-50000]] as litigation costs, all within [[R=30-60:d]] days,
    failing which interest at [[R=12-15:int2]]% per annum shall apply.""")

tpl("consumer_insurance_appeal", ["a1", "days", "yrs", "int", "a2", "d"])(
    """BEFORE THE STATE CONSUMER DISPUTES REDRESSAL COMMISSION, [[C:c1]]. First Appeal No. [[R=100-1999:fa]] of
    [[Y:y1]]. The insurer appeals against the order dated [[T:t2]] directing it to pay [[A:a1]] towards the health
    insurance claim of [[P:p1]], who was hospitalised from [[T:t1]] for [[R=4-21:days]] days. The insurer
    repudiated the claim citing a pre-existing disease, but the policy had been renewed for [[R=4-9:yrs]]
    continuous years without any such disclosure being sought. The appeal is dismissed. The insurer shall pay
    [[A:a1]] with interest at [[R=6-9:int]]% per annum and [[A:a2:5000-50000]] as costs within [[R=30-45:d]] days.""")

tpl("tenancy_eviction", ["rent", "arr", "t1", "d", "t2", "mesne"],
    lambda v, r: {"arr": ("A", v["rent"] * r.randint(6, 24)), "mesne": ("A", v["rent"] * 2)})(
    """IN THE COURT OF THE SMALL CAUSES JUDGE, [[C:c1]]. Rent Suit No. [[R=100-1999:rs]] of [[Y:y1]]. The landlord
    [[P:p1]] seeks eviction of the tenant [[M:p2]] from shop No. [[R=11-60:shop]] on the ground of arrears of rent.
    The monthly rent is [[A:rent:4000-60000]] and the tenant has not paid rent since [[T:t1]], the arrears amounting to
    [[D:arr]] on the date of the suit. The tenant is directed to deposit the arrears of [[D:arr]] within
    [[R=30-60:d]] days and to vacate the premises by [[T:t2]]. Mesne profits are fixed at [[D:mesne]] per month
    from [[T:t2]] until possession is handed over.""")

tpl("land_partition", ["sv", "acre", "t1", "t2", "a1", "p2"])(
    """IN THE COURT OF THE CIVIL JUDGE (SENIOR DIVISION), [[C:c1]]. Original Suit No. [[R=100-999:os]] of [[Y:y1]].
    The plaintiff [[P:p1]] claims a one-third share in agricultural land bearing Survey No. [[R=10-499:sv]]
    measuring [[R=12-29:acre]] acres at village [[C:c2:vil]], purchased by their father [[M:p3]] under a sale deed
    dated [[T:t1]]. The defendant [[M:p2]] relied on a will dated [[T:t2]], but neither attesting witness was
    examined, so the will is not proved. A preliminary decree for partition is passed; the plaintiff is entitled to
    a one-third share. The defendant is restrained from selling or mortgaging the land and shall pay [[A:a1:10000-75000]] as
    costs of the suit.""")

tpl("rti_reply_fee", ["rti", "ward", "pages", "fee", "d", "t1"],
    lambda v, r: {"fee": ("A", 2 * v["pages"])})(
    """OFFICE OF THE PUBLIC INFORMATION OFFICER, MUNICIPAL CORPORATION OF [[C:c1]]. Reply to RTI Application No.
    [[R=1000-9999:rti]]/[[Y:y1]] dated [[T:t1]] filed by [[P:p1]]. Information sought: copies of work orders for
    road resurfacing in Ward No. [[R=11-80:ward]] during the last two years. Reply: [[R=12-80:pages]] pages of
    information are available. You are requested to deposit [[D:fee]] at the rate of ₹2 per page within
    [[R=15-30:d]] days to receive the copies. If you are not satisfied with this reply, you may file a first appeal
    under Section [[N=19]](1) of the Right to Information Act, [[N=2005]] before the First Appellate Authority within
    [[N=30]] days of receiving this reply.""")

tpl("rti_penalty", ["delay", "pen", "inst", "d", "t1", "p2"],
    lambda v, r: {"pen": ("A", min(250 * v["delay"], 25000))})(
    """STATE INFORMATION COMMISSION, [[C:c1]]. Second Appeal No. [[R=100-9999:sa]]/[[Y:y1]]. The appellant
    [[P:p1]] filed an RTI application on [[T:t1]] seeking copies of land mutation records. The Public Information
    Officer, [[M:p2]], did not reply within the mandatory [[N=30]] days. The Commission finds a delay of
    [[R=40-250:delay]] days without reasonable cause and imposes a penalty of [[D:pen]] under Section [[N=20]](1)
    of the RTI Act, [[N=2005]], at ₹250 per day subject to the maximum of ₹25,000. The amount shall be recovered
    from the officer's salary in [[R=2-5:inst]] monthly instalments. The information shall be supplied free of cost
    within [[R=11-21:d]] days of this order dated [[T:t2]].""")


def _mact_death(v, r):
    age = v["age"]
    mult = 17 if age <= 30 else 16 if age <= 35 else 15 if age <= 40 else 14 if age <= 45 else 13
    fp = 0.4 if age < 40 else 0.25
    award = round((v["inc"] * 12 * (1 + fp) * 0.75 * mult + 70000) / 1000) * 1000
    return {"mult": ("N", mult), "award": ("L", award)}


tpl("mact_death", ["age", "inc", "mult", "award", "int", "d"], _mact_death)(
    """BEFORE THE MOTOR ACCIDENT CLAIMS TRIBUNAL, [[C:c1]]. MACP No. [[R=100-2999:macp]] of [[Y:y1]]. The claimants
    are the widow and [[R=2-3:kids]] minor children of [[M:p1]], aged [[R=26-50:age]], who died on [[T:t1]] when
    his motorcycle was hit by a truck bearing registration No. MH-12-AB-[[R=1000-9999:reg]] driven rashly. The
    deceased earned [[A:inc:9000-75000]] per month. Adding [[N=40]]% or [[N=25]]% for future prospects according to age,
    deducting one-fourth for personal expenses and applying a multiplier of [[D:mult]], the Tribunal awards total
    compensation of [[D:award]] with interest at [[R=6-9:int]]% per annum from the date of the petition,
    [[T:t2]]. The insurer shall deposit the amount within [[R=30-60:d]] days.""")


def _mact_injury(v, r):
    return {"total": ("A", v["med"] + v["pain"] + r.randint(5, 40) * 10000)}


tpl("mact_injury", ["days", "med", "dis", "total", "pain", "d"], _mact_injury)(
    """BEFORE THE MOTOR ACCIDENT CLAIMS TRIBUNAL, [[C:c1]]. MACP No. [[R=100-2999:macp]] of [[Y:y1]]. The claimant
    [[M:p1]], aged [[R=19-58:age]], suffered a fracture of the right femur in an accident on [[T:t1]] involving bus
    No. TN-38-N-[[R=1000-9999:reg]]. He was hospitalised for [[R=5-30:days]] days and spent [[A:med:40000-700000]] on treatment.
    The Tribunal assesses permanent disability at [[R=10-40:dis]]% and awards [[D:total]] in total, including
    [[A:med]] towards medical expenses and [[A:pain:20000-150000]] for pain and suffering, with interest at [[R=6-9:int]]% per
    annum. The insurer shall deposit the award within [[R=30-60:d]] days of the order dated [[T:t2]].""")

AMOUNT_RANGES = {"A": (5, 9_00_000), "L": (2_00_000, 95_00_000), "K": (1_00_00_000, 40_00_00_000)}


def fill(kind, template, key_facts, derive, r, pid):
    v, ents, surf = {}, {}, {}
    toks = re.findall(r"\[\[([^\]]+)\]\]", template)
    used = set()

    def name(male):
        while True:
            n = r.choice(MALE if male else MALE + FEMALE)
            if n not in used:
                used.add(n)
                return n

    # dates first, chronological by key, 35-240 days apart, starting 2019-2023
    tkeys = sorted({t.split(":")[1] for t in toks if t.startswith("T:")})
    d0 = date(r.randint(2019, 2023), r.randint(1, 12), r.randint(1, 28))
    for k in tkeys:
        d0 += timedelta(days=r.randint(35, 240))
        v[k] = d0
    for t in toks:
        parts = t.split(":")
        kind_ = parts[0]
        if kind_.startswith("N="):
            continue
        k = parts[1]
        if k in v:
            continue
        if kind_ in ("P", "M"):
            v[k] = name(kind_ == "M")
        elif kind_ == "C":
            v[k] = r.choice(PLACES[parts[2] if len(parts) > 2 else "court"])
        elif kind_ in AMOUNT_RANGES:
            lo, hi = map(int, parts[2].split("-")) if len(parts) > 2 else AMOUNT_RANGES[kind_]
            step = {"A": 500, "L": 50_000, "K": 10_00_000}[kind_]
            v[k] = r.randrange(max(step, lo), hi, step)
        elif kind_.startswith("R="):
            lo, hi = map(int, kind_[2:].split("-"))
            v[k] = r.randint(lo, hi)
        elif kind_ == "Y":  # case-number year: year of the named date, else of the latest date
            v[k] = v[parts[2]].year if len(parts) > 2 else max(v[t] for t in tkeys).year
    derived = derive(v, r) if derive else {}
    for k, (typ, val) in derived.items():
        v[k] = val

    def render(t):
        parts = t.split(":")
        kind_ = parts[0]
        if kind_.startswith("N="):
            num = kind_[2:]
            ents.setdefault(f"n{num}", {"key": f"n{num}", "type": "number", "value": num, "surface": num})
            return num
        k = parts[1]
        typ = derived[k][0] if kind_ == "D" else kind_
        val = v[k]
        if typ in ("P", "M", "C"):
            s, et = val, "name"
        elif typ == "A":
            s, et = "₹" + inr(val), "amount"
        elif typ == "L":
            s, et = "₹" + lakh(val), "amount"
        elif typ == "K":
            s, et = f"₹{val / 1e7:.2f}".rstrip("0").rstrip(".") + " crore", "amount"
        elif typ == "T":
            s, et = f"{val.day} {MONTHS[val.month - 1]} {val.year}", "date"
        else:
            s, et = str(val), "number"
        value = val.isoformat() if typ == "T" else val
        ents.setdefault(k, {"key": k, "type": et, "value": value, "surface": s})
        return s

    text = re.sub(r"\[\[([^\]]+)\]\]", lambda m: render(m.group(1)), template)
    return {"id": pid, "type": kind, "text": text, "entities": list(ents.values()), "key_facts": key_facts}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    r = random.Random(909)
    rows = []
    for i in range(40):
        kind, template, kf, derive = T[i % len(T)]
        rows.append(fill(kind, template, kf, derive, r, f"legal_{i + 1:02d}"))
    for p in rows:
        assert len(p["text"]) <= 1000, (p["id"], len(p["text"]))  # mayura:v1 input limit is 1000 chars
        keys = {e["key"] for e in p["entities"]}
        assert set(p["key_facts"]) <= keys, (p["id"], set(p["key_facts"]) - keys)
    with open(OUT / "passages.jsonl", "w") as f:
        for p in rows:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(len(rows), "passages; max chars", max(len(p["text"]) for p in rows),
          "; entities", sum(len(p["entities"]) for p in rows))


if __name__ == "__main__":
    main()
