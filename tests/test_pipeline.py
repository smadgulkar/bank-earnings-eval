"""End-to-end dry run on a synthetic bank with the offline mock model.

Copies the repo to a temp dir, swaps in one fake bank (TEST), and runs every stage:
prepare -> ground truth validate -> runner (mock) -> score -> grade -> aggregate -> chart.
"""

import csv
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def run(cwd, *args):
    r = subprocess.run([sys.executable, "-m", *args], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, f"{args} failed:\n{r.stdout}\n{r.stderr}"
    return r.stdout


def fill_ground_truth(root: Path):
    blocks = {b["text"]: b["id"] for b in json.loads((root / "prepared/TEST/blocks.json").read_text())}

    def src(prefix):
        return next(bid for text, bid in blocks.items() if text.startswith(prefix))

    m = {
        "eps_reported": (1.27, "Diluted EPS"), "eps_adjusted": (1.39, "Reported diluted EPS"),
        "net_income_common": (548, "Net income available"), "notable_items_eps": (-0.12, "Reported diluted EPS"),
        "nii": (1834, "Net interest income |"), "nim": (3.12, "Net interest margin (FTE)"),
        "nonint_income": (612, "Noninterest income"), "nonint_expense": (1402, "Noninterest expense"),
        "efficiency_ratio": (57.3, "Efficiency ratio"), "provision": (155, "Provision for credit"),
        "nco": (98, "Net charge-offs |"), "nco_ratio": (0.38, "Net charge-off ratio"),
        "acl_ratio": (1.62, "ACL to total loans"), "avg_loans": (103250, "Average loans"),
        "avg_deposits": (131400, "Average deposits"), "eop_deposits": (132050, "Period-end deposits"),
        "cet1": (10.4, "CET1"), "tbvps": (27.85, "Tangible book"), "rotce": (18.6, "Return on average"),
        "buybacks": (250, "The company repurchased"),
    }
    prior = {"eps_reported": 1.36, "nii": 1798, "nim": 3.08, "nonint_expense": 1390, "provision": 120}
    gt = {"ticker": "TEST",
          "metrics": {k: {"value": v, "source": src(p), "note": ""} for k, (v, p) in m.items()},
          "prior_quarter": {k: {"value": v, "source": src(m[k][1])} for k, v in prior.items()},
          "nim_basis": "FTE", "notes": ""}
    (root / "ground_truth/TEST.json").write_text(json.dumps(gt, indent=2))


def test_pipeline(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(REPO, root, ignore=shutil.ignore_patterns("filings", "prepared", "runs", "results",
                                                              "grade", "ground_truth", "traps", "__pycache__"))
    shutil.copytree(REPO / "tests/fixtures/filings", root / "filings")
    (root / "config/banks.json").write_text(json.dumps({
        "quarter": "2026Q3", "quarter_end": "2026-09-30",
        "banks": [{"ticker": "TEST", "name": "Test Bancorp", "cik": 1}]}))
    models = json.loads((root / "config/models.json").read_text())
    for m in models["models"]:
        m["model"] = f"mock-{m['label']}"
    (root / "config/models.json").write_text(json.dumps(models))

    assert "TEST:" in run(root, "beval.prepare")
    doc = (root / "prepared/TEST/document.txt").read_text()
    assert "Net interest income | $1,834 | $1,798 | $1,750" in doc, doc

    run(root, "beval.ground_truth", "template", "TEST")
    fill_ground_truth(root)
    assert "ground truth OK" in run(root, "beval.ground_truth", "validate")

    run(root, "beval.prompt")
    out = run(root, "beval.runner", "--provider-override", "mock")
    assert out.count("ok") == 9, out

    run(root, "beval.score")
    with (root / "results/baseline/run_scores.csv").open() as fh:
        scores = list(csv.DictReader(fh))
    assert len(scores) == 9
    assert all(0.5 < float(s["accuracy"]) <= 1 for s in scores)
    # Re-scoring keeps root-cause tags entered by hand
    fpath = root / "results/baseline/failures.csv"
    rows = list(csv.DictReader(fpath.open()))
    if rows:
        rows[0]["root_cause"] = "model limitation"
        with fpath.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
        run(root, "beval.score")
        assert list(csv.DictReader(fpath.open()))[0]["root_cause"] == "model limitation"

    run(root, "beval.grade", "make")
    g = root / "grade/baseline"
    grades = list(csv.DictReader((g / "grades.csv").open()))
    assert len(grades) == 9 and not any(lab in (g / "packets" / f"{r['blind_id']}.md").read_text() for r in grades for lab in ("openai", "anthropic", "google"))
    rng = random.Random(1)
    for r in grades:
        r.update(so_what=rng.randint(2, 5), no_invented_guidance=rng.randint(3, 5),
                 concision=rng.randint(2, 5), review_minutes=rng.randint(4, 20))
    with (g / "grades.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=grades[0].keys()); w.writeheader(); w.writerows(grades)
    traps = list(csv.DictReader((g / "trap_grades.csv").open()))
    for r in traps:
        r["pass"] = rng.randint(0, 1)
    with (g / "trap_grades.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=traps[0].keys()); w.writeheader(); w.writerows(traps)

    assert "all runs fully graded" in run(root, "beval.aggregate")
    run(root, "beval.chart")
    assert (root / "results/baseline/scores.png").stat().st_size > 10_000
    summary = (root / "results/baseline/summary_by_model.csv").read_text()
    assert "openai" in summary and "total_mean" in summary
