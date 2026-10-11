"""Builds data/uc10_selfhost_business/items.json: 150 synthetic customer-support / back-office texts.

5 tasks x 5 scenarios x 6 languages (Hindi, Marathi, Tamil, Telugu, Bengali, Hinglish). Each scenario was written by
hand in every language (not machine translated); order ids, amounts, dates, invoice numbers and GSTINs are filled in
per language from a seeded RNG so every item has its own checkable gold. All people, companies and ids are fictional.
GSTINs have a valid checksum but are random and labelled SAMPLE in the text.
"""
import json, random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "uc10_selfhost_business" / "items.json"
LANGS = ["hi", "mr", "ta", "te", "bn", "hinglish"]
MONTHS = {
    "hi": "जनवरी फ़रवरी मार्च अप्रैल मई जून जुलाई अगस्त सितंबर अक्टूबर नवंबर दिसंबर",
    "mr": "जानेवारी फेब्रुवारी मार्च एप्रिल मे जून जुलै ऑगस्ट सप्टेंबर ऑक्टोबर नोव्हेंबर डिसेंबर",
    "ta": "ஜனவரி பிப்ரவரி மார்ச் ஏப்ரல் மே ஜூன் ஜூலை ஆகஸ்ட் செப்டம்பர் அக்டோபர் நவம்பர் டிசம்பர்",
    "te": "జనవరి ఫిబ్రవరి మార్చి ఏప్రిల్ మే జూన్ జూలై ఆగస్టు సెప్టెంబర్ అక్టోబర్ నవంబర్ డిసెంబర్",
    "bn": "জানুয়ারি ফেব্রুয়ারি মার্চ এপ্রিল মে জুন জুলাই আগস্ট সেপ্টেম্বর অক্টোবর নভেম্বর ডিসেম্বর",
    "hinglish": "January February March April May June July August September October November December",
}
MONTHS = {k: v.split() for k, v in MONTHS.items()}

# ---------- (a) triage: gold intent + urgency ----------
TRIAGE = [
    ("payment_failed", 3, {
        "hi": "मैंने UPI से ₹{amt} का पेमेंट किया, पैसे मेरे खाते से कट गए लेकिन ऐप में ऑर्डर 'पेमेंट फेल' दिखा रहा है। कृपया जल्दी देखिए।",
        "mr": "मी UPI ने ₹{amt} भरले, माझ्या खात्यातून पैसे कट झाले पण ॲपमध्ये ऑर्डर 'पेमेंट फेल' दाखवत आहे. कृपया लवकर बघा.",
        "ta": "UPI மூலம் ₹{amt} செலுத்தினேன், என் கணக்கிலிருந்து பணம் போய்விட்டது, ஆனால் ஆப்பில் ஆர்டர் 'பேமெண்ட் ஃபெயில்' என்று காட்டுகிறது. தயவுசெய்து சீக்கிரம் பாருங்கள்.",
        "te": "UPI ద్వారా ₹{amt} చెల్లించాను, నా ఖాతా నుండి డబ్బులు కట్ అయ్యాయి కానీ యాప్‌లో ఆర్డర్ 'పేమెంట్ ఫెయిల్' అని చూపిస్తోంది. దయచేసి త్వరగా చూడండి.",
        "bn": "UPI দিয়ে ₹{amt} পেমেন্ট করেছি, আমার অ্যাকাউন্ট থেকে টাকা কেটে গেছে কিন্তু অ্যাপে অর্ডার 'পেমেন্ট ফেল' দেখাচ্ছে। দয়া করে তাড়াতাড়ি দেখুন।",
        "hinglish": "Maine UPI se ₹{amt} pay kiya, account se paise kat gaye lekin app mein order 'payment failed' dikha raha hai. Please jaldi check karo."}),
    ("delivery_delay", 2, {
        "hi": "मेरा ऑर्डर {oid} पिछले हफ्ते आना था, अभी तक नहीं आया। ट्रैकिंग भी अपडेट नहीं हो रही। बताइए कब तक आएगा?",
        "mr": "माझी ऑर्डर {oid} मागच्या आठवड्यात यायला हवी होती, अजून आली नाही. ट्रॅकिंगही अपडेट होत नाहीये. कधी येईल ते सांगा.",
        "ta": "என் ஆர்டர் {oid} கடந்த வாரமே வந்திருக்க வேண்டும், இன்னும் வரவில்லை. டிராக்கிங்கும் அப்டேட் ஆகவில்லை. எப்போது வரும் என்று சொல்லுங்கள்.",
        "te": "నా ఆర్డర్ {oid} గత వారమే రావాల్సింది, ఇంకా రాలేదు. ట్రాకింగ్ కూడా అప్‌డేట్ కావడం లేదు. ఎప్పుడు వస్తుందో చెప్పండి.",
        "bn": "আমার অর্ডার {oid} গত সপ্তাহে আসার কথা ছিল, এখনও আসেনি। ট্র্যাকিংও আপডেট হচ্ছে না। কবে আসবে জানান।",
        "hinglish": "Mera order {oid} pichle hafte aana tha, abhi tak nahi aaya. Tracking bhi update nahi ho rahi. Kab tak aayega batao?"}),
    ("product_question", 1, {
        "hi": "इस मिक्सर ग्राइंडर के साथ वारंटी मिलती है क्या? कितने साल की है?",
        "mr": "या मिक्सर ग्राइंडरसोबत वॉरंटी मिळते का? किती वर्षांची आहे?",
        "ta": "இந்த மிக்ஸர் கிரைண்டருக்கு வாரண்டி உண்டா? எத்தனை வருடம்?",
        "te": "ఈ మిక్సర్ గ్రైండర్‌కి వారంటీ ఉందా? ఎన్ని సంవత్సరాలు?",
        "bn": "এই মিক্সার গ্রাইন্ডারের সাথে কি ওয়ারেন্টি পাওয়া যায়? কত বছরের?",
        "hinglish": "Is mixer grinder ke saath warranty milti hai kya? Kitne saal ki hai?"}),
    ("damaged_item", 2, {
        "hi": "ऑर्डर {oid} में प्रेशर कुकर आया, उसका ढक्कन पिचका हुआ है। मुझे इसकी जगह नया चाहिए।",
        "mr": "ऑर्डर {oid} मध्ये प्रेशर कुकर आला, त्याचे झाकण चेपलेले आहे. मला त्याऐवजी नवीन हवा आहे.",
        "ta": "ஆர்டர் {oid}-இல் வந்த பிரஷர் குக்கரின் மூடி நசுங்கி இருக்கிறது. எனக்கு மாற்றாக புதியது வேண்டும்.",
        "te": "ఆర్డర్ {oid}లో వచ్చిన ప్రెషర్ కుక్కర్ మూత సొట్టపోయి ఉంది. నాకు దాని బదులు కొత్తది కావాలి.",
        "bn": "অর্ডার {oid}-এ প্রেশার কুকার এসেছে, ঢাকনাটা তোবড়ানো। আমার বদলে নতুন একটা চাই।",
        "hinglish": "Order {oid} mein pressure cooker aaya, uska dhakkan pichka hua hai. Mujhe replacement chahiye."}),
    ("account_access", 3, {
        "hi": "मैं अपने अकाउंट में लॉगिन नहीं कर पा रहा, OTP नहीं आ रहा। कल GST फाइलिंग की आखिरी तारीख है और मुझे आज ही इनवॉइस डाउनलोड करना है।",
        "mr": "मला माझ्या अकाउंटमध्ये लॉगिन करता येत नाही, OTP येत नाही. उद्या GST फायलिंगची शेवटची तारीख आहे आणि मला आजच इनव्हॉइस डाउनलोड करायचे आहे.",
        "ta": "என் அக்கவுண்டில் லாகின் செய்ய முடியவில்லை, OTP வரவில்லை. நாளை GST ஃபைலிங் கடைசி நாள், இன்றே இன்வாய்ஸ் டவுன்லோட் செய்ய வேண்டும்.",
        "te": "నా అకౌంట్‌లో లాగిన్ కాలేకపోతున్నాను, OTP రావడం లేదు. రేపు GST ఫైలింగ్‌కు చివరి తేదీ, ఈరోజే ఇన్‌వాయిస్ డౌన్‌లోడ్ చేయాలి.",
        "bn": "আমি আমার অ্যাকাউন্টে লগইন করতে পারছি না, OTP আসছে না। কাল GST ফাইলিংয়ের শেষ তারিখ, আজই ইনভয়েস ডাউনলোড করতে হবে।",
        "hinglish": "Apne account mein login nahi ho raha, OTP nahi aa raha. Kal GST filing ki last date hai aur mujhe aaj hi invoice download karna hai."}),
]

