# run-phase - SDDプロジェクトのフェーズ実行

## 目的
Builder / Validator パターンによる品質担保を行いながら、SDD（スペック駆動開発）プロジェクトの1つ以上のフェーズを実行します。

## 前提条件
- `/init-task` によりプロジェクトが初期化済み（`docs/` と `skills/` が存在）
- `CLAUDE.md` が存在
- `metadata.json` が存在

## 入力
- フェーズ番号：単一（例: `"1"`）、範囲（例: `"1-3"`）、または `"all"`
- オプションフラグ:
  - `--review-only`：実行をスキップし、既存出力のみをレビュー
  - `--no-validation`：Validator エージェントをスキップ（高速だが品質低下）
  - `--output-dir`：出力ディレクトリを指定（デフォルト: `./outputs/`）

## 出力
- 生成された成果物：`./outputs/phase-{N}/`
- 検証レポート：`./outputs/phase-{N}/.validation/`
- フェーズ状態を反映した `metadata.json` の更新

## ワークフロー

### Phase 0: 準備

**Step 0.1: 環境チェック**
```bash
# 必須ファイルの存在確認
- ./docs/ (空でない)
- ./skills/phase-{N}/SKILL.md (要求されたフェーズ分)
- ./CLAUDE.md
- ./metadata.json
```

**Step 0.2: コンテキスト読み込み（トークン効率化）**
- `CLAUDE.md` を読み、プロジェクト概要を把握
- `outputs/.phase-context.json` が存在する場合:
  - このファイルを読み、前Phaseの判断・要約・docs要点を把握
  - docs/ の全ファイル再読み込みは **省略可能**（必要な箇所だけ参照）
- `outputs/.phase-context.json` が存在しない場合（Phase 1 等）:
  - `docs/` 配下の全ファイルをコンテキストに投入
- 対象フェーズの `skills/` 配下 `SKILL.md` を読み込み
- `metadata.json` を確認し、過去フェーズの完了状況を把握

**Step 0.3: 依存関係バリデーション**
要求された各フェーズについて:
- 前提フェーズが完了しているか確認
- Phase N が Phase N-1 の出力を必要とする場合、その存在を確認
- 依存が欠けている場合は、以下のいずれか:
  - 前提フェーズを自動実行（ユーザー確認あり）、または
  - 明確なエラーメッセージを出して中断

### Phase 1: Builder 実行（フェーズごと）

**Step 1.1: エージェント初期化**
Builder エージェントを以下の条件で起動:
- コンテキスト：`CLAUDE.md`、`docs/`、`skills/phase-{N}/SKILL.md`
- （あれば）前フェーズの出力
- ツール：フル read/write 権限
- 目的：`SKILL.md` に記載された成果物を生成

**Builder エージェントの責務**
1. `SKILL.md` の手順（procedure）セクションを読む
2. 要件のために `docs/` を読む
3. 手順をステップバイステップで実行
4. 成果物を生成
5. `./outputs/phase-{N}/` に保存
6. `./outputs/phase-{N}/.metadata.json` を作成:
```json
{
  "phase": {N},
  "builder_session_id": "{uuid}",
  "started_at": "{ISO timestamp}",
  "completed_at": "{ISO timestamp}",
  "deliverables": [
    {
      "file": "report.md",
      "type": "document",
      "status": "pending_validation"
    }
  ]
}
```

**Step 1.2: Builder 出力の取り込み**
- 生成された全ファイルを収集
- ファイルパスが `SKILL.md` の期待どおりか確認
- `SKILL.md` の要件チェックリスト（初期版）を作成

### Phase 1.5: 自動プリチェック（Validator 起動前）

**Step 1.5.1: validate-outputs.py の実行**
Builder 完了後、Validator 起動前に自動プリチェックスクリプトを実行する：

```bash
python3 scripts/validate-outputs.py --phase {N}
```

このスクリプトは以下を自動検証する：
1. **成果物ディレクトリ存在**: `outputs/phase-{N}/` が存在するか
2. **メタデータ完全性**: `.metadata.json` が存在し、必須フィールド（phase, deliverables）があるか
3. **成果物ファイル存在**: 隠しファイル以外の成果物が1つ以上あるか
4. **SKILL.md Quality Criteria**: Quality Criteria セクションの項目数を確認
5. **カテゴリ別必須セクション**: metadata.json の category に基づき、テンプレートの必須セクションがキーワードベースで存在するか

