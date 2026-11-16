"""Combine automatic scores and blind grades into the 100-point score.

  Accuracy            30 x share of 25 values correct (20 current + 5 prior quarter)
  Source traceability 20 x share of reported values whose cited block contains the number
  Judgment on traps   25 x share of traps handled (auto-checked + your manual grades)
  Note quality        15 x average of (so_what, no_invented_guidance, concision) rescaled 1-5 -> 0-1
  Ease of review      10 x clip((30 - review_minutes) / 25, 0, 1)   (<=5 min = full marks, >=30 = 0)

Usage: python -m beval.aggregate [--condition baseline]
Writes results/<condition>/scores_by_run.csv, summary_by_model.csv, root_causes.csv
Runs not yet graded get partial=1 and their grade-based parts left blank.
"""

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
WEIGHTS = {"accuracy": 30, "traceability": 20, "traps": 25, "note": 15, "review": 10}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", default="baseline")
    cond = ap.parse_args().condition
    res, gdir = ROOT / "results" / cond, ROOT / "grade" / cond

    runs = pd.read_csv(res / "run_scores.csv")
    key = json.loads((gdir / ".key.json").read_text()) if (gdir / ".key.json").exists() else {}
    inv = pd.DataFrame({"blind_id": list(key), "run_id": list(key.values())})

    if (gdir / "grades.csv").exists() and len(inv):
        g = pd.read_csv(gdir / "grades.csv").merge(inv, on="blind_id")
        for c in ("so_what", "no_invented_guidance", "concision", "review_minutes"):
            g[c] = pd.to_numeric(g[c], errors="coerce")
        g["note"] = ((g[["so_what", "no_invented_guidance", "concision"]] - 1) / 4).mean(axis=1, skipna=False)
        g["review"] = ((30 - g["review_minutes"]) / 25).clip(0, 1)
        runs = runs.merge(g[["run_id", "note", "review"]], on="run_id", how="left")
    else:
        runs["note"] = runs["review"] = float("nan")

    if (gdir / "trap_grades.csv").exists() and len(inv):
        tg = pd.read_csv(gdir / "trap_grades.csv").merge(inv, on="blind_id")
        tg["pass"] = pd.to_numeric(tg["pass"], errors="coerce")
        agg = tg.groupby("run_id").agg(manual_passed=("pass", "sum"), manual_total=("pass", "size"),
                                       manual_missing=("pass", lambda s: s.isna().sum())).reset_index()
        runs = runs.merge(agg, on="run_id", how="left")
    else:
        runs["manual_passed"] = runs["manual_total"] = runs["manual_missing"] = 0
    runs[["manual_passed", "manual_total", "manual_missing"]] = runs[["manual_passed", "manual_total", "manual_missing"]].fillna(0)

    tot = runs["auto_traps_total"] + runs["manual_total"]
    runs["traps"] = (runs["auto_traps_passed"] + runs["manual_passed"]) / tot.where(tot > 0)
    runs.loc[runs["manual_missing"] > 0, "traps"] = float("nan")

    for dim, w in WEIGHTS.items():
        runs[f"pts_{dim}"] = runs[dim] * w
    pts = [f"pts_{d}" for d in WEIGHTS]
    runs["partial"] = runs[pts].isna().any(axis=1).astype(int)
    runs["total"] = runs[pts].sum(axis=1, min_count=len(pts))
    runs.to_csv(res / "scores_by_run.csv", index=False)

    # Spread between runs: average each run index across banks, then take mean/min/max over runs.
    per_run = runs.groupby(["label", "run"])[pts + ["total"]].mean().reset_index()
    summary = per_run.groupby("label")[pts + ["total"]].agg(["mean", "min", "max"]).round(2)
    summary.columns = [f"{a}_{b}" for a, b in summary.columns]
    summary.to_csv(res / "summary_by_model.csv")

    fail_path = res / "failures.csv"
    if fail_path.exists():
        f = pd.read_csv(fail_path, keep_default_na=False)
        f["cause"] = f["root_cause"].where(f["root_cause"].astype(str).str.strip() != "", f["suggested_root_cause"])
        bucket_map = {"model": "model limitation", "retrieval": "data or retrieval",
                      "definition/basis": "data or retrieval", "data": "data or retrieval",
                      "period mismatch": "workflow", "workflow": "workflow", "product design": "product design"}
        head = f["cause"].str.split(":").str[0].str.strip().str.lower()
        f["bucket"] = head.map(bucket_map).fillna(head)
        rc = f.groupby(["label", "bucket"]).size().unstack(fill_value=0)
        rc.to_csv(res / "root_causes.csv")
    print(summary.to_string())
    print(f"\n{int(runs['partial'].sum())} of {len(runs)} runs still need grading" if runs["partial"].any()
          else "\nall runs fully graded")


if __name__ == "__main__":
    main()