# ---------- (b) complaint -> English CRM note: gold order id, amount, date, issue (regex) ----------
CRM = [
    (r"colou?r|green|wrong (item|saree|product)", {
        "hi": "मैंने {date} को ऑर्डर {oid} से ₹{amt} की साड़ी मंगाई थी। लाल रंग ऑर्डर किया था पर हरे रंग की आई है। यह बिल्कुल ठीक नहीं है।",
        "mr": "मी {date} रोजी ऑर्डर {oid} मधून ₹{amt} ची साडी मागवली होती. लाल रंग ऑर्डर केला होता पण हिरव्या रंगाची आली. हे अजिबात बरोबर नाही.",
        "ta": "{date} அன்று ஆர்டர் {oid} மூலம் ₹{amt} மதிப்புள்ள புடவை ஆர்டர் செய்தேன். சிவப்பு நிறம் கேட்டேன், ஆனால் பச்சை நிறம் வந்திருக்கிறது. இது சரியில்லை.",
        "te": "{date}న ఆర్డర్ {oid} ద్వారా ₹{amt} విలువైన చీర ఆర్డర్ చేశాను. ఎరుపు రంగు ఆర్డర్ చేస్తే ఆకుపచ్చ రంగు వచ్చింది. ఇది అస్సలు సరికాదు.",
        "bn": "আমি {date} তারিখে অর্ডার {oid}-এ ₹{amt} দামের একটা শাড়ি অর্ডার করেছিলাম। লাল রং চেয়েছিলাম কিন্তু সবুজ রঙের এসেছে। এটা একদম ঠিক না।",
        "hinglish": "Maine {date} ko order {oid} se ₹{amt} ki saree mangwayi thi. Red colour order kiya tha par green aayi hai. Yeh bilkul theek nahi hai."}),
    (r"twice|double|duplicate|two times|charged 2|2 times", {
        "hi": "{date} को ऑर्डर {oid} के लिए मेरे कार्ड से ₹{amt} दो बार कट गए। एक बार का पैसा वापस कीजिए।",
        "mr": "{date} रोजी ऑर्डर {oid} साठी माझ्या कार्डमधून ₹{amt} दोनदा कापले गेले. एका वेळचे पैसे परत करा.",
        "ta": "{date} அன்று ஆர்டர் {oid}-க்காக என் கார்டில் இருந்து ₹{amt} இரண்டு முறை எடுக்கப்பட்டது. ஒரு முறை பணத்தை திருப்பித் தாருங்கள்.",
        "te": "{date}న ఆర్డర్ {oid} కోసం నా కార్డు నుండి ₹{amt} రెండుసార్లు కట్ అయ్యాయి. ఒకసారి డబ్బులు తిరిగి ఇవ్వండి.",
        "bn": "{date} তারিখে অর্ডার {oid}-এর জন্য আমার কার্ড থেকে ₹{amt} দুবার কেটেছে। একবারের টাকা ফেরত দিন।",
        "hinglish": "{date} ko order {oid} ke liye mere card se ₹{amt} do baar kat gaye. Ek baar ka paisa wapas karo."}),
    (r"refund", {
        "hi": "मैंने ऑर्डर {oid} के जूते लौटा दिए थे। आपने {date} तक ₹{amt} का रिफंड देने को कहा था, पर अभी तक पैसा नहीं आया।",
        "mr": "मी ऑर्डर {oid} चे बूट परत केले होते. तुम्ही {date} पर्यंत ₹{amt} चा रिफंड देऊ असे सांगितले होते, पण अजून पैसे आले नाहीत.",
        "ta": "ஆர்டர் {oid} ஷூக்களை திருப்பி அனுப்பினேன். {date}-க்குள் ₹{amt} ரீஃபண்ட் தருவதாகச் சொன்னீர்கள், ஆனால் இன்னும் பணம் வரவில்லை.",
        "te": "ఆర్డర్ {oid} షూస్ తిరిగి పంపించాను. {date} లోపు ₹{amt} రీఫండ్ ఇస్తామన్నారు, కానీ ఇంకా డబ్బులు రాలేదు.",
        "bn": "অর্ডার {oid}-এর জুতো ফেরত দিয়েছিলাম। আপনারা {date}-এর মধ্যে ₹{amt} রিফান্ড দেবেন বলেছিলেন, কিন্তু এখনও টাকা আসেনি।",
        "hinglish": "Maine order {oid} ke shoes return kar diye the. Aapne {date} tak ₹{amt} ka refund dene ko bola tha, par abhi tak paisa nahi aaya."}),
    (r"empty|missing|no phone|without (the |a )?phone|not (inside|in the box|included)|did not contain|didn.t contain", {
        "hi": "{date} को ₹{amt} का मोबाइल फोन ऑर्डर किया था (ऑर्डर {oid})। आज डिब्बा आया तो अंदर फोन था ही नहीं, डिब्बा खाली था।",
        "mr": "{date} रोजी ₹{amt} चा मोबाईल फोन ऑर्डर केला होता (ऑर्डर {oid}). आज बॉक्स आला तर आत फोनच नव्हता, बॉक्स रिकामा होता.",
        "ta": "{date} அன்று ₹{amt} மதிப்புள்ள மொபைல் போன் ஆர்டர் செய்தேன் (ஆர்டர் {oid}). இன்று பெட்டி வந்தது, ஆனால் உள்ளே போன் இல்லை, பெட்டி காலியாக இருந்தது.",
        "te": "{date}న ₹{amt} విలువైన మొబైల్ ఫోన్ ఆర్డర్ చేశాను (ఆర్డర్ {oid}). ఈరోజు బాక్స్ వచ్చింది కానీ లోపల ఫోన్ లేదు, బాక్స్ ఖాళీగా ఉంది.",
        "bn": "{date} তারিখে ₹{amt} দামের একটা মোবাইল ফোন অর্ডার করেছিলাম (অর্ডার {oid})। আজ বাক্স এল, কিন্তু ভেতরে ফোন নেই, বাক্সটা খালি।",
        "hinglish": "{date} ko ₹{amt} ka mobile phone order kiya tha (order {oid}). Aaj box aaya to andar phone tha hi nahi, box khaali tha."}),
    (r"no.?show|did ?n.?t (come|arrive|show|turn|visit)|not (come|arrive|show|turn|visit)|never (came|arrived|showed|turned|visited)|failed to (arrive|come|show|visit|turn)|absent", {
        "hi": "मैंने {date} के लिए AC सर्विस बुक की थी और ₹{amt} एडवांस दिए थे (बुकिंग {oid})। टेक्नीशियन आया ही नहीं।",
        "mr": "मी {date} साठी AC सर्व्हिस बुक केली होती आणि ₹{amt} ॲडव्हान्स दिले होते (बुकिंग {oid}). टेक्निशियन आलाच नाही.",
        "ta": "{date} அன்று AC சர்வீஸ் புக் செய்து ₹{amt} அட்வான்ஸ் கட்டினேன் (புக்கிங் {oid}). டெக்னீஷியன் வரவே இல்லை.",
        "te": "{date}కి AC సర్వీస్ బుక్ చేసి ₹{amt} అడ్వాన్స్ కట్టాను (బుకింగ్ {oid}). టెక్నీషియన్ అసలు రాలేదు.",
        "bn": "{date} তারিখের জন্য AC সার্ভিস বুক করেছিলাম আর ₹{amt} অ্যাডভান্স দিয়েছিলাম (বুকিং {oid})। টেকনিশিয়ান আসেইনি।",
        "hinglish": "Maine {date} ke liye AC service book ki thi aur ₹{amt} advance diye the (booking {oid}). Technician aaya hi nahi."}),
]

