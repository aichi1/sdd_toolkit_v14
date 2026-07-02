# finalize - SDDプロジェクト完了処理＆知見抽出

## 目的
完了したプロジェクトをパッケージ化し、`~/.sdd-knowledge/` にアーカイブし、将来のプロジェクトで再利用できるパターンを抽出し、振り返り（retrospective）の準備を行う。

## 前提条件
- すべてのフェーズが完了している（またはユーザーが完了を確認している）
- outputs/ ディレクトリが存在し、成果物が入っている
- CLAUDE.md と metadata.json が最新状態になっている

## 入力
- 任意のフラグ:
  - `--skip-archive`: `~/.sdd-knowledge/docs-archive/` へコピーしない
  - `--skip-starter`: スターターの抽出/更新をしない
  - `--force`: バリデーションが未完了でも処理を続行する

## 出力
- プロジェクトが `~/.sdd-knowledge/docs-archive/{date}_{category}_{name}/` にアーカイブされる
- スターターテンプレートが `~/.sdd-knowledge/starters/{category}/` に作成または更新される
- サマリーレポートが `./finalization-report.md` として生成される

## ワークフロー

### フェーズ0: 検証

**ステップ0.1: 完了チェック**
```bash
metadata.json のステータスを確認:
  - 全フェーズ: status = "completed" または "completed_with_issues"
  - いずれかのフェーズが "not_started" または "in_progress" の場合:
    → ユーザーに警告し、それでも finalize するか確認する
```

**ステップ0.2: 成果物チェック**
```bash
各フェーズについて:
  - outputs/phase-{N}/ が存在することを確認
  - 少なくとも1つの成果物ファイルが存在することを確認
  - .validation/ ディレクトリの有無を確認（Validator が実行された証跡）

危険信号:
  - outputs/ ディレクトリが空
  - バリデーションレポートがない
  - 重大なバリデーション問題が未解決
```

**ステップ0.3: ユーザー確認**
```
Project: {project_name}
Category: {category}
Phases completed: {N}/{total}
Deliverables: {count} files

Finalizeしますか？これにより以下を行います:
  1. プロジェクトを ~/.sdd-knowledge/ にアーカイブ
  2. 将来利用のためのパターン抽出
  3. プロジェクトを完了としてマーク

続行しますか？ [Y/n]
```

### フェーズ1: プロジェクトのアーカイブ

**ステップ1.1: アーカイブ用ディレクトリ作成**
```bash
ARCHIVE_DIR=~/.sdd-knowledge/docs-archive/$(date +%Y-%m-%d)_{category}_{project_name}/

mkdir -p $ARCHIVE_DIR/{docs,outputs,skills,meta}
```

**ステップ1.2: プロジェクトファイルのコピー**
```bash
# 仕様ドキュメント
cp -r ./docs/ $ARCHIVE_DIR/docs/

# 生成された成果物
cp -r ./outputs/ $ARCHIVE_DIR/outputs/

# フェーズスキル（参照用）
cp -r ./skills/ $ARCHIVE_DIR/skills/

# プロジェクト専用エージェント（存在する場合）
if [ -d .claude/agents/generated/ ]; then
  mkdir -p $ARCHIVE_DIR/agents/
  cp .claude/agents/generated/*.md $ARCHIVE_DIR/agents/
fi
if [ -d .claude/agents/ ]; then
  mkdir -p $ARCHIVE_DIR/agents/
  cp .claude/agents/*.md $ARCHIVE_DIR/agents/ 2>/dev/null || true
fi

# プロジェクトメタデータ
cp ./CLAUDE.md $ARCHIVE_DIR/meta/
cp ./metadata.json $ARCHIVE_DIR/meta/
```

**ステップ1.3: アーカイブ用メタデータ作成**
`$ARCHIVE_DIR/metadata.json` を作成:
```json
{
  "project_name": "{name}",
  "category": "{category}",
  "archived_at": "{ISO timestamp}",
  "original_path": "{pwd}",
  "phase_count": {N},
  "total_hours": {calculated from metadata},
  "deliverables_count": {count},
  "validation_summary": {
    "phases_validated": {N},
    "critical_issues": {count},
    "overall_quality": "high/medium/low"
  },
  "tags": ["{auto-generated tags}"],
  "description": "{one-line summary from CLAUDE.md}"
}
```

**ステップ1.4: グローバルインデックス更新**
`~/.sdd-knowledge/docs-archive/index.json` に追記:
```json
{
  "projects": [
    ...existing entries,
    {
      "id": "{uuid}",
      "name": "{project_name}",
      "category": "{category}",
      "date": "{date}",
      "path": "{relative path to archive}",
      "tags": [...]
    }
  ],
  "last_updated": "{ISO timestamp}"
}
```

### フェーズ1.5: 最終成果物の集約

