"""Hinglish (romanised, code-mixed Hindi-English) task specs, written the way Indian developers message each other.
Identifiers, literals and numbers are kept exactly as in English."""
HINGLISH = {
1: """Ek function likho jo check kare ki string ek valid Aadhaar-format number hai ya nahi.
Rules: pehle saare spaces hata do. Jo bache woh exactly 12 ASCII digits hone chahiye. Pehla digit 0 ya 1 nahi hona chahiye.
Last digit Verhoeff checksum digit hai: poora 12-digit number standard Verhoeff check pass karna chahiye.
Saare rules sahi hon toh True return karo, warna False (kabhi bhi exception raise mat karna).""",
2: """Ek function likho jo ASCII digits ki string le (length >= 1) aur woh Verhoeff check digit (0-9 ka int) return kare
jo end mein lagane se poora number Verhoeff checksum pass kar le. Aadhaar-format number ka 12th digit pehle 11 digits se
aise hi banta hai. Agar input empty hai ya usme digits ke alawa kuch bhi hai, toh ValueError raise karo.""",
3: """Ek function likho jo Indian PAN (Permanent Account Number) validate kare aur holder type return kare.
Pehle aage-peeche ka whitespace strip karo aur uppercase karo. Valid PAN 10 characters ka hota hai: 5 letters, 4 digits, 1 letter.
4th character holder type batata hai: P = "Individual", C = "Company", H = "HUF", F = "Firm", A = "AOP",
T = "Trust", B = "BOI", L = "Local Authority", J = "Artificial Juridical Person", G = "Government".
Holder type exactly upar likhi string ki tarah return karo. Format galat ho ya 4th character inme se koi na ho, toh None return karo.""",
4: """GSTIN 15 characters ka hota hai; 15th character pehle 14 characters se nikala gaya check character hai.
Ek function likho jo yeh check character return kare. Algorithm: alphabet "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ" lo,
har character ki value uska index (0-35) hai. 14 characters mein position i (0-based) wale har character ki value ko
i even ho toh 1 se aur i odd ho toh 2 se multiply karo; (product // 36) + (product % 36) ko running sum mein add karo.
Check value = (36 - sum % 36) % 36, aur result alphabet mein us index wala character hai.
Agar input exactly 14 characters ka nahi hai ya characters is alphabet ke nahi hain (sirf uppercase), toh ValueError raise karo.""",
5: """Ek function likho jo GSTIN validate aur parse kare. Pehle whitespace strip karo aur uppercase karo. Valid GSTIN 15 chars ka hota hai:
2-digit state code (01 se 38 tak, ya 97), phir 10-character PAN (5 letters, 4 digits, 1 letter), phir entity number
(ek character, 1-9 ya A-Z), phir letter "Z", phir ek check character.
Check character pehle 14 characters se nikalta hai: alphabet "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", value = index;
0-based position i par value ko i even ho toh 1 se, odd ho toh 2 se multiply karo; (product // 36) + (product % 36) sum mein add karo;
check = alphabet[(36 - sum % 36) % 36].
Valid GSTIN ke liye {"state_code": "27", "pan": "AAPFU0939F", "entity_number": "1"} return karo, warna None.""",
6: """Ek function likho jo Indian bank ka IFSC code validate kare aur split kare. Pehle whitespace strip karo aur uppercase karo.
Valid IFSC exactly 11 characters ka hota hai: 4 letters (bank code), phir digit 0, phir 6 letters ya digits (branch code).
Tuple (bank_code, branch_code) return karo, jaise "SBIN0001234" -> ("SBIN", "001234"). Invalid ho toh None return karo.""",
7: """Ek function likho jo paise mein di gayi amount (integer, 100 paise = 1 rupee) ko Indian digit grouping wali rupee string
mein format kare: rupee part ke last 3 digits ek group, aur usse pehle har 2 digits ek group.
Hamesha exactly 2 decimal places dikhao aur aage rupee sign "₹" lagao. Negative amount mein "₹" se pehle "-" aayega.
Examples: 123456789 -> "₹12,34,567.89", 100000 -> "₹1,000.00", -5050 -> "-₹50.50", 0 -> "₹0.00".""",
8: """Ek function likho jo non-negative integer (0 <= n < 1,000,000,000) ko Indian numbering system mein English words mein
convert kare (thousand, lakh, crore — million ya billion kabhi nahi). Rules: sab lowercase; 21-99 ke jo numbers ten ke
multiple nahi hain woh hyphen ke saath likhe jaate hain ("forty-two"); "and" nahi; words ke beech single space; 0 -> "zero".
Example: 12345678 -> "one crore twenty-three lakh forty-five thousand six hundred seventy-eight".
Agar n negative ho ya >= 1,000,000,000 ho toh ValueError raise karo.""",
9: """Ek function likho jo non-negative integer (0 <= n < 1,000,000,000) ko Indian system mein Devanagari Hindi words mein
convert kare. n ko in parts mein todo: crore part (n // 10^7), lakh part (do digits), thousand part (do digits), hundreds digit,
aur last do digits. Har non-zero part ko uske number word aur phir unit word se likho:
करोड़, लाख, हज़ार, सौ (last do digits ka koi unit nahi). Single spaces se join karo; zero parts skip karo; 0 -> "शून्य".
Exactly yahi number words use karo: 1 एक, 2 दो, 3 तीन, 4 चार, 5 पाँच, 6 छह, 7 सात, 8 आठ, 9 नौ, 10 दस, 20 बीस, 30 तीस,
40 चालीस, 50 पचास, 60 साठ, 70 सत्तर, 80 अस्सी, 90 नब्बे. Inputs mein har two-digit part inhi values mein se ek hoga.
Example: 30405060 -> "तीन करोड़ चार लाख पाँच हज़ार साठ".""",
10: """Indian financial year 1 April se 31 March tak chalta hai. Ek function likho jo kisi date ke liye financial year label
aur quarter return kare. Label format: "FY" + start year + "-" + end year ke last do digits, jaise "FY2024-25".
Quarters: Q1 = April-June, Q2 = July-September, Q3 = October-December, Q4 = January-March.
Example: datetime.date(2025, 2, 10) -> ("FY2024-25", "Q4").""",
11: """Ek function likho jo taxable value (paise mein) par GST calculate kare. supplier_state aur place_of_supply 2-digit GST
state codes hain jaise "27" ya "07". Dono same hain toh supply intra-state hai: CGST aur SGST lagao, dono half rate par.
Warna inter-state hai: full rate par IGST lagao.
Har tax amount ko nearest paisa tak round karo, exact half ho toh upar (round half up — Python ka round() use mat karna).
Intra-state mein CGST aur SGST alag-alag nikalo (har ek = taxable * rate/2 / 100, rounded); dono hamesha equal hote hain.
Paise mein dict {"cgst": int, "sgst": int, "igst": int} return karo, jo tax apply nahi hota uske liye 0.
rate_pct fractional bhi ho sakta hai, jaise 0.25 ya 1.5.""",
12: """Ek function likho jo salaried individual ka annual income tax in rules se nikale (rupees, integers input):
1. Taxable income = gross_salary - 75,000 standard deduction (0 se kam nahi).
2. Taxable income par slab tax: 4,00,000 tak nil; 4,00,001-8,00,000 par 5%; 8,00,001-12,00,000 par 10%;
   12,00,001-16,00,000 par 15%; 16,00,001-20,00,000 par 20%; 20,00,001-24,00,000 par 25%; 24,00,000 se upar 30%.
   Har rate sirf usi band ke andar wali income par lagta hai.
3. Rebate: agar taxable income 12,00,000 ya usse kam hai toh tax 0 hai. (Marginal relief aur surcharge ignore karo.)
4. Tax par 4% health and education cess add karo.
5. Final amount ko nearest rupee tak round karo, exact half upar. Int return karo.""",
13: """Ek function likho jo loan ki monthly EMI calculate kare (Indian bank wala reducing-balance method).
r = annual_rate_pct / 12 / 100. EMI = P * r * (1 + r)^n / ((1 + r)^n - 1), jahan P rupees mein principal hai aur n months ki
sankhya. Agar rate 0 hai toh EMI = P / n. Result ko 2 decimal places (paise) tak round karke float return karo.
Agar months <= 0 ho ya principal < 0 ho ya rate negative ho toh ValueError raise karo.""",
14: """Ek function likho jo UPI ID (VPA) validate kare, jaise "ramesh.kumar@okaxis". Pehle aage-peeche ka whitespace strip karo.
Rules: exactly ek "@". "@" se pehle wala part 2 se 64 characters ka ho, sirf letters, digits, ".", "_" aur "-";
woh letter ya digit se start aur end hona chahiye, aur usme do consecutive dots nahi hone chahiye.
"@" ke baad wala part (handle) 3 se 32 characters ka ho, sirf letters aur digits, aur letter se start ho.
Letters upper ya lower case dono ho sakte hain. True ya False return karo (kabhi raise mat karna).""",
15: """Ek function likho jo in Indian scripts ke har native digit ko matching ASCII digit 0-9 se replace kare:
Devanagari, Bengali, Gurmukhi, Gujarati, Odia, Tamil, Telugu, Kannada, Malayalam. Baaki har character (letters, ASCII digits,
punctuation, non-Indian scripts ke digits jaise Arabic-Indic digits) waise hi rahe.
Example: "कुल ₹१,२५०" -> "कुल ₹1,250", "௨௦௨௪" -> "2024".""",
16: """Ek function likho jo text ke har ASCII digit 0-9 ko di gayi script ke native digit se replace kare. script inme se ek hai
(case-insensitive): "devanagari", "bengali", "gurmukhi", "gujarati", "odia", "tamil", "telugu", "kannada", "malayalam".
Baaki saare characters waise hi rahein. Kisi aur script name ke liye ValueError raise karo.
Example: ascii_to_indic_digits("₹1,250", "devanagari") -> "₹१,२५०".""",
17: """Ek function likho jo di gayi prefix table se Indian PIN code ka state dhoondhe, jaise
{"11": "Delhi", "40": "Maharashtra", "403": "Goa", "56": "Karnataka"}. Pehle PIN se spaces hata do.
Valid PIN exactly 6 ASCII digits ka hota hai aur 0 se start nahi hota; invalid PIN ke liye None return karo.
Table ki jin keys se PIN start hota hai, unme se sabse lambi key use karo. Uska state return karo, ya koi key match na ho toh None.""",
18: """Ek function likho jo Indian Railways ticket ki booking status string parse kare. Case aur aage-peeche ka whitespace ignore karo;
parts "/" ya spaces (ek ya zyada) se separate ho sakte hain. Supported forms:
- Confirmed: "CNF/B2/45" ya "CNF/B2/45/LB" -> {"status": "CNF", "coach": "B2", "berth": 45, "berth_type": "LB"}
  (berth_type na ho toh None; coach aur berth_type uppercase mein return karo; berth int hai).
- RAC: "RAC 12" ya "RAC/12" -> {"status": "RAC", "number": 12}
- Waitlist: "WL 34", "GNWL 34", "RLWL/5", "PQWL 2", "TQWL 9" -> {"status": "WL", "list": "GNWL", "number": 34}
  jahan list wahi waitlist code hai jo likha hai, uppercase mein ("WL", "GNWL", "RLWL", "PQWL" ya "TQWL").
Baaki kisi bhi cheez ke liye None return karo (non-numeric berth/number bhi).""",
19: """Ek function likho jo IST (UTC+05:30) mein Indian-format local time string ko UTC mein convert kare.
Input format: "DD/MM/YYYY hh:mm AM" ya "... PM" (12-hour clock; AM/PM case-insensitive; day aur month hamesha 2 digits,
hour 1 ya 2 digits). 12:xx AM midnight ke just baad hai, 12:xx PM noon ke just baad.
UTC ko ISO format "YYYY-MM-DDTHH:MM:00Z" mein return karo. String ya date/time invalid ho toh ValueError raise karo.
Example: "01/04/2025 12:15 AM" -> "2025-03-31T18:45:00Z".""",
20: """Ek function likho jo payment card number ka network identify kare aur Luhn checksum check kare.
Pehle spaces aur hyphens hata do. Jo bache woh 12-19 ASCII digits nahi hai toh None return karo.
Prefix se network: 34 ya 37 se start ho toh "Amex"; 4 se start ho toh "Visa"; pehle do digits 51-55 hon ya pehle chaar digits
2221-2720 hon toh "Mastercard"; 60, 65, 81, 82 ya 508 se start ho toh "RuPay"; warna "Unknown".
(network, luhn_ok) return karo jahan number Luhn check pass kare toh luhn_ok True hai.""",
21: """Ek function likho jo Indian mobile number ko "+91XXXXXXXXXX" form mein normalise kare.
Pehle spaces, hyphens, dots aur brackets (parentheses) hata do. Phir ek country/trunk prefix hatao: shuru ka "+91", ya shuru ka
"0091", ya shuru ka "91" agar exactly 12 digits bache hon, ya shuru ka "0" agar exactly 11 digits bache hon.
Jo bache woh exactly 10 ASCII digits hone chahiye jo 6, 7, 8 ya 9 se start hon; tab "+91" + woh 10 digits return karo, warna None.""",
22: """Ek function likho jo Indian vehicle registration number parse kare. Pehle uppercase karo aur spaces aur hyphens hata do.
Do formats valid hain:
1. Regular: state code (2 letters), RTO code (1 ya 2 digits), series (1 se 3 letters), number (1 se 4 digits).
   State code inme se ek hona chahiye: AN AP AR AS BR CH CG DD DL GA GJ HP HR JH JK KA KL LA LD MH ML MN MP MZ NL OD PB PY RJ SK TN TR TS UK UP WB.
   {"type": "regular", "state": "MH", "rto": "02", "series": "AB", "number": "0042"} return karo, rto ko 2 digits tak
   aur number ko 4 digits tak zero-pad karke.
2. Bharat series: 2-digit year, "BH", 4 digits, 1 ya 2 letters, jaise "22 BH 1234 AA".
   {"type": "BH", "year": 2022, "number": "1234", "series": "AA"} return karo.
Koi bhi format match na ho toh None return karo.""",
23: """Ek function likho jo GST invoice ka total nikale. items ek list hai (quantity, unit_price_paise, gst_rate_pct) ki.
1. Taxable value = saari lines ka quantity * unit_price ka sum (paise).
2. Lines ko GST rate ke hisaab se group karo. Har rate ke liye tax us rate group ki total taxable value par lagega:
   intra-state: CGST = SGST = group_taxable * rate / 2 / 100 har ek; inter-state: IGST = group_taxable * rate / 100.
   Har tax amount (har rate group, har tax) ko nearest paisa tak round karo, exact half upar.
3. Rounding se pehle ka total = taxable + saare taxes. Grand total ko nearest whole rupee (100 paise) tak round karo,
   exact half (50 paise) upar. round_off = grand_total - rounding se pehle ka total (negative bhi ho sakta hai).
{"taxable", "cgst", "sgst", "igst", "round_off", "grand_total"} return karo — sab int paise mein.""",
24: """Indian data-protection rules follow karne ke liye ek function likho jo free text ke andar Aadhaar numbers ko mask kare.
Candidate 12 digits ka hota hai, ya toh continuous likha ho ya 4-4 digits ke teen groups mein, jahan groups ke beech har gap
ek single space ya ek single hyphen ho; uske turant pehle ya turant baad koi aur digit nahi hona chahiye.
Candidate ko tabhi mask karo jab woh valid Aadhaar-format number ho: pehla digit 0 ya 1 nahi, aur 12 digits Verhoeff
checksum pass karein. Har valid number ko "XXXX XXXX " aur uske baad uske last 4 digits se replace karo. Baaki sab waise hi chhodo.""",
25: """Ek function likho jo Indians ke likhne ke style wali amount parse kare aur whole rupees (int) return kare.
Steps: whitespace strip karo; shuru mein currency marker ho toh hatao ("₹", "Rs.", "Rs", "INR", case-insensitive);
commas aur spaces hatao. Baaki ek number hai (integer ya decimal) jiske baad optional unit ho sakta hai (case-insensitive):
"crore", "crores" ya "cr" = 1,00,00,000; "lakh", "lakhs", "lac", "lacs" ya "l" = 1,00,000; "k" ya "thousand" = 1,000.
Multiply karo, phir nearest rupee tak round karo (exact half upar). Text parse na ho sake toh ValueError raise karo.
Examples: "1.5 crore" -> 15000000, "₹2,50,000" -> 250000, "Rs. 12.5k" -> 12500, "3.25L" -> 325000.""",
26: """Ek function likho jo Indian income-tax rules ke under HRA (house rent allowance) exemption nikale. Saare inputs annual
rupee amounts hain (basic salary mein DA included hai). Exemption inme se minimum hai:
(a) actual HRA received; (b) rent paid minus basic ka 10% (0 se kam nahi); (c) city metro hai toh basic ka 50%,
warna basic ka 40%. Result ko nearest rupee tak round karo (exact half upar) aur int return karo.""",
27: """Ek function likho jo in rules se payable gratuity nikale (Payment of Gratuity Act style).
monthly_salary last drawn basic + DA hai rupees mein; service completed years plus extra months (0-11) mein di gayi hai.
1. Agar completed years < 5 hain, toh gratuity 0 hai.
2. Warna counted years = years, plus 1 agar extra months 6 se zyada hain (exactly 6 months count nahi hote).
3. Gratuity = 15 * monthly_salary * counted_years / 26, nearest rupee tak round (exact half upar).
4. Amount ka cap 20,00,000 hai. Int return karo.""",
28: """Ek function likho jo India mein monthly basic + DA (rupees) ke liye monthly Employees' Provident Fund contributions nikale.
- Employee contribution = basic_da ka 12%.
- Employer ka pension (EPS) share = wage ka 8.33%, jahan wage 15,000 par capped hai (min(basic_da, 15000) use karo).
- Employer ka EPF share = (basic_da ka 12%) - EPS share, already-rounded values use karke.
Har percentage amount ko nearest rupee tak round karo, exact half upar.
{"employee": int, "employer_eps": int, "employer_epf": int} return karo.""",
29: """Ek function likho jo quarterly compounding wale Indian bank fixed deposit ki maturity value nikale.
Maturity = principal * (1 + annual_rate_pct / 400) ** (months / 3). months 3 ka positive multiple hona chahiye, warna
ValueError raise karo. Result ko 2 decimal places tak round karke float return karo.""",
30: """India mein shops aksar GST-inclusive price batati hain. Ek function likho jo GST-inclusive amount (paise) ko taxable
value aur GST amount mein split kare. taxable = inclusive * 100 / (100 + rate_pct), nearest paisa tak round, exact half upar;
gst = inclusive - taxable (taaki dono ka total hamesha exactly match kare). (taxable, gst) ints mein return karo.""",
31: """Ek function likho jo Indian day-first style mein likhi date parse kare aur datetime.date return kare.
Order hamesha day, month, year hai. Separators "/", "-", "." ya spaces ho sakte hain. Month ek number (1 ya 2 digits),
3-letter English abbreviation ("Aug") ya full English month name ("August") ho sakta hai, case-insensitive. Year 4 digits ka hai,
ya 2 digits jiska matlab 2000-2099. Day 1 ya 2 digits ka. Format ya date invalid ho toh ValueError raise karo.
Examples: "15/08/2024", "15-Aug-2024", "5.9.24", "1 January 2025".""",
32: """Ek function likho jo Indian Corporate Identification Number (CIN) validate aur parse kare. Pehle strip aur uppercase karo.
CIN 21 characters ka hota hai: 1 letter "L" (listed) ya "U" (unlisted); 5 digits industry code; 2 letters state code;
incorporation year ke 4 digits (1850-2100 ke beech hona chahiye); company type ke 3 letters, jo inme se ek ho:
PLC, PTC, GOI, SGC, FLC, GAP, NPL, ULL, ULT, OPC; 6 digits registration number.
{"listed": bool, "industry": "72200", "state": "MH", "year": 2010, "type": "PTC", "reg_no": "123456"} return karo
(year int, baaki strings), ya invalid ho toh None.""",
33: """Ek function likho jo India mein QR-code payments ke liye use hone wala UPI deep link banaye:
"upi://pay?pa=<vpa>&pn=<name>&am=<amount>&cu=INR" aur, sirf tab jab note diya ho aur empty na ho, end mein "&tn=<note>".
Amount rupees mein exactly 2 decimals ke saath (amount_paise 12345 -> "123.45").
Har value (pa, pn, am, tn) ko exactly waise percent-encode karo jaise Python ka urllib.parse.quote(value, safe="@") karta hai
(yaani spaces %20 bante hain aur "@" waisa hi rehta hai). amount_paise <= 0 ho toh ValueError raise karo.""",
34: """Indian banks saare Sundays aur har mahine ke 2nd aur 4th Saturday ko band rehte hain (1st, 3rd aur 5th Saturday working
days hain). Ek function likho jo start se end tak (dono inclusive) bank working days count kare, aur holidays mein di gayi
har date ko bhi exclude kare. Agar start end ke baad hai toh 0 return karo.""",
35: """Ek function likho jo amount (paise mein) ko Indian cheque ke liye words mein likhe, Indian system mein
(Thousand, Lakh, Crore). Rupees part n < 1,000,000,000 hona chahiye. Format:
paise part 0 ho toh "Rupees <rupee words> Only", warna "Rupees <rupee words> and <paise words> Paise Only".
Words rules: har word capital letter se start ho; 21-99 ke ten ke non-multiples hyphen se likhe jaayein aur dono parts capital
hon ("Forty-Two"); number ke andar "and" nahi; 0 hai "Zero".
Example: 123456789 -> "Rupees Twelve Lakh Thirty-Four Thousand Five Hundred Sixty-Seven and Eighty-Nine Paise Only".""",
36: """Ek function likho jo telescopic slab tariff se domestic electricity bill nikale (har rate sirf apne slab ke andar ki units par lagta hai):
units 1-100 par ₹3.00 per unit, 101-200 par ₹4.50, 201-500 par ₹6.00, 500 se upar ₹7.50.
Fixed charge: sanctioned load ke har kW par ₹50, load ko UPAR whole kW tak round karke (minimum 1 kW).
Electricity duty: sirf energy charge ka 5% (fixed charge ka nahi).
Total = energy charge + fixed charge + duty, 2 decimals tak round (exact half upar). Float return karo.""",
37: """Ek function likho jo rupee amount ko compact format mein likhe, jaise Indian news aur dashboards karte hain.
- Agar abs(amount) >= 1,00,00,000: crores mein value, 2 decimals tak round (half upar), trailing zeros aur trailing
  "." hata ke, phir " Cr" (12500000 -> "1.25 Cr", 10000000 -> "1 Cr").
- Warna agar abs(amount) >= 1,00,000: same lakhs mein, " L" ke saath (150000 -> "1.5 L", 1234567 -> "12.35 L").
- Warna: Indian digit grouping ke saath integer (99999 -> "99,999", 500 -> "500").
Unit rounding se pehle wali value se decide hota hai (9999999 -> "100 L"). Negative amounts ke aage "-" lagega.""",
38: """GST invoice numbers ek financial year (1 April - 31 March) ke andar sequential hone chahiye. Ek function likho jo agla
invoice number "INV/<FY>/<seq>" format mein return kare, jahan FY "2024-25" jaisa hai (start year, "-", end year ke last 2 digits)
aur seq kam se kam 4 digits tak zero-padded hai ("0001"; "9999" ke baad "10000" aata hai).
prev isi format mein pichla invoice number hai, ya None. Agar prev None hai ya uska FY date d ke FY se alag hai, toh
0001 se start karo; warna prev ke sequence ko ek se badhao.
Example: next_invoice_number("INV/2024-25/0041", date(2025, 3, 31)) -> "INV/2024-25/0042".""",
39: """Ek function likho jo Indian enterprise ko in MSME limits ke under classify kare (dono values crore rupees mein; limit ka
matlab hai "usse tak, including"):
Micro: investment <= 2.5 aur turnover <= 10. Small: investment <= 25 aur turnover <= 100.
Medium: investment <= 125 aur turnover <= 500. Kisi category ke liye dono conditions true honi chahiye; Micro se upar ki taraf
check karo aur jo pehli fit ho woh return karo: "Micro", "Small", "Medium", warna "Not MSME". Koi value negative ho toh ValueError raise karo.""",
40: """Ek function likho jo bataye ki India mein kisi given date tak cumulative kitna advance tax pay ho jaana chahiye tha.
total_tax us financial year (1 April - 31 March) ka estimated tax hai jisme on_date aati hai.
Agar total_tax 10,000 se kam hai toh kuch due nahi (0 return karo). Warna cumulative due amount:
15 June se pehle: 0; 15 June se: 15%; 15 September se: 45%; 15 December se: 75%; 15 March se: 100%
(installment wali date khud bhi count hoti hai, jaise 15 June ko 15% due hai). Nearest rupee tak round karo, exact half upar. Int return karo.""",
}
