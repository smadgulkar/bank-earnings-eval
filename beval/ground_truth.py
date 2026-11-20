"""Ground-truth helpers.

  python -m beval.ground_truth template PNC   # writes ground_truth/PNC.json skeleton (+ traps/PNC.json)
  python -m beval.ground_truth validate       # checks every value against the block you cited

Fill each value in the unit given in beval/fields.py and cite the block id from
prepared/<TICKER>/document.txt. `validate` catches typos before any model is scored.
"""

import json
import sys
from pathlib import Path

from .check import block_contains, find_value
from .fields import FIELD_BY_KEY, FIELDS, PRIOR_Q_FIELDS

ROOT = Path(__file__).resolve().parent.parent

TRAP_TYPES = {
    "eps_basis": "Adjusted vs reported EPS: note must say which it uses",
    "notable_items": "Notable items must be stripped out when explaining the trend",
    "nim_basis": "FTE vs GAAP NIM must not be mixed",
    "period_mismatch": "QoQ vs YoY, average vs period-end balances",
    "reserve_build": "Provision up from loan growth is not credit deterioration",
    "definitions": "Bank-specific efficiency ratio / ROTCE definitions",
    "missing_data": "A field the release does not disclose: answer 'not disclosed'",
}


def template(ticker: str):
    gt = {
        "ticker": ticker,
        "metrics": {f.key: {"value": None, "source": None, "note": ""} for f in FIELDS},
        "prior_quarter": {k: {"value": None, "source": None} for k in PRIOR_Q_FIELDS},
        "nim_basis": "FTE | GAAP",
        "notes": "",
    }
    traps = {"ticker": ticker, "traps": [
        {"id": "eps_basis", "type": "eps_basis", "where": "", "check": "manual"},
        {"id": "nim_basis", "type": "nim_basis", "where": "", "check": "auto:nim_basis"},
        {"id": "prior_quarter", "type": "period_mismatch", "where": "", "check": "auto:prior"},
        {"id": "notable_items", "type": "notable_items", "where": "", "check": "manual"},
        {"id": "reserve_build", "type": "reserve_build", "where": "", "check": "manual"},
        {"id": "missing_eps_adjusted", "type": "missing_data", "where": "",
         "check": "auto:not_disclosed:eps_adjusted", "_delete_if": "the bank DOES report adjusted EPS"},
    ]}
    for path, obj in ((ROOT / "ground_truth" / f"{ticker}.json", gt), (ROOT / "traps" / f"{ticker}.json", traps)):
        path.parent.mkdir(exist_ok=True)
        if path.exists():
            print(f"exists, not overwritten: {path}")
        else:
            path.write_text(json.dumps(obj, indent=2))
            print(f"wrote {path}")


def validate() -> int:
    problems = 0
    for p in sorted((ROOT / "ground_truth").glob("*.json")):
        gt, t = json.loads(p.read_text()), p.stem
        sections = [("metrics", gt["metrics"]), ("prior_quarter", gt["prior_quarter"])]
        for name, sec in sections:
            for key, v in sec.items():
                kind = FIELD_BY_KEY[key].kind
                if "PREFILLED" in (v.get("note") or ""):
                    print(f"{t} {name}.{key}: prefilled but not yet checked (delete 'PREFILLED - check' once verified)")
                    problems += 1
                if v["value"] is None:
                    if name == "metrics" and not v.get("note"):
                        print(f"{t} {name}.{key}: empty -- fill it, or add a note saying 'not disclosed'")
                        problems += 1
                    continue
                if (v.get("note") or "").startswith("derived:"):
                    continue
                if not block_contains(t, v["source"], kind, v["value"]):
                    hits = find_value(t, kind, v["value"])[:5]
                    print(f"{t} {name}.{key}={v['value']} not found in {v['source']}; value appears in {hits}")
                    problems += 1
        if gt.get("nim_basis") not in ("FTE", "GAAP"):
            print(f"{t}: set nim_basis to FTE or GAAP")
            problems += 1
    print("ground truth OK" if not problems else f"{problems} problem(s)")
    return problems


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "template":
        for tk in sys.argv[2:]:
            template(tk)
    elif len(sys.argv) == 2 and sys.argv[1] == "validate":
        sys.exit(1 if validate() else 0)
    else:
        print(__doc__)
