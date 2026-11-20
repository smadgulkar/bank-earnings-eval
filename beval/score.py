"""Automatic scoring: accuracy, citation checks, auto-checkable traps, arithmetic.

Usage: python -m beval.score [--condition baseline]
Writes results/<condition>/:
  field_results.csv  one row per run x field
  run_scores.csv     automatic parts of the 100-point score, per run
  failures.csv       every miss with a SUGGESTED root cause; fill the root_cause column yourself
"""

import argparse
import csv
import json
from pathlib import Path

from .check import block_contains, find_value
from .fields import FIELD_BY_KEY, FIELDS, PRIOR_Q_FIELDS, within_tolerance

ROOT = Path(__file__).resolve().parent.parent
DEFINITION_FIELDS = {"nim", "efficiency_ratio", "rotce", "eps_adjusted", "notable_items_eps", "acl_ratio"}


def num(x):
    if x is None or isinstance(x, bool):
        return None
    try:
        return float(str(x).replace(",", "").replace("$", "").replace("%", ""))
    except ValueError:
        return None


def suggest_cause(ticker, key, kind, truth, value, prior_truth):
    if truth is not None and value is None:
        return "retrieval: missed a disclosed figure"
    if truth is None and value is not None:
        return "model: reported a figure the bank did not disclose"
    if any(within_tolerance(kind, truth, value * s) for s in (1e3, 1e-3, 100, 0.01, 10, 0.1)):
        return "model: unit or scale error"
    if prior_truth is not None and within_tolerance(kind, prior_truth, value):
        return "period mismatch: used the prior quarter"
    if find_value(ticker, kind, value):
        return ("definition/basis: picked a different measure" if key in DEFINITION_FIELDS
                else "retrieval: pulled from the wrong line or table")
    return "model: number not in filing (miscalculated or invented)"


