"""Hindi (Devanagari) task specs. Identifiers, literals and numbers are kept exactly as in English."""
HI = {
1: """एक फ़ंक्शन लिखिए जो जाँचे कि कोई string वैध Aadhaar-format नंबर है या नहीं।
नियम: पहले सारे spaces हटा दीजिए। जो बचे वह ठीक 12 ASCII अंक होने चाहिए। पहला अंक 0 या 1 नहीं होना चाहिए।
आख़िरी अंक Verhoeff checksum अंक है: पूरा 12-अंकों का नंबर standard Verhoeff जाँच में पास होना चाहिए।
सभी नियम सही हों तो True लौटाइए, वरना False (कभी भी exception raise मत कीजिए)।""",
2: """एक फ़ंक्शन लिखिए जो ASCII अंकों की एक string (लंबाई >= 1) ले और वह Verhoeff check digit (0-9 का int) लौटाए
जिसे उसके अंत में जोड़ने पर पूरा नंबर Verhoeff checksum में पास हो जाए। Aadhaar-format नंबर का 12वाँ अंक पहले 11 अंकों से
इसी तरह बनाया जाता है। अगर input ख़ाली हो या उसमें अंकों के अलावा कुछ भी हो, तो ValueError raise कीजिए।""",
3: """एक फ़ंक्शन लिखिए जो भारतीय PAN (Permanent Account Number) को validate करे और धारक का प्रकार लौटाए।
पहले आगे-पीछे का whitespace हटाइए और uppercase में बदलिए। वैध PAN 10 अक्षरों का होता है: 5 अक्षर (letters), 4 अंक, 1 अक्षर।
चौथा अक्षर धारक का प्रकार बताता है: P = "Individual", C = "Company", H = "HUF", F = "Firm", A = "AOP",
T = "Trust", B = "BOI", L = "Local Authority", J = "Artificial Juridical Person", G = "Government".
धारक का प्रकार ठीक ऊपर लिखी string की तरह लौटाइए। अगर format ग़लत है या चौथा अक्षर इनमें से कोई नहीं है, तो None लौटाइए।""",
4: """GSTIN 15 अक्षरों का होता है; 15वाँ अक्षर पहले 14 अक्षरों से निकाला गया check character है।
एक फ़ंक्शन लिखिए जो यह check character लौटाए। Algorithm: alphabet "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ" लीजिए,
जिसमें हर अक्षर का मान उसका index (0-35) है। 14 अक्षरों में से position i (0 से शुरू) वाले हर अक्षर के मान को
i सम (even) हो तो 1 से और i विषम (odd) हो तो 2 से गुणा कीजिए; (product // 36) + (product % 36) को एक running sum में जोड़िए।
Check value = (36 - sum % 36) % 36 है, और नतीजा alphabet में उस index वाला अक्षर है।
अगर input ठीक 14 अक्षरों का न हो या उसके अक्षर इस alphabet से न हों (सिर्फ़ uppercase), तो ValueError raise कीजिए।""",
5: """एक फ़ंक्शन लिखिए जो GSTIN को validate और parse करे। पहले आगे-पीछे का whitespace हटाइए और uppercase कीजिए। वैध GSTIN 15 अक्षरों का होता है:
2 अंकों का state code (01 से 38 तक, या 97), फिर 10 अक्षरों का PAN (5 letters, 4 अंक, 1 letter), फिर entity number
(एक अक्षर, 1-9 या A-Z), फिर अक्षर "Z", फिर एक check character।
Check character पहले 14 अक्षरों से निकलता है: alphabet "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", मान = index;
0 से शुरू होने वाली position i पर मान को i सम हो तो 1 से, विषम हो तो 2 से गुणा कीजिए; (product // 36) + (product % 36) को sum में जोड़िए;
check = alphabet[(36 - sum % 36) % 36]।
वैध GSTIN के लिए {"state_code": "27", "pan": "AAPFU0939F", "entity_number": "1"} लौटाइए, वरना None।""",
6: """एक फ़ंक्शन लिखिए जो भारतीय बैंक के IFSC code को validate करे और उसे दो हिस्सों में बाँटे। पहले आगे-पीछे का whitespace हटाइए और uppercase कीजिए।
वैध IFSC ठीक 11 अक्षरों का होता है: 4 letters (bank code), फिर अंक 0, फिर 6 letters या अंक (branch code)।
एक tuple (bank_code, branch_code) लौटाइए, जैसे "SBIN0001234" -> ("SBIN", "001234")। अवैध हो तो None लौटाइए।""",
7: """एक फ़ंक्शन लिखिए जो paise में दी गई रकम (integer, 100 paise = 1 रुपया) को भारतीय अंक-समूहन (digit grouping) वाली
रुपये की string में बदले: रुपये वाले हिस्से के आख़िरी 3 अंक एक समूह बनाते हैं, और उससे पहले हर 2 अंक एक समूह बनाते हैं।
हमेशा ठीक 2 दशमलव स्थान दिखाइए और आगे रुपये का चिह्न "₹" लगाइए। ऋणात्मक रकम में "₹" से पहले "-" लगेगा।
उदाहरण: 123456789 -> "₹12,34,567.89", 100000 -> "₹1,000.00", -5050 -> "-₹50.50", 0 -> "₹0.00"।""",
8: """एक फ़ंक्शन लिखिए जो किसी non-negative integer (0 <= n < 1,000,000,000) को भारतीय गिनती प्रणाली में अंग्रेज़ी शब्दों में
बदले (thousand, lakh, crore — million या billion कभी नहीं)। नियम: सब कुछ lowercase; 21-99 की वे संख्याएँ जो दस की गुणज नहीं हैं,
hyphen के साथ लिखी जाती हैं ("forty-two"); "and" नहीं; शब्दों के बीच एक-एक space; 0 -> "zero"।
उदाहरण: 12345678 -> "one crore twenty-three lakh forty-five thousand six hundred seventy-eight"।
अगर n ऋणात्मक हो या >= 1,000,000,000 हो तो ValueError raise कीजिए।""",
9: """एक फ़ंक्शन लिखिए जो किसी non-negative integer (0 <= n < 1,000,000,000) को भारतीय प्रणाली में देवनागरी हिंदी शब्दों में बदले।
n को इन हिस्सों में बाँटिए: करोड़ वाला हिस्सा (n // 10^7), लाख वाला हिस्सा (दो अंक), हज़ार वाला हिस्सा (दो अंक), सैकड़े का अंक,
और आख़िरी दो अंक। हर non-zero हिस्से को उसके संख्या-शब्द और उसके बाद इकाई-शब्द से लिखिए:
करोड़, लाख, हज़ार, सौ (आख़िरी दो अंकों की कोई इकाई नहीं)। एक-एक space से जोड़िए; शून्य वाले हिस्से छोड़ दीजिए; 0 -> "शून्य"।
ठीक यही संख्या-शब्द इस्तेमाल कीजिए: 1 एक, 2 दो, 3 तीन, 4 चार, 5 पाँच, 6 छह, 7 सात, 8 आठ, 9 नौ, 10 दस, 20 बीस, 30 तीस,
40 चालीस, 50 पचास, 60 साठ, 70 सत्तर, 80 अस्सी, 90 नब्बे। Inputs में हर दो-अंकों वाला हिस्सा इन्हीं में से कोई मान होगा।
उदाहरण: 30405060 -> "तीन करोड़ चार लाख पाँच हज़ार साठ"।""",
10: """भारतीय वित्त वर्ष (financial year) 1 अप्रैल से 31 मार्च तक चलता है। एक फ़ंक्शन लिखिए जो किसी तारीख़ के लिए वित्त वर्ष का label
और तिमाही (quarter) लौटाए। Label का format: "FY" + शुरुआती साल + "-" + आख़िरी साल के अंतिम दो अंक, जैसे "FY2024-25"।
तिमाहियाँ: Q1 = अप्रैल-जून, Q2 = जुलाई-सितंबर, Q3 = अक्टूबर-दिसंबर, Q4 = जनवरी-मार्च।
उदाहरण: datetime.date(2025, 2, 10) -> ("FY2024-25", "Q4")।""",
11: """एक फ़ंक्शन लिखिए जो taxable value (paise में) पर GST निकाले। supplier_state और place_of_supply 2 अंकों के GST state codes हैं,
जैसे "27" या "07"। अगर दोनों बराबर हैं तो supply intra-state है: CGST और SGST लगाइए, दोनों आधी-आधी दर पर।
वरना supply inter-state है: पूरी दर पर IGST लगाइए।
हर tax की रकम को निकटतम paisa तक round कीजिए, और ठीक आधे (exact half) को ऊपर round कीजिए (round half up — Python का round() इस्तेमाल मत कीजिए)।
Intra-state में CGST और SGST अलग-अलग निकालिए (हर एक = taxable * rate/2 / 100, round किया हुआ); दोनों हमेशा बराबर होते हैं।
paise में एक dict {"cgst": int, "sgst": int, "igst": int} लौटाइए, जो tax लागू नहीं होते उनके लिए 0।
rate_pct भिन्नात्मक (fractional) भी हो सकता है, जैसे 0.25 या 1.5।""",
12: """एक फ़ंक्शन लिखिए जो किसी वेतनभोगी व्यक्ति का सालाना income tax इन नियमों से निकाले (रुपये, input integers में):
1. Taxable income = gross_salary - 75,000 standard deduction (0 से कम नहीं)।
2. Taxable income पर slab tax: 4,00,000 तक शून्य; 4,00,001-8,00,000 पर 5%; 8,00,001-12,00,000 पर 10%;
   12,00,001-16,00,000 पर 15%; 16,00,001-20,00,000 पर 20%; 20,00,001-24,00,000 पर 25%; 24,00,000 से ऊपर 30%।
   हर दर सिर्फ़ उसी band के अंदर वाली आय पर लगती है।
3. Rebate: अगर taxable income 12,00,000 या उससे कम है तो tax 0 है। (Marginal relief और surcharge को नज़रअंदाज़ कीजिए।)
4. Tax पर 4% health and education cess जोड़िए।
5. अंतिम रकम को निकटतम रुपये तक round कीजिए, ठीक आधे को ऊपर। एक int लौटाइए।""",
13: """एक फ़ंक्शन लिखिए जो लोन की मासिक EMI निकाले (भारतीय बैंकों का reducing-balance तरीका)।
r = annual_rate_pct / 12 / 100। EMI = P * r * (1 + r)^n / ((1 + r)^n - 1), जहाँ P रुपयों में principal है और n महीनों की संख्या।
अगर दर 0 है तो EMI = P / n। नतीजे को 2 दशमलव स्थानों (paise) तक round करके float लौटाइए।
अगर months <= 0 हो, या principal < 0 हो, या दर ऋणात्मक हो तो ValueError raise कीजिए।""",
14: """एक फ़ंक्शन लिखिए जो "ramesh.kumar@okaxis" जैसे UPI ID (VPA) को validate करे। पहले आगे-पीछे का whitespace हटाइए।
नियम: ठीक एक "@" हो। "@" से पहले वाला हिस्सा 2 से 64 अक्षरों का हो, जिसमें सिर्फ़ letters, अंक, ".", "_" और "-" हों;
वह letter या अंक से शुरू और ख़त्म होना चाहिए, और उसमें लगातार दो dots नहीं होने चाहिए।
"@" के बाद वाला हिस्सा (handle) 3 से 32 अक्षरों का हो, सिर्फ़ letters और अंक, और letter से शुरू हो।
Letters upper या lower case दोनों हो सकते हैं। True या False लौटाइए (कभी raise मत कीजिए)।""",
15: """एक फ़ंक्शन लिखिए जो इन भारतीय लिपियों के हर देसी अंक को उसके बराबर ASCII अंक 0-9 से बदल दे:
Devanagari, Bengali, Gurmukhi, Gujarati, Odia, Tamil, Telugu, Kannada, Malayalam। बाक़ी हर अक्षर (letters, ASCII अंक,
विराम-चिह्न, ग़ैर-भारतीय लिपियों के अंक जैसे Arabic-Indic अंक) वैसे ही रहें।
उदाहरण: "कुल ₹१,२५०" -> "कुल ₹1,250", "௨௦௨௪" -> "2024"।""",
16: """एक फ़ंक्शन लिखिए जो text के हर ASCII अंक 0-9 को दी गई लिपि के देसी अंक से बदल दे। script इनमें से एक है
(case-insensitive): "devanagari", "bengali", "gurmukhi", "gujarati", "odia", "tamil", "telugu", "kannada", "malayalam"।
बाक़ी सारे अक्षर वैसे ही रहें। किसी और script नाम के लिए ValueError raise कीजिए।
उदाहरण: ascii_to_indic_digits("₹1,250", "devanagari") -> "₹१,२५०"।""",
17: """एक फ़ंक्शन लिखिए जो दी गई prefix table की मदद से किसी भारतीय PIN code का राज्य ढूँढे, जैसे
{"11": "Delhi", "40": "Maharashtra", "403": "Goa", "56": "Karnataka"}। पहले PIN से spaces हटाइए।
वैध PIN ठीक 6 ASCII अंकों का होता है और 0 से शुरू नहीं होता; अवैध PIN के लिए None लौटाइए।
Table की जिन keys से PIN शुरू होता है, उनमें से सबसे लंबी key लीजिए। उसका राज्य लौटाइए, या कोई key match न हो तो None।""",
18: """एक फ़ंक्शन लिखिए जो भारतीय रेलवे टिकट की booking status string को parse करे। Case और आगे-पीछे के whitespace को नज़रअंदाज़ कीजिए;
हिस्से "/" या spaces (एक या ज़्यादा) से अलग हो सकते हैं। Supported रूप:
- Confirmed: "CNF/B2/45" या "CNF/B2/45/LB" -> {"status": "CNF", "coach": "B2", "berth": 45, "berth_type": "LB"}
  (berth_type न हो तो None; coach और berth_type uppercase में लौटाइए; berth एक int है)।
- RAC: "RAC 12" या "RAC/12" -> {"status": "RAC", "number": 12}
- Waitlist: "WL 34", "GNWL 34", "RLWL/5", "PQWL 2", "TQWL 9" -> {"status": "WL", "list": "GNWL", "number": 34}
  जहाँ list वही waitlist code है जो लिखा है, uppercase में ("WL", "GNWL", "RLWL", "PQWL" या "TQWL")।
बाक़ी किसी भी चीज़ के लिए None लौटाइए (non-numeric berth/number समेत)।""",
19: """एक फ़ंक्शन लिखिए जो IST (UTC+05:30) में भारतीय format वाले local time string को UTC में बदले।
Input format: "DD/MM/YYYY hh:mm AM" या "... PM" (12-घंटे की घड़ी; AM/PM case-insensitive; दिन और महीना हमेशा 2 अंकों के,
घंटा 1 या 2 अंकों का)। 12:xx AM आधी रात के ठीक बाद है, 12:xx PM दोपहर के ठीक बाद।
UTC को ISO format "YYYY-MM-DDTHH:MM:00Z" में लौटाइए। अगर string या तारीख़/समय अवैध हो तो ValueError raise कीजिए।
उदाहरण: "01/04/2025 12:15 AM" -> "2025-03-31T18:45:00Z"।""",
20: """एक फ़ंक्शन लिखिए जो payment card नंबर का network पहचाने और उसका Luhn checksum जाँचे।
पहले spaces और hyphens हटाइए। जो बचे वह 12-19 ASCII अंक न हो तो None लौटाइए।
Prefix से network: 34 या 37 से शुरू हो तो "Amex"; 4 से शुरू हो तो "Visa"; पहले दो अंक 51-55 हों या पहले चार अंक
2221-2720 हों तो "Mastercard"; 60, 65, 81, 82 या 508 से शुरू हो तो "RuPay"; वरना "Unknown"।
(network, luhn_ok) लौटाइए, जहाँ नंबर Luhn जाँच में पास हो तो luhn_ok True है।""",
21: """एक फ़ंक्शन लिखिए जो भारतीय मोबाइल नंबर को "+91XXXXXXXXXX" रूप में normalise करे।
पहले spaces, hyphens, dots और कोष्ठक (parentheses) हटाइए। फिर एक country/trunk prefix हटाइए: शुरू का "+91", या शुरू का
"0091", या शुरू का "91" अगर ठीक 12 अंक बचे हों, या शुरू का "0" अगर ठीक 11 अंक बचे हों।
जो बचे वह ठीक 10 ASCII अंक होने चाहिए जो 6, 7, 8 या 9 से शुरू हों; तब "+91" + वे 10 अंक लौटाइए, वरना None।""",
22: """एक फ़ंक्शन लिखिए जो भारतीय वाहन registration नंबर को parse करे। पहले uppercase कीजिए और spaces व hyphens हटाइए।
दो format वैध हैं:
1. Regular: state code (2 letters), RTO code (1 या 2 अंक), series (1 से 3 letters), नंबर (1 से 4 अंक)।
   State code इनमें से एक होना चाहिए: AN AP AR AS BR CH CG DD DL GA GJ HP HR JH JK KA KL LA LD MH ML MN MP MZ NL OD PB PY RJ SK TN TR TS UK UP WB.
   {"type": "regular", "state": "MH", "rto": "02", "series": "AB", "number": "0042"} लौटाइए, जिसमें rto को 2 अंकों तक
   और number को 4 अंकों तक आगे शून्य लगाकर (zero-padded) भरा जाए।
2. Bharat series: 2 अंकों का साल, "BH", 4 अंक, 1 या 2 letters, जैसे "22 BH 1234 AA"।
   {"type": "BH", "year": 2022, "number": "1234", "series": "AA"} लौटाइए।
कोई भी format match न हो तो None लौटाइए।""",
23: """एक फ़ंक्शन लिखिए जो GST invoice का total निकाले। items एक list है जिसमें (quantity, unit_price_paise, gst_rate_pct) हैं।
1. Taxable value = सभी lines का quantity * unit_price का जोड़ (paise)।
2. Lines को GST rate के हिसाब से group कीजिए। हर rate के लिए tax उस rate group की कुल taxable value पर निकलेगा:
   intra-state: CGST = SGST = group_taxable * rate / 2 / 100 हर एक; inter-state: IGST = group_taxable * rate / 100।
   हर tax रकम (हर rate group, हर tax) को निकटतम paisa तक round कीजिए, ठीक आधे को ऊपर।
3. Rounding से पहले का total = taxable + सारे taxes। Grand total को निकटतम पूरे रुपये (100 paise) तक round कीजिए,
   ठीक आधे (50 paise) को ऊपर। round_off = grand_total - rounding से पहले का total (ऋणात्मक भी हो सकता है)।
{"taxable", "cgst", "sgst", "igst", "round_off", "grand_total"} लौटाइए — सब int paise में।""",
24: """भारतीय data-protection नियमों का पालन करने के लिए एक फ़ंक्शन लिखिए जो free text के अंदर Aadhaar नंबरों को mask करे।
Candidate 12 अंकों का होता है, जो या तो लगातार लिखे हों या 4-4 अंकों के तीन समूहों में, जहाँ समूहों के बीच का हर gap
एक space या एक hyphen हो; उसके ठीक पहले या ठीक बाद कोई दूसरा अंक नहीं होना चाहिए।
Candidate को तभी mask कीजिए जब वह वैध Aadhaar-format नंबर हो: पहला अंक 0 या 1 नहीं, और 12 अंक
Verhoeff checksum में पास हों। हर वैध नंबर को "XXXX XXXX " और उसके बाद उसके आख़िरी 4 अंकों से बदल दीजिए। बाक़ी सब वैसा ही छोड़िए।""",
25: """एक फ़ंक्शन लिखिए जो भारतीयों के लिखने के ढंग वाली रकम को parse करे और पूरे रुपये (int) लौटाए।
Steps: आगे-पीछे का whitespace हटाइए; शुरू में currency marker हो तो हटाइए ("₹", "Rs.", "Rs", "INR", case-insensitive);
commas और spaces हटाइए। बाक़ी एक संख्या है (integer या decimal) जिसके बाद optional इकाई हो सकती है (case-insensitive):
"crore", "crores" या "cr" = 1,00,00,000; "lakh", "lakhs", "lac", "lacs" या "l" = 1,00,000; "k" या "thousand" = 1,000।
गुणा कीजिए, फिर निकटतम रुपये तक round कीजिए (ठीक आधे को ऊपर)। अगर text parse न हो सके तो ValueError raise कीजिए।
उदाहरण: "1.5 crore" -> 15000000, "₹2,50,000" -> 250000, "Rs. 12.5k" -> 12500, "3.25L" -> 325000।""",
26: """एक फ़ंक्शन लिखिए जो भारतीय income-tax नियमों के तहत HRA (house rent allowance) छूट (exemption) निकाले। सभी inputs
सालाना रुपये में हैं (basic salary में DA शामिल है)। छूट इनमें से सबसे कम है:
(a) असल में मिला HRA; (b) दिया गया किराया घटा basic का 10% (0 से कम नहीं); (c) शहर metro हो तो basic का 50%,
वरना basic का 40%। नतीजे को निकटतम रुपये तक round कीजिए (ठीक आधे को ऊपर) और int लौटाइए।""",
27: """एक फ़ंक्शन लिखिए जो इन नियमों से देय gratuity निकाले (Payment of Gratuity Act की तरह)।
monthly_salary आख़िरी मिला basic + DA है, रुपये में; सेवा पूरे किए गए साल और अतिरिक्त महीनों (0-11) में दी गई है।
1. अगर पूरे किए गए साल < 5 हैं, तो gratuity 0 है।
2. वरना गिने जाने वाले साल = years, और अगर अतिरिक्त महीने 6 से ज़्यादा हैं तो 1 और (ठीक 6 महीने नहीं गिने जाते)।
3. Gratuity = 15 * monthly_salary * counted_years / 26, निकटतम रुपये तक round (ठीक आधे को ऊपर)।
4. रकम की अधिकतम सीमा 20,00,000 है। int लौटाइए।""",
28: """एक फ़ंक्शन लिखिए जो भारत में मासिक basic + DA (रुपये) के लिए Employees' Provident Fund का मासिक योगदान निकाले।
- कर्मचारी का योगदान = basic_da का 12%।
- Employer का pension (EPS) हिस्सा = wage का 8.33%, जहाँ wage की सीमा 15,000 है (min(basic_da, 15000) लीजिए)।
- Employer का EPF हिस्सा = (basic_da का 12%) - EPS हिस्सा, पहले से round की हुई values से।
हर प्रतिशत वाली रकम को निकटतम रुपये तक round कीजिए, ठीक आधे को ऊपर।
{"employee": int, "employer_eps": int, "employer_epf": int} लौटाइए।""",
29: """एक फ़ंक्शन लिखिए जो तिमाही चक्रवृद्धि (quarterly compounding) वाली भारतीय बैंक fixed deposit की maturity value निकाले।
Maturity = principal * (1 + annual_rate_pct / 400) ** (months / 3)। months 3 का धनात्मक गुणज होना चाहिए, वरना
ValueError raise कीजिए। नतीजे को 2 दशमलव स्थानों तक round करके float लौटाइए।""",
30: """भारत में दुकानें अक्सर GST-सहित दाम बताती हैं। एक फ़ंक्शन लिखिए जो GST-सहित रकम (paise) को taxable value और
GST रकम में बाँटे। taxable = inclusive * 100 / (100 + rate_pct), निकटतम paisa तक round, ठीक आधे को ऊपर;
gst = inclusive - taxable (ताकि दोनों का जोड़ हमेशा बिल्कुल बराबर हो)। (taxable, gst) को ints के रूप में लौटाइए।""",
31: """एक फ़ंक्शन लिखिए जो भारतीय day-first शैली में लिखी तारीख़ को parse करे और datetime.date लौटाए।
क्रम हमेशा दिन, महीना, साल होता है। Separators "/", "-", "." या spaces हो सकते हैं। महीना एक संख्या (1 या 2 अंक),
3 अक्षरों का अंग्रेज़ी संक्षिप्त नाम ("Aug") या पूरा अंग्रेज़ी नाम ("August") हो सकता है, case-insensitive। साल 4 अंकों का होता है,
या 2 अंकों का जिसका मतलब 2000-2099 है। दिन 1 या 2 अंकों का। अगर format या तारीख़ अवैध हो तो ValueError raise कीजिए।
उदाहरण: "15/08/2024", "15-Aug-2024", "5.9.24", "1 January 2025"।""",
32: """एक फ़ंक्शन लिखिए जो भारतीय Corporate Identification Number (CIN) को validate और parse करे। पहले strip और uppercase कीजिए।
CIN 21 अक्षरों का होता है: 1 अक्षर "L" (listed) या "U" (unlisted); 5 अंकों का industry code; 2 letters का state code;
निगमन (incorporation) के साल के 4 अंक (1850-2100 के बीच होना चाहिए); company type के 3 letters, जो इनमें से एक हों:
PLC, PTC, GOI, SGC, FLC, GAP, NPL, ULL, ULT, OPC; 6 अंकों का registration number।
{"listed": bool, "industry": "72200", "state": "MH", "year": 2010, "type": "PTC", "reg_no": "123456"} लौटाइए
(year एक int, बाक़ी strings), या अवैध हो तो None।""",
33: """एक फ़ंक्शन लिखिए जो भारत में QR-code payments के लिए इस्तेमाल होने वाला UPI deep link बनाए:
"upi://pay?pa=<vpa>&pn=<name>&am=<amount>&cu=INR" और, सिर्फ़ तभी जब note दिया गया हो और ख़ाली न हो, अंत में "&tn=<note>"।
Amount रुपयों में ठीक 2 दशमलव के साथ होगा (amount_paise 12345 -> "123.45")।
हर value (pa, pn, am, tn) को ठीक वैसे percent-encode कीजिए जैसे Python का urllib.parse.quote(value, safe="@") करता है
(यानी spaces %20 बनते हैं और "@" वैसा ही रहता है)। अगर amount_paise <= 0 हो तो ValueError raise कीजिए।""",
34: """भारतीय बैंक सभी रविवारों को और हर महीने के दूसरे और चौथे शनिवार को बंद रहते हैं (पहला, तीसरा और पाँचवाँ शनिवार
कामकाजी दिन हैं)। एक फ़ंक्शन लिखिए जो start से end तक (दोनों शामिल) बैंक के कामकाजी दिन गिने, और holidays में दी गई
हर तारीख़ को भी बाहर रखे। अगर start, end के बाद हो तो 0 लौटाइए।""",
35: """एक फ़ंक्शन लिखिए जो (paise में दी गई) रकम को भारतीय cheque के लिए शब्दों में लिखे, भारतीय प्रणाली में
(Thousand, Lakh, Crore)। रुपये वाला हिस्सा n < 1,000,000,000 होना चाहिए। Format:
paise वाला हिस्सा 0 हो तो "Rupees <rupee words> Only", वरना "Rupees <rupee words> and <paise words> Paise Only"।
शब्दों के नियम: हर शब्द capital letter से शुरू हो; 21-99 की दस की ग़ैर-गुणज संख्याएँ hyphen से लिखी जाएँ और दोनों हिस्से capital हों
("Forty-Two"); संख्या के अंदर "and" नहीं; 0 है "Zero"।
उदाहरण: 123456789 -> "Rupees Twelve Lakh Thirty-Four Thousand Five Hundred Sixty-Seven and Eighty-Nine Paise Only"।""",
36: """एक फ़ंक्शन लिखिए जो telescopic slab tariff से घरेलू बिजली बिल निकाले (हर दर सिर्फ़ अपने slab के अंदर वाली units पर लगती है):
units 1-100 पर ₹3.00 प्रति unit, 101-200 पर ₹4.50, 201-500 पर ₹6.00, 500 से ऊपर ₹7.50।
Fixed charge: sanctioned load के हर kW पर ₹50, जहाँ load को ऊपर की ओर पूरे kW तक round किया जाए (कम से कम 1 kW)।
Electricity duty: सिर्फ़ energy charge का 5% (fixed charge का नहीं)।
Total = energy charge + fixed charge + duty, 2 दशमलव तक round (ठीक आधे को ऊपर)। float लौटाइए।""",
37: """एक फ़ंक्शन लिखिए जो रुपये की रकम को छोटे रूप में format करे, जैसे भारतीय news और dashboards करते हैं।
- अगर abs(amount) >= 1,00,00,000: करोड़ में मान, 2 दशमलव तक round (आधे को ऊपर), पीछे के शून्य और आख़िरी
  "." हटाकर, उसके बाद " Cr" (12500000 -> "1.25 Cr", 10000000 -> "1 Cr")।
- वरना अगर abs(amount) >= 1,00,000: इसी तरह लाख में, " L" के साथ (150000 -> "1.5 L", 1234567 -> "12.35 L")।
- वरना: भारतीय digit grouping के साथ integer (99999 -> "99,999", 500 -> "500")।
इकाई rounding से पहले वाले मान से तय होती है (9999999 -> "100 L")। ऋणात्मक रकम के आगे "-" लगेगा।""",
38: """GST invoice नंबर एक वित्त वर्ष (1 अप्रैल - 31 मार्च) के अंदर क्रमवार होने चाहिए। एक फ़ंक्शन लिखिए जो अगला invoice नंबर
"INV/<FY>/<seq>" format में लौटाए, जहाँ FY "2024-25" जैसा है (शुरुआती साल, "-", आख़िरी साल के अंतिम 2 अंक)
और seq कम से कम 4 अंकों तक zero-padded है ("0001"; "9999" के बाद "10000" आता है)।
prev इसी format में पिछला invoice नंबर है, या None। अगर prev None है या उसका FY तारीख़ d के FY से अलग है, तो
0001 से शुरू कीजिए; वरना prev के sequence में एक जोड़िए।
उदाहरण: next_invoice_number("INV/2024-25/0041", date(2025, 3, 31)) -> "INV/2024-25/0042"।""",
39: """एक फ़ंक्शन लिखिए जो किसी भारतीय उद्यम को इन MSME सीमाओं के तहत वर्गीकृत करे (दोनों मान करोड़ रुपये में; सीमा का
मतलब है "उस तक, उसे मिलाकर"):
Micro: investment <= 2.5 और turnover <= 10। Small: investment <= 25 और turnover <= 100।
Medium: investment <= 125 और turnover <= 500। किसी श्रेणी के लिए दोनों शर्तें पूरी होनी चाहिए; Micro से ऊपर की ओर जाँचिए और
जो पहली फ़िट हो वह लौटाइए: "Micro", "Small", "Medium", वरना "Not MSME"। कोई भी मान ऋणात्मक हो तो ValueError raise कीजिए।""",
40: """एक फ़ंक्शन लिखिए जो बताए कि भारत में किसी दी गई तारीख़ तक कुल कितना advance tax भर दिया जाना चाहिए था (cumulative)।
total_tax उस वित्त वर्ष (1 अप्रैल - 31 मार्च) का अनुमानित tax है जिसमें on_date आती है।
अगर total_tax 10,000 से कम है तो कुछ देय नहीं है (0 लौटाइए)। वरना कुल देय रकम:
15 जून से पहले: 0; 15 जून से: 15%; 15 सितंबर से: 45%; 15 दिसंबर से: 75%; 15 मार्च से: 100%
(किस्त वाली तारीख़ ख़ुद भी गिनी जाती है, जैसे 15 जून को 15% देय है)। निकटतम रुपये तक round कीजिए, ठीक आधे को ऊपर। int लौटाइए।""",
}
