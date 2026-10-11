# uc05: Mixed-language consultation -> English clinical note

**Business question.** Indian outpatient consultations are spoken in a mix of the local language and English
("BP थोड़ा high है, 150 by 96"). A clinic wants an AI scribe that turns the conversation, either a transcript
or the recording, into a structured English OPD note. Which model captures the facts, and which one invents a
medicine or a dose? Inventing one is the safety risk that matters most.

## Why the test is realistic
- There are 40 dialogues, 8 in each of 5 language mixes: Hinglish, Malayalam-English, Tamil-English,
  Bengali-English and Marathi-English. Hinglish has 4 dialogues in Devanagari and 4 in romanised
  WhatsApp-style text.
- They cover fever, diabetes, hypertension, pregnancy follow-up and paediatrics (a parent speaking for the
  child), with 11-16 turns each.
- The doctor code-mixes English medical terms, as Indian OPD doctors do. Medicines are named by brand and
  generic. Frequencies are said the way they are in clinic: "subah-shaam", "1-0-1", "दिन में तीन बार". A few
  vitals are spoken as words in the local language rather than digits.
- Every dialogue contains at least one **trap**:
  - a drug that is mentioned but not prescribed (self-medicated, stopped, or asked for and refused);
  - a dose the doctor corrects mid-sentence;
  - an allergy disclosed late that changes the drug.

  A scribe that copies every drug name it hears fails these.

## Data (`data/uc05_clinical_notes/`)
- `dialogues/dNN.json`: the turns plus gold facts: complaint and duration, vitals, diagnosis, each
  medicine (drug aliases, dose, canonical frequency OD/BD/TDS/QID/HS/SOS/weekly, duration in days or null for
  ongoing), allergies, red-flag advice, follow-up, `not_prescribed` trap drugs, and a one-line `trap`
  description.
- `audio/dNN.wav`: 15 dialogues (3 per language mix), voiced with `gemini-3.8-flash-tts` using two prebuilt
  voices (Doctor = Charon, Patient/Attendant = Kore), 24 kHz mono.
- `stt/`, `stt_v4_translate/`, `stt_v4_codemix/`, `stt_openai/`: cached STT outputs, one per dialogue.
- Synthetic: dialogues written by an LLM author (Claude) with fake names. Doses are clinically plausible but
  this is **not** medical guidance. Licence CC-BY-4.0.

## Systems
**Text track** (the dialogue text goes to the model, which returns JSON):
- **Sarvam:** `sarvam-105b`, thinking off and on.
- **Price-matched comparators, thinking off and on:** `gemini-3.8-flash`, `openai:gpt-5.4-mini`,
  `or:anthropic/claude-haiku-5.5`.
- **Frontier, thinking on, 30 of the 40 dialogues** (`dataset.frontier_subset_ids`): `gemini-pro-latest`,
  `openai:gpt-5.5`, `or:anthropic/claude-sonnet-5.5`.
- **Self-hosted:** `sarvam-30b-local` and `qwen3-30b-local` (thinking off, all 40).

**Audio track** (the 15 voiced dialogues):
- `audio:saaras-v3-translate+sarvam-105b`: Sarvam batch STT with `mode=translate` and diarization
  (2 speakers), then sarvam-105b writes the note.
- `audio:saaras-v4-translate+sarvam-105b`: as above with `saaras:v4` (released Sep 2026). It takes
  `with_diarization` directly; the name `saaras:v4-multispk` is rejected as deprecated.
- `audio:saaras-v4-codemix+sarvam-105b`: `saaras:v4` in `mode=codemix`, which keeps English terms in a
  source-language transcript. sarvam-105b then translates while writing the note.
- `audio:gemini-3.8-flash`: the WAV goes inline to the model, which writes the note directly.
- `audio:gpt-4o-transcribe+gpt-5.4-mini`: an OpenAI transcript in the source language, then gpt-5.4-mini
  writes the note.

All systems get the same prompt, `NOTE_PROMPT` in `run.py`.

## Run
```
.venv/bin/python suites/uc05_clinical_notes/run.py                    # TTS + text and audio API systems
.venv/bin/python suites/uc05_clinical_notes/run.py --systems sarvam-30b-local qwen3-30b-local
.venv/bin/python suites/uc05_clinical_notes/run.py --score-only
.venv/bin/python suites/uc05_clinical_notes/test_score.py             # scorer self-check
```
Runs are resumable. Notes already in `results/raw/uc05_clinical_notes.jsonl`, audio files and STT outputs are
reused, not regenerated.

## Metrics (`results/uc05_clinical_notes.json`)
| metric | meaning |
|---|---|
| `recall_<field>` | chief complaint, duration, diagnosis, follow-up, vitals (share of gold vitals with the right value), red flags (share of gold warnings present), med_found (share of prescribed drugs listed) |
| `fact_recall_overall` | mean of the field recalls above, per note |
| `medication_exact_drug_dose_freq` | share of prescribed medicines with drug, dose and frequency all correct (`_incl_duration` also requires the duration) |
| `hallucinated_meds_or_doses_per_note` | **safety metric**: medicines listed that were not prescribed, plus doses whose number never occurs in the dialogue |
| `notes_with_any_hallucinated_med_or_dose` | share of notes with at least one such error |
| `trap_drug_listed_as_prescribed` | share of notes that list a `not_prescribed` drug |
| `note_fully_in_english` | the note contains no Indic-script characters, so it really is an English note |
| `allergy_capture_rate` / `false_allergy_rate` | allergy recorded when there is one / an allergy invented when there is none |

How matching works:
- **Free-text fields** use the author's alias lists. An alias matches if at least 2/3 of its content words
  appear in the output, with a 4-letter stem match, so "no urine" matches "No urination for 8 hours". This
  is still stricter than a human reader, which pushes absolute recall on red flags and complaints down. All
  systems are scored the same way.
- **Doses** are normalised (1 g = 1000 mg).
- **Frequencies** are canonicalised ("twice daily" and "1-0-1" both become BD). HS counts as equal to OD,
  because "once a day, at night" is correctly written either way.

Each metric also has `values_audio_subset`, which scores every system on the same 15 voiced dialogues, so
the text and audio tracks can be compared directly. `speaker_attribution` reports, for the saaras diarized
output, how often exactly 2 speakers were detected and the ratio of detected to scripted speaker changes.
