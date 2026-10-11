"""Generate the synthetic UC03 document set: 60 pages in 8 Indian scripts, clean + phone-photo versions.

Every person, ID, GSTIN, PAN, survey number and amount is fake and every page carries a SAMPLE mark.
Layout is written as JSON specs and rendered by render.swift (CoreText), because Pillow here has no
libraqm and would mis-shape Indic conjuncts. Pillow is used only for the phone-photo degradation.

Outputs (data/uc03_documents/):
  pages/<id>.spec.json, pages/<id>.png   clean render (1240x1754, ~150 dpi A4)
  pages/<id>_photo.jpg                   degraded "phone photo"
  gold.jsonl                             {id, doc_type, lang, script, fields{...}, text}
Run:  .venv/bin/python suites/uc03_documents/make_data.py
"""
import json, random, subprocess, sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "uc03_documents"
PAGES = OUT / "pages"
W, H = 1240, 1754

FONT = {"hi": "KohinoorDevanagari-Regular", "mr": "ITFDevanagariMarathi-Book", "ta": "TamilSangamMN",
        "bn": "KohinoorBangla-Regular", "kn": "NotoSansKannada-Regular", "te": "KohinoorTelugu-Regular",
        "gu": "KohinoorGujarati-Regular", "ml": "MalayalamSangamMN"}
BOLD = {"hi": "KohinoorDevanagari-Semibold", "mr": "ITFDevanagariMarathi-Demi", "ta": "TamilSangamMN-Bold",
        "bn": "KohinoorBangla-Semibold", "kn": "NotoSansKannada-SemiBold", "te": "KohinoorTelugu-Semibold",
        "gu": "KohinoorGujarati-Semibold", "ml": "MalayalamSangamMN-Bold"}
SCRIPT = {"hi": "Devanagari", "mr": "Devanagari", "ta": "Tamil", "bn": "Bengali", "kn": "Kannada",
          "te": "Telugu", "gu": "Gujarati", "ml": "Malayalam"}
LAT, LATB, HAND = "Helvetica", "Helvetica-Bold", "Noteworthy-Light"
DIGIT0 = {"mr": 0x0966, "hi": 0x0966}


def native(s, lang):
    z = DIGIT0[lang]
    return "".join(chr(z + int(c)) if c.isdigit() else c for c in s)


class Page:
    def __init__(self):
        self.items, self.text = [], []  # text = (y, x, string) for the gold transcript

    def t(self, x, y, v, s=24, f=LAT, a="l"):
        self.items.append({"t": "text", "x": x, "y": y, "v": v, "s": s, "f": f, "a": a})
        # approximate left edge for reading order of right/centre aligned text
        self.text.append((y, x - (len(v) * s * 0.5 if a == "r" else len(v) * s * 0.25 if a == "c" else 0), v))

    def rect(self, x, y, w, h, lw=1, fill=None):
        it = {"t": "rect", "x": x, "y": y, "w": w, "h": h, "lw": lw}
        if fill:
            it["fill"] = fill
        self.items.append(it)

    def line(self, x1, y1, x2, y2, lw=1):
        self.items.append({"t": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "lw": lw})

    def sample_mark(self):
        self.t(W - 40, 20, "SAMPLE — SYNTHETIC TEST DOCUMENT", 18, LATB, "r")

    def gold_text(self):
        rows = []
        for y, x, v in sorted(self.text):
            if rows and abs(rows[-1][0] - y) <= 8:
                rows[-1][1].append((x, v))
            else:
                rows.append([y, [(x, v)]])
        return "\n".join(" ".join(v for _, v in sorted(r[1])) for r in rows)


def money(x):  # Indian grouping, 2 decimals: 1234567.5 -> 12,34,567.50
    i, d = f"{x:.2f}".split(".")
    head, tail = i[:-3], i[-3:]
    while len(head) > 2:
        tail = head[-2:] + "," + tail
        head = head[:-2]
    return (head + "," + tail if head else tail) + "." + d


def date(r, y0=2024, y1=2026):
    return f"{r.randint(1, 28):02d}/{r.randint(1, 12):02d}/{r.randint(y0, y1)}"


# ---------- fake IDs ----------
B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def fake_pan(r, kind="P"):
    L = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return "".join(r.choice(L) for _ in range(3)) + kind + r.choice(L) + f"{r.randint(1000, 9999)}" + r.choice(L)


def fake_gstin(r, state):
    base = f"{state:02d}" + fake_pan(r, r.choice("CFP")) + str(r.randint(1, 9)) + "Z"
    tot = 0
    for i, ch in enumerate(base):  # standard GSTIN mod-36 check digit, so it is well-formed but fake
        p = B36.index(ch) * (2 if i % 2 else 1)
        tot += p // 36 + p % 36
    return base + B36[(36 - tot % 36) % 36]


