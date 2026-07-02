# /plot

評価履歴（eval/history と eval/summary.csv）からグラフを生成/更新してください。

手順：
1. `python3 eval/make_plots.py` を実行（ユーザーに案内）
2. 生成物：
   - eval/plots/radar_latest.png（最新）
   - eval/plots/timeseries_overall.png（時系列）
3. matplotlib が無い場合は、代替として `eval/plots/README.md` に「生成できなかった理由」と「インストール方法（例：python -m pip install matplotlib）」を記載
