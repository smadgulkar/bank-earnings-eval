"""Blind grading of the earnings notes and the manual traps.

  python -m beval.grade make [--condition baseline]
      -> grade/<condition>/packets/<blind_id>.md   one note per file, model name removed, order shuffled
      -> grade/<condition>/grades.csv              fill: so_what, no_invented_guidance, concision (1-5),
                                                   review_minutes (time to verify the note vs the filing)
      -> grade/<condition>/trap_grades.csv         fill pass = 1 or 0 for each manual trap
      -> grade/<condition>/.key.json               blind id -> run (don't open until grading is done)

Existing grades are never overwritten; re-running `make` only adds new packets.
"""

import argparse
import csv
import json
import random
import secrets
from pathlib import Path

from .ground_truth import TRAP_TYPES

ROOT = Path(__file__).resolve().parent.parent

RUBRIC = """## How to grade (1-5 each)
- so_what: does it identify what actually changed in the quarter and whether the thesis moves? (5 = what you'd send a PM)
- no_invented_guidance: 5 = every forward-looking statement is in the release; 1 = invents or distorts guidance
- concision: 5 = nothing a PM would skip; 1 = padded or repetitive
- review_minutes: time it took you to verify the note against the filing (start a timer when you open the packet)
"""


def read_csv(path):
    if not path.exists():
        return []
    with path.open() as fh:
        return list(csv.DictReader(fh))


def write_csv(path, rows, fields):
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def make(condition: str):
    gdir = ROOT / "grade" / condition
    (gdir / "packets").mkdir(parents=True, exist_ok=True)
    key_path = gdir / ".key.json"
    key = json.loads(key_path.read_text()) if key_path.exists() else {}
    known_runs = set(key.values())
    banks = {b["ticker"]: b["name"] for b in json.loads((ROOT / "config" / "banks.json").read_text())["banks"]}

    new = [f for f in sorted((ROOT / "runs" / condition).glob("*/*/run*.json"))]
    random.shuffle(new)
    grades = read_csv(gdir / "grades.csv")
    trap_rows = read_csv(gdir / "trap_grades.csv")
    added = 0
    for f in new:
        rec = json.loads(f.read_text())
        run_id = f"{rec['label']}/{rec['ticker']}/run{rec['run']}"
        if run_id in known_runs:
            continue
        p = rec.get("parsed") or {}
        blind = secrets.token_hex(3)
        key[blind] = run_id
        t = rec["ticker"]
        traps = json.loads((ROOT / "traps" / f"{t}.json").read_text()).get("traps", []) \
            if (ROOT / "traps" / f"{t}.json").exists() else []
        manual = [tr for tr in traps if tr.get("check", "manual") == "manual"]
        lines = [f"# Packet {blind}: {banks.get(t, t)} ({t})", "",
                 f"EPS basis declared: {p.get('eps_basis_used_in_note', '-')} | NIM basis declared: {p.get('nim_basis', '-')}",
                 "", "## Note", "", p.get("note_markdown") or "_(no note produced)_", "",
                 "## Notable items it listed", ""]
        lines += [f"- {n.get('description')} ({n.get('eps_impact')}) [{n.get('source')}]" for n in p.get("notable_items") or []] or ["- none"]
        lines += ["", "## Guidance it quoted", ""]
        lines += [f"- {g.get('item')}: \"{g.get('quote')}\" [{g.get('source')}]" for g in p.get("guidance") or []] or ["- none"]
        lines += ["", "## Manual traps to grade (trap_grades.csv)", ""]
        lines += [f"- {tr['id']}: {TRAP_TYPES.get(tr['type'], tr['type'])}. Where: {tr.get('where') or '-'}" for tr in manual] or ["- none"]
        lines += ["", RUBRIC]
        (gdir / "packets" / f"{blind}.md").write_text("\n".join(lines))
        grades.append({"blind_id": blind, "ticker": t, "so_what": "", "no_invented_guidance": "",
                       "concision": "", "review_minutes": "", "comment": ""})
        trap_rows += [{"blind_id": blind, "ticker": t, "trap_id": tr["id"], "type": tr["type"], "pass": ""}
                      for tr in manual]
        added += 1

    key_path.write_text(json.dumps(key, indent=1))
    write_csv(gdir / "grades.csv", grades,
              ["blind_id", "ticker", "so_what", "no_invented_guidance", "concision", "review_minutes", "comment"])
    write_csv(gdir / "trap_grades.csv", trap_rows, ["blind_id", "ticker", "trap_id", "type", "pass"])
    print(f"{added} new packets in {gdir / 'packets'}; grade them in grades.csv and trap_grades.csv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["make"])
    ap.add_argument("--condition", default="baseline")
    a = ap.parse_args()
    make(a.condition)


if __name__ == "__main__":
    main()