# ---------- names & places (all invented) ----------
NAMES = {
    "hi": ["राजेश शर्मा", "सुनीता वर्मा", "अमित गुप्ता", "प्रिया सिंह", "विकास यादव", "नेहा अग्रवाल",
           "संजय मिश्रा", "पूजा तिवारी", "अनिल चौहान", "कविता जोशी", "रामप्रसाद पांडे", "गीता देवी"],
    "mr_first": ["प्रकाश", "सुरेश", "विठ्ठल", "ज्ञानेश्वर", "संगीता", "मंगल", "दत्तात्रय", "शालिनी",
                 "बाळासाहेब", "रखमाबाई", "नामदेव", "सखाराम"],
    "mr_last": ["पाटील", "जाधव", "शिंदे", "कुलकर्णी", "देशमुख", "पवार", "गायकवाड", "भोसले", "चव्हाण", "कांबळे"],
    "ta": ["முருகன்", "செல்வி", "ராமசாமி", "லட்சுமி", "கார்த்திகேயன்", "மீனாட்சி", "சுப்பிரமணியன்", "வள்ளி",
           "பழனிசாமி", "அன்பழகன்", "சரஸ்வதி", "ஆறுமுகம்"],
    "kn": ["ರಮೇಶ್ ಗೌಡ", "ಸುಮಾ ಹೆಗಡೆ", "ಮಂಜುನಾಥ ಶೆಟ್ಟಿ", "ಲಕ್ಷ್ಮೀ ನಾಯಕ್", "ಪ್ರಕಾಶ್ ರಾವ್", "ಗೀತಾ ಭಟ್",
           "ಶಿವಕುಮಾರ್ ಕೆ", "ನಾಗರಾಜ ಎಸ್"],
    "te": ["వెంకటేశ్వర రావు", "లక్ష్మి దేవి", "శ్రీనివాస్ రెడ్డి", "సరోజ కుమారి", "రామకృష్ణ ప్రసాద్",
           "పద్మావతి", "సురేష్ నాయుడు", "అనిత రాణి"],
    "bn": ["সুব্রত দাস", "মিতালী ঘোষ", "অমিত বন্দ্যোপাধ্যায়", "রুমা সেন", "প্রদীপ মণ্ডল", "শিপ্রা রায়",
           "বিশ্বজিৎ সাহা", "তাপস চক্রবর্তী", "অনিমা পাল", "গৌতম বিশ্বাস"],
    "en": ["Ramesh Kumar Yadav", "Sunita Devi", "Arjun Menon", "Fathima Beevi", "Joseph Varghese",
           "Priya Nair", "Mohammed Rafeeq", "Kavita Joshi", "Suresh Pillai", "Anjali Sharma", "Vikram Singh",
           "Lakshmi Iyer", "Deepak Chauhan", "Meera Krishnan"],
}


# ---------- 1. GST tax invoice (bilingual) ----------
GST = {
    "hi": dict(title="कर बीजक", seller="विक्रेता", buyer="क्रेता", inv="बीजक संख्या", date="दिनांक",
               pos="आपूर्ति का स्थान", sno="क्र.", desc="वस्तु का विवरण", qty="मात्रा", rate="दर",
               taxable="कर योग्य मूल्य", total="कुल देय राशि", foot="यह कंप्यूटर जनित बीजक है",
               items=[("बासमती चावल (25 किग्रा)", "1006", 5), ("गेहूं का आटा (10 किग्रा)", "1101", 5),
                      ("सरसों का तेल (15 लीटर)", "1514", 5), ("चीनी (50 किग्रा)", "1701", 5),
                      ("स्टील की अलमारी", "9403", 18), ("प्लास्टिक कुर्सी", "9401", 18),
                      ("सूती कपड़ा (मीटर)", "5208", 5), ("एलईडी बल्ब 9W", "8539", 12)],
               firms=["श्री गणेश ट्रेडर्स", "महालक्ष्मी एंटरप्राइजेज", "शर्मा जनरल स्टोर्स", "बालाजी होलसेल मार्ट",
                      "गंगा किराना भंडार", "न्यू भारत फर्नीचर"],
               states=[(9, "Uttar Pradesh"), (8, "Rajasthan"), (23, "Madhya Pradesh")]),
    "gu": dict(title="કર ભરતિયું", seller="વેચનાર", buyer="ખરીદનાર", inv="ભરતિયા નંબર", date="તારીખ",
               pos="પુરવઠાનું સ્થળ", sno="ક્રમ", desc="વસ્તુનું વર્ણન", qty="જથ્થો", rate="દર",
               taxable="કરપાત્ર કિંમત", total="કુલ ચૂકવવાપાત્ર રકમ", foot="આ કમ્પ્યુટર દ્વારા બનાવેલ ભરતિયું છે",
               items=[("ચોખા (25 કિલો)", "1006", 5), ("ઘઉંનો લોટ (10 કિલો)", "1101", 5),
                      ("મગફળીનું તેલ (15 લિટર)", "1508", 5), ("ખાંડ (50 કિલો)", "1701", 5),
                      ("સ્ટીલનું કબાટ", "9403", 18), ("પ્લાસ્ટિક ખુરશી", "9401", 18),
                      ("સુતરાઉ કાપડ (મીટર)", "5208", 5), ("એલઇડી બલ્બ 9W", "8539", 12)],
               firms=["જય અંબે ટ્રેડર્સ", "પટેલ એન્ટરપ્રાઇઝ", "શ્રીજી ટેક્સટાઇલ્સ", "ગોકુલ કિરાણા સ્ટોર"],
               states=[(24, "Gujarat")]),
    "ta": dict(title="வரி விலைப்பட்டியல்", seller="விற்பனையாளர்", buyer="வாங்குபவர்", inv="விலைப்பட்டியல் எண்",
               date="தேதி", pos="வழங்கல் இடம்", sno="வ.எண்", desc="பொருள் விவரம்", qty="அளவு", rate="விலை",
               taxable="வரிக்குட்பட்ட மதிப்பு", total="மொத்தம் செலுத்த வேண்டியது",
               foot="இது கணினி மூலம் உருவாக்கப்பட்ட விலைப்பட்டியல்",
               items=[("பொன்னி அரிசி (25 கிலோ)", "1006", 5), ("கோதுமை மாவு (10 கிலோ)", "1101", 5),
                      ("நல்லெண்ணெய் (15 லிட்டர்)", "1515", 5), ("சர்க்கரை (50 கிலோ)", "1701", 5),
                      ("எஃகு அலமாரி", "9403", 18), ("பிளாஸ்டிக் நாற்காலி", "9401", 18),
                      ("பருத்தி துணி (மீட்டர்)", "5208", 5), ("எல்இடி விளக்கு 9W", "8539", 12)],
               firms=["ஸ்ரீ முருகன் டிரேடர்ஸ்", "லட்சுமி ஸ்டோர்ஸ்", "அண்ணாமலை எண்டர்பிரைசஸ்", "காவேரி மொத்த வியாபாரம்"],
               states=[(33, "Tamil Nadu")]),
}
OTHER_STATES = [(27, "Maharashtra"), (29, "Karnataka"), (7, "Delhi"), (19, "West Bengal")]


