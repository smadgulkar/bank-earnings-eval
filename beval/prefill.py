"""Rule-based first draft of the ground truth, for a human to check.

No language model is involved: it matches table-row labels with regular expressions
and reads the first two numeric columns (current quarter, prior quarter). Every value
it writes carries the note "PREFILLED - check"; `beval.ground_truth validate` refuses
to pass until you have checked each one and deleted that marker.

Usage:
  python -m beval.prefill            # all banks with prepared text
  python -m beval.prefill PNC KEY    # some banks
  python -m beval.prefill --confirm PNC   # after fixing any wrong values in PNC.json,
                                          # clear the remaining PREFILLED markers
Writes ground_truth/<TICKER>.json (only empty fields; never overwrites your values)
and review/<TICKER>.md (each value beside the block it came from, for fast checking).
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

from .fields import FIELD_BY_KEY, PRIOR_Q_FIELDS
from .ground_truth import template

ROOT = Path(__file__).resolve().parent.parent
MARK = "PREFILLED - check"

# Label patterns (lower-case, matched against the first cell of a table row).
PATTERNS = {
    "eps_reported": [r"^diluted (earnings per (common )?share|eps)\b", r"^earnings per (common )?share.{0,15}diluted",
                     r"^net income per diluted", r"^diluted net income per"],
    "eps_adjusted": [r"^adjusted diluted (eps|earnings per)", r"^diluted (eps|earnings per (common )?share).{0,20}adjusted",
                     r"^adjusted earnings per (common )?share"],
    "net_income_common": [r"^net income (available|applicable|attributable) to common"],
    "nii": [r"^net interest income( \((gaap|nii)\))?$"],
    "nim": [r"^net interest margin"],
    "nonint_income": [r"^(total )?non-?interest income$", r"^total non-?interest income"],
    "nonint_expense": [r"^(total )?non-?interest expense$", r"^total non-?interest expense"],
    "efficiency_ratio": [r"^efficiency ratio( \(gaap\))?$", r"^efficiency ratio", r"efficiency ratio"],
    "provision": [r"^provision for credit losses", r"^provision for loan and lease losses", r"^total provision for credit"],
    "nco": [r"^net (loan (and lease )?)?charge-offs$", r"^total net (loan )?charge-offs$"],
    "nco_ratio": [r"net (loan (and lease )?)?charge-offs? (to|as a % of|as a percentage of) average (total )?loans",
                  r"^net charge-off ratio", r"^annualized net charge-offs"],
    "acl_ratio": [r"^allowance for credit losses (to|as a % of|as a percentage of) (total )?loans",
                  r"^acl (to|as a % of) (total )?loans", r"^allowance for (loan and lease|credit) losses to period-end loans"],
    "avg_loans": [r"^average (total )?loans( and leases)?$", r"^total average loans", r"^average loans and leases"],
    "avg_deposits": [r"^average (total )?deposits$", r"^total average deposits"],
    "eop_deposits": [r"^(period-end|end of period|ending) (total )?deposits$", r"^total deposits$"],
    "cet1": [r"common equity tier 1( capital)? ratio", r"cet ?1( capital)? ratio", r"common equity tier 1 \(cet1\)"],
    "tbvps": [r"^tangible book value per (common )?share", r"^tbv per (common )?share", r"tangible (common )?book value per"],
    "rotce": [r"^return on (average )?tangible common (shareholders' |stockholders' )?equity", r"^rotce"],
}
# notable_items_eps and buybacks are usually in prose, so they are left for you.

NUM = re.compile(r"^\$?\(?-?\$?\s?\d[\d,]*\.?\d*\s?%?\)?%?$")


def to_number(cell: str):
    c = cell.strip()
    if not NUM.match(c):
        return None
    neg = ("(" in c and c.rstrip("%").endswith(")")) or c.lstrip("($ ").startswith("-")
    digits = re.sub(r"[^\d.]", "", c)
    try:
        v = float(digits)
    except ValueError:
        return None
    return -v if neg else v

BILLIONS_PRONE = {"avg_loans", "avg_deposits", "eop_deposits"}


def fix_billions(cands):
    """Summary tables often show balances in $ billions (372.2) while detail tables use
    $ millions (372,214). Prefer a millions row that agrees with a billions row; otherwise
    convert the billions row and flag it."""
    small = [c for c in cands if abs(c[0]) < 10_000]
    big = [c for c in cands if abs(c[0]) >= 10_000]
    if small:
        # The first billions row is the consolidated summary; later ones are segments.
        best = small[0]
        match = [b for b in big if abs(b[0] - best[0] * 1000) <= 0.006 * abs(b[0])]
        if match:
            return match, ""
        conv = [(best[0] * 1000, (best[1] * 1000 if best[1] is not None else None), best[2], best[3])]
        return conv, ("  \n  **converted from $ billions** (rounded): find the exact $ millions figure "
                      "in the average balance sheet table if there is one")
    return cands, ""


def candidates(blocks, patterns):
    """(value_current, value_prior, block_id, text) for every table row whose label matches."""
    out = []
    for b in blocks:
        if " | " not in b["text"]:
            continue
        cells = b["text"].split(" | ")
        label = cells[0].lower().strip(" :*")
        label = re.sub(r"\s*\(\d\)$", "", label)          # drop footnote markers like "(1)"
        if not any(re.search(p, label) for p in patterns):
            continue
        nums = [n for n in (to_number(c) for c in cells[1:]) if n is not None]
        if nums:
            out.append((nums[0], nums[1] if len(nums) > 1 else None, b["id"], b["text"]))
    return out


def scale_for(doc_text: str) -> float:
    """Money tables in thousands -> divide by 1000 to get millions."""
    head = doc_text[:20000].lower()
    return 1e-3 if ("in thousands" in head and "in millions" not in head) else 1.0


def prefill_bank(ticker: str):
    pdir = ROOT / "prepared" / ticker
    blocks = json.loads((pdir / "blocks.json").read_text())
    scale = scale_for((pdir / "document.txt").read_text())
    gt_path = ROOT / "ground_truth" / f"{ticker}.json"
    if not gt_path.exists():
        template(ticker)
    gt = json.loads(gt_path.read_text())

    review = [f"# {ticker}: prefilled values to check", "",
              "Check each value against its block. If right, delete `PREFILLED - check` from its note in "
              f"ground_truth/{ticker}.json. If wrong, fix value/source. Blank = find it yourself.", ""]
    filled = 0
    for key, pats in PATTERNS.items():
        cands = candidates(blocks, pats)
        kind = FIELD_BY_KEY[key].kind
        k_scale = scale if kind == "money_mm" else 1.0
        cur = gt["metrics"][key]
        if not cands:
            review.append(f"- **{key}**: no table row found; fill by hand")
            continue
        # Most common current-quarter value across matching rows; cite its LAST occurrence
        # (main financial tables come after the summary at the top).
        flag = ""
        if key in BILLIONS_PRONE:
            cands, flag = fix_billions(cands)
        mode_val = Counter(c[0] for c in cands).most_common(1)[0][0]
        best = [c for c in cands if c[0] == mode_val][-1]
        others = sorted({c[0] for c in cands} - {mode_val})
        if (cur["value"] is None and not cur.get("note")) or cur.get("note") == MARK:   # re-run updates unchecked drafts
            cur.update(value=round(best[0] * k_scale, 6), source=best[2], note=MARK)
            filled += 1
        line = f"- **{key}** = {round(best[0] * k_scale, 6)} [{best[2]}]: `{best[3][:140]}`{flag}"
        if others:
            line += f"  \n  other values seen in matching rows: {others[:5]} (segment, FTE or adjusted lines?)"
        review.append(line)
        if key in PRIOR_Q_FIELDS and best[1] is not None:
            pq = gt["prior_quarter"][key]
            if pq["value"] is None:
                pq.update(value=round(best[1] * k_scale, 6), source=best[2])
            review.append(f"  prior quarter = {round(best[1] * k_scale, 6)} (2nd number in the same row; "
                          "confirm the column is 2Q, not 3Q of last year)")
    for key in ("notable_items_eps", "buybacks"):
        review.append(f"- **{key}**: usually in the text, not a table; fill by hand")

    gt_path.write_text(json.dumps(gt, indent=2))
    (ROOT / "review").mkdir(exist_ok=True)
    (ROOT / "review" / f"{ticker}.md").write_text("\n".join(review) + "\n")
    scale_note = " (money tables in thousands, converted to millions)" if scale != 1.0 else ""
    print(f"{ticker}: prefilled {filled}/18 fields{scale_note} -> review/{ticker}.md")


def confirm(ticker: str):
    gt_path = ROOT / "ground_truth" / f"{ticker}.json"
    gt = json.loads(gt_path.read_text())
    n = 0
    for v in gt["metrics"].values():
        if v.get("note") == MARK:
            v["note"] = ""
            n += 1
    gt_path.write_text(json.dumps(gt, indent=2))
    print(f"{ticker}: confirmed {n} prefilled values")


def main():
    if sys.argv[1:2] == ["--confirm"]:
        for t in sys.argv[2:]:
            confirm(t)
        return
    tickers = sys.argv[1:] or sorted(p.name for p in (ROOT / "prepared").iterdir() if p.is_dir())
    for t in tickers:
        prefill_bank(t)


if __name__ == "__main__":
    main()
