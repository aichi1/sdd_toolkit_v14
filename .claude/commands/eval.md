# /eval <iteration_id>

このコマンドは「自己評価（A案）」を実行します。**固定3シナリオ（T1/T2/T3）**を同じ基準で採点し、履歴を保存し、グラフを更新します。

採点ブレを抑えるため、必ず **`eval/SCORING_GUIDE.md`** の手順に従ってください。

## 入力
- iteration_id（例：v6.1, 2026-02-12_1 など）
- オプション: `--review-interval N`（シナリオ見直し間隔。デフォルト: 5）

## 手順

### 0) 準備
- `eval/rubric.json`（評価軸）を確認
- `eval/SCORING_GUIDE.md`（採点手順/アンカー/上限制約）を確認
- （必要なら）`templates/eval_scoring_prompt.md` を参照して、採点時の"型"を守る

### 1) シナリオの確認
`eval/scenarios/` にある3シナリオを読み、各シナリオの「期待成果物」と「チェックリスト」を理解します：
- T1_research
- T2_implement
- T3_proposal

### 2) 各シナリオの採点（0〜5点、整数）
各シナリオごとに、次の軸を 0〜5 点で採点し、根拠とメトリクスを添えて保存してください：

軸（rubric）：`eval/rubric.json` の axes を使用
- correctness
- completeness
- efficiency
- robustness
- maintainability
- usability
- safety

保存先：
`eval/runs/<iteration_id>/<scenario>/score.json`

score.json の必須項目（最低限）：
- scores（各軸 0〜5、整数）
- checklist（各チェック項目の pass/partial/fail と evidence）
- metrics（任意：turns, retries, manifest_fill_rate など。分からない場合は "unknown"）
- evidence_files（参照した主要ファイルパス配列）
- notes（短文で良い：上げられない理由/改善点）

> 採点は **証拠（evidence）ベース**。推測で点を上げない。

### 3) 集計と履歴化（自動ファイル生成）
採点が揃ったら、ターミナルで次を実行してください：

`python3 eval/aggregate.py --iteration <iteration_id>`

これにより：
- `eval/history/<date>_<iteration_id>.json` が作成/更新
- `eval/summary.csv` が更新
- matplotlib があれば `eval/plots/` にPNGが生成

### 4) レポート
最後に `eval/reports/<date>_<iteration_id>.md` を作り、
- overall のレーダー形状の要約
- 前回から上がった/下がった軸（前回との差分）
- 次の改善仮説（最大3つ）
を簡潔に記述してください（根拠のファイルパスも添える）。

### 5) シナリオ見直しプロセス

#### トリガー条件
- **デフォルト**: 5 回の `/eval` 実行ごとにシナリオ見直しを推奨
- **カスタム**: `/eval --review-interval N` で間隔を変更可能
- **追加トリガー**: 直近 3 回の評価で全軸のスコア変動が ±0.5 未満の場合（スコア安定 = 過適合の兆候）

#### 見直し判定
Step 3 の集計後、以下を確認する:

1. `eval/summary.csv` の行数（= 累積実行回数）をカウント
2. 実行回数が `review-interval`（デフォルト 5）の倍数であるか確認
3. 直近 3 回のスコア変動を確認（全軸 ±0.5 未満なら追加トリガー発動）

#### 見直しプロンプト（トリガー発動時に出力）
```
⚠️ シナリオ見直し推奨: 過去{N}回の評価でスコアが安定しています。
過適合リスクを避けるため、以下を確認してください:
1. 新しいユースケースがシナリオに反映されているか
2. 評価基準が現在の品質目標と一致しているか
3. 最後のシナリオ更新日: {last_scenario_update}

見直しガイドライン: docs/scenario-review-guide.md を参照してください。
```

#### summary.csv 追加フィールド
集計時に以下のフィールドを追加する:
- `run_count`: 累積実行回数（1 から連番）
- `last_scenario_update`: 最後にシナリオファイルを更新した日付（YYYY-MM-DD）
- `review_due`: 見直しが必要か（`true` / `false`）

既存行には以下のデフォルト値を適用:
- `run_count`: 行番号（既存データの順序で 1, 2, 3, ...）
- `last_scenario_update`: 空欄
- `review_due`: `false`

#### シナリオ見直し実行時のルール
- **既存シナリオの削除・変更は禁止**（後方互換性維持）
- 新シナリオの追加のみ許可（T4_xxx, T5_xxx 等）
- 見直し実施後、`last_scenario_update` を更新
- 見直し結果は `eval/reports/` に記録（通常のレポートと同じディレクトリ）