def gst_invoice(r, lang):
    L, p = GST[lang], Page()
    F, FB = FONT[lang], BOLD[lang]
    st_code, st_name = r.choice(L["states"])
    inter = r.random() < 0.35
    b_code, b_name = r.choice(OTHER_STATES) if inter else (st_code, st_name)
    seller, buyer = r.sample(L["firms"], 2)
    s_gstin, b_gstin = fake_gstin(r, st_code), fake_gstin(r, b_code)
    inv_no = f"{r.choice(['INV', 'GST', 'TI'])}/{r.choice(['24-25', '25-26'])}/{r.randint(1, 999):04d}"
    d = date(r)
    p.sample_mark()
    p.t(W / 2, 60, L["title"], 40, FB, "c")
    p.t(W / 2, 115, "TAX INVOICE", 26, LATB, "c")
    p.rect(60, 170, 1120, 250)
    p.line(620, 170, 620, 420)
    p.t(80, 185, f"{L['seller']} / Seller", 22, FB)
    p.t(80, 225, seller, 28, FB)
    p.t(80, 270, f"{r.randint(1, 250)}, Main Market Road, {st_name}", 20)
    p.t(80, 310, f"GSTIN: {s_gstin}", 22, LATB)
    p.t(640, 185, f"{L['buyer']} / Buyer", 22, FB)
    p.t(640, 225, buyer, 28, FB)
    p.t(640, 270, f"Shop {r.randint(1, 99)}, Station Road, {b_name}", 20)
    p.t(640, 310, f"GSTIN: {b_gstin}", 22, LATB)
    p.t(80, 360, f"{L['inv']} / Invoice No.: {inv_no}", 22, F)
    p.t(640, 360, f"{L['date']} / Date: {d}", 22, F)
    p.t(80, 445, f"{L['pos']} / Place of Supply: {b_name} ({b_code:02d})", 22, F)
    # items table
    cols = [60, 130, 560, 680, 790, 930, 1180]
    y0 = 500
    p.rect(60, y0, 1120, 60, fill=[230, 230, 230])
    heads = [f"{L['sno']}", f"{L['desc']}", "HSN", f"{L['qty']}", f"{L['rate']} (₹)", f"{L['taxable']} (₹)"]
    for i, h in enumerate(heads):
        p.t(cols[i] + 8, y0 + 15, h, 18, FB)
    items = r.sample(L["items"], r.randint(2, 4))
    y = y0 + 60
    taxable_total, tax_total = 0.0, 0.0
    rates = []
    for k, (desc, hsn, rate) in enumerate(items, 1):
        qty = r.randint(2, 40)
        price = round(r.uniform(80, 4500), 0)
        amt = qty * price
        taxable_total += amt
        tax_total += round(amt * rate / 100, 2)
        rates.append(rate)
        p.rect(60, y, 1120, 52)
        p.t(cols[0] + 15, y + 13, str(k), 20)
        p.t(cols[1] + 8, y + 10, f"{desc} @{rate}%", 21, F)
        p.t(cols[2] + 8, y + 13, hsn, 20)
        p.t(cols[3] + 8, y + 13, str(qty), 20)
        p.t(cols[5] - 12, y + 13, money(price), 20, LAT, "r")
        p.t(cols[6] - 12, y + 13, money(amt), 20, LAT, "r")
        y += 52
    for c in cols[1:-1]:
        p.line(c, y0, c, y)
    tax_total = round(tax_total, 2)
    cgst = sgst = igst = 0.0
    y += 30
    lines = [(f"{L['taxable']} / Taxable Value", taxable_total)]
    if inter:
        igst = tax_total
        lines.append(("IGST", igst))
    else:
        cgst = sgst = round(tax_total / 2, 2)
        lines += [("CGST", cgst), ("SGST", sgst)]
    grand = round(taxable_total + cgst + sgst + igst, 2)
    lines.append((f"{L['total']} / Grand Total", grand))
    for lab, v in lines:
        bold = "Grand" in lab
        p.t(420, y, lab, 22, FB if bold else F)
        p.t(1170, y, "₹ " + money(v), 22, LATB if bold else LAT, "r")
        y += 44
    p.t(80, y + 60, f"{L['foot']} / This is a computer generated invoice.", 18, F)
    p.t(900, y + 160, "Authorised Signatory", 20, LAT)
    fields = {"invoice_number": inv_no, "invoice_date": d, "seller_name": seller, "seller_gstin": s_gstin,
              "buyer_name": buyer, "buyer_gstin": b_gstin, "place_of_supply_state": b_name,
              "first_item_hsn": items[0][1], "item_count": str(len(items)),
              "taxable_value": money(taxable_total), "cgst_amount": money(cgst), "sgst_amount": money(sgst),
              "igst_amount": money(igst), "grand_total": money(grand)}
    return p, fields


GST_SCHEMA = {
    "invoice_number": "invoice number as printed", "invoice_date": "invoice date DD/MM/YYYY",
    "seller_name": "seller firm name, in the script printed", "seller_gstin": "seller GSTIN",
    "buyer_name": "buyer firm name, in the script printed", "buyer_gstin": "buyer GSTIN",
    "place_of_supply_state": "place of supply state name in English", "first_item_hsn": "HSN code of line item 1",
    "item_count": "number of line items", "taxable_value": "total taxable value (number)",
    "cgst_amount": "total CGST amount (0 if none)", "sgst_amount": "total SGST amount (0 if none)",
    "igst_amount": "total IGST amount (0 if none)", "grand_total": "grand total payable (number)"}


