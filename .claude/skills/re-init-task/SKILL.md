# /re-init-task — 新イテレーション開始

## Objective
現在のイテレーション完了後に、新しいイテレーションを開始する。既存の docs/ を活用し、差分のみを収集して新フェーズを構成する。

## Prerequisites

### 前提条件チェック手順
1. `metadata.json` を読み込む
2. `phase_count` フィールドの存在を確認（なければエラー: `/init-task を先に実行してください`）
3. `phases` オブジェクトの存在を確認（なければエラー: `/run-phase を先に実行してください`）
4. 全対象フェーズの完了状態を確認:
   - `iterations[]` がある場合: 最新イテレーションのフェーズのみチェック
   - `iterations[]` がない場合: 全フェーズをチェック
   - 許容ステータス: `completed`, `completed_with_issues`
   - 未完了フェーズがあればエラー表示（フェーズ番号とステータスの一覧）

### エラー表示例
```
Error: /re-init-task の前提条件を満たしていません。

以下のフェーズが未完了です:
  - Phase 3: in_progress
  - Phase 4: not_started

全フェーズを completed または completed_with_issues にしてから
/re-init-task を実行してください。
```

## Input Requirements
- `metadata.json`（現在のプロジェクト状態）
- `docs/`（既存仕様ファイル一式）
- `CLAUDE.md`（プロジェクト概要）
- ユーザーからの差分要件（対話形式で収集）

## Output Specification

### 更新されるファイル
- `metadata.json` — `iterations[]` 追加、`phase_count` 更新、`current_iteration` 更新、`status` を `in_progress` に変更
- `docs/` — 差分更新（既存ファイルの追記 or 新規追加）
- `CLAUDE.md` — Deliverables セクションをイテレーション区分付きに更新
- `iteration_history.md` — 新イテレーションセクションを追加

### 新規作成されるファイル
- `skills/phase-{N+1}/SKILL.md` 〜 `skills/phase-{M}/SKILL.md` — 新フェーズ

## Quality Criteria
- [ ] 前提条件チェックが completed と completed_with_issues の両方を許容している
- [ ] 差分インテークが最大5問に収まっている
- [ ] docs/ の既存内容を破壊せず追記・更新している
- [ ] metadata.json の iterations[] が正しく構成されている
- [ ] 新フェーズ番号が継続番号になっている（例: Iter1が4フェーズなら Iter2は5から開始）
- [ ] iteration_history.md に新セクションが追加されている
- [ ] CLAUDE.md の Deliverables がイテレーション区分付きフォーマットに更新されている

## Procedure

### ステップ1: 前提条件チェック

1. `metadata.json` を読み込む
2. Prerequisites セクションの手順に従い、前提条件を検証する
3. 前提条件を満たさない場合、エラーメッセージを表示して終了する

### ステップ2: 現状サマリーの表示

1. `metadata.json` から `current_iteration`, `phase_count`, `iterations[]` を取得
2. `docs/` 配下の全ファイルを読み込む
3. ユーザーに現状を提示:
   ```
   Iteration {N} が完了しました。
   - フェーズ: Phase 1〜{M}（全 {M} フェーズ）
   - ステータス: {completed / completed_with_issues の内訳}

   現在の docs/ 仕様:
   - requirements.md: {要約1行}
   - plan.md: {要約1行}
   - ...
   ```

### ステップ3: 差分インテーク（最大5問）

以下の質問を **1回のメッセージで** 提示する:

1. **「今回のイテレーションの目標は何ですか？」**（必須）
   - 1行で簡潔に記述
2. **「追加・変更する機能は何ですか？」**（必須）
   - 箇条書きで列挙
3. **「新しい制約や技術的変更はありますか？」**（任意、変更なしならスキップ）
4. **「フェーズ数はいくつを想定していますか？」**（デフォルト: 前回と同数）
5. **「docs/ に追加すべきファイルはありますか？」**（通常は不要）

**効率化ルール:**
- 前回の docs/ 内容を引用して「変更がありますか？」と聞く
- 変更なしの場合は「前回と同じ」で即スキップ
- 全インテークをやり直さない（差分のみ）

### ステップ4: docs/ の差分更新

1. ユーザー回答に基づき、変更が必要な docs/ ファイルを特定する
2. 各ファイルに対して:
   - **追記**: 新機能要件を既存内容の後に追加（例: requirements.md に F6, F7 を追加）
   - **更新**: 変更された制約やスコープを反映（既存内容は維持）
   - **新規作成**: 必要な場合のみ（質問5でユーザーが要求した場合）
3. `docs/_manifest.json` を更新（新規ファイルがあれば `required_files` に追加）

### ステップ5: 新フェーズの skills/ 作成

