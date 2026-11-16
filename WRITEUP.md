# Can frontier models do earnings morning at a bank?

*Shubhankar Madgulkar · [date] · models run [date]*

<!-- Six parts, one page. Fill in after `beval.aggregate` and `beval.chart`. -->

## Headline

[One sentence with the finding and its number, e.g. "The best model got X% of 25 figures right from ten Q3 2026 bank
releases, but only Y% of its notes handled notable items correctly."]

## Scores

![Score by dimension](results/baseline/scores.png)

[One sentence on what the chart shows that matters.]

## Where they fail

| Root cause | Model A | Model B | Model C | What it means |
| --- | --- | --- | --- | --- |
| Model limitation | | | | |
| Data or retrieval | | | | |
| Workflow | | | | |
| Product design | | | | |

<!-- counts from results/baseline/root_causes.csv -->

## Three failures a bank analyst would catch

1. **[Bank, trap]**. The filing says: "…" [block]. The model wrote: "…". Why it matters: …
2. …
3. …

## What a finance product should do about it

1. [Decision taken from failure type 1, e.g. route every derived number through code and show the formula]
2. [Supply the prior quarter automatically, so period mismatches can't happen]
3. [Require a citation for every figure and show the source block next to the claim]
4. [Treat "not disclosed" as a first-class answer]
5. [Measured gain from the scaffold condition, if run]

## Method and limits

Ten banks, three models, three runs each (90 runs). Ground truth was hand-keyed and checked against cited blocks
(`beval.ground_truth validate`). One grader (me, 16 years in equities, former US banks coverage), grading blind.
Small sample: the results show patterns, not rankings. Code, prompts, raw outputs and grades: this repo.