# ---------- 2. KYC / account opening form (Indic labels, handwritten-style English entries) ----------
KYC = {
    "hi": dict(title="खाता खोलने का फॉर्म", name="ग्राहक का नाम", father="पिता/पति का नाम", dob="जन्म तिथि",
               gender="लिंग", pan="पैन", aadhaar="आधार (अंतिम 4 अंक)", mobile="मोबाइल नंबर", addr="पता",
               pin="पिन कोड", acct="खाते का प्रकार", occ="व्यवसाय", income="वार्षिक आय", nominee="नामांकित व्यक्ति",
               sign="ग्राहक के हस्ताक्षर"),
    "ml": dict(title="അക്കൗണ്ട് തുറക്കൽ ഫോം", name="ഉപഭോക്താവിന്റെ പേര്", father="അച്ഛന്റെ/ഭർത്താവിന്റെ പേര്",
               dob="ജനന തീയതി", gender="ലിംഗം", pan="പാൻ", aadhaar="ആധാർ (അവസാന 4 അക്കങ്ങൾ)", mobile="മൊബൈൽ നമ്പർ",
               addr="വിലാസം", pin="പിൻ കോഡ്", acct="അക്കൗണ്ട് തരം", occ="തൊഴിൽ", income="വാർഷിക വരുമാനം",
               nominee="നോമിനി", sign="ഉപഭോക്താവിന്റെ ഒപ്പ്"),
}
CITIES = {"hi": [("Lucknow", "226001"), ("Varanasi", "221002"), ("Jaipur", "302001"), ("Indore", "452001")],
          "ml": [("Kochi", "682011"), ("Thrissur", "680001"), ("Kozhikode", "673001"), ("Kollam", "691001")]}


def kyc_form(r, lang):
    L, p = KYC[lang], Page()
    F, FB = FONT[lang], BOLD[lang]
    name, father, nominee = r.sample(NAMES["en"], 3)
    gender = r.choice(["Male", "Female"])
    dob = date(r, 1960, 2002)
    pan = fake_pan(r)
    aad = f"{r.randint(1000, 9999)}"
    mob = f"{r.choice('6789')}{r.randint(100000000, 999999999)}"
    city, pin = r.choice(CITIES[lang])
    acct = r.choice(["Savings", "Current"])
    occ = r.choice(["Farmer", "Teacher", "Shopkeeper", "Driver", "Nurse", "Tailor"])
    income = money(r.choice([1.8, 2.4, 3.6, 4.8, 6.0, 7.2]) * 100000).replace(".00", "")
    p.sample_mark()
    p.t(W / 2, 60, "SAMPLE CO-OPERATIVE BANK LTD. (fictitious)", 26, LATB, "c")
    p.t(W / 2, 110, L["title"], 34, FB, "c")
    p.t(W / 2, 160, "ACCOUNT OPENING FORM — KYC (Individual)", 22, LATB, "c")
    rows = [(L["name"], "Customer Name", name), (L["father"], "Father's / Spouse Name", father),
            (L["dob"], "Date of Birth", dob), (L["gender"], "Gender", gender), (L["pan"], "PAN", pan),
            (L["aadhaar"], "Aadhaar (last 4)", "XXXX XXXX " + aad), (L["mobile"], "Mobile No.", mob),
            (L["addr"], "Address", f"H.No. {r.randint(1, 400)}, Ward {r.randint(1, 30)}, {city}"),
            (L["pin"], "PIN Code", pin), (L["acct"], "Account Type", acct), (L["occ"], "Occupation", occ),
            (L["income"], "Annual Income (₹)", income), (L["nominee"], "Nominee", nominee)]
    y = 230
    for lab, en, val in rows:
        p.rect(60, y, 1120, 82)
        p.line(520, y, 520, y + 82)
        p.t(75, y + 8, lab, 22, F)
        p.t(75, y + 46, en, 17, LAT)
        p.t(540 + r.randint(0, 20), y + 18 + r.randint(-4, 4), val, 34, HAND)
        y += 82
    p.t(75, y + 80, f"{L['sign']} / Signature of Customer", 20, F)
    p.t(700, y + 70, name.split()[0], 40, HAND)
    p.t(75, y + 140, "Date: " + date(r, 2025, 2026), 20, LAT)
    fields = {"customer_name": name, "father_or_spouse_name": father, "date_of_birth": dob, "gender": gender,
              "pan": pan, "aadhaar_last4": aad, "mobile": mob, "city": city, "pin_code": pin,
              "account_type": acct, "occupation": occ, "annual_income": income, "nominee_name": nominee}
    return p, fields


KYC_SCHEMA = {"customer_name": "customer name", "father_or_spouse_name": "father's or spouse name",
              "date_of_birth": "DD/MM/YYYY", "gender": "Male/Female", "pan": "PAN",
              "aadhaar_last4": "last 4 digits of Aadhaar", "mobile": "mobile number", "city": "city in address",
              "pin_code": "PIN code", "account_type": "Savings/Current", "occupation": "occupation",
              "annual_income": "annual income (number)", "nominee_name": "nominee name"}


# ---------- 3. Maharashtra 7/12 extract (Marathi, Devanagari digits) ----------
MR_PLACES = [("पुणे", "हवेली", ["वडगाव", "लोणी काळभोर", "उरुळी कांचन"]), ("पुणे", "शिरूर", ["रांजणगाव", "कारेगाव"]),
             ("सातारा", "कराड", ["उंब्रज", "मसूर"]), ("नाशिक", "निफाड", ["पिंपळगाव", "ओझर"]),
             ("अहमदनगर", "राहुरी", ["देवळाली", "टाकळीमिया"])]