1. 前イテレーションの最終フェーズ番号を取得（例: 4）
2. ユーザー指定のフェーズ数から新フェーズ番号を計算（例: 5〜8）
3. 各フェーズについて `skills/phase-{N}/SKILL.md` を作成:
   - テンプレート: カテゴリ別テンプレート（`templates/skills/{category}.md`）をベース
   - プレースホルダーをユーザー回答で埋める
   - Input Requirements に前イテレーションの成果物を含める

### ステップ6: metadata.json の更新

```python
# 擬似コード
def update_metadata(metadata, goal, new_phase_count):
    old_count = metadata["phase_count"]

    # iterations[] の初期化（初回 re-init 時）
    if "iterations" not in metadata:
        metadata["iterations"] = [{
            "id": 1,
            "goal": metadata.get("project_name", "Initial iteration"),
            "phases": list(range(1, old_count + 1)),
            "status": "completed",
            "started_at": metadata.get("created_at", ""),
            "completed_at": datetime.now().isoformat()
        }]
        metadata["current_iteration"] = 1

    # 新イテレーション追加
    new_iter_id = metadata["current_iteration"] + 1
    new_phases = list(range(old_count + 1, old_count + new_phase_count + 1))

    metadata["iterations"].append({
        "id": new_iter_id,
        "goal": goal,
        "phases": new_phases,
        "status": "in_progress",
        "started_at": date.today().isoformat(),
        "completed_at": None
    })

    metadata["current_iteration"] = new_iter_id
    metadata["phase_count"] = old_count + new_phase_count
    metadata["status"] = "in_progress"

    # 新フェーズのステータス初期化
    for p in new_phases:
        metadata.setdefault("phases", {})[str(p)] = {"status": "not_started"}
```

### ステップ7: iteration_history.md の更新

1. `iteration_history.md` が存在しない場合は新規作成（ヘッダー付き）
2. 新イテレーションセクションをヘッダー直後に挿入:
   ```markdown
   ## Iteration {N} — {goal}（{date}）

   ### 目標
   {goal}

   ### フェーズ構成
   | Phase | 成果物 | ステータス |
   |-------|--------|-----------|
   | {NN}  | (未定) | ⏳ |

   ### docs/ 変更点
   - {changed_doc}: {summary}

   ---
   ```

### ステップ8: CLAUDE.md の更新

1. `## Deliverables` セクションを検出する
2. 既存のテーブルをイテレーション区分付きフォーマットに変換:
   ```markdown
   ## Deliverables

   ### Iteration 1: {goal}
   | Phase | Deliverable | Format | Status |
   |-------|-------------|--------|--------|
   | 01    | {name}      | {fmt}  | completed |
   ...

   ### Iteration 2: {goal}
   | Phase | Deliverable | Format | Status |
   |-------|-------------|--------|--------|
   | 05    | {name}      | {fmt}  | not_started |
   ...
   ```
3. 既存のフェーズ情報を Iteration 1 としてラベル付けする
4. 新イテレーションのフェーズテーブルを追加する

### ステップ9: 完了確認

ユーザーに以下を提示:
```
✓ Iteration {N} を開始しました

更新ファイル:
  - metadata.json（iterations[] 追加、phase_count: {old} → {new}）
  - docs/requirements.md（新要件 {count} 件追加）
  - iteration_history.md（新セクション追加）
  - CLAUDE.md（Deliverables 更新）

新規作成:
  - skills/phase-{start}/SKILL.md 〜 skills/phase-{end}/SKILL.md

次のステップ:
  /run-phase {start}       - 新イテレーションの最初のフェーズを実行
  /run-phase {start}-{end} - 新イテレーションの全フェーズを実行
  /run-phase all           - 全フェーズを実行（既に完了分はスキップ）
```

## Error Handling

| エラー | 対処 |
|--------|------|
| metadata.json が存在しない | `/init-task を先に実行してください` と表示して終了 |
| 未完了フェーズがある | フェーズ一覧を表示し、完了を促して終了 |
| docs/ が存在しない | `/init-task を先に実行してください` と表示して終了 |
| skills/ の書き込み権限なし | エラーメッセージを表示して終了 |
| iteration_history.md のパースエラー | 新規作成にフォールバック |
| CLAUDE.md の Deliverables セクションが見つからない | セクションを新規追加 |
| ユーザーが差分質問に「変更なし」と回答 | その docs/ ファイルの更新をスキップ |

## Common Pitfalls
- init-task のインテークを全部やり直してしまう → 差分のみ質問する
- iterations[] を追加せずに phases だけ増やす → 必ず iterations[] を初期化・追加する
- 新フェーズ番号を 1 から始めてしまう → 前イテレーション最終 +1 から開始
- CLAUDE.md の Deliverables セクションを全置換してしまう → 既存内容を Iteration 1 として維持