**Step 1.5.2: プリチェック結果の処理**
- **PASS**: 全チェック通過 → ファストパス判定（下記）へ進む
- **WARN**: 警告あり → Phase 2（Validator フル検証）へ進む
- **FAIL**: 必須項目欠落 → Builder に差し戻し（Validator の時間を節約）

**Step 1.5.3: ファストパス判定（効率化）**
プリチェック PASS の場合、以下の条件をすべて満たせば **ファストパス**（軽量検証）を適用する：

ファストパス条件：
1. プリチェック結果が **全項目 PASS**（WARN なし）
2. SKILL.md の Quality Criteria が **5項目以下**
3. 成果物ファイルが **3つ以下**

ファストパスの場合（Phase 2 を軽量化）：
- Validator フルエージェントを起動しない
- 代わりにメインセッション内で Quality Criteria を1項目ずつ確認する
- 全項目 Met → 即 PASS（Phase 4 へ）
- 1項目でも Missing → 通常の Phase 2（Validator フル検証）にフォールバック

ファストパスでない場合：
- 通常どおり Phase 2（Validator フル検証）へ進む

### Phase 2: Validator 実行

**Step 2.0: カテゴリ別検証チェックリストの準備**
Validator 起動時に、以下を検証の入力として渡す：
1. SKILL.md の Quality Criteria（最重要 — 必ず全項目を検証する）
2. プリチェック結果（WARN 項目があればそこを重点チェック）
3. `templates/skills/{category}.md` のテンプレート（存在する場合）
   - テンプレートの「必須セクション構成」を成果物と照合
   - テンプレートの「Quality Criteria」が SKILL.md に反映されているか確認

Validator は SKILL.md の Quality Criteria の **全項目** を1つずつ検証し、検証レポートにチェック結果（Met/Partial/Missing）を記載しなければならない。

**Step 2.1: エージェント初期化**
Validator エージェントを以下の条件で起動:
- コンテキスト：`CLAUDE.md`、`docs/`、`skills/phase-{N}/SKILL.md`
- Builder の出力：`./outputs/phase-{N}/`
- ツール：**読み取り専用（ファイル変更不可）**
- 目的：成果物がすべての要件を満たしているか検証

**Validator エージェントの責務**
1. `SKILL.md` の品質基準（quality criteria）を読む
2. `docs/` の要件を読む
3. Builder の成果物を読む
4. 各要件に対してチェック:
   - ✓ Met：要件を満たす
   - ⚠ Partial：一部満たすが改善が必要
   - ✗ Missing：未対応
5. 検証レポートを生成

**Step 2.2: 検証レポートの形式**
`./outputs/phase-{N}/.validation/report.md` に保存:

```markdown
# Validation Report: Phase {N}

**Validator Session**: {uuid}
**Timestamp**: {ISO timestamp}
**Overall Status**: {PASS / NEEDS_REVISION / FAIL}

## Requirements Checklist

### From docs/{file}.md
- [x] Requirement 1: Description
  - **Status**: Met
  - **Evidence**: {specific file/section}
  
- [⚠] Requirement 2: Description
  - **Status**: Partial
  - **Issue**: {what's missing or incorrect}
  - **Suggestion**: {how to fix}

- [ ] Requirement 3: Description
  - **Status**: Missing
  - **Issue**: {what's missing}
  - **Required Action**: {what needs to be added}

### From skills/phase-{N}/SKILL.md Quality Criteria
- [x] Criterion 1: ...
- [⚠] Criterion 2: ...

## Detailed Findings

### Critical Issues (must fix)
1. {Issue description}
   - Location: {file}:{line}
   - Expected: {what was expected}
   - Actual: {what was found}
   - Fix: {how to address}

### Suggestions (nice to have)
1. {Suggestion description}
   - Benefit: {why this improves quality}
   - Effort: {low/medium/high}

## Summary
- Total Requirements: {N}
- Met: {N}
- Partial: {N}
- Missing: {N}

**Recommendation**: {APPROVE / REQUEST_REVISION / REJECT}
```