# ---------- (c) reply drafting under policy: gold refund window N (days) ----------
REPLY = [
    (7, {
        "hi": "ऑर्डर {oid} में गलत साइज़ के जूते आए हैं। मुझे पूरा रिफंड चाहिए और परेशानी के लिए ₹500 मुआवज़ा भी।",
        "mr": "ऑर्डर {oid} मध्ये चुकीच्या साइजचे बूट आले. मला पूर्ण रिफंड हवा आहे आणि त्रासाबद्दल ₹500 नुकसानभरपाई पण.",
        "ta": "ஆர்டர் {oid}-இல் தவறான சைஸ் ஷூ வந்திருக்கிறது. எனக்கு முழு ரீஃபண்ட் வேண்டும், சிரமத்துக்கு ₹500 இழப்பீடும் வேண்டும்.",
        "te": "ఆర్డర్ {oid}లో తప్పు సైజ్ షూస్ వచ్చాయి. నాకు పూర్తి రీఫండ్ కావాలి, ఇబ్బందికి ₹500 పరిహారం కూడా కావాలి.",
        "bn": "অর্ডার {oid}-এ ভুল সাইজের জুতো এসেছে। আমার পুরো রিফান্ড চাই, আর ঝামেলার জন্য ₹500 ক্ষতিপূরণও চাই।",
        "hinglish": "Order {oid} mein galat size ke shoes aaye hain. Mujhe full refund chahiye aur pareshani ke liye ₹500 compensation bhi."}),
    (10, {
        "hi": "मेरा ऑर्डर {oid} एक हफ्ता देर से आया। मुझे कैशबैक चाहिए, वरना मैं सामान लौटा दूँगा।",
        "mr": "माझी ऑर्डर {oid} एक आठवडा उशिरा आली. मला कॅशबॅक हवा आहे, नाहीतर मी सामान परत करीन.",
        "ta": "என் ஆர்டர் {oid} ஒரு வாரம் தாமதமாக வந்தது. எனக்கு கேஷ்பேக் வேண்டும், இல்லையென்றால் பொருளை திருப்பி அனுப்புவேன்.",
        "te": "నా ఆర్డర్ {oid} ఒక వారం ఆలస్యంగా వచ్చింది. నాకు క్యాష్‌బ్యాక్ కావాలి, లేకపోతే వస్తువు తిరిగి పంపిస్తాను.",
        "bn": "আমার অর্ডার {oid} এক সপ্তাহ দেরিতে এসেছে। আমার ক্যাশব্যাক চাই, নইলে জিনিসটা ফেরত দেব।",
        "hinglish": "Mera order {oid} ek hafta late aaya. Mujhe cashback chahiye, warna main saamaan return kar dunga."}),
    (15, {
        "hi": "जो ब्लूटूथ स्पीकर लिया था (ऑर्डर {oid}), वह कुछ ही दिनों में बंद हो गया। क्या मैं इसे लौटा सकता हूँ? और पैसे ठीक किस तारीख तक वापस आएँगे?",
        "mr": "घेतलेला ब्लूटूथ स्पीकर (ऑर्डर {oid}) काही दिवसांतच बंद पडला. मी तो परत करू शकतो का? आणि पैसे नक्की कोणत्या तारखेपर्यंत परत येतील?",
        "ta": "வாங்கிய ப்ளூடூத் ஸ்பீக்கர் (ஆர்டர் {oid}) சில நாட்களிலேயே வேலை செய்யவில்லை. இதை திருப்பி அனுப்பலாமா? பணம் சரியாக எந்த தேதிக்குள் வரும்?",
        "te": "కొన్న బ్లూటూత్ స్పీకర్ (ఆర్డర్ {oid}) కొన్ని రోజుల్లోనే పనిచేయడం ఆగిపోయింది. దీన్ని తిరిగి ఇవ్వవచ్చా? డబ్బులు సరిగ్గా ఏ తేదీలోగా వస్తాయి?",
        "bn": "যে ব্লুটুথ স্পিকারটা কিনেছিলাম (অর্ডার {oid}), সেটা কয়েক দিনের মধ্যেই বন্ধ হয়ে গেছে। এটা কি ফেরত দিতে পারি? আর টাকা ঠিক কোন তারিখের মধ্যে ফেরত আসবে?",
        "hinglish": "Jo bluetooth speaker liya tha (order {oid}), woh kuch hi dino mein band ho gaya. Kya main ise return kar sakta hoon? Aur paise exactly kis date tak wapas aayenge?"}),
    (30, {
        "hi": "मैंने जो ड्रेस मँगाई थी (ऑर्डर {oid}), वह पसंद नहीं आई। क्या इसे वापस कर सकती हूँ? रिफंड जल्दी दे दीजिए।",
        "mr": "मी मागवलेला ड्रेस (ऑर्डर {oid}) आवडला नाही. तो परत करू शकते का? रिफंड लवकर द्या.",
        "ta": "நான் ஆர்டர் செய்த டிரெஸ் (ஆர்டர் {oid}) பிடிக்கவில்லை. இதை திருப்பி அனுப்பலாமா? ரீஃபண்டை சீக்கிரம் தாருங்கள்.",
        "te": "నేను ఆర్డర్ చేసిన డ్రెస్ (ఆర్డర్ {oid}) నచ్చలేదు. దీన్ని తిరిగి ఇవ్వొచ్చా? రీఫండ్ త్వరగా ఇవ్వండి.",
        "bn": "যে ড্রেসটা অর্ডার করেছিলাম (অর্ডার {oid}), সেটা পছন্দ হয়নি। এটা কি ফেরত দিতে পারি? রিফান্ড তাড়াতাড়ি দিন।",
        "hinglish": "Jo dress order ki thi (order {oid}), woh pasand nahi aayi. Kya ise return kar sakti hoon? Refund jaldi de do."}),
    (7, {
        "hi": "अगर कल तक मेरे ₹{amt} वापस नहीं आए तो मैं ट्विटर पर आपकी कंपनी के बारे में लिखूँगा। ऑर्डर {oid}।",
        "mr": "उद्यापर्यंत माझे ₹{amt} परत आले नाहीत तर मी ट्विटरवर तुमच्या कंपनीबद्दल लिहीन. ऑर्डर {oid}.",
        "ta": "நாளைக்குள் என் ₹{amt} திரும்ப வரவில்லை என்றால் உங்கள் நிறுவனத்தைப் பற்றி ட்விட்டரில் எழுதுவேன். ஆர்டர் {oid}.",
        "te": "రేపటిలోగా నా ₹{amt} తిరిగి రాకపోతే మీ కంపెనీ గురించి ట్విట్టర్‌లో రాస్తాను. ఆర్డర్ {oid}.",
        "bn": "কালকের মধ্যে আমার ₹{amt} ফেরত না এলে আমি টুইটারে আপনাদের কোম্পানির কথা লিখব। অর্ডার {oid}।",
        "hinglish": "Agar kal tak mere ₹{amt} wapas nahi aaye to main Twitter pe aapki company ke baare mein likhunga. Order {oid}."}),
]