def seven_twelve(r, lang="mr"):
    p, F, FB = Page(), FONT["mr"], BOLD["mr"]
    n = lambda s: native(s, "mr")
    dist, tal, villages = r.choice(MR_PLACES)
    vil = r.choice(villages)
    survey = f"{r.randint(12, 480)}/{r.randint(1, 6)}{r.choice(['', 'अ', 'ब'])}"
    owner = f"{r.choice(NAMES['mr_last'])} {r.choice(NAMES['mr_first'])} {r.choice(NAMES['mr_first'])}"
    area = f"{r.randint(0, 3)}.{r.randint(5, 99):02d}.{r.choice([0, 0, 50, 20]):02d}"
    assess = f"{r.randint(1, 15)}.{r.randint(0, 99):02d}"
    mut = str(r.randint(150, 4800))
    year = r.choice(["2024-25", "2025-26"])
    season = r.choice(["खरीप", "रब्बी"])
    crop = r.choice({"खरीप": ["सोयाबीन", "कापूस", "बाजरी", "ऊस"], "रब्बी": ["गहू", "ज्वारी", "हरभरा", "कांदा"]}[season])
    src = r.choice(["विहीर", "कालवा", "कूपनलिका"])
    p.sample_mark()
    p.t(W / 2, 60, "नमुना प्रत — SAMPLE (बनावट माहिती)", 22, FB, "c")
    p.t(W / 2, 100, "गाव नमुना सात", 36, FB, "c")
    p.t(W / 2, 150, "(अधिकार अभिलेख पत्रक)", 24, F, "c")
    p.t(80, 210, f"गाव : {vil}", 26, F)
    p.t(480, 210, f"तालुका : {tal}", 26, F)
    p.t(860, 210, f"जिल्हा : {dist}", 26, F)
    p.rect(60, 260, 1120, 520)
    p.line(500, 260, 500, 780)
    p.t(80, 280, f"भूमापन क्रमांक : {n(survey)}", 26, FB)
    p.t(80, 330, "भूधारणा पद्धती : भोगवटादार वर्ग -१", 22, F)
    p.t(80, 380, "क्षेत्र (हे.आर.चौ.मी.)", 22, F)
    p.t(80, 420, f"जिरायत : {n(area)}", 24, F)
    p.t(80, 470, f"आकारणी (रु.पै.) : {n(assess)}", 24, F)
    p.t(80, 520, "पोटखराब : —", 22, F)
    p.t(520, 280, "भोगवटादाराचे नाव", 24, FB)
    p.t(520, 330, owner, 28, F)
    p.t(520, 380, f"({n(mut)})", 24, F)
    p.t(520, 450, "इतर अधिकार : —", 22, F)
    p.t(520, 500, f"फेरफार क्रमांक : {n(mut)}", 24, F)
    p.t(W / 2, 820, "गाव नमुना बारा", 34, FB, "c")
    p.t(W / 2, 865, "(पिकांची नोंदवही)", 22, F, "c")
    cols = [60, 250, 420, 700, 930, 1180]
    hs = ["वर्ष", "हंगाम", "पिकाचे नाव", "क्षेत्र (हे.आर)", "जलसिंचनाचे साधन"]
    p.rect(60, 920, 1120, 60, fill=[235, 235, 235])
    p.rect(60, 980, 1120, 60)
    for i, h in enumerate(hs):
        p.t(cols[i] + 10, 935, h, 20, FB)
    crop_area = area.rsplit(".", 1)[0]
    for i, v in enumerate([n(year), season, crop, n(crop_area), src]):
        p.t(cols[i] + 10, 993, v, 22, F)
    for c in cols[1:-1]:
        p.line(c, 920, c, 1040)
    p.t(80, 1120, f"दिनांक : {n(date(r, 2025, 2026))}", 22, F)
    p.t(800, 1200, "तलाठी (नमुना)", 24, F)
    fields = {"village": vil, "taluka": tal, "district": dist, "survey_number": survey, "occupant_name": owner,
              "area_hectare": area, "assessment_rupees": assess, "mutation_number": mut, "crop_year": year,
              "season": season, "crop_name": crop, "irrigation_source": src}
    return p, fields


SEVEN_TWELVE_SCHEMA = {"village": "गाव", "taluka": "तालुका", "district": "जिल्हा",
                       "survey_number": "भूमापन क्रमांक", "occupant_name": "भोगवटादाराचे नाव (full name)",
                       "area_hectare": "क्षेत्र हे.आर.चौ.मी. e.g. 0.45.00", "assessment_rupees": "आकारणी",
                       "mutation_number": "फेरफार क्रमांक", "crop_year": "वर्ष of crop record e.g. 2025-26",
                       "season": "हंगाम", "crop_name": "पिकाचे नाव", "irrigation_source": "जलसिंचनाचे साधन"}


# ---------- 4. Tamil Nadu patta / chitta extract (Tamil) ----------
TA_PLACES = [("மதுரை", ["மேலூர்", "திருமங்கலம்"]), ("சேலம்", ["ஆத்தூர்", "ஓமலூர்"]),
             ("திருநெல்வேலி", ["அம்பாசமுத்திரம்", "நாங்குநேரி"]), ("தஞ்சாவூர்", ["கும்பகோணம்", "பாபநாசம்"]),
             ("ஈரோடு", ["கோபிச்செட்டிபாளையம்", "பவானி"])]
TA_VILLAGES = ["அய்யம்பட்டி", "கீழையூர்", "வடகரை", "புதூர்", "சின்னக்குளம்", "மேலப்பாளையம்", "கோவில்பட்டி"]


