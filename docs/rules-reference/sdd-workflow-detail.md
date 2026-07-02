# SDD Workflow Rules - SDDワークフロー全体ルール

## 目的
Specification-Driven Development（SDD）ワークフローの実行ルールを定義する。
各コマンドの実行順序、前提条件、完了条件を明確化し、安定した品質を保証する。

## ワークフロー全体図

```
[新規プロジェクト開始]
       ↓
   /init-task ────────→ docs/, skills/, CLAUDE.md 作成
       ↓
   /run-phase 1 ──┬──→ Builder: 成果物生成
       ↓          └──→ Validator: 検証
   /run-phase 2
       ↓
   /run-phase N
       ↓
   /finalize ─────────→ アーカイブ & スターター抽出
       ↓
   /retrospective ────→ 教訓記録
       ↓
   [次のプロジェクトで活用]
```

## コマンド実行ルール

### Rule 1: init-task - プロジェクト初期化

**実行タイミング:**
- プロジェクト開始時（最初に1回のみ）
- 既存プロジェクトで再初期化する場合は明示的な確認が必要

**前提条件:**
- カレントディレクトリが空、または新規プロジェクト用
- `~/.sdd-knowledge/` が存在する（初回の場合は自動作成）

**実行内容:**
1. Planner Agentを起動してカテゴリ判定
2. Researcher Agentで類似プロジェクト検索
3. スターター適用 or ゼロから設計
4. ユーザーとの対話でdocs/の内容確定
5. skills/の概要設計
6. CLAUDE.md, metadata.json 作成

**完了条件:**
- [ ] docs/ に必要なファイルが全て存在
- [ ] 各docs/ファイルに具体的な内容が記載（テンプレートのままはNG）
- [ ] skills/phase-{N}/SKILL.md が全Phase分存在
- [ ] CLAUDE.md に成果物一覧とPhase構成が記載
- [ ] metadata.json に基本情報が記録

**違反時の対処:**
- docs/が空の場合 → init-task再実行を推奨
- skills/が不完全 → Phase実行前に補完
- metadata.jsonがない → 手動作成または再init

---

### Rule 2: run-phase - Phase実行

**実行タイミング:**
- init-task完了後
- 単発実行: `/run-phase 1`, `/run-phase 2`
- 範囲実行: `/run-phase 1-3`
- 全実行: `/run-phase all`

**前提条件:**
- init-task完了済み
- 実行対象Phaseのskills/SKILL.mdが存在
- 依存する前PhaseがPASS状態（または明示的にスキップ承認）

**実行内容:**
1. Builder Agentを起動
   - SKILL.mdの手順を実行
   - outputs/phase-{N}/ に成果物保存
2. Validator Agentを起動
   - docs/とSKILL.mdの要件照合
   - 検証レポート作成
3. 結果判定:
   - PASS → 次Phaseへ
   - NEEDS_REVISION → 修正サイクル
   - FAIL → 停止して原因調査

**修正サイクルルール:**
- 最大2回まで自動修正
- 3回目以降は手動介入必須
- 各修正でmetadata.jsonのiterationをインクリメント

**完了条件:**
- [ ] outputs/phase-{N}/ に成果物が存在
- [ ] Validator検証レポートが PASS または ユーザー承認済み
- [ ] metadata.json の該当Phase statusが "completed"

**スキップルール:**
- ユーザーが明示的に「問題を承知で次へ」と指示した場合のみ
- statusを "completed_with_issues" に設定
- 最終的なfinalize時に警告を表示

**違反時の対処:**
- 依存Phase未完了 → エラーで停止、依存Phase実行を促す
- SKILL.md不在 → エラーで停止、init-task再実行を促す
- Validator FAIL → 原因をユーザーに報告、修正 or スキップ選択

---

### Rule 3: finalize - プロジェクト完了処理

**実行タイミング:**
- 全Phase完了後（推奨）
- 途中でも実行可能（未完了Phaseがあれば警告）

**前提条件:**
- 少なくとも1つのPhaseが完了している
- outputs/ に成果物が存在

**実行内容:**
1. 完了状態の検証
   - 全Phase完了？未完了Phaseは？
   - Validation問題の残存チェック
2. アーカイブ作成
   - `~/.sdd-knowledge/docs-archive/` にコピー
   - metadata.json作成
   - index.json更新
3. スターター抽出/更新
   - Researcher Agentで既存スターター確認
   - 新規作成 or 既存更新
   - ユーザー承認後に適用
4. finalization-report.md 生成

**完了条件:**
- [ ] アーカイブディレクトリ作成完了
- [ ] index.json更新済み
- [ ] スターター処理完了（作成/更新/スキップ）
- [ ] finalization-report.md 生成済み
- [ ] metadata.json の status が "finalized"