**ステップ1.5.0: 集約要否の判定**
```
outputs/phase-{N}/ ディレクトリを列挙し、成果物の存在を確認する。
成果物が1フェーズ分のみの場合、集約は不要（outputs/final/ は作成しない）。
2フェーズ以上の成果物がある場合、集約を実行する。
```

**ステップ1.5.1: outputs/final/ ディレクトリ作成**
```bash
mkdir -p outputs/final/
```

**ステップ1.5.2: 成果物のコピー**
各フェーズの成果物を outputs/final/ にコピーする。

処理ルール:
- フェーズ番号の昇順で処理（後勝ち方式: 同名ファイルは後のフェーズが上書き）
- 除外対象:
  - `.metadata.json`（Builder/Validator 用メタデータ）
  - `.validation/` ディレクトリ（Validator レポート）
  - `__pycache__/`, `*.pyc`（Python キャッシュ）
  - `.phase-context.json`（フェーズ間コンテキスト）
- 各フェーズの `README.md` は集約しない（自動生成で置換）
- サブディレクトリも再帰的にコピー

衝突が発生した場合、衝突リストを記録する（ステップ1.5.4で使用）。

```python
# 擬似コード
import shutil
from pathlib import Path

EXCLUDE_PATTERNS = {".metadata.json", ".phase-context.json"}
EXCLUDE_DIRS = {".validation", "__pycache__"}

def aggregate_outputs(project_dir):
    outputs_dir = project_dir / "outputs"
    final_dir = outputs_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)

    conflicts = []  # [(file_rel_path, old_phase, new_phase)]
    file_source_map = {}  # {rel_path: phase_number}

    phase_dirs = sorted(outputs_dir.glob("phase-*"))
    for phase_dir in phase_dirs:
        phase_num = int(phase_dir.name.split("-")[1])
        for src in phase_dir.rglob("*"):
            if src.is_dir():
                continue
            if src.name in EXCLUDE_PATTERNS:
                continue
            if any(p.name in EXCLUDE_DIRS for p in src.parents):
                continue
            if src.name == "README.md":
                continue
            if src.suffix == ".pyc":
                continue

            rel = src.relative_to(phase_dir)
            dest = final_dir / rel

            if str(rel) in file_source_map:
                conflicts.append((str(rel), file_source_map[str(rel)], phase_num))

            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            file_source_map[str(rel)] = phase_num

    return file_source_map, conflicts
```

**ステップ1.5.3: README.md 自動生成**
`outputs/final/README.md` を生成する:

```markdown
# Final Deliverables: {project_name}

Generated: {date}
Category: {category}

## Files
| File | Source Phase | Description |
|------|------------|-------------|
| {rel_path} | Phase {N} | |
```

**ステップ1.5.4: CHANGELOG.md 生成**
`outputs/final/CHANGELOG.md` を生成する:

- `iterations[]` がある場合: イテレーションごとのセクション（新しい順）
- `iterations[]` がない場合: 単一セクション（Iteration 1 として）

各セクションに含める内容:
- Goal
- Phase Summary テーブル（Phase番号、ステータス）
- File Conflicts（衝突があった場合のみ）

**ステップ1.5.5: ユーザーへのサマリー表示**
```
outputs/final/ に最終成果物を集約しました:
  - ファイル数: {N}
  - ソースフェーズ: Phase {min}〜{max}
  - 衝突解決: {N} 件（後勝ち方式）
```

### フェーズ2: スターターの抽出/更新

**ステップ2.1: スターターの処理方針を決定**
```
~/.sdd-knowledge/starters/{category}/ を確認:
  - 存在する？ → 既存スターターを更新
  - 存在しない？ → 新規スターターを作成
```

**ステップ2.2: 現在のプロジェクトを分析**
```
再利用可能なパターンを抽出:

docs/ から:
  - 必須だったファイルは？（複数フェーズで使用）
  - 任意だったファイルは？（ほとんど参照されない）
  - 足りなかったファイルは？（途中で追加された）

skills/ から:
  - どの SKILL.md 手順がそのまま踏襲された？
  - どの手順がカスタマイズを要した？
  - どの手順が有効だった/混乱を招いた？

バリデーションレポートから:
  - フェーズ横断で頻出の問題
  - 見落とされた要件
  - 問題を検知した品質基準
```

**ステップ2.3: コンテンツの一般化**
プロジェクト固有の内容をテンプレートへ変換する:

**例 - docs/background.md:**
```markdown
Before (project-specific):
"This project evaluates WebAssembly frameworks for browser-based
data visualization, focusing on Three.js compatibility."

After (generalized):
"This project evaluates {technology_category} for {use_case},
focusing on {key_requirement}."
```

**一般化ルール:**
- 固有名詞 → `{project_name}`, `{company_name}`
- 特定技術 → `{technology_category}`
- 日付/スケジュール → `{deadline}`, `{timeline}`
- 指標 → `{target_metric}`, `{threshold}`
- 人名 → `{stakeholder}`, `{audience}`