# ---------- (d) sentiment + escalation ----------
ESCALATE = [
    ("positive", False, {
        "hi": "आज ऑर्डर {oid} मिल गया, पैकिंग बहुत अच्छी थी और समय पर आया। धन्यवाद!",
        "mr": "आज ऑर्डर {oid} मिळाली, पॅकिंग खूप छान होती आणि वेळेवर आली. धन्यवाद!",
        "ta": "இன்று ஆர்டர் {oid} கிடைத்தது, பேக்கிங் மிக நன்றாக இருந்தது, சரியான நேரத்தில் வந்தது. நன்றி!",
        "te": "ఈరోజు ఆర్డర్ {oid} అందింది, ప్యాకింగ్ చాలా బాగుంది, సమయానికి వచ్చింది. ధన్యవాదాలు!",
        "bn": "আজ অর্ডার {oid} পেয়েছি, প্যাকিং খুব ভালো ছিল আর সময়মতো এসেছে। ধন্যবাদ!",
        "hinglish": "Aaj order {oid} mil gaya, packing bahut achhi thi aur time pe aaya. Thank you!"}),
    ("negative", True, {  # safety hazard
        "hi": "आपसे खरीदा चार्जर लगाते ही उसमें से चिंगारी निकली और मेरा हाथ जल गया। यह बहुत खतरनाक है।",
        "mr": "तुमच्याकडून घेतलेला चार्जर लावताच त्यातून ठिणगी आली आणि माझा हात भाजला. हे खूप धोकादायक आहे.",
        "ta": "உங்களிடம் வாங்கிய சார்ஜரை போட்டவுடன் தீப்பொறி வந்து என் கை சுட்டுவிட்டது. இது மிகவும் ஆபத்தானது.",
        "te": "మీ దగ్గర కొన్న ఛార్జర్ పెట్టగానే నిప్పురవ్వలు వచ్చి నా చేయి కాలింది. ఇది చాలా ప్రమాదకరం.",
        "bn": "আপনাদের থেকে কেনা চার্জারটা লাগাতেই স্পার্ক করল আর আমার হাত পুড়ে গেল। এটা খুব বিপজ্জনক।",
        "hinglish": "Aapse kharida charger lagate hi usme se spark nikla aur mera haath jal gaya. Yeh bahut dangerous hai."}),
    ("negative", True, {  # legal threat
        "hi": "ऑर्डर {oid} का रिफंड अब तक नहीं मिला। अगर इस हफ्ते नहीं मिला तो मैं उपभोक्ता अदालत में शिकायत दर्ज करूँगा।",
        "mr": "ऑर्डर {oid} चा रिफंड अजून मिळाला नाही. या आठवड्यात मिळाला नाही तर मी ग्राहक न्यायालयात तक्रार करेन.",
        "ta": "ஆர்டர் {oid} ரீஃபண்ட் இன்னும் கிடைக்கவில்லை. இந்த வாரத்துக்குள் கிடைக்கவில்லை என்றால் நுகர்வோர் நீதிமன்றத்தில் புகார் செய்வேன்.",
        "te": "ఆర్డర్ {oid} రీఫండ్ ఇంకా రాలేదు. ఈ వారంలో రాకపోతే వినియోగదారుల కోర్టులో ఫిర్యాదు చేస్తాను.",
        "bn": "অর্ডার {oid}-এর রিফান্ড এখনও পাইনি। এই সপ্তাহে না পেলে আমি কনজিউমার কোর্টে অভিযোগ করব।",
        "hinglish": "Order {oid} ka refund ab tak nahi mila. Is hafte nahi mila to main consumer court mein complaint karunga."}),
    ("neutral", False, {
        "hi": "कृपया ऑर्डर {oid} का डिलीवरी पता बदलकर मेरे ऑफिस का पता कर दीजिए। पता प्रोफ़ाइल में सेव है।",
        "mr": "कृपया ऑर्डर {oid} चा डिलिव्हरी पत्ता बदलून माझ्या ऑफिसचा पत्ता करा. पत्ता प्रोफाइलमध्ये सेव्ह आहे.",
        "ta": "தயவுசெய்து ஆர்டர் {oid}-இன் டெலிவரி முகவரியை என் அலுவலக முகவரிக்கு மாற்றுங்கள். முகவரி ப்ரொஃபைலில் சேமிக்கப்பட்டுள்ளது.",
        "te": "దయచేసి ఆర్డర్ {oid} డెలివరీ అడ్రస్‌ను నా ఆఫీసు అడ్రస్‌కు మార్చండి. అడ్రస్ ప్రొఫైల్‌లో సేవ్ అయి ఉంది.",
        "bn": "দয়া করে অর্ডার {oid}-এর ডেলিভারি ঠিকানা বদলে আমার অফিসের ঠিকানা করে দিন। ঠিকানাটা প্রোফাইলে সেভ করা আছে।",
        "hinglish": "Please order {oid} ka delivery address change karke mere office ka address kar do. Address profile mein saved hai."}),
    ("negative", False, {
        "hi": "आज का खाना बिल्कुल ठंडा आया और दाल में नमक बहुत ज़्यादा था। बहुत निराशा हुई।",
        "mr": "आजचे जेवण पूर्ण थंड आले आणि डाळीत मीठ खूप जास्त होते. खूप निराशा झाली.",
        "ta": "இன்றைய சாப்பாடு முழுவதும் ஆறிப்போய் வந்தது, பருப்பில் உப்பு அதிகமாக இருந்தது. மிகவும் ஏமாற்றமாக இருந்தது.",
        "te": "ఈరోజు భోజనం పూర్తిగా చల్లగా వచ్చింది, పప్పులో ఉప్పు చాలా ఎక్కువగా ఉంది. చాలా నిరాశ కలిగింది.",
        "bn": "আজকের খাবার একদম ঠান্ডা এসেছে আর ডালে নুন খুব বেশি ছিল। খুব হতাশ হলাম।",
        "hinglish": "Aaj ka khana bilkul thanda aaya aur dal mein namak bahut zyada tha. Bahut disappointing tha."}),
]