**Step 2.3: 検証判定**
- すべて Met → Status: PASS
- Critical Issues がある → Status: NEEDS_REVISION
- 根本的な不整合 → Status: FAIL

### Phase 3: 修正ループ（必要なら）

**Step 3.1: 検証結果をユーザーに提示**
```
Phase {N} validation completed.
Status: {NEEDS_REVISION}

Critical Issues: {N}
Suggestions: {N}

Options:
1. Auto-fix: Builder エージェントに問題の修正をさせる
2. Review: 詳細な検証レポートを表示
3. Manual: 自分で修正する
4. Accept: 問題が残っていても先へ進む
```

**Step 3.2: Auto-fix 実行**
ユーザーが auto-fix を選んだ場合:
1. Builder エージェントを再起動:
   - 元のコンテキスト
   - 追加入力として検証レポート
   - タスク:「クリティカル問題のみ修正」
2. Builder が成果物を修正
3. `./outputs/phase-{N}/` に保存（上書きまたはバージョン付与）
4. Validator を再実行
5. PASS になるか最大2回まで反復

**Step 3.3: 反復回数の上限**
2回の Builder/Validator サイクル後:
- まだ NEEDS_REVISION の場合 → ユーザーへエスカレーション
- 残課題を表示
- 「auto-fix を継続するか、手動に切り替えるか」を質問

### Phase 4: 完了処理

**Step 4.1: ステータス更新**
`./outputs/phase-{N}/.metadata.json` を更新:
```json
{
  "phase": {N},
  "status": "completed",
  "validation_status": "pass",
  "iterations": 1,
  "completed_at": "{ISO timestamp}",
  "deliverables": [...]
}
```

ルートの `./metadata.json` を更新:
```json
{
  ...
  "phases": {
    "1": {"status": "completed", "completed_at": "..."},
    "{N}": {"status": "completed", "completed_at": "..."}
  },
  "current_phase": {N+1 or "complete"}
}
```

**Step 4.1.5: フェーズ間コンテキスト引き継ぎ**
Phase完了時に `./outputs/.phase-context.json` を作成/更新する。
次Phaseはこのファイルを読むことで、docs/全体の再読み込みを省略できる。

```json
{
  "last_phase": {N},
  "last_phase_summary": "Phase {N}で達成した内容の1-2文要約",
  "key_decisions": ["判断1", "判断2"],
  "output_files": ["outputs/phase-{N}/file1.md", "outputs/phase-{N}/file2.md"],
  "pending_issues": ["未解決の問題があれば記載"],
  "next_phase_hint": "次Phaseで重要な情報や注意点",
  "docs_digest": {
    "scope": "docs/scope.mdの核心を1-2文で",
    "key_requirements": ["要件1", "要件2", "要件3"]
  }
}
```

このファイルはフェーズ完了ごとに上書きされる（最新フェーズの情報のみ保持）。

**Step 4.2: 次アクションのプロンプト**
```
✓ Phase {N} completed successfully.

Deliverables:
  - {file1}
  - {file2}

Next:
  /run-phase {N+1}    - 次フェーズへ進む
  /finalize           - まとめてパッケージ化しアーカイブ
  /retrospective      - 学びの記録
```

## 複数フェーズ実行

範囲指定（例: `/run-phase 1-3` または `/run-phase all`）の場合:

**Strategy 1: 逐次 + チェックポイント**
```
range内の各フェーズについて:
  1. Phase N を実行（Builder + Validator）
  2. PASS → Phase N+1 へ
  3. NEEDS_REVISION → 一時停止
     - 検証課題を提示
     - 「今修正するか、次にスキップするか」を質問
  4. ユーザーが skip を選ぶ → "completed_with_issues" として記録
```

**Strategy 2: バッチモード（高速）**
```
range内の各フェーズについて:
  1. Builder のみ実行（Validatorなし）
  2. 次フェーズへ

すべて完了後:
  1. 全フェーズに対して Validator を実行
  2. 統合検証レポートを提示
  3. 一括修正（batch revision）を提案
```

ユーザーはフラグで戦略を選択可能:
- `/run-phase all --checkpoint` → Strategy 1（安全だが遅い）
- `/run-phase all --batch` → Strategy 2（高速だが最後にレビュー）
- `/run-phase all` → Strategy 3: スマートモード（デフォルト）