**スキップ可能なステップ:**
- アーカイブ（`--skip-archive`）
- スターター抽出（`--skip-starter`）
- ただし、retrospectiveのためにアーカイブは推奨

**違反時の対処:**
- アーカイブ失敗 → ディスク容量確認、パーミッション確認
- スターター更新失敗 → 手動レビュー推奨

---

### Rule 4: retrospective - 振り返り記録

**実行タイミング:**
- finalize完了後（推奨）
- finalize前でも実行可能

**前提条件:**
- 少なくとも1つのPhaseが完了
- outputs/ と metadata.json が存在

**実行内容:**
1. プロジェクトデータ収集
   - metadata.json, validation reports読み込み
   - 時間、品質メトリクス計算
2. ユーザー対話
   - 構造化質問（7-10問）
   - 自由形式フィードバック
3. 教訓抽出
   - パターン認識
   - 優先度付け
4. 記録保存
   - ./retrospective.md（人間用）
   - ~/.sdd-knowledge/retrospectives/{date}_{category}_{name}.json（機械用）
   - summary.json更新

**完了条件:**
- [ ] retrospective.mdファイル生成
- [ ] retrospectives/*.json保存
- [ ] summary.json更新
- [ ] 教訓が lessons コマンドで参照可能

**スキップ可能な部分:**
- ユーザー対話（データのみから自動生成可能）
- ただし、対話を含めた方が教訓の質が高い

**違反時の対処:**
- 対話が中断 → 部分的なretrospectiveを保存、後で再開可能
- JSON保存失敗 → パーミッション確認

---

## ワークフロー実行パターン

### パターン1: 標準フロー（全自動）
```bash
# 1. 初期化
/init-task "タスク説明"
# → Planner/Researcherが設計、ユーザーがdocs/確定

# 2. 全Phase実行
/run-phase all --checkpoint
# → 各PhaseでBuilder/Validatorが協調、問題あれば停止

# 3. 完了処理
/finalize
# → アーカイブ & スターター更新

# 4. 振り返り
/retrospective
# → 教訓記録、次回プロジェクトで活用
```

### パターン2: 段階的フロー（慎重派）
```bash
# 1. 初期化
/init-task "タスク説明"

# 2. Phase 1のみ実行
/run-phase 1
# → 結果確認、問題なければ次へ

# 3. Phase 2実行
/run-phase 2
# → 修正が必要なら手動調整

# 4. 残りのPhase
/run-phase 3-5

# 5. 完了処理と振り返り
/finalize
/retrospective
```

### パターン3: 試行錯誤フロー（探索的）
```bash
# 1. 初期化
/init-task "タスク説明"

# 2. Phase 1を試す
/run-phase 1
# → うまくいかない、SKILL.mdを手動修正

# 3. Phase 1再実行
/run-phase 1
# → OK、次へ

# 4. 以降継続...
```

---

## Phase依存関係ルール

### Rule: Phase実行順序
- Phase Nは Phase N-1 が完了するまで実行不可
- 例外: Phase間に依存がない場合（並列実行可能）
  - 通常は依存あり（Phase 2 は Phase 1 の成果物を使う）
  - 稀に並列可能（Phase 3とPhase 4が独立など）

### Rule: 依存関係の明示
各SKILL.mdに記載:
```markdown
## Input Requirements
- outputs/phase-01/analysis.md (必須)
- docs/criteria.md (必須)
```

依存がない場合は明示:
```markdown
## Input Requirements
- なし（Phase 1のため前Phaseなし）
```

---

## エラーハンドリング

### エラー1: init-task実行済みプロジェクトで再実行
```
検出: CLAUDE.md または metadata.json が既に存在
対処:
  1. ユーザーに確認「既存のプロジェクトです。上書きしますか？」
  2. Yes → バックアップ作成後に上書き
  3. No → 中断
```

### エラー2: Phase実行で前Phase未完了
```
検出: metadata.json で前Phaseのstatusが "not_started" or "in_progress"
対処:
  1. エラーメッセージ「Phase {N-1}が未完了です」
  2. 選択肢:
     a. Phase {N-1}を先に実行
     b. 強制的にPhase {N}実行（非推奨）
     c. 中断
```

### エラー3: Validator検証が3回連続FAIL
```
検出: 同一Phaseで iteration >= 3 かつ status = NEEDS_REVISION
対処:
  1. 自動修正を停止
  2. ユーザーに報告:
     「3回修正しましたが問題が解決しません。
      考えられる原因:
      - SKILL.mdの手順が不適切
      - docs/の要件が矛盾
      - タスク自体の見直しが必要
      
      推奨対応:
      1. SKILL.mdを手動レビュー
      2. docs/を見直し
      3. Phase設計を再検討」
```

### エラー4: finalize時にCritical Issue残存
```
検出: いずれかのPhaseで critical_issues > 0
対処:
  1. 警告表示「Phase {N}にCritical Issueが{count}件残っています」
  2. 選択肢:
     a. 問題を修正してから finalize
     b. 問題を承知でfinalize（記録には残る）
```

---

## ベストプラクティス

### 推奨1: init-task直後にdocs/をレビュー
```
init-task完了後:
  1. 生成されたdocs/を全て読む
  2. 不足・誤解があれば修正
  3. CLAUDE.mdで全体像を確認
  4. 問題なければrun-phase開始
```

### 推奨2: Phase完了ごとに成果物確認
```
各Phase完了後:
  1. outputs/phase-{N}/を確認
  2. 期待通りの内容か？
  3. 次Phaseで使える状態か？
  4. 問題あれば早めに修正
```

### 推奨3: finalizeとretrospectiveはセット
```
finalize実行後、すぐに retrospective:
  - 記憶が新鮮なうちに振り返り
  - 問題点・改善点が明確
  - 教訓の質が向上
```

### 推奨4: retrospectiveの教訓を次回活用
```
新プロジェクト開始前:
  1. /lessons {category} で教訓確認
  2. よくある落とし穴を把握
  3. スターターの最新版を確認
  4. init-taskで効率的に開始
```

---

## アンチパターン（やってはいけないこと）

### NG1: init-taskをスキップしてrun-phase
```
✗ 直接 /run-phase 1
理由: docs/とskills/がないため、何を作るべきか不明

✓ 必ず /init-task → /run-phase の順序
```

### NG2: Validator結果を無視して次へ
```
✗ Validator: FAIL → 「まあいいや」→ /run-phase 2
理由: 問題が蓄積し、後で大きな手戻り

✓ Validator問題を解決してから次Phase
```

### NG3: retrospectiveを省略
```
✗ finalize → 次のプロジェクトへ（retrospective未実施）
理由: 教訓が蓄積されず、同じ失敗を繰り返す

✓ finalize → retrospective → 次のプロジェクトで活用
```

### NG4: 複数プロジェクトを同じディレクトリで
```
✗ プロジェクトAとBを同じフォルダで実行
理由: outputs/, docs/, skills/が混在し、混乱

✓ プロジェクトごとに別ディレクトリ
```

---

## トラブルシューティング

### 問題: 「どのPhaseまで完了したか分からない」
```
確認方法:
  1. metadata.json の phases セクションを確認
  2. outputs/ のディレクトリを確認
  3. 各phase-{N}/.metadata.json のstatusを確認

復旧:
  - 最後に完了したPhaseから再開
  - または /run-phase all で未完了分を実行
```

### 問題: 「init-taskの設計が間違っていた」
```
対処:
  1. docs/を手動修正
  2. SKILL.mdを手動修正（必要に応じて）
  3. CLAUDE.mdを更新
  4. /run-phase で再実行

または:
  1. プロジェクトをバックアップ
  2. 新しいディレクトリで /init-task 再実行
  3. 学んだことを反映
```

### 問題: 「スターターが古い」
```
対処:
  1. ~/.sdd-knowledge/starters/{category}/metadata.json 確認
  2. 最終更新日とバージョンチェック
  3. 必要なら手動更新
  4. または最新プロジェクトから /finalize で更新
```

---

## ワークフロー品質指標

### 良好なプロジェクトの特徴:
- [ ] 全Phaseが PASS で完了
- [ ] Critical Issues が0件
- [ ] 見積もり時間と実績の乖離が ±20% 以内
- [ ] retrospectiveで満足度 4/5 以上
- [ ] スターターへの貢献あり

### 改善が必要なプロジェクトの特徴:
- [ ] Phaseの半数以上で NEEDS_REVISION が2回以上
- [ ] Critical Issues が累計10件以上
- [ ] 見積もり時間の2倍以上かかった
- [ ] retrospectiveで「うまくいかなかった」が多い
- [ ] docs/やskills/の大幅な手動修正が必要だった

→ このような場合、init-taskの設計に問題があった可能性
→ retrospectiveで根本原因を分析し、次回に活かす

---

## まとめ

SDDワークフローの成功は、**ルールを守ること**にかかっている。

**必ず守るべきルール:**
1. init-task → run-phase → finalize → retrospective の順序
2. Phase依存関係の遵守
3. Validator結果の尊重
4. retrospectiveによる継続的改善

**推奨事項:**
- 各Phase完了時の成果物確認
- finalizeとretrospectiveをセットで実行
- 教訓の定期的なレビュー

**禁止事項:**
- ワークフローのスキップ
- Validator結果の無視
- retrospectiveの省略

このルールに従うことで、**使うほど質が上がるサイクル**が回り始める。