# ---------- (e) invoice / email field extraction ----------
EXTRACT = [
    {"hi": "नमस्ते, श्री लक्ष्मी ट्रेडर्स की ओर से इनवॉइस संख्या {inv} संलग्न है। GSTIN: {gstin} (SAMPLE – परीक्षण हेतु)। माल का मूल्य ₹{sub}, GST 18% ₹{gst}, कुल देय राशि ₹{tot}। कृपया {due} तक भुगतान करें।",
     "mr": "नमस्कार, श्री लक्ष्मी ट्रेडर्सकडून इनव्हॉइस क्रमांक {inv} सोबत जोडला आहे. GSTIN: {gstin} (SAMPLE – चाचणीसाठी). मालाची किंमत ₹{sub}, GST 18% ₹{gst}, एकूण देय रक्कम ₹{tot}. कृपया {due} पर्यंत पैसे भरा.",
     "ta": "வணக்கம், ஸ்ரீ லட்சுமி டிரேடர்ஸ் சார்பில் இன்வாய்ஸ் எண் {inv} இணைக்கப்பட்டுள்ளது. GSTIN: {gstin} (SAMPLE – சோதனைக்காக). பொருட்களின் மதிப்பு ₹{sub}, GST 18% ₹{gst}, மொத்தம் செலுத்த வேண்டியது ₹{tot}. தயவுசெய்து {due}-க்குள் பணம் செலுத்தவும்.",
     "te": "నమస్కారం, శ్రీ లక్ష్మి ట్రేడర్స్ తరఫున ఇన్‌వాయిస్ నంబర్ {inv} జత చేశాము. GSTIN: {gstin} (SAMPLE – పరీక్ష కోసం). సరుకు విలువ ₹{sub}, GST 18% ₹{gst}, మొత్తం చెల్లించాల్సింది ₹{tot}. దయచేసి {due} లోగా చెల్లించండి.",
     "bn": "নমস্কার, শ্রী লক্ষ্মী ট্রেডার্সের পক্ষ থেকে ইনভয়েস নম্বর {inv} সংযুক্ত করা হলো। GSTIN: {gstin} (SAMPLE – পরীক্ষার জন্য)। মালের দাম ₹{sub}, GST 18% ₹{gst}, মোট প্রদেয় ₹{tot}। অনুগ্রহ করে {due}-এর মধ্যে পেমেন্ট করুন।",
     "hinglish": "Namaste, Shri Lakshmi Traders ki taraf se invoice number {inv} attach hai. GSTIN: {gstin} (SAMPLE – testing ke liye). Maal ki value ₹{sub}, GST 18% ₹{gst}, total payable ₹{tot}. Please {due} tak payment kar dijiye."},
    {"hi": "स्मरण पत्र: गणेश पैकेजिंग का बिल {inv}, दिनांक {idate}, अभी तक बकाया है। कुल राशि ₹{tot} (₹{sub} + GST ₹{gst})। भुगतान की अंतिम तिथि {due} है। विक्रेता GSTIN {gstin} (SAMPLE)।",
     "mr": "आठवण: गणेश पॅकेजिंगचे बिल {inv}, दिनांक {idate}, अजून थकित आहे. एकूण रक्कम ₹{tot} (₹{sub} + GST ₹{gst}). पैसे भरण्याची शेवटची तारीख {due} आहे. विक्रेता GSTIN {gstin} (SAMPLE).",
     "ta": "நினைவூட்டல்: கணேஷ் பேக்கேஜிங் பில் {inv}, தேதி {idate}, இன்னும் நிலுவையில் உள்ளது. மொத்தத் தொகை ₹{tot} (₹{sub} + GST ₹{gst}). பணம் செலுத்த கடைசி நாள் {due}. விற்பனையாளர் GSTIN {gstin} (SAMPLE).",
     "te": "రిమైండర్: గణేష్ ప్యాకేజింగ్ బిల్లు {inv}, తేదీ {idate}, ఇంకా బకాయి ఉంది. మొత్తం ₹{tot} (₹{sub} + GST ₹{gst}). చెల్లింపుకు చివరి తేదీ {due}. విక్రేత GSTIN {gstin} (SAMPLE).",
     "bn": "অনুস্মারক: গণেশ প্যাকেজিংয়ের বিল {inv}, তারিখ {idate}, এখনও বকেয়া। মোট টাকা ₹{tot} (₹{sub} + GST ₹{gst})। পেমেন্টের শেষ তারিখ {due}। বিক্রেতার GSTIN {gstin} (SAMPLE)।",
     "hinglish": "Reminder: Ganesh Packaging ka bill {inv}, dated {idate}, abhi tak pending hai. Total amount ₹{tot} (₹{sub} + GST ₹{gst}). Payment ki last date {due} hai. Seller GSTIN {gstin} (SAMPLE)."},
    {"hi": "आनंद लॉजिस्टिक्स – भाड़ा बिल नं. {inv}। भाड़ा ₹{sub}, GST ₹{gst}, कुल ₹{tot}। GSTIN {gstin} (SAMPLE)। भुगतान {due} तक करें। किसी सवाल के लिए 98765 43210 पर कॉल करें।",
     "mr": "आनंद लॉजिस्टिक्स – भाडे बिल क्र. {inv}. भाडे ₹{sub}, GST ₹{gst}, एकूण ₹{tot}. GSTIN {gstin} (SAMPLE). {due} पर्यंत पैसे भरा. काही प्रश्न असल्यास 98765 43210 वर कॉल करा.",
     "ta": "ஆனந்த் லாஜிஸ்டிக்ஸ் – சரக்குக் கட்டண பில் எண் {inv}. கட்டணம் ₹{sub}, GST ₹{gst}, மொத்தம் ₹{tot}. GSTIN {gstin} (SAMPLE). {due}-க்குள் செலுத்தவும். சந்தேகங்களுக்கு 98765 43210 என்ற எண்ணை அழைக்கவும்.",
     "te": "ఆనంద్ లాజిస్టిక్స్ – రవాణా ఛార్జీల బిల్లు నం. {inv}. ఛార్జీ ₹{sub}, GST ₹{gst}, మొత్తం ₹{tot}. GSTIN {gstin} (SAMPLE). {due} లోగా చెల్లించండి. సందేహాలుంటే 98765 43210కి కాల్ చేయండి.",
     "bn": "আনন্দ লজিস্টিকস – ভাড়ার বিল নং {inv}। ভাড়া ₹{sub}, GST ₹{gst}, মোট ₹{tot}। GSTIN {gstin} (SAMPLE)। {due}-এর মধ্যে পেমেন্ট করুন। কোনো প্রশ্ন থাকলে 98765 43210 নম্বরে ফোন করুন।",
     "hinglish": "Anand Logistics – freight bill no. {inv}. Bhaada ₹{sub}, GST ₹{gst}, total ₹{tot}. GSTIN {gstin} (SAMPLE). {due} tak payment karein. Koi sawaal ho to 98765 43210 pe call karein."},
    {"hi": "कावेरी ऑफिस स्पेसेज़: अक्टूबर महीने का किराया इनवॉइस {inv}। किराया ₹{sub}, GST (18%) ₹{gst}, कुल ₹{tot}। देय तिथि: {due}। हमारा GSTIN {gstin} (SAMPLE) है।",
     "mr": "कावेरी ऑफिस स्पेसेस: ऑक्टोबर महिन्याचे भाडे इनव्हॉइस {inv}. भाडे ₹{sub}, GST (18%) ₹{gst}, एकूण ₹{tot}. देय तारीख: {due}. आमचा GSTIN {gstin} (SAMPLE) आहे.",
     "ta": "காவேரி ஆபீஸ் ஸ்பேசஸ்: அக்டோபர் மாத வாடகை இன்வாய்ஸ் {inv}. வாடகை ₹{sub}, GST (18%) ₹{gst}, மொத்தம் ₹{tot}. செலுத்த வேண்டிய தேதி: {due}. எங்கள் GSTIN {gstin} (SAMPLE).",
     "te": "కావేరి ఆఫీస్ స్పేసెస్: అక్టోబర్ నెల అద్దె ఇన్‌వాయిస్ {inv}. అద్దె ₹{sub}, GST (18%) ₹{gst}, మొత్తం ₹{tot}. చెల్లింపు తేదీ: {due}. మా GSTIN {gstin} (SAMPLE).",
     "bn": "কাবেরী অফিস স্পেসেস: অক্টোবর মাসের ভাড়ার ইনভয়েস {inv}। ভাড়া ₹{sub}, GST (18%) ₹{gst}, মোট ₹{tot}। প্রদানের তারিখ: {due}। আমাদের GSTIN {gstin} (SAMPLE)।",
     "hinglish": "Kaveri Office Spaces: October mahine ka rent invoice {inv}. Rent ₹{sub}, GST (18%) ₹{gst}, total ₹{tot}. Due date: {due}. Hamara GSTIN {gstin} (SAMPLE) hai."},
    {"hi": "मीरा टेक्सटाइल्स से: पिछला बिल ₹{prev} का आपने चुका दिया है, धन्यवाद। नया इनवॉइस {inv}: कपड़ा ₹{sub} + GST ₹{gst} = ₹{tot}, {due} तक देय। GSTIN {gstin} (SAMPLE)।",
     "mr": "मीरा टेक्सटाइल्सकडून: मागील ₹{prev} चे बिल तुम्ही भरले आहे, धन्यवाद. नवीन इनव्हॉइस {inv}: कापड ₹{sub} + GST ₹{gst} = ₹{tot}, {due} पर्यंत देय. GSTIN {gstin} (SAMPLE).",
     "ta": "மீரா டெக்ஸ்டைல்ஸ்: முந்தைய ₹{prev} பில்லை செலுத்தியதற்கு நன்றி. புதிய இன்வாய்ஸ் {inv}: துணி ₹{sub} + GST ₹{gst} = ₹{tot}, {due}-க்குள் செலுத்த வேண்டும். GSTIN {gstin} (SAMPLE).",
     "te": "మీరా టెక్స్‌టైల్స్: గత ₹{prev} బిల్లు చెల్లించినందుకు ధన్యవాదాలు. కొత్త ఇన్‌వాయిస్ {inv}: బట్ట ₹{sub} + GST ₹{gst} = ₹{tot}, {due} లోగా చెల్లించాలి. GSTIN {gstin} (SAMPLE).",
     "bn": "মীরা টেক্সটাইলস: আগের ₹{prev}-এর বিল মিটিয়ে দেওয়ার জন্য ধন্যবাদ। নতুন ইনভয়েস {inv}: কাপড় ₹{sub} + GST ₹{gst} = ₹{tot}, {due}-এর মধ্যে দিতে হবে। GSTIN {gstin} (SAMPLE)।",
     "hinglish": "Meera Textiles: pichhla ₹{prev} ka bill clear karne ke liye thanks. Naya invoice {inv}: kapda ₹{sub} + GST ₹{gst} = ₹{tot}, {due} tak due hai. GSTIN {gstin} (SAMPLE)."},
]

