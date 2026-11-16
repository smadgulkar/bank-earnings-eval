# Bank Earnings Eval

How well do frontier models do a bank analyst's earnings-morning job? Each model gets a US bank's
Q3 2026 earnings release (filed after the models' training cutoffs) and has to:

1. **Extract** 20 metrics (EPS, NII, NIM, credit, capital, returns), each cited to a block of the filing.
2. **Report the prior quarter** for 5 of them and compute the quarter-over-quarter change.
3. **Write a 400-word earnings note** that a portfolio manager could act on.

Scoring is out of 100 points. Accuracy (30) and source traceability (20) are checked automatically. Judgment on real
filing traps (25), note quality (15) and ease of review (10) are graded blind. Every miss is tagged with a
root cause: **model limitation, data or retrieval, workflow, or product design**.

> Results: see [WRITEUP.md](WRITEUP.md).

## Run it

```bash
pip install -r requirements.txt
python -m pytest -q tests                   # offline end-to-end dry run on a synthetic bank

export SEC_USER_AGENT="Your Name you@email.com"
python -m beval.fetch --check               # confirm the 10 CIKs map to the right banks
python -m beval.fetch                       # download each bank's earnings 8-K exhibits
python -m beval.prepare                     # -> prepared/<TICKER>/document.txt (block-numbered)

python -m beval.ground_truth template PNC TFC FITB KEY HBAN RF MTB CFG ZION FHN
#   fill ground_truth/<TICKER>.json and traps/<TICKER>.json by hand from document.txt
python -m beval.ground_truth validate        # every value must appear in the block you cited

# set model ids in config/models.json, then:
export OPENAI_API_KEY=... ANTHROPIC_API_KEY=... GEMINI_API_KEY=...
python -m beval.prompt                       # writes prompts/task.md (the exact prompt, for the record)
python -m beval.runner --only-bank PNC --runs 1     # smoke test, then:
python -m beval.runner                       # 10 banks x 3 models x 3 runs = 90 runs, resume-safe

python -m beval.score                        # accuracy, citations, auto traps, arithmetic
python -m beval.grade make                   # blind packets; fill grade/baseline/*.csv
python -m beval.aggregate                    # 100-point scores + root-cause counts
python -m beval.chart                        # results/baseline/scores.png
```

Stretch: write `context/<TICKER>.md` (prior-quarter figures, required-citation reminder) and run
`--condition scaffold` on the weakest model to measure how much product scaffolding recovers.

## Design choices

- **Identical text input for every model.** Exhibits are converted to numbered blocks (`[B0142] Net interest
  income | $1,834 | $1,798`). No model gets an advantage from better PDF handling, and every citation can be checked.
- **Post-cutoff filings.** Q3 2026 releases came out in October 2026, so the models can't answer from memory.
- **Fixed units and tolerances** (`beval/fields.py`): $ millions within ±0.5%, ratios within ±1 bp, per-share within ±$0.005.
- **"Not disclosed" is a valid answer.** Making up a figure the bank didn't report counts as an error.
- **Blind grading.** Packets carry no model name and are shuffled. The key is published only after grading.
- **Plain HTTPS** calls to each lab's API (`beval/runner.py`), so there are no SDK-version effects; raw outputs are saved.

## Layout

```
config/        banks (EDGAR CIKs) and models
beval/         fetch, prepare, prompt, runner, score, grade, aggregate, chart
filings/       meta.json per bank (raw exhibits are re-fetchable, not committed)
prepared/      block-numbered filing text given to every model
ground_truth/  hand-keyed values with block citations
traps/         where each filing's traps sit
runs/          raw model outputs
grade/         blind packets and grading sheets
results/       scores, failures with root causes, chart
```

Public SEC filings only. Model versions and run dates are recorded in every run file.
