# uc04: Q&A over company documents in Indian languages (RAG)

**Business question.** An Indian company puts its HR policy, insurance rules, bank charges or hospital
billing rules, written in Hindi, Tamil, Malayalam, Bengali, Marathi or Kannada, behind a chatbot. Employees
and customers ask in their own language, in English, or in WhatsApp-style romanised text ("OPD bills ka saal
ka reimbursement limit kitna hai?"). Which model gives the right number, replies in the user's language, and
says "not in the documents" instead of guessing?

## Why the test is realistic
- Six fictional but realistic policy documents, one per language, dense with numbers (₹ amounts, days,
  limits, dates, form codes, designations). Numbers are distinct within a document, so pulling the wrong
  section gives a wrong answer that the scorer catches.
- All six documents share **one** search index, as a help-desk bot over several sources would. This creates
  a real failure mode: a Tamil insurance question about dental cover retrieves the Hindi HR policy's dental
  rule, and a model that answers from it gives another organisation's figure.
- Every fact is asked three ways (native script, English, romanised code-mix) so the effect of question form
  is measured on the same facts.
- 24 of 132 questions have no answer in any document. Refusing is the right behaviour.

## Data (`data/uc04_indic_rag/`)
- `docs/<doc_id>.json`: 6 documents, 39 sections of 150-250 words. One section = one chunk.
- `questions/<doc_id>.jsonl`: 22 questions per document, 132 in total. 36 answerable facts x 3 forms = 108
  questions, plus 12 unanswerable facts x 2 forms = 24. Each answerable question records gold answer strings,
  the verbatim evidence sentence and the gold section.
- Synthetic: written by an LLM author (Claude) for this benchmark. Organisations, names and numbers are
  invented. The Marathi ration circular is marked as a sample and does not state real entitlements. A
  machine check confirmed that each gold answer occurs in its gold section and that no gold number occurs in
  any other section of the same document. Licence CC-BY-4.0.
- `embedding_cache.json`: cached gemini-embedding-2 vectors, so reruns cost nothing.

## Pipeline
1. Retrieval: `gemini-embedding-2` (3072-d). This model has no `task_type`, so the task goes in the text:
   queries are embedded as `task: search result | query: …`, chunks as `title: <heading> | text: …`. Top-5 by
   cosine similarity over all 39 chunks.
2. Generation: the system prompt says to answer only from the excerpts, reply in the user's language and
   script, and append `[NOT_FOUND]` when the answer is absent.
3. Two conditions:
   - **rag**: the top-5 retrieved chunks.
   - **oracle**: only the gold chunk, for answerable questions. This separates retrieval errors from
     generation errors.

**Systems:**
- **Sarvam:** `sarvam-105b` (thinking off), `sarvam-105b-think` (reasoning_effort medium),
  `sarvam-105b-conversations`.
- **Price-matched comparators, full set, thinking off:** `gemini-3.8-flash`, `openai:gpt-5.4-mini`,
  `or:anthropic/claude-haiku-5.5`.
- **Frontier ceiling, thinking on:** `gemini-pro-latest`, `openai:gpt-5.5`, `or:anthropic/claude-sonnet-5.5`.
  These ran on a fixed 38-question subset: 30 evenly spaced over the sorted qids plus 8 unanswerable,
  listed in `dataset.frontier_subset_qids`.
- **Self-hosted:** `sarvam-30b-local` and `qwen3-30b-local` (llama.cpp Q4_K_M, thinking off) ran the rag
  condition on all 132 questions.

The `values_frontier_subset` and `values_local_subset` fields give every system's score on the same
questions.

## Run
```
.venv/bin/python suites/uc04_indic_rag/run.py                                   # API systems
.venv/bin/python suites/uc04_indic_rag/run.py --systems sarvam-30b-local qwen3-30b-local
.venv/bin/python suites/uc04_indic_rag/run.py --score-only                      # rebuild results JSON from raw
```
Runs are resumable. Calls already in `results/raw/uc04_indic_rag.jsonl` are skipped, and failed calls,
including HTTP 402, are retried on the next run. After a 402 the script stops calling that API for the rest
of the run.

## Metrics (`results/uc04_indic_rag.json`)
| metric | meaning |
|---|---|
| `retrieval_recall_at5` / `_at1` | gold chunk is in the top 5 / ranked first; also broken down by question form |
| `answer_correct_rag` / `_oracle` | a gold string appears in the reply, with no `[NOT_FOUND]` tag. Indic digits are mapped to ASCII and commas inside numbers removed. Numeric golds are compared as whole numbers, so "12" does not match "120" |
| `reply_in_user_language_rag` | the reply's dominant script matches the question's. A romanised question expects a Latin-script reply |
| `unanswerable_refused_rag` | share of unanswerable questions answered with `[NOT_FOUND]` (higher is better) |
| `false_refusal_rag` | share of answerable questions answered with `[NOT_FOUND]` (lower is better) |
| `hallucinated_number_rate_*` | share of replies containing a number that is in neither the retrieved context nor the question. 1-12 and 2026 are ignored because they are usually a month or year re-rendered from a written date |

95% bootstrap CIs (2,000 resamples over questions) accompany every value. `per_language` breaks the main
metrics down by document language.
