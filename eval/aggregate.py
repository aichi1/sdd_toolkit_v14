#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import json
from pathlib import Path
from datetime import datetime

def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def mean(values, weights=None):
    if not values:
        return 0.0
    if weights is None:
        return sum(values) / len(values)
    total_w = sum(weights)
    if total_w == 0:
        return 0.0
    return sum(v*w for v,w in zip(values, weights)) / total_w

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iteration", required=True, help="iteration id, e.g. v6.1")
    ap.add_argument("--commit", default="", help="optional git commit hash")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent
    rubric = load_json(root / "rubric.json")
    axes = [a["key"] for a in rubric["axes"]]
    weights = rubric.get("overall", {}).get("scenario_weights", {})

    scenarios_dir = root / "scenarios"
    scenario_keys = sorted([p.name for p in scenarios_dir.iterdir() if p.is_dir()])

    run_root = root / "runs" / args.iteration
    if not run_root.exists():
        raise SystemExit(f"runs folder not found: {run_root}. Create score.json first.")

    scenarios_out = {}
    overall_scores = {k: 0.0 for k in axes}
    overall_weights = {k: 0.0 for k in axes}

    for skey in scenario_keys:
        score_path = run_root / skey / "score.json"
        if not score_path.exists():
            raise SystemExit(f"missing score.json: {score_path}")
        sdata = load_json(score_path)
        sscores = sdata.get("scores", {})
        scenarios_out[skey] = sdata

        w = float(weights.get(skey, 1.0))
        for ax in axes:
            v = float(sscores.get(ax, 0.0))
            overall_scores[ax] += v * w
            overall_weights[ax] += w

    for ax in axes:
        if overall_weights[ax] > 0:
            overall_scores[ax] = overall_scores[ax] / overall_weights[ax]
        else:
            overall_scores[ax] = 0.0

    date = datetime.now().strftime("%Y-%m-%d")
    record = {
        "iteration_id": args.iteration,
        "date": date,
        "commit": args.commit,
        "scenarios": scenarios_out,
        "overall": {
            "scores": {ax: round(overall_scores[ax], 3) for ax in axes},
            "computed_by": "eval/aggregate.py"
        }
    }

    hist_dir = root / "history"
    hist_dir.mkdir(exist_ok=True)
    hist_path = hist_dir / f"{date}_{args.iteration}.json"
    hist_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    # Update summary.csv
    summary_path = root / "summary.csv"
    header = ["date", "iteration_id", "commit"] + axes
    rows = []
    if summary_path.exists():
        with summary_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

    # remove existing row with same date+iteration_id to avoid duplicates
    rows = [r for r in rows if not (r.get("date")==date and r.get("iteration_id")==args.iteration)]

    new_row = {"date": date, "iteration_id": args.iteration, "commit": args.commit}
    for ax in axes:
        new_row[ax] = f"{overall_scores[ax]:.3f}"
    rows.append(new_row)

    with summary_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for r in rows:
            writer.writerow({h: r.get(h, "") for h in header})

    # Try generate plots
    try:
        import subprocess, sys
        subprocess.run([sys.executable, str(root / "make_plots.py")], check=False)
    except Exception:
        pass

    print(f"Wrote: {hist_path}")
    print(f"Updated: {summary_path}")
    print("Plots: eval/plots/ (if matplotlib installed)")

if __name__ == "__main__":
    main()
