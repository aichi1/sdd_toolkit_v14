# Changelog

## v6.5 (2026-02-12) — Token Optimization
- `.claude/rules/` を93%圧縮: 7ファイル 3,308行 → 5ファイル 222行
  - 核心ルールのみ残し、詳細は `docs/rules-reference/` に移動（自動注入されない）
  - 毎メッセージ約18,500トークン削減（推定）
- `MEMORY.md` にプロジェクト構造・eval推移・パターンを記録
  - セッション開始時のコンテキスト再構築コストを削減
- フェーズ間コンテキスト引き継ぎ: `outputs/.phase-context.json`
  - Phase完了時に判断・要約・docs要点を出力
  - 次Phase開始時にdocs/全体の再読み込みを省略可能
- Builder エージェント更新: `.phase-context.json` 参照の優先度追加

## v6.4 (2026-02-12)
- カテゴリ別インテークテンプレートを追加（`templates/intake/`）
  - `research_report.md`: 10問一括 + カテゴリ固有の深掘り指針
  - `small_implementation.md`: 8問一括 + 入出力・エラー処理の深掘り指針
  - `internal_proposal.md`: 9問一括 + 成功条件・選択肢制約の深掘り指針
- `/init-task` SKILL.md Step 1.3 を全面改訂: per-file Q&A → 構造化仕様収集
  - 初回: インテークテンプレートで基本情報を一括収集
  - 以降: 回答に応じて適応的に深掘り（必要なだけ繰り返す）
- `/run-phase` SKILL.md にファストパス判定（Step 1.5.3）を追加
  - プリチェックPASS + Quality Criteria≤5 + 成果物≤3 → 軽量検証で高速通過
- `/run-phase all` のデフォルトをスマートモード（Strategy 3）に変更
  - PASS時は自動で次Phase、問題時のみ停止
- `templates/team-roster.json` に `intake_template` フィールド追加
- eval: efficiency 3.00→4.00, overall 3.43→3.57

## v6.3 (2026-02-12)
- `scripts/validate-outputs.py` を新規作成: Builder 成果物の自動プリチェック
  - ファイル存在、メタデータ完全性、カテゴリ別必須セクションを自動検証
  - Validator 起動前に実行し、明らかな欠落を早期検出
- `/run-phase` SKILL.md に Phase 1.5（自動プリチェック）と Step 2.0（カテゴリ別チェックリスト準備）を追加
- Validator エージェント定義を更新: Quality Criteria 全項目検証の義務化、カテゴリテンプレ参照追加
- eval: correctness 3.00→4.00, robustness 3.00→3.33, overall 3.24→3.43

## v6.2 (2026-02-12)
- カテゴリ別 SKILL.md テンプレートを追加（`templates/skills/`）
  - `research_report.md`: TL;DR、比較軸理由、出典、不確実性セクション必須化
  - `small_implementation.md`: README/src/tests 構成、テスト指針、エラー処理指示
  - `internal_proposal.md`: 選択肢比較、リスク対策、次アクション（担当/期限/成果物）必須化
- `/init-task` SKILL.md を更新: Step 1.5 でカテゴリ別テンプレ参照を必須化
- `/init-task` に small-implementation 用 docs 構造（tech-stack.md, io-spec.md）を追加
- `templates/team-roster.json` に `skill_template` と `invocation_timing` フィールド追加
- eval: completeness 2.00→4.00, usability 2.33→3.67, overall 2.52→3.24

## v6.1 (2026-02-12)
- /eval の採点ブレを抑えるため、`eval/SCORING_GUIDE.md`（採点手順・アンカー・上限制約）を追加
- `templates/eval_scoring_prompt.md` を追加（score.json を安定したJSON形式で出力するためのテンプレ）
- `/eval` コマンド説明を更新（score.json 必須項目を明文化）

## v6.0 (2026-02-11)
- v6 initial
