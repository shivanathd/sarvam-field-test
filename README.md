# Sarvam Field Test

An open, reproducible benchmark of **Sarvam AI**'s speech, translation, document and chat models against **Google Gemini**,
**OpenAI**, **Anthropic Claude** and **self-hosted open weights** (Sarvam-30B and Qwen3-30B on llama.cpp), on twelve jobs
Indian businesses and developers actually do. Every test has known answers, so scoring is automatic and no model grades another.

**Read the full interactive report:** [`report/index.html`](report/index.html) (open it in a browser; it has every chart, the
per-language tables, API quirks, costs, and the source of every script).

Run on 11 October 2026 on one Apple M5 Max (128 GB). Sarvam leads **1**, is level on **7** and behind on
**7** of 15 head-to-heads.

## Results at a glance

Best Sarvam system against the best rival that ran on the same full test set. **Level** means the 95% bootstrap confidence
intervals overlap or the scores are under 2% apart. Frontier models (Gemini Pro, GPT-5.5, Claude Sonnet 5.5) ran on fixed
30-item subsets and are reported inside each suite, not here.

| Test | Best Sarvam | Best rival | Result |
|---|---|---|---|
| [Hinglish support calls: numbers captured](#uc01-voice-support) | Saaras v3 codemix mode **81%** | Gemini 3.8 Flash **94%** | Sarvam behind |
| [Helpline speech in 13 languages: word error rate](#uc02-helpline-stt) | Saaras v3 transcribe mode **0.23** | Gemini 3.8 Flash **0.21** | Level |
| [Documents from bad phone photos: fields right](#uc03-documents) | Sarvam Vision+Sarvam-105B **92%** | Claude Sonnet 5.5 **96%** | Level |
| [Q&A over Indian-language policies: correct](#uc04-indic-rag) | Sarvam-105B · thinking **96%** | Gemini 3.8 Flash **100%** | Sarvam behind |
| [Clinical notes: drug + dose + frequency exact](#uc05-clinical-notes) | Sarvam-105B **92%** | Gemini 3.8 Flash **100%** | Sarvam behind |
| [Crop advisory (incl. refusing out-of-scope)](#uc06-offline-agri) | Sarvam-105B **90%** | Gemini Pro · thinking **100%** | Level |
| [Translation into Indian languages (chrF++)](#uc07-translation-dubbing) | Sarvam-Translate **51.8** | Gemini 3.8 Flash **49.7** | Level |
| [Translation into English (chrF++)](#uc07-translation-dubbing) | Sarvam-105B **57.8** | Gemini 3.8 Flash **64.3** | Sarvam behind |
| [Dubbing: time to first audio](#uc07-translation-dubbing) | Bulbul v3 **430 ms** | GPT-4o mini TTS **1.04 s** | Sarvam leads |
| [WhatsApp orders: whole order exactly right](#uc08-quick-commerce) | Sarvam-105B · thinking(16k cap) **91%** | Gemini 3.8 Flash **98%** | Level |
| [Legal translation: facts kept](#uc09-legal) | Sarvam-105B **100%** | GPT-5.4 mini **100%** | Level |
| [Legal summaries: key facts kept](#uc09-legal) | Sarvam-105B · thinking (empties rerun at 16k) **89%** | Gemini 3.8 Flash **98%** | Sarvam behind |
| [Business text tasks: fully correct](#uc10-selfhost-business) | Sarvam-105B **94%** | Gemini 3.8 Flash **100%** | Sarvam behind |
| [Coding Indian business logic: first try](#uc11-bharat-code) | Sarvam-105B · thinking-t0 **69%** | Gemini 3.8 Flash **100%** | Sarvam behind |
| [Voice-assistant tool calls: exact](#uc11-bharat-code) | Sarvam-105B **100%** | Gemini 3.8 Flash **100%** | Level |

## What to use for which job

- **Speech recognition in Indian languages:** Saaras v3 (lowest word error rate in 12 of 13 languages, about 4x faster). For calls where amounts and account digits matter, Gemini 3.8 Flash captured them exactly more often, because Saaras often writes numbers as words.
- **Real-time voice bot:** the all-Sarvam stack (Saaras, Sarvam-105B, Bulbul): about 1.5 s to first audio, replies in the caller's language, ₹1.56 per conversation-minute.
- **Text-to-speech:** Bulbul v3, as intelligible as Gemini and OpenAI voices and the fastest to start.
- **Translating into Indian languages:** Sarvam-Translate. Avoid Mayura for text with numbers (it garbled every decimal crore amount). **Into English:** Gemini 3.8 Flash, Claude Haiku 5.5 or GPT-5.4 mini.
- **KYC, invoices, land records:** Gemini 3.8 Flash or Claude Sonnet 5.5 on the image. On poor photos Sarvam Vision invented text that was not on the page.
- **Chat, Q&A, business text, clinical notes, coding:** a price-matched Gemini, OpenAI or Claude model. Sarvam-105B gets close only with thinking on, which is slow and sometimes returns nothing.
- **Data must stay on your servers:** Qwen3-30B over Sarvam-30B for accuracy; Sarvam-30B is faster and its tokenizer is much cheaper for Indian text, but it ignores format instructions.
- **Token cost of Indian text:** Sarvam's tokenizer is cheapest (1.55x the English count on average), then Gemini (1.89x), OpenAI (2.10x), Claude (3.44x), Qwen3 (5.89x).

## How to read the metrics

- **Accuracy / exact match / recall** (higher is better): share of items fully right against the gold answer, checked by code.
- **WER / CER** (lower is better): word or character error rate of a transcript against the reference; 0.20 means one word in five is wrong.
- **chrF++** (higher is better, 0–100): character and word n-gram overlap between a translation and a human reference.
- **Entity accuracy / entity preservation**: numbers, amounts, dates, section numbers and names carried over exactly.
- **pass@1 / pass@3**: share of coding tasks whose hidden unit tests pass on the first try, or within three tries with failing tests fed back.
- **95% CI**: bootstrap confidence interval over items. When two systems' intervals overlap, treat them as level.
- **Token tax**: tokens for a sentence in an Indian language divided by tokens for the same sentence in English.

Every results file (`results/<suite>.json`) holds: `metrics` (each with per-system mean, lo, hi, n), `per_language`,
`speed` (p50/p95 ms), `usage` (tokens, audio seconds, pages, characters), `examples`, `findings`, `caveats` and `verdict`.
`results/raw/<suite>.jsonl` has every model output with its score, so any number can be audited.

## Reproduce

```bash
git clone https://github.com/shivanathd/sarvam-field-test && cd sarvam-field-test
cp .env.example .env            # SARVAM_API_KEY, GOOGLE_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Rebuild the report and README from the committed results (no API keys needed)
.venv/bin/python report/build_report.py && .venv/bin/python report/make_readme.py

# Re-run a suite (resumable: only missing items call an API; delete results/raw/<suite>.jsonl to start fresh)
.venv/bin/python suites/uc08_quick_commerce/run.py api

# Optional: self-hosted models (downloads ~38 GB of GGUF files into gguf/, needs llama.cpp's llama-server)
LLAMA_SERVER=/path/to/llama-server scripts/serve_local.sh
```

Each suite folder has its own README with exact steps. Audio (synthesised test calls and dubbing output), FLEURS recordings
and tokenizer files are not committed; the suites regenerate or download them. Synthesising the test audio uses Gemini TTS
and macOS `say` voices. Expect roughly ₹1,200 of Sarvam credit, a few US dollars of OpenAI, US$4 of OpenRouter and a few million
Gemini tokens for a full run at the committed sizes.

## Repository layout

```
common/bench.py          shared clients (Sarvam, Gemini, OpenAI, OpenRouter, local llama.cpp), scoring helpers, result writer
suites/<suite>/          run.py (resumable), README.md, data builders, scorers
data/<suite>/            test inputs (authored text, document images, gold answers)
results/<suite>.json     scored results; results/raw/<suite>.jsonl every output
report/                  build_report.py, template.html, index.html (the report), make_readme.py
logs/                    run logs
scripts/serve_local.sh   starts self-hosted Sarvam-30B (:8101) and Qwen3-30B (:8102)
```

## Method and caveats

- Test sets for orders, KYC, invoices, policies, consultations, legal passages, farming and business text were written for
  this benchmark with fake people and clearly marked sample IDs. No native speaker reviewed them; treat absolute scores as
  indicative and the comparisons as the result.
- Public data: FLEURS / FLORES sentences (CC-BY 4.0) for speech recognition, translation and the token tax.
- Sarvam-105B ran with thinking off (`reasoning_effort: null`) and on. Sarvam-30B is no longer offered on Sarvam's API, so it
  was self-hosted from the official Q4_K_M GGUF; its thinking can only be disabled by pre-filling an empty think block.
- Model-written code ran only inside a macOS `sandbox-exec` profile with no network, no home-folder reads and no writes outside a temp folder.
- Speed figures were measured on a shared, often heavily loaded Mac; treat them as floors.
- Prices are list prices in October 2026.

## Use cases

### uc01-voice-support

**1. Code-mixed voice support & collections calls.** A bank, telecom or insurer handling Hinglish/Tanglish/Manglish/Benglish/Kanglish calls: which speech-to-text gets the caller's card digits, amounts, dates and phone numbers right, and which voice-agent stack answers fastest?

- Data: uc01 code-mixed customer-care utterances (n=80; synthetic, written for this benchmark; licence CC-BY-4.0 (this repo))
- Code: [`suites/uc01_voice_support/`](suites/uc01_voice_support/) · results: [`results/uc01_voice_support.json`](results/uc01_voice_support.json) · every output: `results/raw/uc01_voice_support.jsonl`

**Verdict.** For capturing what a collections or card-services call actually needs — the digits — use gemini-3.8-flash as the transcriber or add a number-normalisation step after saaras: Gemini got 94% of amounts, card digits, dates and phone numbers exactly, saaras:v3 codemix 74-81%, gpt-4o-transcribe ~60%, hosted whisper-1 ~50%. Use saaras:v3 codemix (not transcribe) when latency matters: it returns in ~0.6 s versus 1.2 s (gpt-4o-transcribe) and 3.9 s (Gemini), and has the lowest CER on phone-line audio. For the full voice loop, Sarvam's speech ends (saaras + bulbul, ~0.9 s combined) are the fastest available; sarvam-105b is the fastest reply LLM at p50 and the most reliable at answering in the caller's language, while gpt-5.4-mini gives steadier tail latency but often switches Dravidian/Bengali callers to Hindi or English. The all-Gemini stack is the most accurate on numbers but takes ~6.8 s to start speaking. Do not use Whisper (local or hosted) for code-mixed Indian calls.

- Entity accuracy (what a bank needs: card last-4, amounts, dates, phone and claim numbers, 100 entities): gemini-3.8-flash 0.94 [0.89-0.98] on both clean and phone-line audio; saaras:v3 codemix 0.74 [0.65-0.83] clean / 0.81 [0.73-0.88] phone; gpt-4o-transcribe 0.61 / 0.57; whisper-1 (hosted Whisper) 0.50 / 0.51; saaras:v3 transcribe 0.43 / 0.46; local whisper-large-v3-turbo 0.24 / 0.26.
- Most saaras misses are formatting, not hearing: in codemix mode 15 of 26 clean misses (11 of 19 phone) had no digits at all — the number came back as words (e.g. hi02 'बारह हज़ार चार सौ निन्यानवे', 'सेवन थ्री ज़ीरो सिक्स'). Codemix mode is not applied consistently: 48/160 codemix outputs contain no Latin letters at all, i.e. it fell back to transcribe-style output. Transcribe mode writes numbers as words almost always (51 of 57 misses). Add inverse text normalisation before using saaras output for account data.
- Gemini never wrote a number as words (0 such misses); its 6 misses were genuinely wrong digits. It does not follow the script convention reliably either: 59/160 Gemini outputs had no Latin letters (English loanwords written in native script).
- Word error rate is convention-bound. Against the code-mix reference, saaras codemix and Gemini tie on clean audio (0.38 vs 0.36) and saaras codemix is better on phone audio (0.30 [0.24-0.36] vs 0.35 [0.31-0.39]); CER on phone audio 0.24 vs 0.37. Scoring each output against whichever reference convention suits it better (code-mix or all-native script, no transliteration), Gemini is lower: 0.17-0.18 vs saaras codemix 0.25.
- Phone-line degradation (8 kHz, 300-3400 Hz, mu-law, 20 dB SNR) barely hurt any API system; saaras codemix even scored better on phone than clean, which reflects run-to-run variation in its number formatting rather than a real benefit.
- Whisper is not usable for code-mixed Indian calls. Local whisper-large-v3-turbo: WER 0.80 (per-clip capped at 1), entity accuracy 0.24, repetition loops on noisy audio, Malayalam answered in Devanagari on 15 of 32 clips even with language='ml'. Hosted whisper-1 is somewhat better (WER 0.72, entities 0.50) but rejects language='bn' and 'ml' outright (HTTP 400 'Language 'bn' is not supported.'), so Benglish and Manglish ran on auto-detect.

### uc02-helpline-stt

**2. Citizen helpline speech-to-text across India's languages.** A state or national citizen helpline takes calls in many Indian languages: which speech-to-text works in all of them, and how bad is its weakest language?

- Data: FLEURS (google/fleurs) test split (n=350; public; licence CC-BY-4.0)
- Code: [`suites/uc02_helpline_stt/`](suites/uc02_helpline_stt/) · results: [`results/uc02_helpline_stt.json`](results/uc02_helpline_stt.json) · every output: `results/raw/uc02_helpline_stt.jsonl`

**Verdict.** For a multi-language citizen helpline, saaras:v3 is the strongest default: lowest WER in 12 of the 13 comparable languages (several near-ties), macro CER about half of Gemini's and gpt-4o-transcribe's, every clip transcribed, and answers in under a second. Plan for its two gaps: it writes Sindhi only in Devanagari, and it accepts at most 30 s per REST call. Gemini-3.8-flash (worst language Assamese 0.31) and gpt-4o-transcribe (worst Nepali 0.42, never blocks, 1.4 s) are the credible alternatives and both handle Arabic-script Sindhi; Gemini silently returned nothing for about 3% of clips. Whisper — hosted whisper-1 or local large-v3-turbo — is not fit for an Indian helpline: it rejects or mis-scripts six of the fourteen languages.

- In the 13 languages where its output script matches FLEURS, saaras:v3 has the lowest WER in 12 (all except Urdu; Nepali 0.271 vs 0.272 and Telugu 0.170 vs 0.173 are ties; on CER Gemini wins Telugu, Marathi and Urdu): macro WER 0.17 / CER 0.052 vs gemini-3.8-flash 0.21 / 0.090, gpt-4o-transcribe 0.27 / 0.090, whisper-1 (hosted) 0.79 / 0.54 and whisper-large-v3-turbo (local) 0.75 / 0.45. Biggest saaras leads: Assamese 0.16 vs 0.31, Malayalam 0.17 vs 0.27, Punjabi 0.15 vs 0.23 (Gemini figures include its blocked clips).
- Worst language: saaras Nepali 0.27 [0.22-0.33], Gemini Assamese 0.31 [0.21-0.42], Whisper Malayalam 1.00. Gemini's worst-language CI overlaps saaras's, so on read speech the two are close on the weakest language; Whisper is not.
- gpt-4o-transcribe is the most robust OpenAI option and the only system besides Gemini that writes every language, including Sindhi, in the reference script: WER worst language Nepali 0.42 [0.32-0.53], best CER of all systems on Tamil (0.091), zero blocked clips, p50 1.4 s (RTF 0.12). Its WER trails saaras in 12 of 13 comparable languages (it wins only Urdu, and on CER also Tamil); the gap is mostly word boundaries and spelling choices — its macro CER (0.090) equals Gemini's.
- Sindhi: saaras:v3 (language_code sd-IN) writes Sindhi in Devanagari, FLEURS uses Perso-Arabic script, so it scores WER 0.996 here. The Devanagari text reads as a faithful transcript (e.g. 'होस्टाइल माहौल वारे कोर्स…' for 'هوسٽائل ماحول واري ڪورس…'), so this is a script choice, not deafness — but a helpline that needs Arabic-script Sindhi cannot get it from saaras. Gemini handles Sindhi in Arabic script at WER 0.21.
- Gemini returned no transcript at all for 20 of 350 clips on the first try (prompt blocked, block_reason OTHER) and for 11 (3.1%) even after three attempts, spread over 7 languages (Assamese 3, Punjabi 2, Malayalam 2, Bengali, Tamil, Kannada, Odia 1 each). On the clips it did transcribe, its macro WER is 0.185. A helpline using Gemini needs a fallback for blocked audio.
- Hosted whisper-1 rejects language codes bn, te, gu, pa ('Language 'bn' is not supported.', HTTP 400) and has no Odia, so those ran on auto-detect; it then wrote Bengali, Gujarati, Malayalam, Odia, Punjabi and Sindhi mostly in the wrong script, and Assamese/Telugu at CER >= 0.5. Only Hindi (0.30) and Urdu (0.24) are usable — no better than the local model.

### uc03-documents

**3. Documents: KYC, GST invoices, land records and bills in Indian scripts.** Can I digitise Indian-language business documents (GST invoices, KYC forms, land records, utility bills, ration cards) into correct structured fields, from clean scans and from phone photos, and which stack should I use?

- Data: uc03-synthetic-indic-docs (n=60; synthetic, written for this benchmark; licence CC0 (synthetic); fonts are macOS system fonts used only to render images)
- Code: [`suites/uc03_documents/`](suites/uc03_documents/) · results: [`results/uc03_documents.json`](results/uc03_documents.json) · every output: `results/raw/uc03_documents.jsonl`

**Verdict.** For clean scans and ordinary phone photos of Indian-script business documents, any of these stacks reads about 99.5% of fields correctly. Choose on cost, latency and where the data may go. The all-Sarvam pipeline (Vision plus sarvam-105b) costs about ₹0.52 per page and runs on an Indian provider. Gemini on the image is faster at p95 (8.7 s vs 33.5 s) and simpler, since it needs no job API. Poor photos are the exception. There, Gemini on the image was clearly more robust (93% of fields and 56% of pages fully right, against 86% and 25%), and Sarvam Vision sometimes wrote fluent text that was not on the page, occasionally in the wrong script. So if your intake is mostly phone photos taken by customers or field staff, use Gemini, or put an image-quality gate and a re-capture step in front of Sarvam Vision. With either stack, validate IDs such as PAN and GSTIN by format and checksum. Among the added comparators, claude-sonnet-5.5 was the most accurate on bad photos, and claude-haiku-5.5 matched the leaders on clean and normal photos at about $0.37 per 1,000 pages. OpenAI's gpt-5.4-mini and gpt-5.5 misread or invented Indic-script values far more often in this test, so don't use them for this job without validation.

- Clean scans and ordinary phone photos are essentially solved by all three stacks. Field exact-match: clean 99.5% (Sarvam Vision + sarvam-105b), 99.5% (Sarvam Vision + Gemini), 99.6% (Gemini on the image). Phone photo: 99.3% / 99.5% / 99.3%. The CIs overlap completely (60 pages, 783 fields each). Pages with every field correct: 93-95% clean, 92-93% photo.
- Bad photos separate the stacks. On the 16-page harsh subset (6 deg tilt, strong skew, hand shadow, noise, 0.55x resolution, JPEG q 22-30), Gemini on the image kept 92.8% of fields [87.2, 97.2] and got 56% of pages fully right. The Sarvam pipeline kept 85.6% [78.5, 92.1] and 25% of pages. Swapping sarvam-105b for Gemini as the extractor on the same Vision text only moved this to 86.5%, so the gap is OCR, not extraction.
- Text accuracy tells the same story. Order-free CER for Sarvam Vision vs Gemini OCR is 0.020 vs 0.023 clean and 0.015 vs 0.004 photo, then 0.193 vs 0.028 on harsh photos (gold-word recall 0.84 vs 0.95). The harsh-photo CER by script for Vision is worst in Tamil (0.32), Bengali (0.21) and Devanagari (0.20).
- On degraded pages Sarvam Vision writes fluent text that is not on the page. The Tamil patta header 'மாதிரி ஆவணம்' (sample document) came out as 'எதிரி ஆயுதம் - தற்காப்பு' (enemy weapon - defence). A line of Kannada about Belagavi district appeared inside the Tamil page. The 7/12 subtitle '(पिकांची नोंदवही)' became '(पिंपरी चिंचवड)', a real Pune place name, and sarvam-105b then put that into the taluka field. During the smoke test, a Kannada line on a mixed-script page also came back in Bengali script.
- Handwriting-style PANs expose character confusions. Sarvam Vision misread I/1 and O/0 in 3 of 10 KYC forms (e.g. FADPQ1032L read as FADPQI032L, HLOPM1790W as HLOPM179OW), the same way on clean and photo pages. Gemini got 1 of 10 wrong. A PAN or GSTIN format and checksum check would catch these, whichever OCR you use.
- Latency per page, p50 / p95: Sarvam Vision job 5.9 s / 25.3 s (the job API queues; one job per page), Vision + sarvam-105b 9.2 s / 33.5 s, Gemini on the image 5.0 s / 8.7 s.

### uc04-indic-rag

**4. Q&A over company documents in Indian languages (RAG).** Employees and customers ask questions (in their own language, in English, or in romanised WhatsApp-style text) over company documents written in Indian languages. Which model answers correctly, in the user's language, and says 'not in the documents' instead of guessing?

- Data: uc04 synthetic Indian-language policy documents (n=132; synthetic, written for this benchmark; licence CC-BY-4.0 (this repo))
- Code: [`suites/uc04_indic_rag/`](suites/uc04_indic_rag/) · results: [`results/uc04_indic_rag.json`](results/uc04_indic_rag.json) · every output: `results/raw/uc04_indic_rag.jsonl`

**Verdict.** For an Indian-language document help-desk, retrieval with gemini-embedding-2 is solved at this scale. Pick the generator for instruction-following. gemini-3.8-flash is the best default in the price-matched tier: 100% correct, 95% English replies to English questions, but only 62% romanised replies to romanised questions. sarvam-105b is fast (0.6 s) and cheap, and nearly always finds the right figure. With thinking off, though, it marks a third of its correct answers as not found and answers English questions in the document's language, so run it with reasoning on (0.96 correct, 3% false refusals, about 5 s) or don't use a refusal tag. Skip sarvam-105b-conversations for this task. gpt-5.4-mini is accurate but almost never answers in the user's language. If users write romanised or English text against Indic documents and language matching matters, only the frontier models (gemini-pro-latest, gpt-5.5, claude-sonnet-5.5) got it right every time on our subset. Whatever the model, scope retrieval to the right organisation: almost every model will quote another company's policy if retrieval hands it one. For on-premise use, qwen3-30b-local reads Indic documents well but over-answers when the documents don't contain the answer and overflows an 8k context on Kannada. sarvam-30b-local tokenizes Indic text efficiently but needs work on its refusal behaviour before it is usable.

- Retrieval was not the bottleneck. gemini-embedding-2 put the gold chunk in the top 5 for 108/108 answerable questions (recall@1 0.98), the same for native-script, English and romanised questions. Cross-script search works with the task written into the text (gemini-embedding-2 has no task_type). The corpus is small, though: 39 chunks, each document in a different language.
- Answer correctness on the full 108 answerable questions (top-5 retrieval): gemini-3.8-flash 1.00, gpt-5.4-mini 0.99, sarvam-105b with thinking 0.96, claude-haiku-5.5 0.94, sarvam-105b with thinking off 0.67, sarvam-105b-conversations 0.52. On the 30-question frontier subset: gemini-pro-latest 1.00, gpt-5.5 0.97, claude-sonnet-5.5 0.97.
- sarvam-105b with thinking off finds the right number almost every time (gold value present in 98% of replies, 96% for -conversations). It then appends the [NOT_FOUND] tag to 32% of correct answers (47% for -conversations), apparently because some of the 5 excerpts come from other documents. One reply says the answer is in the Periyar bank document, then tags it as not found because it is absent from the Surma Telecom excerpt. A bot that routes on the tag would hide about a third of correct answers. With reasoning on, false refusals fall to 3% and correctness rises to 0.96, at about 8x the latency (p50 4.9 s vs 0.6 s) and 220k reasoning tokens for 240 calls.
- The oracle condition gives the gold chunk alone, and sarvam-105b with thinking off still scores 0.62. Its errors come from generation and instruction-following, not retrieval. The other systems score the same with or without retrieval.
- Replying in the user's language is the biggest gap. For native-script questions every system replies in that script (98-100%). For English questions about an Indic document, most models answer in the document's language. Share of English questions answered in English: gpt-5.4-mini 0.07, sarvam-105b 0.11, sarvam-105b-conversations 0.17, claude-haiku-5.5 0.33, sarvam-105b with thinking 0.88, gemini-3.8-flash 0.95, all three frontier models 1.00.
- Self-hosted models (llama.cpp Q4_K_M, thinking off, all 132 questions, rag condition): qwen3-30b-local answered 0.94 of the 108 answerable questions correctly, but refused only 0.62 of the unanswerable ones and replied in Latin script to 0 of 38 romanised questions. sarvam-30b-local found the gold value in 0.85 of replies, but appended [NOT_FOUND] to 64% of answerable questions (correct 0.30). It answered English questions in English only 5% of the time, refused 0.79 of the unanswerable questions, and is the only system that invented numbers (2 of 132 replies; for example, it made up a ₹1,500 ambulance charge for an unanswerable Kanglish question). sarvam-30b-local is not usable for this task without heavy prompt or format work.

### uc05-clinical-notes

**5. Mixed-language doctor-patient consultation -> English clinical note.** A clinic records an outpatient consultation held in Hinglish / Malayalam-English / Tamil-English / Bengali-English / Marathi-English. Which model turns it into a correct structured English note, and which one invents medicines or doses (the safety risk)?

- Data: uc05 synthetic OPD consultations (n=40; synthetic, written for this benchmark; licence CC-BY-4.0 (this repo))
- Code: [`suites/uc05_clinical_notes/`](suites/uc05_clinical_notes/) · results: [`results/uc05_clinical_notes.json`](results/uc05_clinical_notes.json) · every output: `results/raw/uc05_clinical_notes.jsonl`

**Verdict.** For an AI scribe working from a transcript, gemini-3.8-flash (thinking off) is the pick in the price-matched tier: perfect on every field we scored, no invented drugs, 4 s per note. gpt-5.4-mini (1.5 s) is a close, faster second. sarvam-105b is as safe (it never invented a medicine) and fast (1.8 s), but it gets about 1 in 15 frequencies wrong, typically turning an as-needed dose into a scheduled one. Reasoning mode does not fix that and makes it 14x slower, so any Sarvam-based scribe needs a frequency check by the doctor. From audio, sending the recording straight to gemini-3.8-flash was the most accurate path in our test (100% on 15 dialogues). The Sarvam pipeline is cheap (₹45/hour of audio with diarization) and diarizes correctly. Use saaras:v4 in codemix mode, then sarvam-105b: on 15 dialogues it scored 0.97 fact recall vs 0.94 for v3 translate, and it fixes v3's spoken-number errors. But every saaras version dropped the same prescription sentence in one Malayalam consultation, and medication exactness stays at 0.83 vs 1.00 for Gemini on the raw audio, so always show the doctor the transcript next to the note. Self-hosted 30B models are not ready to be an unsupervised scribe: about 1 in 5 medicine lines have an error, and 30-40% of notes are not fully in English. qwen3-30b-local was the safer of the two.

- From the dialogue text, every cloud model wrote a usable English note. fact_recall_overall over 40 dialogues: gemini-3.8-flash 1.00, gemini-pro-latest 1.00, claude-sonnet-5.5 1.00, gemini-3.8-flash with thinking, gpt-5.4-mini with thinking, claude-haiku-5.5 with thinking and gpt-5.5 all 0.99, sarvam-105b with thinking 0.98, gpt-5.4-mini 0.97, sarvam-105b 0.96 (CI 0.94-0.98), claude-haiku-5.5 without thinking 0.93.
- Safety metric: no text-track system listed a drug that was not prescribed or a dose that was never said (hallucinated meds/doses per note = 0.00 for all, n=30-40). All 40 traps were handled: refused antibiotics, stopped drugs, self-medication, mid-sentence dose corrections and late-disclosed allergies. With an explicit 'final prescription only' instruction, these models do not invent medicines.
- The errors that remain are frequency errors, and they are clinically meaningful. 'Paracetamol 5 ml only when fever is above 100, not more than 4 times a day' (an as-needed/SOS dose with a daily cap) was written as scheduled QID or TDS by sarvam-105b (d03, d13), sarvam-105b with thinking (d03, d19, d27, d28), claude-haiku-5.5 (d03, d13, d19, d27, d28), gpt-5.4-mini (d27) and the gpt-4o-transcribe pipeline. sarvam-105b also turned two 'morning one, night one' (BD) prescriptions into OD (d28 cefixime, d31 calcium). Medication exactness (drug + dose + frequency): gemini-3.8-flash 1.00, claude-haiku-5.5 with thinking 1.00, all frontier models 1.00, gpt-5.4-mini 0.99, sarvam-105b 0.93, sarvam-105b with thinking 0.91, claude-haiku-5.5 without thinking 0.90.
- Writing the note in English is not automatic. Share of notes with no Indic-script text: sarvam-105b, gemini (all modes), the frontier models and all audio pipelines 1.00, gpt-5.4-mini 0.95, claude-haiku-5.5 0.60 (0.90 with thinking), qwen3-30b-local 0.68, sarvam-30b-local 0.58. Claude Haiku and the local models often copied the patient's words in Hindi, Tamil or Bengali into the complaint or red-flag fields, e.g. 'बुखार, पूरे बदन में दर्द…' as the chief complaint.
- Self-hosted models (Q4_K_M, thinking off, all 40 dialogues), fact recall / medication exactness: qwen3-30b-local 0.79 / 0.87 with 0 invented medicines; sarvam-30b-local 0.78 / 0.79 with one invented medicine (d25: it listed 'Dolo 650' as a second drug next to paracetamol, which could lead to a double paracetamol dose). Neither listed a trap drug as prescribed. Most of their recall loss is complaint and red-flag text left in the source language; vitals recall stays at 0.95-0.97. p50 is 12 s per note on the shared Mac.
- Thinking did not help sarvam-105b here: medication exactness 0.91 with thinking vs 0.93 without. It cost 173k reasoning tokens for 40 notes, latency rose from 1.8 s to 25.8 s (p50), one note was not valid JSON (d37), and one omitted metformin after a mid-sentence dose correction (d18). For claude-haiku-5.5 and gpt-5.4-mini, thinking did help (0.90 to 1.00, and 0.97 to 0.99 fact recall).

### uc06-offline-agri

**6. Offline crop advisory.** Can an open-weight model running on a local box (no internet, possibly no GPU) answer farmers' questions correctly from an advisory sheet, in their own language and script?

- Data: uc06 advisory sheet + farmer questions (n=70; synthetic, written for this benchmark; licence CC-BY-4.0 (this repo))
- Code: [`suites/uc06_offline_agri/`](suites/uc06_offline_agri/) · results: [`results/uc06_offline_agri.json`](results/uc06_offline_agri.json) · every output: `results/raw/uc06_offline_agri.jsonl`

**Verdict.** Neither open-weight 30B model is safe as an unsupervised offline crop advisor in this setup. With thinking off, they give the right numbers for only ~70% of sheet questions and, worse, invent answers to most questions the sheet does not cover. Thinking on stops most of the invention but takes minutes per answer on shared hardware and produces more wrong-language replies. The two models tie on accuracy. Sarvam-30B replies in the farmer's language more reliably and processes Indic prompts with fewer tokens, so prefer it if you must go offline, behind a retrieval or whitelist layer and code checks that every number in an answer appears in the sheet. If there is any connectivity, use gemini-3.8-flash (100% grounded, no inventions) or sarvam-105b (95% grounded, 100% correct language, sub-second, ~₹0.02 per answer). The frontier models are perfect on the subset. Avoid gpt-5.4-mini and claude-haiku-5.5 for this job: they don't invent answers, but they refuse a quarter of answerable farmer questions.

- Grounded correctness on the 60 in-scope questions (answer contains every gold number from the sheet): gemini-3.8-flash 100%, sarvam-105b 95% [90,100]. Every offline variant lands at 68-77% with overlapping CIs: Sarvam-30B 73% (without thinking, with thinking, and on CPU alike), Qwen3-30B-A3B 68% without thinking, 77% with, 73% on CPU.
- The big offline risk is invented answers. Without thinking, Sarvam-30B refuses only 1 of 10 out-of-scope questions (3/10 if a helpline redirect without the code counts) and Qwen3 refuses 0/10 (4/10 lenient). Examples: Sarvam told a Tamil farmer to use 150 kg DAP per acre on tomato, and Qwen3 told a Marathi farmer that soybean is ₹1,800 per quintal today. Neither appears in the sheet.
- Cloud comparators (ADDENDUM). Cloud models do NOT invent answers to out-of-scope questions: gpt-5.4-mini, claude-haiku-5.5, gemini-pro-latest, gpt-5.5 and claude-sonnet-5.5 all refused 10/10. But the cheap ones over-refuse real sheet questions: gpt-5.4-mini answered 'NOT_IN_SHEET' to 23% of in-scope questions and claude-haiku-5.5 to 27%. This happened mostly on romanised or farmer-vocabulary phrasings (e.g. 'kandu jigihulu' for brown planthopper, 'ਨਰਮਾ' for cotton). As a result their grounded correctness, 75% and 70%, is no better than the offline 30B models. gpt-5.4-mini also mixes English into native-script replies ('40 kg प्रति acre'), so only 79% of its replies are in the farmer's language. On the fixed 30-question subset (all 10 out-of-scope + 20 in-scope), all three frontier models pass 30/30. On the same subset gemini-3.8-flash passes 93% and sarvam-105b 90%. gpt-5.4-mini and claude-haiku-5.5 pass 70%. Offline: Sarvam-30B 50% and Qwen3 40% without thinking; 60% each with thinking.
- Thinking fixes most of the invention (out-of-scope refusal: Sarvam-30B 100%, Qwen3 90%) but costs a lot. Sarvam-30B produced 1,577 output tokens per answer (p50 198 s on the shared GPU). False refusals rise to 13% (Sarvam) and 8% (Qwen3). Sarvam-30B's correct-language replies fall from 96% to 76%.
- Replying in the farmer's language and script, without thinking: Sarvam-30B 96% [90,100], Qwen3 90% [81,97], sarvam-105b 100%, Gemini 96%. Romanised questions are harder for every offline model: Sarvam-30B 67% grounded (native 80%), Qwen3 57% (native 80%). Several replies switched to native script or to English.
- Offline accuracy depends heavily on language. Overall pass, Sarvam-30B no-think: Hindi 83%, Marathi 83%, Tamil 82%, Kannada 58%, Punjabi 36%, Telugu 33%. sarvam-105b on the same questions: 100/100/100/92/91/75%.

### uc07-translation-dubbing

**7. Translation and dubbing of training content / product copy.** Localising training content and product copy into Indian languages, then dubbing it: which translation system and which TTS should an Indian business use?

- Data: FLEURS test transcriptions (= FLORES-101 sentences) aligned by id (n=32; public; licence CC-BY 4.0)
- Code: [`suites/uc07_translation_dubbing/`](suites/uc07_translation_dubbing/) · results: [`results/uc07_translation_dubbing.json`](results/uc07_translation_dubbing.json) · every output: `results/raw/uc07_translation_dubbing.jsonl`

**Verdict.** For localising formal English content into Indian languages, use sarvam-translate:v1. It was the most accurate system into Indian languages in 8 of 10 languages, and on a small subset no frontier model (gemini-pro, gpt-5.5, claude-sonnet-5.5) did better. Its lead over mayura:v1 and gemini-3.8-flash is only about 2 chrF, and it costs about 80x more per item than prompting sarvam-105b, so high-volume, lower-stakes copy can go through 105b or a price-matched model. For Indian languages into English (customer feedback, regional documents), use gemini-3.8-flash or claude-haiku-5.5. They lead sarvam-translate by 10-12 chrF, and sarvam-translate makes meaning-changing errors in that direction. Use mayura's colloquial mode only when you want code-mixed copy. For dubbing, bulbul:v3, gemini-3.8-flash-tts and gpt-4o-mini-tts are all intelligible in all 10 languages, with bulbul and Gemini slightly ahead. Bulbul starts playback about 3x sooner (357 ms) and has a simple per-character rupee price, so it is the best default for interactive voice and a fine choice for batch voice-overs. The self-hosted 30B models are not ready for production translation into Indian languages.

- English->Indic, full set (320 items per system): sarvam-translate:v1 has the highest chrF++, 51.8 [50.1-53.5]. Next are mayura:v1 49.8, gemini-3.8-flash 49.7, claude-haiku-5.5 47.8, gpt-5.4-mini 46.6 and sarvam-105b 45.6. sarvam-translate is best of these systems in 8 of 10 languages (Gemini wins Kannada, Haiku wins Malayalam).
- Frontier models do not beat sarvam-translate into Indian languages. On the 30 sentence-language pairs where every system ran, sarvam-translate scores 53.5 against gemini-pro-latest 51.9, gemini-3.8-flash 51.9, gpt-5.5 51.0 and claude-sonnet-5.5 51.0, all with thinking on. The CIs (about +/-5 points at n=30) overlap, so the honest reading is 'no better', not 'worse'.
- Indic->English ranks the other way round: gemini-3.8-flash 64.3 [62.5-66.2], claude-haiku-5.5 62.1, gpt-5.4-mini 60.4, sarvam-105b 57.8, mayura 54.6, sarvam-translate:v1 52.5. On the 30-pair frontier subset, claude-sonnet-5.5 scores 65.9, about level with gemini-3.8-flash at 62.8. sarvam-translate's errors into English change the meaning. Hindi 'fabric ... shrinkage, or scorch' became 'clothing ... could lead to hypothermia or even burns', and Tamil 'appeared in court with covered faces' became 'was present in the court in the dock'.
- Cost differs by about 80x for similar volume. sarvam-105b translated all 640 items for about INR 1.4 in tokens (34.5k in, 15.3k out). sarvam-translate and mayura each cost about INR 115 at INR 20 per 10k input chars (57.8k chars). claude-haiku-5.5 cost US$0.029 for the same 640 items, as reported by OpenRouter.
- mayura:v1 modern-colloquial mode produces Hinglish/Tanglish copy: 61% of output letters are Latin, e.g. 'Fabric ரொம்ப hot ஆகாம பாத்துக்கோங்க'. Against the formal reference it scores chrF++ 16 vs 49 for formal mode. That is a deliberate change of register, not an error, and suits chat or marketing copy rather than formal training material.
- Dubbing intelligibility (26 sentences x 6 languages per TTS, three STT judges): bulbul:v3 and gemini-3.8-flash-tts are statistically tied, and gpt-4o-mini-tts is slightly behind. CER with saaras:v3 as judge: bulbul 1.8%, Gemini 1.9%, OpenAI 2.4%. With the vendor-neutral gpt-4o-transcribe as judge: Gemini 3.5%, bulbul 4.3%, OpenAI 5.0%, CIs overlapping. With Gemini as judge, counting its refusals as failures: Gemini 5.9%, OpenAI 6.7%, bulbul 7.3%. Without the refusals those three are 2.8%, 2.3% and 2.3%.

### uc08-quick-commerce

**8. Code-mixed quick-commerce orders and product/place-name transliteration.** Can a model turn code-mixed WhatsApp/quick-commerce order and search messages into a correct structured order, and write Indian names in native script correctly?

- Data: uc08 hand-authored orders (100) + transliteration names (100) (n=200; synthetic, written for this benchmark; licence CC-BY 4.0)
- Code: [`suites/uc08_quick_commerce/`](suites/uc08_quick_commerce/) · results: [`results/uc08_quick_commerce.json`](results/uc08_quick_commerce.json) · every output: `results/raw/uc08_quick_commerce.jsonl`

**Verdict.** To turn WhatsApp-style code-mixed orders into structured carts, gemini-3.8-flash with thinking off is the best value. It got 98% of whole orders exactly right in about 3 s and was within the CI of the frontier models (gpt-5.5 100% and gemini-pro 97% on a 30-message subset). claude-haiku-5.5 (85%) is a reasonable second choice. sarvam-105b is usable only with thinking on (90-91% exact). Even then it takes 9 s p50 and 23-27 s p95, and it needs a max_tokens of 16k plus a retry on empty replies. Without thinking it confuses regional grocery words and should not write orders unsupervised. Every cloud model reads pincode and payment correctly, so those fields are safe to automate today. For writing names in native script (labels, invoices, search), use gemini-3.8-flash, claude-haiku-5.5 or gpt-5.4-mini (96-99%). The Sarvam transliterate API is cheap and fast for Hindi and Marathi but makes visible errors on Tamil and Bengali names. The local 30B models are not yet good enough for either task without a catalog-mapping layer.

- Order extraction, exact whole-order accuracy over 100 code-mixed messages. Thinking off: gemini-3.8-flash 98% [95-100], claude-haiku-5.5 85%, gpt-5.4-mini 77%, sarvam-105b 71% [62-80]. With thinking, sarvam-105b reaches 90-91%. Strict item F1 for the same systems is 0.99, 0.92, 0.89, 0.85 and 0.95 (105b-think with the 16k cap). On the 50-message local subset, qwen3-30b-local scores 36% exact.
- On the fixed 30-message frontier subset (ids with (id-1)%10 in {0,3,6}, covering every language group), exact accuracy with thinking on is gpt-5.5 100%, gemini-pro-latest 97% and claude-sonnet-5.5 93%. Price-matched systems on the same messages: gemini-3.8-flash 93%, claude-haiku-5.5 90%, sarvam-105b-think 87% (16k cap), gpt-5.4-mini 63%, sarvam-105b 63%. gemini-3.8-flash with thinking off is within the CI of the frontier ceiling.
- sarvam-105b without thinking makes regional-vocabulary mistakes, not format mistakes. Bengali 'sorsher tel' (mustard oil) became sesame oil, Tamil 'sakkarai' (sugar) became jaggery, Tamil 'theangai' (coconut) became banana, and 'sona masoori' became basmati rice. It also drops brands written in Tamil script (மேகி -> no brand), treats varieties as brands (Ponni, alphonso), sets search quantities to 1 packet instead of '200g', and invents slot labels ('night', 'evening_16-20') on 6% of messages. Its catalog-name F1 is still 0.98: it finds the products but gets the details wrong.
- sarvam-105b thinking can return nothing. At max_tokens 6000, 3 of 100 replies (ids 18, 74, 99) came back empty after spending the whole budget on reasoning. Rerun at 16000, all 3 answered correctly, using about 3.8k completion tokens each, below the earlier cap. The reasoning length is non-deterministic, not simply too long for the cap. docs-legal saw the same pattern (16 of 80 empty), so any 105b-think deployment needs a high max_tokens and a retry on empty content. Exact accuracy goes from 90% to 91%, p95 latency stays at 23-27 s, and reasoning averages about 1,700 tokens per message.
- Pincode and payment extraction is solved for every cloud model: 100% for gemini-3.8-flash, gpt-5.4-mini, claude-haiku-5.5, sarvam-105b and all three frontier models. That includes pincodes in Bengali (৭০০০৬৪), Devanagari (४११०३८) and Kannada (೫೬೦೦೧೧) digits, and slang such as GPay/PhonePe/Paytm/nakad/'cash e debo'. Gemini 3.8 Flash's only 2 misses wrote the brand in Devanagari (मैगी, हल्दीराम), which a catalog lookup would not match.
- qwen3-30b-local copies the customer's word instead of mapping it to the catalog (bhindi, gajar, theangai, pauruti, Bisleri, Pampers instead of okra, carrot, coconut, bread, packaged water, diapers), so name-only F1 is 0.72. It is fast (p50 5.5 s on the shared Mac) and always produced valid JSON.

### uc09-legal

**9. Courts and legal: translating and summarising judgments without losing facts.** If I translate or summarise English court orders, RTI replies and tribunal awards into Hindi, Tamil, Marathi or Bengali for litigants, which system keeps every amount, date, section, case number and party name intact?

- Data: uc09-synthetic-legal-passages (n=40; synthetic, written for this benchmark; licence CC0 (synthetic))
- Code: [`suites/uc09_legal/`](suites/uc09_legal/) · results: [`results/uc09_legal.json`](results/uc09_legal.json) · every output: `results/raw/uc09_legal.jsonl`

**Verdict.** For translating court orders, RTI replies and tribunal awards into Hindi, Tamil, Marathi or Bengali, gemini-3.8-flash, sarvam-105b (think off) and sarvam-translate:v1 all keep about 99.5% or more of the facts. Hindi is essentially solved, and Tamil is where they differ. If you want a Sarvam stack, prefer sarvam-105b: it matched sarvam-translate on facts at roughly 1/80th of the list cost per passage. Do not use mayura:v1 for legal or financial text: it loses about one fact in every two passages and garbles decimal crore amounts (₹25.5 crore became 5 crore). For plain-language litigant summaries, every non-Sarvam cloud model tested (gemini-3.8-flash, gpt-5.4-mini, claude-haiku-5.5, and the frontier tier on its subset) is clearly better: 98% of key facts and no invented numbers, against 85% and 9% of summaries with unsupported numbers for sarvam-105b. If you use sarvam-105b, either keep thinking off or give it at least 16k max_tokens (89% recall at about 20x the tokens and 21 s); tell it not to compute dates or totals, and check every number in the output against the source before it reaches a litigant. Self-hosted, qwen3-30b did better than sarvam-30b on this small sample.

- Translation, share of source facts preserved (120 passage-language items each): gemini-3.8-flash 99.8% [99.6, 100], sarvam-105b (think off) 99.6% [99.3, 99.9], sarvam-translate:v1 99.5% [99.1, 99.8], mayura:v1 96.2% [95.1, 97.3]. Facts dropped or altered per passage: 0.025 / 0.058 / 0.075 / 0.53. Every system wrote 100% of outputs in the target script.
- Hindi is nearly solved: no facts were lost by any system except mayura (0.1 per passage). Tamil is hardest. Dropped or altered facts per Tamil passage: mayura 0.68, sarvam-105b 0.18, sarvam-translate 0.13, gemini 0.05. Marathi and Bengali sit in between, with mayura at 0.9 and 0.75.
- mayura:v1 alters money and identifiers, and it is the only system that lost amounts at a meaningful rate (93.5% preserved vs at least 99.6% for the others). With a decimal crore amount it keeps only the digits after the point, in every language: ₹25.5 crore became '5 करोड़', '5 கோடி', '5 कोटी' and '5 কোটি', and ₹15.4 and ₹14.8 crore became 4 and 8 crore. That happened in 10 of 10 decimal-crore cases; the whole-number ₹20 crore was kept. It dropped cheque numbers and Act years. One Tamil passage got stuck repeating a sentence about 10 times. It changed a party's name (Rajendra Prasad Yadav became ராஜசேகர பிரசாத் யாதவ்). In one order it labelled both parties 'accused'.
- sarvam-translate:v1 altered 1 number in 120 items: cheque no. 493369 became '4933/69' in Bengali. Otherwise it matched the LLMs.
- Cost per 650-character passage at Sarvam list prices: the translate APIs cost about ₹1.25 (₹20 per 10k characters). sarvam-105b costs about ₹0.016 (about 230 input and 215 output tokens), roughly 80x cheaper, with equal or better fact preservation. Latency p50: mayura 1.5 s, sarvam-105b 1.5 s, sarvam-translate 1.8 s, gemini 3.7 s.
- Litigant summaries, key-fact recall (80 items each, 6 facts per item): gemini-3.8-flash 98.3% [96.9, 99.4], sarvam-105b think off 85.2% [81.5, 88.7], think on 72.1% [63.5, 80.4]. Mostly sarvam-105b omits dates and case or FIR numbers: by type it kept 77% of dates, 81% of numbers and 91% of amounts, against Gemini's 100% / 96% / 100%.

### uc10-selfhost-business

**10. Self-hosting Sarvam-30B for business text.** Can an Indian business run Sarvam-30B on its own hardware instead of a cloud API, and what does it give up in accuracy and speed?

- Data: uc10 synthetic support & back-office set (n=150; synthetic, written for this benchmark; licence CC-BY-4.0 (this repo))
- Code: [`suites/uc10_selfhost_business/`](suites/uc10_selfhost_business/) · results: [`results/uc10_selfhost_business.json`](results/uc10_selfhost_business.json) · every output: `results/raw/uc10_selfhost_business.jsonl`

**Verdict.** Self-hosting Sarvam-30B works on a 128 GB Mac-class box: about 21 GB of memory, ~27 tok/s single-stream and a 1 s first token on a 1k-token Indic prompt. That is faster than Qwen3-30B-A3B, largely because its tokenizer needs 2.4x fewer tokens for the same Indic text. But the official Q4_K_M build is the least accurate system tested on Indian back-office tasks: 63% fully correct vs 84% for Qwen3-30B-A3B without thinking and 91% with it. Its failures are about following output instructions, not understanding the text. If data must stay on-premises, Qwen3-30B-A3B (thinking on for accuracy, off for latency) is the better self-hosted choice today. Use Sarvam-30B only where its Indic token efficiency matters and code validates every output. If an API is allowed, any price-matched cloud model is clearly better: gemini-3.8-flash 100%, gpt-5.4-mini 99%, claude-haiku-5.5 96%, sarvam-105b with reasoning off 94% (₹0.87 per 150 items, 0.6 s). Keep 105B reasoning off for structured outputs. A GPU-less CPU box is only viable for overnight batch work.

- Fully-correct rate over 150 items (95% CI): gemini-3.8-flash 100% [100,100]; sarvam-105b reasoning off 94% [90,97]; Qwen3-30B-A3B local with thinking 91% [87,95], without 84% [77,89]; sarvam-105b reasoning on 80% [73,86]; Sarvam-30B local without thinking 63% [55,70], with thinking 61% [53,69]. Self-hosted Sarvam-30B trails the same-class Qwen3-30B-A3B by 21 points (no-think vs no-think) and the CIs do not overlap.
- Cloud comparators added later (ADDENDUM). Price-matched tier, full 150 items, thinking off: openai:gpt-5.4-mini 99%, claude-haiku-5.5 96% (p50 0.9 s and 1.5 s). Frontier tier, thinking on, fixed 30-item subset (6 per task, one per language): gemini-pro-latest 100%, claude-sonnet-5.5 100%, gpt-5.5 97% (its one miss is a language label). On the same subset: sarvam-105b 93%, Qwen3-30B thinking 97%, Sarvam-30B 67% without thinking. Every cloud model in the price-matched tier beats both self-hosted options. Because this set saturates at the top, the frontier runs add little.
- Sarvam-30B reads the Indic text fine; it loses on following output instructions. It gets order id 100%, amount 100%, intent 100% and invoice fields 97%. But only 23% of its CRM notes are in English with the date as YYYY-MM-DD: it often writes the note in the customer's language (30% non-English without thinking, 80% with thinking) and keeps dates as '13 ऑगस्ट 2026'. It labels the ticket language correctly 20% of the time, calling Tamil, Telugu and Bengali tickets 'hinglish' or 'english'. Qwen3 makes the same Hindi/Marathi/Hinglish confusions but gets the other scripts right (67%).
- Thinking does not help Sarvam-30B here: 61% vs 63%. It averages 1,610 output tokens per item (vs 66) and p50 latency rises from 8.6 s to 150 s on the shared GPU. Qwen3 gains 7 points from thinking at 386 tokens per item.
- sarvam-105b is better with reasoning OFF (94%) than ON (80%). With reasoning on, 15 of 90 JSON answers break. 7 have keys and values translated into the customer's language, e.g. {"सेंटिमेंट": "पॉजिटिव", "एस्केलेट": फॉल्स}, and 8 do not parse. 23% of CRM notes also come out non-English. Reasoning on also costs 11x more at list price (₹9.43 vs ₹0.87 for 150 items; 143k reasoning tokens) and is 7x slower (p50 4.6 s vs 0.6 s).
- Speed on dedicated measurement servers, thinking off, same business prompt. Sarvam-30B Q4_K_M on GPU: prompt 1,003-1,031 tok/s, generation 26.4-27.4 tok/s single-stream, TTFT 1.07 s, aggregate 40-56 tok/s with 4 concurrent requests. Qwen3-30B-A3B Q4_K_M: 776-787 tok/s, 18.5-18.7 tok/s, TTFT 3.2-3.6 s, aggregate 26-28 tok/s. The same prompt is 1,014 Sarvam tokens vs 2,428 Qwen3 tokens (the token tax, see uc12), so Sarvam reaches its first token about 3x sooner.

### uc11-bharat-code

**11. Bharat Code: coding agents for Indian business logic, prompted in Indian languages.** Can these models act as coding agents for Indian business logic when the developer writes the task in their own language (Hindi, Tamil, Hinglish) instead of English? And can they drive a payments-app tool schema from Indian-language voice commands?

- Data: uc11 Bharat Code (40 tasks x 4 prompt languages) + 50 tool-calling commands (n=160; synthetic, written for this benchmark; licence CC-BY-4.0 (authored here))
- Code: [`suites/uc11_bharat_code/`](suites/uc11_bharat_code/) · results: [`results/uc11_bharat_code.json`](results/uc11_bharat_code.json) · every output: `results/raw/uc11_bharat_code.jsonl`

**Verdict.** For an Indian team building fintech, GST or HR logic with an AI coding assistant, any of the price-matched cloud models works. Gemini-3.8-flash (100% first try, think off), Claude Haiku 5.5 (99%) and GPT-5.4-mini with thinking (98%) all reach 97-100% after test-feedback repair, in English, Hindi, Tamil and Hinglish alike. Frontier models are not needed for this class of task. Sarvam-105b is not yet a reliable coding agent for this work. Use it only with thinking on and a test loop (83% within 3 attempts, ~46 s and ~8.5k tokens per solved task), retry its frequent empty replies, and never trust it with checksum algorithms (Verhoeff/Aadhaar) without tests. For Indian-language voice-command tool calling, Sarvam-105b, Gemini, Claude and GPT score 94-100% on these payment commands (thinking-on variants 98-100%; the misses are fractional amounts like paune teen sau = 275), so choose on price, latency or data residency. Watch OpenAI's Responses-API strict default with optional arguments. If you must self-host, Qwen3-30B-A3B beat the official Sarvam-30B Q4 GGUF on code (42% vs 20%) and on tool calls, and was about 10x faster. Neither is usable as an unattended coding agent.

- Gemini-3.8-flash (think off) solved every task in every language on the first try: pass@1 100% (95% CI 100%-100%, n=160). Sarvam-105b reached 56% (95% CI 48%-63%, n=160) with thinking off and 68% (95% CI 61%-75%, n=160) with thinking on (temperature 0.5, as Sarvam's docs recommend for thinking mode).
- Test-feedback repair helps Sarvam: thinking on goes from 68% to 83% within 3 attempts, and thinking off goes from 56% to 64%. With thinking off at temperature 0, Sarvam-105b re-sent byte-identical code in 63 of 131 repair turns (48%), even though the failing asserts were in its context. At temperature 0.7 that drops to 18%, and pass@3 is 67% vs 64%, but pass@1 falls to 51%.
- Sarvam-105b thinking mode often never answers. In 71 of 245 calls (29%) it used the whole 16k-token budget on reasoning and returned content=null. Its reasoning_content was also null, so the tokens are billed and nothing is visible. A 32k-token retry of one such item also ran out. Solved items cost 8539 output tokens and 46.0 s on average, vs 481 tokens and 3.2 s with thinking off (about ₹1.03 vs ₹0.16 per solved item at list price).
- Ironically, the Aadhaar checksum is Sarvam's blind spot. On the two Verhoeff tasks (validate an Aadhaar-format number, generate a check digit), Sarvam-105b solved 0% of 8 items first try with thinking off and 0% with thinking on, vs Gemini-3.8-flash 100%. Its Verhoeff implementations either crashed (IndexError/TypeError on the tables) or returned wrong check digits. Other consistent Sarvam failures were compact '1.25 Cr' formatting, advance-tax instalment boundaries (on 15 Sep it returned 15% instead of 45%), and GST invoices where it rounded the total tax and then floor-halved it (898 paise) instead of computing CGST and SGST separately as specified (899).
- Language penalty (English pass@1 minus the other language, paired by task): Sarvam-105b with thinking off loses +0.17 on Hinglish (CI +0.00 to +0.35), +0.12 on Hindi and +0.07 on Tamil. With thinking on the penalty disappears (hi -0.05, ta -0.03, hinglish -0.05; all CIs span 0). Gemini scores 100% in every language, so it has no measurable penalty. Writing the task in Tamil or Hindi did not hurt any system by a statistically clear margin. The only borderline case is Sarvam with thinking off on Hinglish and Hindi.
- Tool calling is solved for this kind of schema. Every API system used native tools (Sarvam /v1/chat/completions accepts OpenAI-style `tools` and `tool_choice`, and returns `tool_calls`). sarvam-105b: base 100%, hard 100%; sarvam-105b-think: base 100%, hard 95%; gemini-3.8-flash: base 100%, hard 100%; gemini-3.8-flash-think: base 100%, hard 100%; gpt-5.4-mini: base 97%, hard 95%; gpt-5.4-mini-think: base 100%, hard 100%; claude-haiku-5.5: base 97%, hard 90%; claude-haiku-5.5-think: base 100%, hard 100%; gemini-pro-latest-think: base 100%, hard 100%; gpt-5.5-think: base 100%, hard 100%; claude-sonnet-5.5-think: base 100%, hard 100%; sarvam-30b-local: base 73%, hard 40%; qwen3-30b-local: base 90%, hard 80%. Hard items include 'पौने दो हज़ार' (1750), 'paune teen sau' (275), 'সাড়ে তিনশো' (350), 'ஈபி பில்' (electricity) and 'Tata Play' (DTH).

### uc12-token-tax

**12. The Indic token tax.** What does each model's tokenizer charge you, in tokens (and so in money, latency and context window), for the same sentence written in each Indian language?

- Data: FLEURS transcripts (FLoRes-101 sentences) (n=100; public; licence CC-BY-4.0)
- Code: [`suites/uc12_token_tax/`](suites/uc12_token_tax/) · results: [`results/uc12_token_tax.json`](results/uc12_token_tax.json) · every output: `results/raw/uc12_token_tax.jsonl`

**Verdict.** Claude is the expensive outlier among the cloud models: 1.9-6.6x Sarvam's tokens on Indic text (Kannada and Punjabi worst), and 1.6x even on English. OpenAI's tokenizer sits between Sarvam and Claude (0.8-3.5x Sarvam: cheaper only on Sindhi, worst on Odia). If your traffic is mostly Hindi, Bengali, Marathi, Tamil, Urdu or Nepali, Sarvam and Gemini/Gemma tokenize identically, so per-token price is the only cost lever. For Telugu, Kannada, Malayalam, Gujarati, Punjabi and especially Odia, Sarvam's tokenizer needs 18-60% fewer tokens than Gemini's on the same text. Avoid Qwen3-class byte-level tokenizers for Indic workloads: 3-10x the tokens of English means 3-10x the generation time when self-hosted and a context window that holds 3-10x less Indic text.

- Average Indic token tax (tokens vs the same sentence in English, mean over 14 languages): Sarvam (30B/105B tokenizer) 1.55x, Qwen3-30B-A3B 5.89x, Gemma 4 1.89x, Gemini 3.8 Flash (count_tokens) 1.89x, OpenAI gpt-5.4-mini (API prompt_tokens) 2.10x, Claude Haiku 5.5 (OpenRouter prompt_tokens) 3.44x.
- Sarvam's tokenizer is the cheapest of the 6 on 12/14 Indic languages; per language the cheapest is: Hindi=sarvam, Bengali=sarvam, Marathi=sarvam, Telugu=sarvam, Tamil=sarvam, Gujarati=sarvam, Kannada=sarvam, Malayalam=sarvam, Punjabi=sarvam, Odia=sarvam, Assamese=openai, Urdu=sarvam, Nepali=sarvam, Sindhi=openai.
- Qwen3 spends this many times more tokens than Sarvam on the same sentence: Odia 7.1x, Telugu 5.0x, Punjabi 4.9x, Kannada 4.7x, Gujarati 4.7x, Malayalam 4.6x, Tamil 4.3x, Bengali 4.3x, Hindi 3.5x, Marathi 3.4x, Nepali 2.9x, Assamese 2.7x, Urdu 2.1x, Sindhi 1.4x (English 1.03x).
- Worst/best tokenizer spread per language (same sentence): Odia 7.1x, Punjabi 6.6x, Kannada 6.0x, Telugu 5.0x, Gujarati 4.7x, Malayalam 4.6x, Tamil 4.3x, Bengali 4.3x, Hindi 3.5x, Marathi 3.4x, Nepali 2.9x, Assamese 2.8x, Urdu 2.5x, Sindhi 2.3x.
- Implied sarvam-105b list cost per 1,000 FLEURS sentences sent as input: English INR 0.36, Hindi INR 0.47, Bengali INR 0.45, Marathi INR 0.51, Telugu INR 0.53, Tamil INR 0.53, Gujarati INR 0.55, Kannada INR 0.56, Malayalam INR 0.59, Punjabi INR 0.56, Odia INR 0.51, Assamese INR 0.73, Urdu INR 0.55, Nepali INR 0.56, Sindhi INR 0.74; as generated output (INR 60/1M) multiply by 4.
- Cross-check: Sarvam API prompt_tokens minus the HF tokenizer count is a constant per sentence (distinct deltas across all 150 sampled sentences: [14]), i.e. the API bills exactly the open tokenizer plus a fixed chat-template overhead.


## Licence

Code: MIT. Authored test data and results: CC-BY 4.0. FLEURS/FLORES-derived text: CC-BY 4.0 (Google). Model outputs are
included for auditability.