def patta(r, lang="ta"):
    p, F, FB = Page(), FONT["ta"], BOLD["ta"]
    dist, taluks = r.choice(TA_PLACES)
    tk, vil = r.choice(taluks), r.choice(TA_VILLAGES)
    owner, father = r.sample(NAMES["ta"], 2)
    pno = str(r.randint(12, 2900))
    sv, sub = str(r.randint(5, 640)), f"{r.randint(1, 9)}{r.choice(['', 'A', 'B'])}"
    ltype = r.choice(["நன்செய்", "புன்செய்"])
    ext = f"{r.randint(0, 2)}.{r.randint(5, 99):02d}.{r.choice([0, 50, 25]):02d}"
    tax = f"{r.randint(2, 60)}.{r.randint(0, 99):02d}"
    d = date(r, 2024, 2026)
    p.sample_mark()
    p.t(W / 2, 60, "மாதிரி ஆவணம் — SAMPLE (கற்பனை விவரங்கள்)", 22, FB, "c")
    p.t(W / 2, 110, "பட்டா / சிட்டா", 38, FB, "c")
    p.t(W / 2, 165, "(நில உரிமை பதிவேடு சாறு)", 22, F, "c")
    rows = [("மாவட்டம்", dist), ("வட்டம்", tk), ("வருவாய் கிராமம்", vil), ("பட்டா எண்", pno)]
    y = 230
    for lab, v in rows:
        p.t(100, y, f"{lab} :", 26, F)
        p.t(500, y, v, 26, FB)
        y += 50
    y += 20
    p.t(100, y, "உரிமையாளர் பெயர்", 24, FB)
    p.t(100, y + 45, f"1. {owner}  —  தந்தை பெயர் : {father}", 26, F)
    y += 130
    cols = [60, 230, 400, 640, 880, 1180]
    hs = ["புல எண்", "உட்பிரிவு", "நிலவகை", "பரப்பு (ஹெ-ஏ)", "தீர்வை (ரூ)"]
    p.rect(60, y, 1120, 60, fill=[235, 235, 235])
    p.rect(60, y + 60, 1120, 60)
    for i, h in enumerate(hs):
        p.t(cols[i] + 10, y + 15, h, 20, FB)
    for i, v in enumerate([sv, sub, ltype, ext, tax]):
        p.t(cols[i] + 10, y + 75, v, 23, F)
    for c in cols[1:-1]:
        p.line(c, y, c, y + 120)
    y += 190
    p.t(100, y, f"வழங்கிய தேதி : {d}", 24, F)
    p.t(780, y + 90, "வட்டாட்சியர் (மாதிரி)", 24, F)
    fields = {"district": dist, "taluk": tk, "village": vil, "patta_number": pno, "owner_name": owner,
              "father_name": father, "survey_number": sv, "subdivision": sub, "land_type": ltype,
              "extent_hectare": ext, "tax_rupees": tax, "issue_date": d}
    return p, fields


PATTA_SCHEMA = {"district": "மாவட்டம்", "taluk": "வட்டம்", "village": "வருவாய் கிராமம்", "patta_number": "பட்டா எண்",
                "owner_name": "உரிமையாளர் பெயர்", "father_name": "தந்தை பெயர்", "survey_number": "புல எண்",
                "subdivision": "உட்பிரிவு", "land_type": "நிலவகை", "extent_hectare": "பரப்பு e.g. 0.45.50",
                "tax_rupees": "தீர்வை", "issue_date": "வழங்கிய தேதி DD/MM/YYYY"}


# ---------- 5. Electricity bill (Kannada / Telugu) ----------
EB = {
    "kn": dict(co="ಮಾದರಿ ವಿದ್ಯುತ್ ಸರಬರಾಜು ಕಂಪನಿ (ಕಾಲ್ಪನಿಕ)", title="ವಿದ್ಯುತ್ ಬಿಲ್ಲು", name="ಗ್ರಾಹಕರ ಹೆಸರು",
               acct="ಖಾತೆ ಸಂಖ್ಯೆ", bill="ಬಿಲ್ ಸಂಖ್ಯೆ", bdate="ಬಿಲ್ ದಿನಾಂಕ", due="ಪಾವತಿ ಕೊನೆಯ ದಿನಾಂಕ",
               tariff="ದರಪಟ್ಟಿ", prev="ಹಿಂದಿನ ರೀಡಿಂಗ್", pres="ಪ್ರಸ್ತುತ ರೀಡಿಂಗ್", units="ಬಳಸಿದ ಯೂನಿಟ್‌ಗಳು",
               fixed="ಸ್ಥಿರ ಶುಲ್ಕ", energy="ವಿದ್ಯುತ್ ಶುಲ್ಕ", tax="ತೆರಿಗೆ", pay="ಪಾವತಿಸಬೇಕಾದ ಮೊತ್ತ",
               note="ದಯವಿಟ್ಟು ಕೊನೆಯ ದಿನಾಂಕದೊಳಗೆ ಪಾವತಿಸಿ", city=["ಮೈಸೂರು", "ಹುಬ್ಬಳ್ಳಿ", "ತುಮಕೂರು"]),
    "te": dict(co="నమూనా విద్యుత్ పంపిణీ సంస్థ (కల్పితం)", title="విద్యుత్ బిల్లు", name="వినియోగదారుని పేరు",
               acct="సర్వీస్ నంబర్", bill="బిల్లు నంబర్", bdate="బిల్లు తేదీ", due="చెల్లింపు గడువు తేదీ",
               tariff="కేటగిరీ", prev="గత రీడింగ్", pres="ప్రస్తుత రీడింగ్", units="వినియోగించిన యూనిట్లు",
               fixed="స్థిర ఛార్జీలు", energy="ఎనర్జీ ఛార్జీలు", tax="పన్ను", pay="చెల్లించవలసిన మొత్తం",
               note="దయచేసి గడువు తేదీలోపు చెల్లించండి", city=["విజయవాడ", "గుంటూరు", "వరంగల్"]),
}


