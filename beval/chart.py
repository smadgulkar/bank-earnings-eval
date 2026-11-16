"""The write-up's one chart: score on each dimension, by model, with the spread between runs.

Each dimension is shown as % of its available points so the five are comparable;
whiskers span the lowest to highest run. Writes results/<condition>/scores.png and .svg.

Usage: python -m beval.chart [--condition baseline]
"""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .aggregate import WEIGHTS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]          # validated categorical slots 1-3, fixed order
INK, MUTED, GRID = "#1f1f1e", "#6b6a64", "#e4e3de"
DIM_LABELS = {"accuracy": "Accuracy", "traceability": "Source\ntraceability", "traps": "Judgment\non traps",
              "note": "Note\nquality", "review": "Ease of\nreview"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", default="baseline")
    cond = ap.parse_args().condition
    res = ROOT / "results" / cond
    s = pd.read_csv(res / "summary_by_model.csv", index_col=0)

    dims = list(WEIGHTS)
    import json
    order = [m["label"] for m in json.loads((ROOT / "config" / "models.json").read_text())["models"]]
    labels = [lab for lab in order if lab in s.index] + [lab for lab in s.index if lab not in order]
    x = np.arange(len(dims))
    width = 0.8 / len(labels)
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=200)
    for i, lab in enumerate(labels):
        mean = np.array([s.loc[lab, f"pts_{d}_mean"] / WEIGHTS[d] * 100 for d in dims], dtype=float)
        lo = np.array([s.loc[lab, f"pts_{d}_min"] / WEIGHTS[d] * 100 for d in dims], dtype=float)
        hi = np.array([s.loc[lab, f"pts_{d}_max"] / WEIGHTS[d] * 100 for d in dims], dtype=float)
        pos = x - 0.4 + width * (i + 0.5)
        color = SERIES[i % len(SERIES)]
        total = s.loc[lab, "total_mean"]
        name = f"{lab}  {total:.0f}/100" if pd.notna(total) else f"{lab}  (grading pending)"
        ax.bar(pos, np.nan_to_num(mean), width - 0.03, color=color, label=name, zorder=2)
        ax.errorbar(pos, np.nan_to_num(mean), yerr=[np.nan_to_num(mean - lo), np.nan_to_num(hi - mean)],
                    fmt="none", ecolor=INK, elinewidth=1, capsize=2.5, zorder=3)

    ax.set_xticks(x, [f"{DIM_LABELS[d]}\n({WEIGHTS[d]} pts)" for d in dims], fontsize=9, color=INK)
    ax.set_ylim(0, 100)
    ax.set_ylabel("% of available points", fontsize=9, color=MUTED)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8, zorder=0)
    ax.tick_params(axis="y", labelsize=8, colors=MUTED, length=0)
    ax.tick_params(axis="x", length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.legend(loc="upper left", bbox_to_anchor=(0, 1.13), ncol=len(labels), frameon=False, fontsize=9)
    ax.set_title("Score by dimension (bars = mean of runs, whiskers = lowest to highest run)",
                 fontsize=10, color=INK, loc="left", pad=28)
    fig.tight_layout()
    for ext in ("png", "svg"):
        fig.savefig(res / f"scores.{ext}", facecolor="white")
    print(f"wrote {res / 'scores.png'}")


if __name__ == "__main__":
    main()
