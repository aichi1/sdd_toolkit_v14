# Evaluation (A案)

このディレクトリは、SDD toolkit が「自分自身を改善しているか」を **同じ土俵で測る**ための仕組みです。

## 目的
- 固定の3シナリオ（T1/T2/T3）で毎回評価し、時系列で改善を可視化する
- 評価結果（スコア＋根拠）を機械可読（JSON/CSV）で残す

## 主要コマンド（Claude Code）
- `/eval <iteration_id>` : 採点を行い、履歴化・レポート化する
- `/plot` : 履歴からグラフを生成する
- `/improve-toolkit <iteration_id>` : ツールキット改良→評価→レポート

## データ構造
- `runs/<iteration_id>/<scenario>/score.json` : シナリオ別の採点（手動/LLM）
- `history/<date>_<iteration_id>.json` : 3シナリオを集計した履歴レコード
- `summary.csv` : 履歴を表形式で累積（グラフ用）
- `plots/` : 生成されたPNG（matplotlibが必要）

## グラフ生成
- `python3 eval/make_plots.py`

matplotlib が無い場合は、PNG生成をスキップします（CSV/JSONは生成されます）。


## Scoring stability
採点ブレを抑えるため、`/eval` 実行時は **`eval/SCORING_GUIDE.md`** の手順・アンカー・上限制約に従ってください。
必要なら `templates/eval_scoring_prompt.md` のJSONフォーマットをそのまま使って score.json を作成します。