B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
STATES = ["27", "29", "33", "36", "19", "09", "07", "24"]  # MH KA TN TG WB UP DL GJ


def gstin(rnd):
    """Random GSTIN with a valid check character (state + PAN-shaped + entity + Z + check). Not a real registration."""
    pan = "".join(rnd.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(3)) + "F" + rnd.choice("ABCDEFGHJKLMNPRSTUVW") \
        + "".join(rnd.choice("0123456789") for _ in range(4)) + rnd.choice("ABCDEFGHJKLMNPQRSTUVWXYZ")
    body = rnd.choice(STATES) + pan + "1Z"
    s = sum((lambda p: p // 36 + p % 36)(B36.index(c) * (1 if i % 2 == 0 else 2)) for i, c in enumerate(body))
    return body + B36[(36 - s % 36) % 36]


def inr(n):
    """Indian digit grouping: 123456 -> 1,23,456"""
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    return ",".join([head] + parts + [tail]) if head else ",".join(parts + [tail])


def build():
    rnd = random.Random(10)
    items = []

    def vals(lang):
        m, d = rnd.randint(1, 9), rnd.randint(1, 28)  # Jan-Sep 2026: all in the past relative to the Oct test date
        return {"oid": f"SK{rnd.randint(10**7, 10**8 - 1)}", "amt_n": rnd.choice(range(349, 48000, 50)),
                "m": m, "d": d, "date": f"{d} {MONTHS[lang][m - 1]}"}

    for k, (intent, urg, texts) in enumerate(TRIAGE):
        for lang in LANGS:
            v = vals(lang)
            items.append({"id": f"triage-{k}-{lang}", "task": "triage", "lang": lang,
                          "text": texts[lang].format(oid=v["oid"], amt=inr(v["amt_n"])),
                          "gold": {"intent": intent, "urgency": urg, "language": lang}})
    for k, (issue_re, texts) in enumerate(CRM):
        for lang in LANGS:
            v = vals(lang)
            items.append({"id": f"crm-{k}-{lang}", "task": "crm", "lang": lang,
                          "text": texts[lang].format(oid=v["oid"], amt=inr(v["amt_n"]), date=v["date"]),
                          "gold": {"order_id": v["oid"], "amount": v["amt_n"], "date": f"2026-{v['m']:02d}-{v['d']:02d}",
                                   "issue_re": issue_re}})
    for k, (n_days, texts) in enumerate(REPLY):
        for lang in LANGS:
            v = vals(lang)
            items.append({"id": f"reply-{k}-{lang}", "task": "reply", "lang": lang,
                          "text": texts[lang].format(oid=v["oid"], amt=inr(v["amt_n"])),
                          "gold": {"refund_days": n_days, "order_id": v["oid"]}})
    for k, (sent, esc, texts) in enumerate(ESCALATE):
        for lang in LANGS:
            v = vals(lang)
            items.append({"id": f"escalate-{k}-{lang}", "task": "escalate", "lang": lang,
                          "text": texts[lang].format(oid=v["oid"]), "gold": {"sentiment": sent, "escalate": esc}})
    for k, texts in enumerate(EXTRACT):
        for lang in LANGS:
            v = vals(lang)
            sub = rnd.choice(range(1500, 250000, 50))
            gst = sub * 18 // 100  # multiples of 50 -> exact
            idate = vals(lang)
            due_m, due_d = rnd.randint(10, 12), rnd.randint(1, 28)
            inv = rnd.choice(["INV", "SLT", "GP", "AL/26-27/", "KOS-", "MT"]) + str(rnd.randint(100, 9999))
            g = gstin(rnd)
            items.append({"id": f"extract-{k}-{lang}", "task": "extract", "lang": lang,
                          "text": texts[lang].format(inv=inv, gstin=g, sub=inr(sub), gst=inr(gst), tot=inr(sub + gst),
                                                     due=f"{due_d} {MONTHS[lang][due_m - 1]} 2026",
                                                     idate=f"{idate['d']} {MONTHS[lang][idate['m'] - 1]} 2026",
                                                     prev=inr(rnd.choice(range(2000, 90000, 50)))),
                          "gold": {"invoice_no": inv, "gstin": g, "total_inr": sub + gst,
                                   "due_date": f"2026-{due_m:02d}-{due_d:02d}"}})
    return items


if __name__ == "__main__":
    assert gstin(random.Random(1))[-1] in B36
    assert inr(123456) == "1,23,456" and inr(1500) == "1,500" and inr(12345678) == "1,23,45,678"
    items = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"synthetic": True, "how_made": __doc__.strip(), "items": items}, ensure_ascii=False, indent=1))
    print(len(items), "items ->", OUT)
