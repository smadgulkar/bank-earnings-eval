SYSTEM:
You are a sell-side bank equity research analyst on earnings morning. You work only from the filing text you are given. Every number you report must come from a specific block of that text, cited by its block id. If a figure is not disclosed, say so; never estimate a figure the bank did not report.

USER:
# Task: <Bank name> <Quarter> earnings

Below is <Bank name>'s earnings release and financial supplement for <Quarter>, split into
numbered blocks like [B0123]. Do three things.

1. **Extract** every metric in the table below, in the stated unit, citing the block id the
   number appears in.
2. **Prior quarter:** report the prior-quarter (Q2) value for eps_reported, nii, nim, nonint_expense, provision, with
   citations, and the quarter-over-quarter change for each.
3. **Write the earnings note** (max 400 words, markdown): headline result and whether it beat
   or missed the prior quarter; what drove EPS; revenue and margin; credit; capital and returns;
   guidance changes; and a final line on whether this quarter changes the investment thesis.
   State whether you are discussing reported or adjusted EPS, and strip out notable items when
   explaining the underlying trend.

## Metrics
| key | what | unit |
| --- | --- | --- |
| eps_reported | GAAP diluted earnings per common share for the quarter. | US$ per share (e.g. 1.27) |
| eps_adjusted | The bank's own adjusted / ex-notable-items diluted EPS. null if the release gives none. | US$ per share (e.g. 1.27) |
| net_income_common | Net income available to common shareholders, GAAP. | US$ millions (e.g. 1834.5) |
| notable_items_eps | Total after-tax EPS impact of items the bank calls notable/significant. Negative if they reduced EPS. null if none disclosed. | US$ per share (e.g. 1.27) |
| nii | GAAP net interest income (not FTE). | US$ millions (e.g. 1834.5) |
| nim | Headline NIM as the bank reports it; declare the basis (FTE or GAAP) in nim_basis. | percent (e.g. 3.12 for 3.12%) |
| nonint_income | GAAP noninterest income, including any securities gains/losses. | US$ millions (e.g. 1834.5) |
| nonint_expense | GAAP noninterest expense. | US$ millions (e.g. 1834.5) |
| efficiency_ratio | The bank's headline (reported, not adjusted) efficiency ratio, using its own definition. | percent (e.g. 3.12 for 3.12%) |
| provision | Total provision for credit losses for the quarter. | US$ millions (e.g. 1834.5) |
| nco | Net charge-offs in dollars for the quarter. | US$ millions (e.g. 1834.5) |
| nco_ratio | Annualized net charge-offs to average loans. | percent (e.g. 3.12 for 3.12%) |
| acl_ratio | Allowance for credit losses to period-end total loans (use the bank's headline ACL ratio). | percent (e.g. 3.12 for 3.12%) |
| avg_loans | Average total loans (and leases) for the quarter. | US$ millions (e.g. 1834.5) |
| avg_deposits | Average total deposits for the quarter. | US$ millions (e.g. 1834.5) |
| eop_deposits | Total deposits at quarter end. | US$ millions (e.g. 1834.5) |
| cet1 | Common equity tier 1 ratio at quarter end (estimated/preliminary is fine, as reported). | percent (e.g. 3.12 for 3.12%) |
| tbvps | Tangible book value per common share at quarter end. | US$ per share (e.g. 1.27) |
| rotce | Headline return on average tangible common equity, as reported (annualized). | percent (e.g. 3.12 for 3.12%) |
| buybacks | Dollar amount of common shares repurchased in the quarter. 0 if the release says none; null if not disclosed. | US$ millions (e.g. 1834.5) |

## Output
Return ONE JSON object and nothing else, in this shape (comments are guidance only):

```json
{
  "metrics": {
    "<key>": {"value": 1834.5, "source": "B0142", "not_disclosed": false}
    // one entry for EVERY key in the table; value null + not_disclosed true if the release does not give it
  },
  "prior_quarter": {
    "<key>": {"value": 1801.0, "source": "B0142"}
    // prior quarter (Q2) values for: eps_reported, nii, nim, nonint_expense, provision
  },
  "changes_qoq": {
    "<key>": 33.5
    // current minus prior quarter, same units as the field (NIM change in percentage points)
  },
  "eps_basis_used_in_note": "reported | adjusted",
  "nim_basis": "FTE | GAAP | unclear",
  "notable_items": [
    {"description": "Securities repositioning loss", "eps_impact": -0.12, "source": "B0031"}
  ],
  "guidance": [
    {"item": "2026 NII growth", "quote": "exact words from the release", "source": "B0051"}
  ],
  "note_markdown": "The earnings note (max 400 words)."
}
```

## Filing text
<block-numbered filing text>