def electricity(r, lang):
    L, p = EB[lang], Page()
    F, FB = FONT[lang], BOLD[lang]
    name = r.choice(NAMES[lang])
    acct = f"{r.choice(['RR', 'SC', 'EB'])}{r.randint(1000000, 9999999)}"
    bill = str(r.randint(10 ** 9, 10 ** 10 - 1))
    m = r.randint(1, 11)
    bdate, due = f"{r.randint(1, 10):02d}/{m:02d}/2026", f"{r.randint(20, 28):02d}/{m:02d}/2026"
    prev = r.randint(1200, 48000)
    units = r.randint(45, 420)
    pres = prev + units
    fixed = float(r.choice([110, 125, 140, 160]))
    energy = round(min(units, 100) * 4.75 + max(0, units - 100) * 7.0, 2)
    tax = round(energy * 0.09, 2)
    pay = round(fixed + energy + tax, 2)
    tariff = r.choice(["LT-1", "LT-2(a)"])
    p.sample_mark()
    p.t(W / 2, 60, L["co"], 30, FB, "c")
    p.t(W / 2, 115, f"{L['title']} / ELECTRICITY BILL", 30, FB, "c")
    p.t(W / 2, 165, f"{r.choice(L['city'])} — SAMPLE", 22, F, "c")
    rows = [(L["name"], name), (L["acct"], acct), (L["bill"], bill), (L["bdate"], bdate), (L["due"], due),
            (L["tariff"], tariff)]
    y = 230
    p.rect(60, y - 15, 1120, len(rows) * 55 + 20)
    for lab, v in rows:
        p.t(90, y, lab, 24, F)
        p.t(560, y, v, 26, FB if lab == L["name"] else LAT)
        y += 55
    y += 50
    p.rect(60, y, 1120, 120)
    p.line(433, y, 433, y + 120)
    p.line(806, y, 806, y + 120)
    p.line(60, y + 60, 1180, y + 60)
    for i, (lab, v) in enumerate([(L["prev"], prev), (L["pres"], pres), (L["units"], units)]):
        p.t(80 + i * 373, y + 15, lab, 21, FB)
        p.t(80 + i * 373, y + 75, str(v), 26)
    y += 180
    for lab, v in [(L["fixed"], fixed), (L["energy"], energy), (L["tax"], tax)]:
        p.t(90, y, lab, 24, F)
        p.t(1150, y, "₹ " + money(v), 24, LAT, "r")
        y += 50
    p.line(60, y + 5, 1180, y + 5, 2)
    p.t(90, y + 25, L["pay"], 28, FB)
    p.t(1150, y + 25, "₹ " + money(pay), 30, LATB, "r")
    p.t(90, y + 120, L["note"], 22, F)
    fields = {"consumer_name": name, "account_number": acct, "bill_number": bill, "bill_date": bdate,
              "due_date": due, "tariff_category": tariff, "previous_reading": str(prev),
              "present_reading": str(pres), "units_consumed": str(units), "fixed_charges": money(fixed),
              "energy_charges": money(energy), "tax": money(tax), "amount_payable": money(pay)}
    return p, fields


EB_SCHEMA = {"consumer_name": "consumer name in the script printed", "account_number": "account / service number",
             "bill_number": "bill number", "bill_date": "DD/MM/YYYY", "due_date": "DD/MM/YYYY",
             "tariff_category": "tariff category code", "previous_reading": "previous meter reading",
             "present_reading": "present meter reading", "units_consumed": "units consumed",
             "fixed_charges": "fixed charges amount", "energy_charges": "energy charges amount", "tax": "tax amount",
             "amount_payable": "total amount payable"}


# ---------- 6. Ration card (Bengali / Hindi) ----------
RC = {
    "bn": dict(title="রেশন কার্ড", card="কার্ড নম্বর", cat="শ্রেণী",
               cats={"AAY": "অন্ত্যোদয় অন্ন যোজনা (AAY)", "PHH": "অগ্রাধিকার পরিবার (PHH)"},
               head="পরিবারের প্রধানের নাম", father="পিতা/স্বামীর নাম", dist="জেলা", block="ব্লক",
               fps="ন্যায্য মূল্যের দোকান নং", issue="ইস্যুর তারিখ", members="পরিবারের সদস্যগণ",
               cols=["ক্রম", "নাম", "সম্পর্ক", "বয়স"], rel=["নিজে", "স্ত্রী", "পুত্র", "কন্যা", "মা"],
               places=[("নদিয়া", "কৃষ্ণনগর-১"), ("পূর্ব বর্ধমান", "কালনা-২"), ("হুগলি", "চুঁচুড়া-মগরা"),
                       ("মুর্শিদাবাদ", "বহরমপুর")], prefix="WB"),
    "hi": dict(title="राशन कार्ड", card="कार्ड संख्या", cat="श्रेणी",
               cats={"AAY": "अंत्योदय अन्न योजना (AAY)", "PHH": "प्राथमिकता परिवार (PHH)"},
               head="परिवार के मुखिया का नाम", father="पिता/पति का नाम", dist="जिला", block="ब्लॉक",
               fps="उचित मूल्य दुकान संख्या", issue="जारी करने की तिथि", members="परिवार के सदस्य",
               cols=["क्र.", "नाम", "संबंध", "आयु"], rel=["स्वयं", "पत्नी", "पुत्र", "पुत्री", "माता"],
               places=[("वाराणसी", "चोलापुर"), ("गया", "बोधगया"), ("सीतापुर", "मिश्रिख")], prefix="UP"),
}


def ration_card(r, lang):
    L, p = RC[lang], Page()
    F, FB = FONT[lang], BOLD[lang]
    head, father, *others = r.sample(NAMES[lang], 2 + 4)
    k = r.randint(2, 5)
    members = [(head, L["rel"][0], r.randint(32, 70))] + [
        (others[i], L["rel"][min(i + 1, 4)], r.randint(4, 60)) for i in range(k - 1)]
    card = f"{L['prefix']}{r.randint(10 ** 9, 10 ** 10 - 1)}"
    cat = r.choice(["AAY", "PHH"])
    dist, block = r.choice(L["places"])
    fps = str(r.randint(100, 9999))
    d = date(r, 2018, 2025)
    p.sample_mark()
    p.t(W / 2, 70, f"{L['title']} — SAMPLE", 40, FB, "c")
    p.t(W / 2, 130, "RATION CARD (fictitious test document)", 22, LATB, "c")
    rows = [(L["card"], card), (L["cat"], L["cats"][cat]), (L["head"], head), (L["father"], father),
            (L["dist"], dist), (L["block"], block), (L["fps"], fps), (L["issue"], d)]
    y = 200
    p.rect(60, y - 15, 1120, len(rows) * 55 + 20)
    for lab, v in rows:
        p.t(90, y, lab, 23, F)
        p.t(560, y, v, 25, F if not v[:1].isascii() else LAT)
        y += 55
    y += 50
    p.t(90, y, L["members"], 26, FB)
    y += 50
    cols = [60, 170, 620, 900, 1180]
    p.rect(60, y, 1120, 55, fill=[235, 235, 235])
    for i, h in enumerate(L["cols"]):
        p.t(cols[i] + 12, y + 12, h, 21, FB)
    y0 = y
    y += 55
    for i, (nm, rel, age) in enumerate(members, 1):
        p.rect(60, y, 1120, 55)
        for j, v in enumerate([str(i), nm, rel, str(age)]):
            p.t(cols[j] + 12, y + 12, v, 22, F)
        y += 55
    for c in cols[1:-1]:
        p.line(c, y0, c, y)
    fields = {"card_number": card, "category_code": cat, "head_of_family": head,
              "father_or_husband_name": father, "district": dist, "block": block, "fps_number": fps,
              "issue_date": d, "member_count": str(len(members)), "member2_name": members[1][0],
              "member2_age": str(members[1][2])}
    return p, fields


