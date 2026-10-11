# UC03 Documents: KYC, GST invoices, land records and bills in Indian scripts

**Business question.** A lender, an accounting firm or a land-records service has to turn Indian-language
paperwork into structured data: GST invoices, account-opening (KYC) forms, 7/12 and patta land extracts,
electricity bills, ration cards. Some of it arrives as clean scans and some as phone photos. Which stack gets the
fields right, how fast, and at what cost?

## Why the test is realistic
- **Six document types that Indian back offices actually process.** GST tax invoices are bilingual, with GSTIN,
  HSN, and CGST+SGST (intra-state) or IGST (inter-state) lines. KYC forms have Indic labels and handwriting-style
  English entries. The Maharashtra 7/12 extract is in Marathi with **Devanagari digits** (१२३). The Tamil Nadu
  patta/chitta is in Tamil. Electricity bills are in Kannada and Telugu. Ration cards are in Bengali and Hindi.
- **8 scripts:** Devanagari (hi, mr), Tamil, Bengali, Kannada, Telugu, Gujarati, Malayalam.
- **Three capture conditions:**
  - `clean`: the PNG render.
  - `photo`: the same page on a darker table, rotated ±3°, with a perspective skew, an uneven-lighting gradient,
    Gaussian blur, 0.8x downscaling and JPEG quality 40–55.
  - `harsh`: a bad photo with ±6° tilt, strong skew, a hand-shadow band, sensor noise, 0.55x resolution and JPEG
    quality 22–30. It covers 16 pages only (one per type/language group plus 5) to stay inside the Sarvam budget.
- **Scoring needs no AI judge.** Each page has 11–14 gold fields and its full gold text.

## Data (synthetic)
`make_data.py` creates 60 pages × 2 conditions, plus 16 harsh photos, in `data/uc03_documents/pages/`, with gold in `gold.jsonl`.
- **Every value is invented.** Names come from lists of common names. GSTINs carry a valid mod-36 check digit but
  are random. PANs are random, Aadhaar appears only as a masked last-4. Every page says `SAMPLE`. No real
  organisation's name or branding is used: the bank, the power company and the issuing offices are labelled
  fictitious.
- **Rendering.** Text is shaped with macOS CoreText (`render.swift`, run by `make_data.py`) using system fonts:
  Kohinoor, ITF Devanagari Marathi, Tamil/Malayalam Sangam MN, Noto Sans Kannada, and Noteworthy for the
  handwriting style. Pillow on this machine has no libraqm, so it would draw Indic conjuncts and vowel signs in the
  wrong order. Pillow is used only for the photo degradation.
- **Mix:**

  | Document | Pages by language |
  |---|---|
  | GST invoice | 12 (hi 5, gu 4, ta 3) |
  | KYC form | 10 (hi 5, ml 5) |
  | 7/12 extract | 10 (mr) |
  | Patta | 10 (ta) |
  | Electricity bill | 10 (kn 5, te 5) |
  | Ration card | 8 (bn 5, hi 3) |

  783 gold fields in total.
- **Licence:** CC0. The fonts are only used to make the images.

## Systems
| name | what it is |
|---|---|
| `sarvam-vision` | Sarvam Vision document intelligence, run as a job with markdown output (scored on text only) |
| `sarvam-vision+sarvam-105b` | Vision markdown, then field JSON from `sarvam-105b` with thinking off: the all-Sarvam pipeline |
| `sarvam-vision+gemini-3.8-flash` | the same markdown, with Gemini doing the extraction (isolates OCR quality from extraction quality) |
| `gemini-3.8-flash` | the page image sent straight to Gemini, which returns the same JSON schema |
| `gemini-3.8-flash-ocr` | the page image sent to Gemini for a plain transcription (for text accuracy against the same gold) |
| `openai:gpt-5.4-mini`, `or:anthropic/claude-haiku-5.5` | price-matched tier, sent the image directly (OpenAI chat format, image as a data URI) with the same JSON schema, think off, on all 136 images |
| `gemini-pro-latest`, `openai:gpt-5.5`, `or:anthropic/claude-sonnet-5.5` | frontier ceiling, think on, on a fixed 30 images: the 16 harsh photos plus the phone photos of the first 14 other pages (`FRONTIER_SET` in run.py) |

Sarvam Vision job flow (from the Sarvam docs):
1. `POST /doc-digitization/job/v1` with `{job_parameters:{language, output_format:"md"}}`.
2. `POST .../upload-files` with `{job_id, files:["page.zip"]}`.
3. `PUT` the ZIP to the presigned Azure URL with header `x-ms-blob-type: BlockBlob`.
4. `POST .../{job_id}/start`.
5. Poll `GET .../{job_id}/status`.
6. `POST .../{job_id}/download-files` returns a ZIP containing `document.md` plus a JSON file per page.

Uploads must be a PDF or a ZIP, so each page is sent as a one-image ZIP. One job is used per page, which gives
per-page latency and isolates failures.

## Run
```
.venv/bin/python suites/uc03_documents/make_data.py   # once; deterministic (seed 2026)
.venv/bin/python suites/uc03_documents/run.py         # resumable; skips (id, cond, system) already in raw
```

## Metrics
- **Field exact-match accuracy.** The share of gold fields that are exactly right after normalisation:
  - Unicode NFC, zero-width characters removed, Indic digits folded to ASCII.
  - Lower-cased; whitespace and `, . - / : ₹ ( )` stripped.
  - Numbers compared as numbers, so `1,93,200.00` equals `193200`.
  - A null tax line counts as 0.
  - Names must stay in the printed script. A transliteration counts as wrong.
- **Pages with every field correct.** The straight-through-processing rate a back office cares about.
- **Order-free CER and gold-word recall** of the full-page text. Reading order on forms and tables is ambiguous
  (labels beside or above values), and plain CER gave a perfect transcription 0.38. Order-free CER aligns words
  instead. Markdown and HTML table markup is stripped first.
- **Latency per page** (p50 / p95). For the Vision pipelines this includes the whole job: create, upload, start,
  poll and download.
- **Cost per 1,000 pages.** Sarvam Vision ₹0.50 per page plus sarvam-105b tokens at list price. For Gemini, tokens
  per 1,000 pages are recorded but not priced.
- **Breakdowns** by script, by document type, and the most-missed fields per system.
