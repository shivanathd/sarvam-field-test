"""Builds data/uc06_offline_agri/questions.json: 60 in-scope farmer questions + 10 out-of-scope ones.

30 facts from advisory_sheet.md, 5 per language (Hindi, Marathi, Kannada, Telugu, Tamil, Punjabi); each fact is asked
once in native script and once romanised (how many farmers actually type on phones). Gold = the number(s) the answer
must contain, taken from the sheet. Hand-written; synthetic.
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "data" / "uc06_offline_agri" / "questions.json"

# (fact id, gold numbers, sheet line, {lang: (native, romanised)})
FACTS = [
    ("paddy_urea", [90], "Urea 90 kg in total", {"hi": ("धान में एक एकड़ में कुल कितना यूरिया डालना है?", "dhaan mein ek acre mein kul kitna urea daalna hai?")}),
    ("pbw_traps", [4], "install 4 pheromone traps per acre", {"hi": ("कपास में गुलाबी सुंडी के लिए एक एकड़ में कितने फेरोमोन ट्रैप लगाएँ?", "kapas mein gulabi sundi ke liye ek acre mein kitne pheromone trap lagayein?")}),
    ("wheat_seed_timely", [40], "timely sowing 40 kg per acre", {"hi": ("गेहूँ की समय पर बुवाई के लिए प्रति एकड़ कितना बीज चाहिए?", "gehun ki samay par buvai ke liye prati acre kitna beej chahiye?")}),
    ("scheme_cap", [2000], "up to Rs 2,000 per acre", {"hi": ("किसान बीज सहायता योजना में एक एकड़ पर ज़्यादा से ज़्यादा कितनी सब्सिडी मिलेगी?", "kisan beej sahayata yojana mein ek acre par zyada se zyada kitni subsidy milegi?")}),
    ("soy_seed", [30], "Seed rate: 30 kg per acre", {"hi": ("सोयाबीन का बीज एक एकड़ में कितना लगेगा?", "soybean ka beej ek acre mein kitna lagega?")}),

    ("cotton_packets", [2], "2 packets (450 g each) per acre", {"mr": ("कापसाच्या बीटी बियाण्याची एकरी किती पाकिटे लागतात?", "kapsachya BT biyanyachi ekari kiti pakite lagtat?")}),
    ("cotton_rain", [75, 100], "after 75 to 100 mm of cumulative rainfall", {"mr": ("कापसाची पेरणी किती मिलीमीटर पाऊस झाल्यावर करावी?", "kapsachi perni kiti millimeter paus zalyavar karavi?")}),
    ("soy_row", [45], "Row spacing 45 cm", {"mr": ("सोयाबीनच्या दोन ओळींमध्ये किती अंतर ठेवायचे?", "soybeanchya don olinmadhye kiti antar thevayche?")}),
    ("girdle_dose", [300], "thiacloprid 21.7 SC at 300 ml per acre", {"mr": ("सोयाबीनवर चक्री भुंगा आला तर थायक्लोप्रिड एकरी किती मिली फवारायचे?", "soybeanvar chakri bhunga ala tar thiacloprid ekari kiti ml favarayche?")}),
    ("scheme_acres", [5], "for at most 5 acres per farmer", {"mr": ("बियाणे सहाय्य योजनेत जास्तीत जास्त किती एकरांसाठी अनुदान मिळते?", "biyane sahayya yojanet jastit jast kiti ekransathi anudan milte?")}),

    ("paddy_seed", [8], "transplanted paddy 8 kg per acre", {"kn": ("ನಾಟಿ ಭತ್ತಕ್ಕೆ ಎಕರೆಗೆ ಎಷ್ಟು ಕೆಜಿ ಬೀಜ ಬೇಕು?", "naati bhattakke ekarege eshtu kg beeja beku?")}),
    ("bph_threshold", [10], "10 hoppers per hill", {"kn": ("ಭತ್ತದಲ್ಲಿ ಕಂದು ಜಿಗಿಹುಳು ಒಂದು ಗುಣಿಗೆ ಎಷ್ಟು ಇದ್ದಾಗ ಔಷಧಿ ಸಿಂಪಡಿಸಬೇಕು?", "bhattadalli kandu jigihulu ondu gunige eshtu iddaga aushadhi simpadisabeku?")}),
    ("cotton_ssp", [150], "SSP 150 kg", {"kn": ("ಹತ್ತಿಗೆ ಎಕರೆಗೆ ಎಷ್ಟು ಕೆಜಿ ಎಸ್‌ಎಸ್‌ಪಿ ಹಾಕಬೇಕು?", "hattige ekarege eshtu kg SSP haakabeku?")}),
    ("soy_rhizobium", [5], "Rhizobium culture at 5 g per kg of seed", {"kn": ("ಸೋಯಾಬೀನ್ ಬೀಜಕ್ಕೆ ಒಂದು ಕೆಜಿಗೆ ರೈಜೋಬಿಯಂ ಎಷ್ಟು ಗ್ರಾಂ ಹಾಕಬೇಕು?", "soyabean beejakke ondu kg ge rhizobium eshtu gram haakabeku?")}),
    ("spray_water", [200], "200 litres of water per acre", {"kn": ("ಔಷಧಿ ಸಿಂಪಡಣೆಗೆ ಎಕರೆಗೆ ಎಷ್ಟು ಲೀಟರ್ ನೀರು ಬಳಸಬೇಕು?", "aushadhi simpadanege ekarege eshtu litre neeru balasabeku?")}),

    ("paddy_seedling_age", [21, 25], "seedlings 21 to 25 days old", {"te": ("వరి నాట్లకు నారు ఎన్ని రోజుల వయసులో ఉండాలి?", "vari naatlaku naaru enni rojula vayasulo undali?")}),
    ("paddy_zinc", [10], "zinc sulphate 10 kg", {"te": ("వరికి ఎకరానికి ఎంత జింక్ సల్ఫేట్ వేయాలి?", "variki ekaraniki entha zinc sulphate veyali?")}),
    ("cotton_spacing", [90, 60], "90 cm between rows x 60 cm between plants", {"te": ("పత్తి మొక్కల మధ్య, సాళ్ల మధ్య దూరం ఎంత ఉండాలి?", "patti mokkala madhya, saalla madhya dooram entha undali?")}),
    ("whitefly_threshold", [8, 10], "8 to 10 adults per leaf", {"te": ("పత్తిలో ఆకుకు ఎన్ని తెల్లదోమలు ఉంటే మందు కొట్టాలి?", "pattilo aakuku enni telladomalu unte mandu kottali?")}),
    ("scheme_deadline", [31], "by 31 July 2026 for kharif crops", {"te": ("విత్తన సహాయ పథకానికి ఖరీఫ్ పంటలకు దరఖాస్తు చివరి తేదీ ఎప్పుడు?", "vittana sahaya pathakaniki kharif pantalaku darakhastu chivari tedi eppudu?")}),

    ("stemborer_dose", [60], "chlorantraniliprole 18.5 SC at 60 ml per acre", {"ta": ("நெல்லில் தண்டு துளைப்பானுக்கு குளோரான்ட்ரானிலிப்ரோல் ஏக்கருக்கு எவ்வளவு மில்லி தெளிக்க வேண்டும்?", "nellil thandu thulaippanukku chlorantraniliprole ekkarukku evvalavu ml thelikka vendum?")}),
    ("cotton_urea", [100], "Urea 100 kg in total", {"ta": ("பருத்திக்கு ஏக்கருக்கு மொத்தம் எவ்வளவு யூரியா போட வேண்டும்?", "paruthikku ekkarukku mottham evvalavu urea poda vendum?")}),
    ("soy_dap", [50], "DAP 50 kg", {"ta": ("சோயாபீனுக்கு ஏக்கருக்கு எவ்வளவு டிஏபி போட வேண்டும்?", "soyabeanukku ekkarukku evvalavu DAP poda vendum?")}),
    ("wheat_first_irrigation", [21], "first irrigation ... 21 days after sowing", {"ta": ("கோதுமைக்கு விதைத்து எத்தனை நாளில் முதல் தண்ணீர் பாய்ச்ச வேண்டும்?", "kothumaikku vidhaithu ethanai naalil mudhal thanneer paaycha vendum?")}),
    ("rust_dose", [200], "propiconazole 25 EC at 200 ml per acre", {"ta": ("கோதுமையில் மஞ்சள் துரு வந்தால் ப்ரோபிகோனசோல் ஏக்கருக்கு எவ்வளவு மில்லி?", "kothumaiyil manjal thuru vandhal propiconazole ekkarukku evvalavu ml?")}),

    ("wheat_seed_late", [50], "late sowing 50 kg per acre", {"pa": ("ਪਿਛੇਤੀ ਕਣਕ ਲਈ ਪ੍ਰਤੀ ਏਕੜ ਕਿੰਨਾ ਬੀਜ ਚਾਹੀਦਾ ਹੈ?", "pichheti kanak layi prati ekad kinna beej chahida hai?")}),
    ("wheat_urea", [110], "Urea 110 kg in total", {"pa": ("ਕਣਕ ਨੂੰ ਪ੍ਰਤੀ ਏਕੜ ਕੁੱਲ ਕਿੰਨਾ ਯੂਰੀਆ ਪਾਉਣਾ ਹੈ?", "kanak nu prati ekad kull kinna urea pauna hai?")}),
    ("aphid_threshold", [10], "10 aphids per tiller", {"pa": ("ਕਣਕ ਵਿੱਚ ਪ੍ਰਤੀ ਬੂਝਾ ਕਿੰਨਾ ਤੇਲਾ ਹੋਣ 'ਤੇ ਸਪਰੇਅ ਕਰੀਏ?", "kanak vich prati boojha kinna tela hon te spray kariye?")}),
    ("soy_weedfree", [45], "weed-free for the first 45 days", {"pa": ("ਸੋਇਆਬੀਨ ਨੂੰ ਬਿਜਾਈ ਤੋਂ ਬਾਅਦ ਕਿੰਨੇ ਦਿਨ ਨਦੀਨ ਮੁਕਤ ਰੱਖਣਾ ਹੈ?", "soyabean nu bijai ton baad kinne din nadeen mukat rakhna hai?")}),
    ("cotton_mop", [40], "MOP 40 kg", {"pa": ("ਨਰਮੇ ਨੂੰ ਪ੍ਰਤੀ ਏਕੜ ਕਿੰਨਾ ਪੋਟਾਸ਼ (MOP) ਪਾਈਏ?", "narme nu prati ekad kinna potash (MOP) paiye?")}),
]

# (lang, script, question) - nothing in the sheet answers these
OOS = [
    ("hi", "native", "सेब के बगीचे में कौन सी खाद डालें?"),
    ("mr", "roman", "aajcha soybean cha bajarbhav kay ahe?"),
    ("kn", "native", "ನಾಳೆ ನಮ್ಮ ಊರಲ್ಲಿ ಮಳೆ ಬರುತ್ತದೆಯೇ?"),
    ("te", "native", "ట్రాక్టర్ లోన్‌కి వడ్డీ రేటు ఎంత?"),
    ("ta", "native", "தக்காளிக்கு ஏக்கருக்கு எவ்வளவு உரம் போட வேண்டும்?"),
    ("pa", "native", "ਮੇਰੀ ਗਾਂ ਦੁੱਧ ਘੱਟ ਦੇ ਰਹੀ ਹੈ, ਕੀ ਕਰਾਂ?"),
    ("hi", "roman", "ganne mein ek acre mein kitna urea dalna hai?"),
    ("mr", "native", "ठिबक सिंचनासाठी किती अनुदान मिळते?"),
    ("kn", "roman", "PM-Kisan kantu yavaga barutte?"),
    ("te", "roman", "mirchi pantaku ekaraniki entha DAP veyali?"),
]


def build():
    qs = []
    for fid, gold, src, d in FACTS:
        (lang, (native, roman)), = d.items()
        qs.append({"id": f"{fid}-{lang}-native", "lang": lang, "script": "native", "q": native, "gold": gold, "sheet": src, "oos": False})
        qs.append({"id": f"{fid}-{lang}-roman", "lang": lang, "script": "roman", "q": roman, "gold": gold, "sheet": src, "oos": False})
    for k, (lang, script, q) in enumerate(OOS):
        qs.append({"id": f"oos{k}-{lang}-{script}", "lang": lang, "script": script, "q": q, "gold": [], "sheet": None, "oos": True})
    return qs


if __name__ == "__main__":
    sheet = " ".join((OUT.parent / "advisory_sheet.md").read_text().split())
    for fid, gold, src, _ in FACTS:  # every gold fact must literally be in the sheet
        assert src.split("...")[0].strip() in sheet, fid
    qs = build()
    assert len({q["id"] for q in qs}) == len(qs) == 70
    OUT.write_text(json.dumps({"synthetic": True, "how_made": __doc__.strip(), "questions": qs}, ensure_ascii=False, indent=1))
    print(len(qs), "questions ->", OUT)