**Strategy 3: スマートモード（デフォルト、v6.4〜）**
```
range内の各フェーズについて:
  1. Builder を実行
  2. プリチェックを実行
  3. ファストパス判定:
     - ファストパス適用可 → 軽量検証 → PASS なら自動で次へ
     - ファストパス不可 → Validator フル検証
  4. PASS → 自動で次フェーズへ（ユーザー確認なし）
  5. NEEDS_REVISION → 一時停止してユーザー確認
```

Strategy 3 は Strategy 1 と Strategy 2 の中間。ファストパスが効くフェーズは高速に通過し、問題があるフェーズだけ停止する。

## エラーハンドリング

**Builder エージェントの失敗**
- タイムアウト（フェーズあたり10分超）→ 部分出力を保存しユーザーに確認
- ツールエラー → ログを残し1回だけ再試行
- 要件が不明確 → 一時停止してユーザーに確認

**Validator エージェントの失敗**
- 成果物が読めない → FAIL としてレポート
- タイムアウト → 検証をスキップし "not_validated" として記録

**依存関係の失敗**
- 前提フェーズ出力が欠けている → 前提フェーズ実行を自動提案
- フェーズ出力が破損 → フェーズ再実行か継続かを提案

## 品質ゲート

フェーズを完了とマークする前に:
- [ ] `SKILL.md` に指定された成果物がすべて存在
- [ ] Validator が正常に実行された（または `--no-validation` を使用）
- [ ] クリティカルな検証問題が残っていない
- [ ] `metadata.json` が更新されている

## Builder / Validator エージェント定義

**Builder エージェント**（`.claude/agents/builder.md`）:
```yaml
name: SDD Builder
role: Generate deliverables according to SKILL.md
tools:
  - bash_tool (full access)
  - str_replace
  - create_file
  - view
constraints:
  - Must follow SKILL.md procedure exactly
  - Must save outputs to designated directory
  - Must not skip quality criteria from SKILL.md
context_priority:
  1. skills/phase-{N}/SKILL.md
  2. docs/ (all files)
  3. CLAUDE.md
  4. Previous phase outputs
```

**Validator エージェント**（`.claude/agents/validator.md`）:
```yaml
name: SDD Validator
role: Verify deliverables against requirements
tools:
  - view (read-only)
  - bash_tool (read-only commands: cat, grep, find, wc)
constraints:
  - Cannot modify any files
  - Cannot generate new content
  - Must reference specific requirements from docs/
  - Must provide actionable feedback
context_priority:
  1. skills/phase-{N}/SKILL.md (quality criteria)
  2. docs/ (all files)
  3. Builder deliverables
evaluation_criteria:
  - Completeness: All requirements addressed?
  - Accuracy: Correct interpretation of requirements?
  - Format: Follows specified structure?
  - Quality: Meets professional standards?
```

## パフォーマンス最適化

**コンテキスト管理**
- 開始時に `docs/` を1回読み込み、全フェーズで再利用
- 各フェーズは自分の `SKILL.md` のみを読み込む
- 前フェーズ出力は必要時のみオンデマンドで読み込む

**並列実行（将来）**
- 独立フェーズ（依存チェーンなし）を検出
- Builder を並列実行
- Validator は順次実行（コンテキスト競合を避ける）

**キャッシュ**
- パース済み `SKILL.md` 要件をキャッシュ
- `docs/` 内容をフェーズ間でキャッシュ
- 修正ループ間で検証基準を再利用

## 実行例

```bash
$ /run-phase 1

Loading context...
✓ CLAUDE.md
✓ docs/ (5 files)
✓ skills/phase-01/SKILL.md

Starting Phase 1: Research & Analysis
  └─ Builder agent executing...
     ├─ Reading background requirements
     ├─ Generating market analysis
     └─ Creating comparison table
  ✓ Deliverables saved to outputs/phase-01/

Starting Validation...
  └─ Validator agent reviewing...
     ├─ Checking completeness
     ├─ Verifying format
     └─ Assessing quality
  ⚠ Validation: NEEDS_REVISION (2 issues)

Critical Issues:
  1. Missing: Competitor pricing comparison
  2. Format: Table missing required columns

Auto-fix? [Y/n/review]
```
