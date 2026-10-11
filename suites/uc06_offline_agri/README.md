# UC06: Offline crop advisory

**Question:** where connectivity is poor (a village kiosk, an FPO office, a KVK field laptop), can an open-weight
model running on a local box answer farmers' questions correctly, from an advisory sheet, in the farmer's own
language and script? Does it still work without a GPU?

Sarvam's on-device stack (Sarvam Edge) cannot be downloaded publicly, so this suite tests the route a developer can
actually take today: the open Sarvam-30B weights (official Q4_K_M GGUF) under llama.cpp, against the same-class
Qwen3-30B-A3B.

## Data (synthetic, `data/uc06_offline_agri/`)
- `advisory_sheet.md`: a 770-word English advisory sheet covering paddy, cotton, soybean, wheat, one FICTIONAL seed
  subsidy scheme (clearly labelled) and spraying rules. Doses, seed rates, sowing windows and pest thresholds are
  modelled on typical state package-of-practice figures. The sheet says it is test material and not for real use.
- `questions.json` (built by `make_data.py`): 30 facts × 2 forms = 60 in-scope questions, plus 10 out-of-scope ones.
  - Each fact is asked in Hindi, Marathi, Kannada, Telugu, Tamil or Punjabi (5 facts per language).
  - Each fact is asked twice: once in native script and once romanised, the way many farmers type on phones
    (`dhaan mein ek acre mein kul kitna urea daalna hai?`).
  - The questions use farmer vocabulary: ਤੇਲਾ for aphid, ਨਰਮਾ for cotton in Punjab, ಕಂದು ಜಿಗಿಹುಳು for brown
    planthopper, ಗುಣಿ for hill.
  - The 10 out-of-scope questions ask about apple, tomato, chilli, sugarcane, cattle, market price, tomorrow's rain,
    loan interest, drip subsidy and PM-Kisan. None of these is answerable from the sheet.
- Gold for each question is the number or numbers in the sheet that the answer must contain.

## Prompt
The sheet goes in the system prompt, and the model is told to:
- answer only from the sheet
- reply in the farmer's language and script, and romanised if the farmer wrote romanised
- write numbers as digits, in 1-3 sentences
- answer `NOT_IN_SHEET` plus a helpline sentence when the sheet has no answer

## Metrics
- `grounded_correct`: in-scope answers that contain every gold number and are not a refusal (60 items). Native and
  romanised are also reported separately.
- `reply_language_correct`: the answer's dominant script matches the question. For Hindi vs Marathi, function-word
  markers decide. A romanised answer must be Latin script and not English (English stopwords below 20%).
- `oos_refusal`: out-of-scope questions answered `NOT_IN_SHEET` (10 items).
- `false_refusal`: in-scope questions refused.
- `overall_pass`: correct (or refused, if out of scope) and in the right language.
- Latency: p50/p95 per answer. CPU systems are run one request at a time, which is what a single farmer at a
  GPU-less box would wait.

## Systems
- `sarvam-30b-local-nothink`, `qwen3-30b-local-nothink` (GPU, :8101/:8102), plus `-think` variants if run
- `sarvam-30b-cpu-nothink`, `qwen3-30b-cpu-nothink`: CPU-only llama-server on :8111, started per model:
  ```
  ~/embed-bench/llamacpp/llama-b11541/llama-server -m gguf/<model>.gguf --jinja -ngl 0 -dev none --no-op-offload \
      -c 32768 -np 4 --port 8111
  ```
- Online references: `sarvam-105b` (reasoning off), `gemini-3.8-flash`, `openai:gpt-5.4-mini`, `or:anthropic/claude-haiku-5.5` (all thinking off, full set)
- Frontier, thinking on, fixed 30-question `SUBSET` (all 10 out-of-scope + every 3rd fact in both forms): `gemini-pro-latest-think`, `openai:gpt-5.5-think`, `or:anthropic/claude-sonnet-5.5-think`. Compare these with the `*_subset30` metrics.

## Run
```
.venv/bin/python suites/uc06_offline_agri/make_data.py
.venv/bin/python suites/uc06_offline_agri/run.py gemini-3.8-flash sarvam-105b sarvam-30b-local-nothink qwen3-30b-local-nothink
# start the CPU server for one model, then:
.venv/bin/python suites/uc06_offline_agri/run.py sarvam-30b-cpu-nothink   # stop the server, repeat with qwen3-30b-cpu-nothink
.venv/bin/python suites/uc06_offline_agri/run.py --summarize
```
The run is resumable: items already in `results/raw/uc06_offline_agri.jsonl` are skipped. Thinking control for the
local models lives in `suites/uc10_selfhost_business/localcall.py`.

## Caveats
- A number being present is necessary but not sufficient. An answer that mentions the right number in a wrong
  context still passes, so this is an upper bound on correctness.
- One sheet and 60 questions give wide CIs (about ±10 points).