def score_run(rec, gt, traps):
    t, p = rec["ticker"], rec.get("parsed") or {}
    run_id = f"{rec['label']}/{t}/run{rec['run']}"
    fields, failures = [], []
    pm, pp = p.get("metrics") or {}, p.get("prior_quarter") or {}

    checks = [("current", f.key, gt["metrics"][f.key]["value"], (pm.get(f.key) or {})) for f in FIELDS]
    checks += [("prior", k, gt["prior_quarter"][k]["value"], (pp.get(k) or {})) for k in PRIOR_Q_FIELDS]
    for period, key, truth, ans in checks:
        kind = FIELD_BY_KEY[key].kind
        value = num(ans.get("value")) if isinstance(ans, dict) else num(ans)
        source = ans.get("source") if isinstance(ans, dict) else None
        truth = num(truth)
        NONE_EQ_ZERO = {"notable_items_eps", "buybacks"}   # "none" can be written as 0 or not disclosed
        if truth is None:
            correct = value is None or (key in NONE_EQ_ZERO and value == 0)
        else:
            correct = value is not None and within_tolerance(kind, truth, value)
        gt_note = ((gt["metrics"] if period == "current" else gt["prior_quarter"]).get(key) or {}).get("note") or ""
        skip_cite = key == "notable_items_eps" or gt_note.startswith("derived:") or (truth is None and value == 0)
        cite_ok = None if (value is None or skip_cite) else block_contains(t, source, kind, value)
        fields.append({"run_id": run_id, "label": rec["label"], "ticker": t, "run": rec["run"],
                       "period": period, "field": key, "truth": truth, "value": value,
                       "source": source, "correct": int(correct),
                       "citation_ok": "" if cite_ok is None else int(cite_ok)})
        if not correct:
            prior_truth = num(gt["prior_quarter"].get(key, {}).get("value")) if period == "current" else None
            cause = ("workflow: output missing or unparseable" if not p
                     else suggest_cause(t, key, kind, truth, value, prior_truth))
            failures.append({"run_id": run_id, "label": rec["label"], "ticker": t, "period": period,
                             "field": key, "truth": truth, "value": value, "source": source,
                             "suggested_root_cause": cause, "root_cause": "", "comment": ""})
        elif cite_ok is False:
            failures.append({"run_id": run_id, "label": rec["label"], "ticker": t, "period": period,
                             "field": key, "truth": truth, "value": value, "source": source,
                             "suggested_root_cause": "product design: right number, citation does not support it",
                             "root_cause": "", "comment": ""})

    # Arithmetic: does the model's QoQ change match its own current minus prior?
    arith_errors = 0
    for k, ch in (p.get("changes_qoq") or {}).items():
        if k not in FIELD_BY_KEY:
            continue
        cur, pri, ch = num((pm.get(k) or {}).get("value")), num((pp.get(k) or {}).get("value")), num(ch)
        if None not in (cur, pri, ch) and not within_tolerance(FIELD_BY_KEY[k].kind, cur - pri, ch):
            arith_errors += 1
            failures.append({"run_id": run_id, "label": rec["label"], "ticker": t, "period": "change",
                             "field": k, "truth": round(cur - pri, 4), "value": ch, "source": "",
                             "suggested_root_cause": "model: arithmetic", "root_cause": "", "comment": ""})

    # Auto-checkable traps
    auto_pass = auto_total = 0
    for trap in traps.get("traps", []):
        chk = trap.get("check", "manual")
        if chk == "manual":
            continue
        auto_total += 1
        if chk == "auto:nim_basis":
            ok = p.get("nim_basis") == gt.get("nim_basis")
        elif chk == "auto:prior":
            ok = all(r["correct"] for r in fields if r["period"] == "prior")
        elif chk.startswith("auto:not_disclosed:"):
            key = chk.split(":")[-1]
            ok = num((pm.get(key) or {}).get("value")) is None
        elif chk.startswith("auto:field:"):
            key = chk.split(":")[-1]
            ok = any(r["correct"] for r in fields if r["field"] == key and r["period"] == "current")
        else:
            auto_total -= 1
            continue
        auto_pass += int(ok)

    answered = [r for r in fields if r["value"] is not None]
    score = {
        "run_id": run_id, "label": rec["label"], "ticker": t, "run": rec["run"],
        "parsed": int(bool(p)), "error": rec.get("error") or "",
        "accuracy": sum(r["correct"] for r in fields) / len(fields),
        "traceability": (sum(r["citation_ok"] == 1 for r in answered) / len(answered)) if answered else 0.0,
        "auto_traps_passed": auto_pass, "auto_traps_total": auto_total,
        "arithmetic_errors": arith_errors,
        "input_tokens": (rec.get("usage") or {}).get("input_tokens"),
        "output_tokens": (rec.get("usage") or {}).get("output_tokens"),
        "latency_s": rec.get("latency_s"),
    }
    return fields, score, failures


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", default="baseline")
    args = ap.parse_args()
    run_dir = ROOT / "runs" / args.condition
    all_fields, all_scores, all_fail = [], [], []
    for f in sorted(run_dir.glob("*/*/run*.json")):
        rec = json.loads(f.read_text())
        gt_path = ROOT / "ground_truth" / f"{rec['ticker']}.json"
        if not gt_path.exists():
            print(f"skip {f}: no ground truth")
            continue
        traps_path = ROOT / "traps" / f"{rec['ticker']}.json"
        traps = json.loads(traps_path.read_text()) if traps_path.exists() else {}
        fr, sc, fa = score_run(rec, json.loads(gt_path.read_text()), traps)
        all_fields += fr
        all_scores.append(sc)
        all_fail += fa
    out = ROOT / "results" / args.condition
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "field_results.csv", all_fields)
    write_csv(out / "run_scores.csv", all_scores)
    # Keep root-cause tags you already entered when re-scoring.
    fail_path = out / "failures.csv"
    if fail_path.exists():
        with fail_path.open() as fh:
            kept = {(r["run_id"], r["period"], r["field"]): r for r in csv.DictReader(fh)}
        for r in all_fail:
            old = kept.get((r["run_id"], r["period"], r["field"]))
            if old:
                r["root_cause"], r["comment"] = old.get("root_cause", ""), old.get("comment", "")
    write_csv(fail_path, all_fail)
    print(f"scored {len(all_scores)} runs, {len(all_fail)} failures -> {out}")


if __name__ == "__main__":
    main()
