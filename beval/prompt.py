"""Builds the task prompt from fields.py so the prompt, schema and scorer never drift.

`python -m beval.prompt` writes prompts/task.md (published with the repo).
"""

from pathlib import Path

from .fields import FIELDS, PRIOR_Q_FIELDS

ROOT = Path(__file__).resolve().parent.parent

UNITS = {
    "money_mm": "US$ millions (e.g. 1834.5)",
    "ratio_pct": "percent (e.g. 3.12 for 3.12%)",
    "per_share": "US$ per share (e.g. 1.27)",
}

SYSTEM = (
    "You are a sell-side bank equity research analyst on earnings morning. "
    "You work only from the filing text you are given. Every number you report must "
    "come from a specific block of that text, cited by its block id. If a figure is not "
    "disclosed, say so; never estimate a figure the bank did not report."
)


def field_table() -> str:
    rows = ["| key | what | unit |", "| --- | --- | --- |"]
    for f in FIELDS:
        rows.append(f"| {f.key} | {f.definition} | {UNITS[f.kind]} |")
    return "\n".join(rows)


SCHEMA_EXAMPLE = """{
  "metrics": {
    "<key>": {"value": 1834.5, "source": "B0142", "not_disclosed": false}
    // one entry for EVERY key in the table; value null + not_disclosed true if the release does not give it
  },
  "prior_quarter": {
    "<key>": {"value": 1801.0, "source": "B0142"}
    // prior quarter (Q2) values for: %s
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
}""" % ", ".join(PRIOR_Q_FIELDS)


def build_prompt(bank_name: str, quarter: str, document: str, context: str | None = None) -> str:
    ctx = f"\n## Prior-quarter context supplied by the desk\n{context}\n" if context else ""
    return f"""# Task: {bank_name} {quarter} earnings

Below is {bank_name}'s earnings release and financial supplement for {quarter}, split into
numbered blocks like [B0123]. Do three things.

1. **Extract** every metric in the table below, in the stated unit, citing the block id the
   number appears in.
2. **Prior quarter:** report the prior-quarter (Q2) value for {", ".join(PRIOR_Q_FIELDS)}, with
   citations, and the quarter-over-quarter change for each.
3. **Write the earnings note** (max 400 words, markdown): headline result and whether it beat
   or missed the prior quarter; what drove EPS; revenue and margin; credit; capital and returns;
   guidance changes; and a final line on whether this quarter changes the investment thesis.
   State whether you are discussing reported or adjusted EPS, and strip out notable items when
   explaining the underlying trend.

## Metrics
{field_table()}

## Output
Return ONE JSON object and nothing else, in this shape (comments are guidance only):

```json
{SCHEMA_EXAMPLE}
```
{ctx}
## Filing text
{document}
"""


def main():
    out = ROOT / "prompts" / "task.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("SYSTEM:\n" + SYSTEM + "\n\nUSER:\n" +
                   build_prompt("<Bank name>", "<Quarter>", "<block-numbered filing text>"))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