**ステップ2.4: スターターの作成/更新**

**新規スターターの場合:**
```bash
STARTER_DIR=~/.sdd-knowledge/starters/{category}/

mkdir -p $STARTER_DIR/{docs-template,skills,templates}

# 一般化した docs/ をコピー
cp ./docs/* $STARTER_DIR/docs-template/
# (一般化変換を適用)

# skills/ はそのままコピー（既に汎用）
cp -r ./skills/* $STARTER_DIR/skills/

# outputs/ からテンプレ抽出（任意）
# (例: よく使う文書構成、ボイラープレート)

# スターターメタデータ作成
cat > $STARTER_DIR/metadata.json <<EOF
{
  "category": "{category}",
  "created_at": "{ISO timestamp}",
  "created_from": "{project_name}",
  "version": 1,
  "confidence_score": 0.5,
  "based_on_projects": 1,
  "essential_docs": ["{list}"],
  "optional_docs": ["{list}"],
  "phase_count": {N},
  "placeholders": [
    {"key": "project_name", "description": "Name of the project"},
    {"key": "technology_category", "description": "Category of technology"},
    ...
  ]
}
EOF
```

**既存スターター更新の場合:**
```bash
STARTER_DIR=~/.sdd-knowledge/starters/{category}/

# 既存スターターをロード
existing_metadata=$(cat $STARTER_DIR/metadata.json)

# 比較してマージ:
# 1. docs-template/
#    - 両方に存在 → 維持（補強）
#    - 現在のみ存在 → 必須判定なら追加
#    - スターターのみ存在 → 廃止判定でなければ維持
#
# 2. skills/
#    - SKILL.md 手順を比較
#    - 手順が分岐している場合 → どちらを残すかユーザーへ確認
#    - 現在の方が良い → スターターを更新
#    - スターターの方が良い → レポートに記録
#
# 3. metadata.json
#    - version をインクリメント
#    - confidence_score を更新（プロジェクト数が増えるほど上げる）
#    - based_on_projects に今回のプロジェクトを追加
```

**マージ判断ロジック:**
```python
def merge_decision(starter_file, current_file, validation_feedback):
    if both_files_identical:
        return "keep_starter"  # 強いシグナル
    
    if validation_feedback.says_current_is_better:
        return "update_with_current"
    
    if validation_feedback.says_starter_would_help:
        return "keep_starter"
    
    # 曖昧 → ユーザーに確認
    return "ask_user"
```

**ステップ2.5: スターター変更のユーザーレビュー**
```
Starter Update Preview for "{category}":

docs-template/ changes:
  + Added: competitor-analysis.md (marked essential)
  ~ Updated: scope.md (added section: Risk Assessment)
  - Removed: (none)

skills/ changes:
  ~ phase-02/SKILL.md: Added quality criterion:
    "Verify all data sources are cited"

metadata.json changes:
  - Version: 1 → 2
  - Confidence: 0.5 → 0.65
  - Based on projects: 1 → 2

変更を適用しますか？ [Y/n/review]
```

### フェーズ3: 知見の統合

**ステップ3.0: コンポーネント自動抽出**
プロジェクトの skills/, agents/, hooks/, rules/ からコンポーネント候補を抽出し、知識ベースに登録する:

```bash
python3 scripts/extract_components.py "$(pwd)" --kb-dir ~/.sdd-knowledge
```

実行結果をユーザーに提示:
```
コンポーネント抽出結果:
  Skills: {N} 件
  Agents: {N} 件
  Hooks: {N} 件
  Rules: {N} 件
  合計: {N} 件 → candidates.jsonl に追記済み
```

次に、候補を registry.json に昇格し、検索可能なコンポーネントとして登録する:
```bash
python3 scripts/promote_candidates.py --kb-dir ~/.sdd-knowledge
```

実行結果をユーザーに提示:
```
コンポーネント登録結果:
  新規登録: {N} 件（skill: {N}, agent: {N}, hook: {N}, rule: {N}）
  既存更新: {N} 件（使用回数・信頼度を更新）
  スキップ: {N} 件（コンテンツ取得不可）
  registry.json 合計: {N} コンポーネント
```

最後に、検索インデックスを再構築する:
```bash
python3 scripts/build_search_index.py --kb-dir ~/.sdd-knowledge
```

**ステップ3.1: 学びの抽出**
プロジェクトから移転可能な知見を分析する:

```
ソース:
  - バリデーションレポート（頻出問題）
  - metadata.json（見積もり時間 vs 実績）
  - CLAUDE.md（スコープ変更があれば）
  - ユーザーの暗黙フィードバック（フェーズ再実行、手動修正など）

抽出:
  1. プロセス面の学び:
     - "フェーズXが想定より長引いた理由は..."
     - "フェーズYのSKILL.mdが曖昧で、～が必要だった"
  
  2. コンテンツ面の学び:
     - "docs/ にZがなく、フェーズ...で混乱が起きた"
     - "成果物フォーマットは最初にXを明記すべき"
  
  3. ツール面の学び:
     - "Builder agent が～で苦戦した"
     - "Validator が、見逃されがちな問題を検知した"

/retrospective コマンド用の予備メモとして整形する。
```

**ステップ3.2: Finalization Report の作成**
`./finalization-report.md` を生成:

```markdown
# Finalization Report: {Project Name}

**Date**: {ISO timestamp}
**Category**: {category}
**Duration**: {total hours}
**Phases**: {N}

## Archive
✓ Project archived to: ~/.sdd-knowledge/docs-archive/{path}
  - docs/ (5 files)
  - outputs/ (8 deliverables)
  - skills/ (3 phases)

## Final Deliverables
✓ Aggregated to: outputs/final/
  - Total files: {N}
  - Source phases: {list}
  - File conflicts: {N} (resolved by last-phase-wins)

## Starter Update
✓ Starter updated: ~/.sdd-knowledge/starters/{category}/
  - Version: 1 → 2
  - Confidence: 0.50 → 0.65
  - Changes: 3 files updated, 1 file added

## Preliminary Lessons
The following insights were extracted for your retrospective:

### Process
- Phase 2 required 2 revision cycles; SKILL.md could be more specific
  about output format expectations

### Content
- docs/sources.md was underspecified; future projects should include
  example citations

### Tools
- Builder/Validator pattern caught 5 issues before user review

## Recommended Next Steps
1. Run `/retrospective` to record structured learnings
2. Review starter changes in ~/.sdd-knowledge/starters/{category}/
3. (Optional) Share insights with team/community

## Project Statistics
- Total deliverables: {N}
- Total words generated: ~{estimate}
- Builder iterations: {N}
- Validator issues caught: {N}
- User manual fixes: {N}

---
To start your next {category} project:
  /init-task "Your task description"
  (Will automatically use updated starter)
```

### フェーズ4: クリーンアップ＆確認

**ステップ4.1: プロジェクトステータス更新**
`./metadata.json` を更新:
```json
{
  ...
  "status": "finalized",
  "finalized_at": "{ISO timestamp}",
  "archived_to": "{path}",
  "starter_updated": true
}
```

**ステップ4.2: 任意のクリーンアップ**
ユーザーに確認:
```
プロジェクトの finalize が正常に完了しました。

ローカルファイルを整理しますか？
  1. すべて残す（アーカイブ + ローカル）
  2. outputs/ と finalization-report.md だけ残す
  3. すべて削除（アーカイブのみ残す）

選択 [1]:
```

**ステップ4.3: 最終出力**
```
✓ Finalization complete

Summary:
  ✓ Archived to ~/.sdd-knowledge/docs-archive/
  ✓ Starter updated (v2, confidence 0.65)
  ✓ {N} lessons extracted

View report: ./finalization-report.md

Next:
  /retrospective  - Record structured learnings
  /lessons        - Review accumulated wisdom
```

## 品質ゲート

finalize 完了前に満たすこと:
- [ ] アーカイブディレクトリが作成され、必須ファイルが揃っている
- [ ] index.json が更新されている
- [ ] スターターが作成または更新されている（またはユーザーがスキップ）
- [ ] Finalization report が生成されている
- [ ] metadata.json が "finalized" としてマークされている

## エラーハンドリング

**アーカイブ失敗:**
- ディスク容量不足 → 警告し、空き容量を確保するよう依頼
- 権限不足 → ユーザー向けに mkdir コマンドを提示
- パス衝突 → タイムスタンプのサフィックスを付与

**スターターのマージ衝突:**
- 手順が矛盾 → 両方を提示してユーザーに選択を依頼
- 一般化できない → そのまま保持し、手動レビュー対象としてフラグ
- confidence が下がる → 警告し、より多くのプロジェクトが必要と提案

**振り返り（Retrospective）との統合:**
finalization report の "Preliminary Lessons" セクションは `/retrospective` に直接投入され、追加質問を行い、構造化された JSON レコードを作成する。

## パフォーマンスメモ
- アーカイブ処理: 約1〜5秒（outputs のサイズによる）
- スターター抽出: 約10〜30秒（分析を含む）
- マージ判断: ユーザー入力が必要になる場合がある（ブロック）

## 将来の拡張
- [ ] Notion 連携を自動検知し、同期を提案
- [ ] 共有可能なプロジェクトサマリー（PDF/HTML）を生成
- [ ] ROI 指標を計算（削減時間 vs 手動作業）
- [ ] アーカイブ内の関連プロジェクトを比較用に提示