RC_SCHEMA = {"card_number": "card number", "category_code": "AAY or PHH", "head_of_family": "head of family name",
             "father_or_husband_name": "father/husband name", "district": "district", "block": "block",
             "fps_number": "fair price shop number", "issue_date": "DD/MM/YYYY",
             "member_count": "number of family members listed", "member2_name": "name of member no. 2",
             "member2_age": "age of member no. 2"}

DOC_TYPES = {"gst_invoice": (gst_invoice, GST_SCHEMA), "kyc_form": (kyc_form, KYC_SCHEMA),
             "land_7_12": (seven_twelve, SEVEN_TWELVE_SCHEMA), "patta": (patta, PATTA_SCHEMA),
             "electricity_bill": (electricity, EB_SCHEMA), "ration_card": (ration_card, RC_SCHEMA)}
PLAN = [("gst_invoice", "hi", 5), ("gst_invoice", "gu", 4), ("gst_invoice", "ta", 3), ("kyc_form", "hi", 5),
        ("kyc_form", "ml", 5), ("land_7_12", "mr", 10), ("patta", "ta", 10), ("electricity_bill", "kn", 5),
        ("electricity_bill", "te", 5), ("ration_card", "bn", 5), ("ration_card", "hi", 3)]


# first page of every (type, language) group + a second page of the five 10-page-type groups = 16 pages
HARSH_IDS = [f"{d}_{l}_01" for d, l, _ in PLAN] + ["gst_invoice_hi_02", "kyc_form_hi_02", "land_7_12_mr_02",
                                                  "patta_ta_02", "electricity_bill_kn_02"]

# ---------- phone-photo degradation ----------
def phone_photo(png, out, seed, harsh=False):
    """harsh=True: a bad photo (stronger tilt/skew, a hand shadow, sensor noise, low resolution, JPEG q~25)."""
    r = random.Random(seed + ("/harsh" if harsh else ""))
    im = Image.open(png).convert("RGB")
    w, h = im.size
    pad = 60  # page lying on a darker table
    bg = Image.new("RGB", (w + 2 * pad, h + 2 * pad), tuple(r.randint(90, 140) for _ in range(3)))
    bg.paste(im, (pad, pad))
    im = bg.rotate(r.uniform(-6, 6) if harsh else r.uniform(-3, 3), resample=Image.BICUBIC, fillcolor=(110, 105, 100))
    W2, H2 = im.size
    j = lambda: r.uniform(0, 110 if harsh else 45)  # perspective: jitter the four source corners
    quad = (j(), j(), j(), H2 - j(), W2 - j(), H2 - j(), W2 - j(), j())
    im = im.transform((W2, H2), Image.QUAD, quad, resample=Image.BICUBIC)
    # uneven lighting: brightness gradient from one corner + slight warm cast
    grad = Image.linear_gradient("L").resize((W2, H2)).rotate(r.choice([0, 90, 180, 270]))
    lo = 95 if harsh else 150
    grad = grad.point(lambda v: int(lo + v * (255 - lo) / 255))
    im = Image.composite(im, Image.new("RGB", im.size, (0, 0, 0)), grad)
    if harsh:  # a diagonal hand/phone shadow band and sensor noise
        x0 = r.randint(0, W2 // 2)
        shade = Image.new("L", im.size, 255)
        ImageDraw.Draw(shade).polygon([(x0, 0), (x0 + W2 // 3, 0), (x0 + W2 // 2, H2), (x0 + W2 // 6, H2)], fill=150)
        shade = shade.filter(ImageFilter.GaussianBlur(40))
        im = Image.composite(im, Image.new("RGB", im.size, (0, 0, 0)), shade)
        noise = Image.effect_noise(im.size, 40).convert("RGB")
        im = Image.blend(im, noise, 0.12)
    im = ImageEnhance.Color(im).enhance(0.85)
    im = im.filter(ImageFilter.GaussianBlur(r.uniform(1.6, 2.1) if harsh else r.uniform(0.9, 1.5)))
    k = 0.55 if harsh else 0.8
    im = im.resize((int(W2 * k), int(H2 * k)), Image.BILINEAR)
    im.save(out, "JPEG", quality=r.randint(22, 30) if harsh else r.randint(40, 55))


def main():
    PAGES.mkdir(parents=True, exist_ok=True)
    r = random.Random(2026)
    golds = []
    for dtype, lang, k in PLAN:
        fn = DOC_TYPES[dtype][0]
        for i in range(k):
            pid = f"{dtype}_{lang}_{i + 1:02d}"
            page, fields = fn(r, lang)
            (PAGES / f"{pid}.spec.json").write_text(json.dumps({"w": W, "h": H, "items": page.items},
                                                               ensure_ascii=False))
            golds.append({"id": pid, "doc_type": dtype, "lang": lang, "script": SCRIPT[lang],
                          "fields": fields, "text": page.gold_text()})
    subprocess.run(["swift", str(Path(__file__).with_name("render.swift")), str(PAGES)], check=True)
    for g in golds:
        phone_photo(PAGES / f"{g['id']}.png", PAGES / f"{g['id']}_photo.jpg", g["id"])
    for pid in HARSH_IDS:  # subset only: Sarvam budget
        phone_photo(PAGES / f"{pid}.png", PAGES / f"{pid}_harsh.jpg", pid, harsh=True)
    with open(OUT / "gold.jsonl", "w") as f:
        for g in golds:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")
    print(len(golds), "pages")


if __name__ == "__main__":
    sys.exit(main())
