#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import json
import math
from pathlib import Path

AXES_DEFAULT = ["correctness","completeness","efficiency","robustness","maintainability","usability","safety"]
MAX_SCORE = 5.0

def load_rubric(root: Path):
    rub_path = root / "rubric.json"
    if rub_path.exists():
        data = json.loads(rub_path.read_text(encoding="utf-8"))
        axes = [a["key"] for a in data.get("axes", [])] or AXES_DEFAULT
        return axes
    return AXES_DEFAULT

def load_latest_history(root: Path):
    hist_dir = root / "history"
    files = sorted(hist_dir.glob("*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))

def ensure_matplotlib(root: Path):
    try:
        import matplotlib.pyplot as plt  # noqa
        return True
    except Exception as e:
        plots = root / "plots"
        plots.mkdir(exist_ok=True)
        (plots / "README.md").write_text(
            "# plots\n\nPNG生成には matplotlib が必要です。\n\n"
            "インストール例:\n"
            "```bash\npython -m pip install matplotlib\n```\n\n"
            f"Error: {type(e).__name__}: {e}\n",
            encoding="utf-8"
        )
        return False

def radar_plot(plt, axes, scores, title, outpath: Path):
    values = [float(scores.get(a, 0.0)) / MAX_SCORE for a in axes]
    values += values[:1]
    angles = [2 * math.pi * i / len(axes) for i in range(len(axes))]
    angles += angles[:1]

    fig = plt.figure()
    ax = fig.add_subplot(111, polar=True)
    ax.plot(angles, values)
    ax.fill(angles, values, alpha=0.15)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(axes)
    ax.set_yticks([0.2,0.4,0.6,0.8,1.0])
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(outpath, dpi=200)
    plt.close(fig)

def timeseries_plot(plt, axes, summary_rows, outpath: Path):
    dates = [r["date"] for r in summary_rows]
    fig = plt.figure()
    ax = fig.add_subplot(111)
    for a in axes:
        ys = [float(r.get(a, 0.0) or 0.0) for r in summary_rows]
        ax.plot(dates, ys, marker="o")
    ax.set_ylim(0, MAX_SCORE)
    ax.set_xlabel("date")
    ax.set_ylabel("score (0-5)")
    ax.set_title("SDD toolkit evaluation (overall axes)")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(outpath, dpi=200)
    plt.close(fig)

def main():
    root = Path(__file__).resolve().parent
    axes = load_rubric(root)
    plots = root / "plots"
    plots.mkdir(exist_ok=True)

    if not ensure_matplotlib(root):
        print("matplotlib not available; skipped PNG generation.")
        return

    import matplotlib.pyplot as plt

    latest = load_latest_history(root)
    if latest:
        radar_plot(
            plt, axes,
            latest.get("overall", {}).get("scores", {}),
            f"Radar (latest): {latest.get('iteration_id','')}",
            plots / "radar_latest.png"
        )

    # time series from summary.csv
    summary_path = root / "summary.csv"
    if summary_path.exists():
        with summary_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        if rows:
            timeseries_plot(plt, axes, rows, plots / "timeseries_overall.png")

    print("Updated plots in eval/plots/")

if __name__ == "__main__":
    main()
