# File Structure Rules - ファイル命名とディレクトリ構造ルール

## 目的
プロジェクト内のファイル配置、命名規則を統一し、誰が見ても理解しやすい構造を維持する。

## プロジェクトディレクトリ構造

### 標準構造
```
project-root/
├── docs/                    # 仕様（What）
│   ├── background.md
│   ├── scope.md
│   ├── sources.md
│   └── ...
│
├── skills/                  # 手順（How）
│   ├── phase-01/
│   │   └── SKILL.md
│   ├── phase-02/
│   │   └── SKILL.md
│   └── ...
│
├── outputs/                 # 成果物
│   ├── phase-01/
│   │   ├── .metadata.json
│   │   ├── .validation/
│   │   │   └── report.md
│   │   ├── analysis.md
│   │   └── data.csv
│   ├── phase-02/
│   ├── ...
│   ├── final/              # 最終成果物の集約（/finalize で生成）
│   │   ├── README.md       # ファイル索引（自動生成）
│   │   ├── CHANGELOG.md    # イテレーション差分サマリー
│   │   └── {deliverables}  # 各フェーズの最終成果物（コピー）
│   └── .phase-context.json # フェーズ間コンテキスト
│
├── CLAUDE.md                # プロジェクト仕様書
├── metadata.json            # プロジェクトメタデータ
├── finalization-report.md   # 完了レポート（finalize後）
├── iteration_history.md     # イテレーション履歴（/re-init-task で作成・更新）
└── retrospective.md         # 振り返り（retrospective後）
```

---

## ディレクトリ別ルール

### docs/ - 仕様ディレクトリ

**目的**: プロジェクトの要件、制約、背景を記録

**命名規則:**
```
推奨: {目的}.md
  - background.md（背景）
  - scope.md（スコープ）
  - requirements.md（要件）
  - constraints.md（制約）
  - audience.md（対象読者）
  - format.md（成果物形式）

複数ファイルに分割する場合:
  - requirements-functional.md
  - requirements-nonfunctional.md

プロジェクト固有のファイル:
  - sources.md（調査プロジェクト）
  - competitors.md（比較プロジェクト）
  - topology.md（ネットワーク設計）
```

**禁止事項:**
```
✗ docs/temp.md（一時ファイル）
✗ docs/draft1.md, draft2.md（バージョン管理はGit使用）
✗ docs/note.txt（Markdown以外）
✗ docs/phase-01-requirements.md（Phase番号不要、全体の要件）
```

**ファイル構造:**
```markdown
# {ファイル名のタイトル}

## 概要
{1-2段落で要約}

## 詳細
### {サブセクション1}
{内容}

### {サブセクション2}
{内容}

## 参考
{関連docs/や外部リンク}
```

---

### skills/ - 手順ディレクトリ

**目的**: 各Phaseの実行手順を記録

**命名規則:**
```
必須: phase-{NN}/SKILL.md

例:
  skills/phase-01/SKILL.md
  skills/phase-02/SKILL.md
  ...
  skills/phase-10/SKILL.md（10以降も2桁）

補助ファイル（任意）:
  skills/phase-02/template.md（テンプレート）
  skills/phase-02/example.py（コード例）
  skills/phase-02/checklist.md（チェックリスト）
```

**Phase番号ルール:**
```
- 1から開始
- 連番
- ゼロ埋め2桁（phase-01, phase-02, ..., phase-10）
- 欠番を作らない（phase-01, phase-03はNG）

Phase追加時:
  既存: phase-01, phase-02, phase-03
  追加: phase-04（phase-02とphase-03の間に追加不可）
  
Phase削除時:
  既存: phase-01, phase-02, phase-03
  削除: phase-02 → phase-03をphase-02に改名
```

**SKILL.mdフォーマット:**
```markdown
# Phase {N}: {Phase名}

## Objective
{このPhaseの目的}

## Input Requirements
{必要なdocs/, 前Phase成果物}

## Output Specification
{生成すべき成果物}

## Procedure
{ステップバイステップの手順}

## Quality Criteria
{品質基準}

## Common Pitfalls
{よくある問題と対処}
```

---

### outputs/ - 成果物ディレクトリ

**目的**: 各Phaseで生成された成果物を保存

**命名規則:**
```
ディレクトリ:
  outputs/phase-{NN}/

成果物ファイル:
  - SKILL.mdで指定された名前を使用
  - 拡張子: .md, .csv, .json, .py, .html等
  
例:
  outputs/phase-01/
    ├── analysis.md
    ├── raw-data.csv
    └── summary.json
  
  outputs/phase-02/
    ├── comparison-table.md
    └── recommendation.md
```

**メタデータファイル:**
```
必須: outputs/phase-{NN}/.metadata.json

構造:
{
  "phase": 2,
  "builder_session_id": "uuid",
  "started_at": "2026-02-05T10:00:00Z",
  "completed_at": "2026-02-05T11:30:00Z",
  "status": "completed",
  "validation_status": "pass",
  "deliverables": [
    {
      "file": "comparison-table.md",
      "type": "document",
      "word_count": 1500
    }
  ],
  "revision_history": [
    {
      "iteration": 1,
      "timestamp": "2026-02-05T10:30:00Z",
      "changes": "初回生成"
    }
  ]
}
```

**検証ディレクトリ:**
```
任意: outputs/phase-{NN}/.validation/

内容:
  - report.md（検証レポート）
  - quality-gates.json（品質ゲート結果）
  - iteration-{N}.md（修正サイクル記録）
```

### outputs/final/ — 最終成果物の集約

`/finalize` 実行時に自動生成される。各フェーズの成果物を1つのディレクトリに集約する。

**集約ルール:**
- フェーズ番号の昇順でコピー（後勝ち方式: 同名ファイルは後のフェーズが上書き）
- 除外対象: `.metadata.json`, `.validation/`, `__pycache__/`, `.phase-context.json`, 各フェーズの `README.md`
- `README.md` と `CHANGELOG.md` は自動生成

**CHANGELOG.md のフォーマット:**
- `iterations[]` がある場合: イテレーションごとのセクション（新しい順）
- `iterations[]` がない場合: 単一セクション（Iteration 1 として）
- 各セクションに Goal、Phase Summary テーブル、File Conflicts を含む

**生成条件:**
- 2フェーズ以上の成果物がある場合に集約を実行
- 1フェーズのみの場合は集約不要（outputs/final/ を作成しない）

---

**一時ファイル禁止:**
```
✗ outputs/phase-01/temp.md
✗ outputs/phase-01/backup.md
✗ outputs/phase-01/old-version.md

理由: outputs/は最終成果物のみ
      一時ファイルは .gitignore or 別ディレクトリ
```

---

## ルートファイル

### CLAUDE.md - プロジェクト仕様書

**目的**: プロジェクト全体の概要、Phase構成、規約を1ファイルに集約

**必須セクション:**
```markdown
# {プロジェクト名}

## Metadata
- Category: {category}
- Start Date: {date}
- Estimated Duration: {hours}
- Phase Count: {N}

## Objective
{1段落でプロジェクト目的}

## Deliverables
| Phase | Deliverable | Format | Estimated Time |
|-------|-------------|--------|----------------|
| ...   | ...         | ...    | ...            |

## Specification Files
{docs/の各ファイル説明}

## Skills Structure
{skills/の各Phase説明}

## Conventions
{プロジェクト固有の規約}

## Next Steps
{進捗や次のアクション}
```

**更新タイミング:**
```
- init-task実行時: 作成
- Phase完了時: 「Next Steps」更新
- finalize実行時: 最終更新
```

---

### metadata.json - プロジェクトメタデータ

**目的**: 機械可読なプロジェクト情報

**必須フィールド:**
```json
{
  "project_name": "WebAssembly Framework Evaluation",
  "category": "investigation-report",
  "created_at": "2026-02-05T09:00:00Z",
  "estimated_hours": 6.5,
  "phase_count": 3,
  "status": "in_progress",
  "phases": {
    "1": {
      "status": "completed",
      "completed_at": "2026-02-05T10:30:00Z",
      "actual_hours": 2.1
    },
    "2": {
      "status": "in_progress",
      "started_at": "2026-02-05T10:35:00Z"
    },
    "3": {
      "status": "not_started"
    }
  },
  "starter_used": true,
  "starter_version": 2
}
```

**status値:**
```
プロジェクトレベル:
  - initialized: init-task完了
  - in_progress: 少なくとも1 Phase実行中
  - completed: 全Phase完了
  - finalized: finalize実行完了

Phaseレベル:
  - not_started: 未開始
  - in_progress: Builder実行中
  - completed: Validator PASS
  - completed_with_issues: 問題ありだがユーザー承認
```

**v11 追加フィールド:**

| フィールド | 型 | 説明 |
|-----------|---|------|
| `current_iteration` | number | 現在のイテレーション番号（デフォルト: 1） |
| `iterations` | array | イテレーション一覧 |
| `iterations[].id` | number | イテレーション番号（1始まり） |
| `iterations[].goal` | string | イテレーションの目標 |
| `iterations[].phases` | number[] | このイテレーションのフェーズ番号リスト |
| `iterations[].status` | string | in_progress / completed / completed_with_issues |
| `iterations[].started_at` | string | ISO 8601 日付 |
| `iterations[].completed_at` | string / null | ISO 8601 日付、未完了時は null |

**後方互換性:**
- `iterations` フィールドが存在しない場合、全フェーズを Iteration 1 として暗黙的にグループ化する
- `current_iteration` が存在しない場合、`1` とみなす

**更新タイミング:**
```
- init-task: 作成
- run-phase開始: 該当Phase statusを in_progress
- run-phase完了: 該当Phase statusを completed
- re-init-task: iterations[] 追加、phase_count 更新
- finalize: プロジェクトstatusを finalized
```

---

### finalization-report.md - 完了レポート

**作成タイミング**: `/finalize` 実行時

**目的**: プロジェクト完了の記録

**構造:**
```markdown
# Finalization Report: {Project Name}

**Date**: {date}
**Duration**: {hours}
**Phases**: {N}

## Archive
{アーカイブ先パス}

## Starter Update
{スターター更新内容}

## Preliminary Lessons
{retrospective用の予備的教訓}

## Statistics
{統計情報}

## Next Steps
{推奨される次のアクション}
```

---

### retrospective.md - 振り返り

**作成タイミング**: `/retrospective` 実行時

**目的**: 人間が読む振り返り記録

**構造:**
```markdown
# Retrospective: {Project Name}

**Date**: {date}
**Duration**: {actual hours}
**Satisfaction**: {N}/5

## What Went Well
{成功したこと}

## Challenges & Learnings
{課題と学び}

## Time Analysis
{見積もりvs実績}

## docs/ Assessment
{docs/の評価}

## skills/ Assessment
{skills/の評価}

## Lessons for Next Time
{次回への教訓}
```

---

## グローバル知識ベース構造

### ~/.sdd-knowledge/

```
~/.sdd-knowledge/
├── config.json              # 全体設定
│
├── docs-archive/            # アーカイブ
│   ├── 2026-02-05_investigation_WebAssembly/
│   │   ├── docs/
│   │   ├── outputs/
│   │   ├── skills/
│   │   └── meta/
│   │       ├── CLAUDE.md
│   │       └── metadata.json
│   └── index.json
│
├── starters/                # スターター
│   ├── investigation-report/
│   │   ├── docs-template/
│   │   ├── skills/
│   │   └── metadata.json
│   └── ...
│
├── retrospectives/          # 振り返り
│   ├── 2026-02-05_investigation_WebAssembly.json
│   └── summary.json
│
└── skills-library/          # 汎用skills
    └── ...
```

**命名規則:**

**アーカイブディレクトリ:**
```
形式: {YYYY-MM-DD}_{category}_{project-name}/

例:
  2026-02-05_investigation_WebAssembly/
  2026-01-20_technical-proposal_API-Optimization/
```

**retrospectiveファイル:**
```
形式: {YYYY-MM-DD}_{category}_{project-name}.json

例:
  2026-02-05_investigation_WebAssembly.json
```

---

## ファイル命名ベストプラクティス

### 推奨される命名
```
✓ background.md
✓ phase-01-analysis.md
✓ comparison-table.md
✓ final-report.md

特徴:
  - 小文字
  - ハイフン区切り
  - 目的が明確
  - 拡張子適切
```

### 避けるべき命名
```
✗ Background.md（大文字始まり）
✗ phase_01_analysis.md（アンダースコア）
✗ comparisonTable.md（キャメルケース）
✗ temp123.md（意味不明）
✗ new-file.md（genericすぎる）
✗ 背景.md（非ASCII）
```

### 日本語ファイル名の扱い
```
プロジェクトディレクトリ内: 英語推奨
  理由: Git, CI/CD, 他ツールとの互換性

成果物の内容: 日本語OK
  例: final-report.md の内容は日本語で記述可能

ただし、日本語ファイル名を使う場合:
  - UTF-8エンコーディング必須
  - スペース不可（ハイフン使用）
  - 例: 最終報告書.md → final-report.md（英語推奨）
```

---

## 禁止パターン

### NG1: バージョン番号をファイル名に
```
✗ report-v1.md
✗ report-v2.md
✗ report-final.md
✗ report-final-final.md

理由: Gitでバージョン管理すべき

✓ report.md（Gitで履歴管理）
```

### NG2: 日付をファイル名に
```
✗ analysis-2026-02-05.md
✗ draft-0205.md

理由: metadata.jsonやGitのタイムスタンプで管理

✓ analysis.md（日付はmetadata.jsonに記録）
```

### NG3: 曖昧なファイル名
```
✗ temp.md
✗ new.md
✗ test.md
✗ misc.md
✗ untitled.md

理由: 目的が不明確

✓ {目的を表す具体的な名前}.md
```

### NG4: 深すぎる階層
```
✗ outputs/phase-01/data/raw/2026/february/05/file.csv

理由: 複雑すぎて管理困難

✓ outputs/phase-01/raw-data.csv
  （深くても3階層まで）
```

---

## ファイル整理のタイミング

### init-task実行時
```
作成:
  - docs/ 配下のファイル
  - skills/ 配下のディレクトリと SKILL.md
  - CLAUDE.md
  - metadata.json
```

### run-phase実行時
```
作成:
  - outputs/phase-{N}/ ディレクトリ
  - outputs/phase-{N}/.metadata.json
  - outputs/phase-{N}/ 配下の成果物

更新:
  - metadata.json（Phase status更新）
```

### finalize実行時
```
作成:
  - finalization-report.md
  - ~/.sdd-knowledge/docs-archive/ 配下にコピー

更新:
  - metadata.json（status: finalized）
  - ~/.sdd-knowledge/starters/（更新があれば）
```

### retrospective実行時
```
作成:
  - retrospective.md
  - ~/.sdd-knowledge/retrospectives/*.json

更新:
  - ~/.sdd-knowledge/retrospectives/summary.json
```

---

## クリーンアップルール

### プロジェクト完了後
```
保持:
  ✓ docs/
  ✓ skills/
  ✓ outputs/
  ✓ CLAUDE.md
  ✓ metadata.json
  ✓ finalization-report.md
  ✓ retrospective.md

削除可能:
  - 一時ファイル（あれば）
  - ログファイル（あれば）
  - キャッシュ（あれば）

アーカイブ:
  - ~/.sdd-knowledge/docs-archive/ に保存済み
  - ローカルは削除してもOK（ただし推奨は保持）
```

### 知識ベースの整理
```
定期実行（月1回程度）:
  1. docs-archive/のindex.json更新
  2. retrospectives/summary.json再集計
  3. 古いstarters/のバージョン整理
  4. 破損ファイルチェック
```

---

## トラブルシューティング

### 問題: ファイルが見つからない
```
確認事項:
  1. ファイル名の綴り（大文字小文字も）
  2. ディレクトリ階層（どこに保存したか）
  3. 拡張子（.md / .json等）

対処:
  find . -name "*{filename}*"
  → ファイルシステム全体を検索
```

### 問題: ディレクトリ構造が崩れた
```
原因:
  - 手動でファイル移動
  - コマンド実行の中断

対処:
  1. CLAUDE.mdとmetadata.jsonから正しい構造を確認
  2. 手動で再構築
  3. または init-task から再実行
```

### 問題: metadata.jsonが壊れた
```
症状:
  - JSON parse error
  - 必須フィールド欠落

対処:
  1. バックアップから復元（Gitコミット履歴）
  2. または手動で再作成（CLAUDE.md参照）
  3. 最悪の場合、新規作成して過去情報は諦める
```

---

## まとめ

ファイル構造の原則は**「一目で分かる、予測可能」**。

**ディレクトリ:**
- docs/ - 仕様
- skills/ - 手順
- outputs/ - 成果物
- ~/.sdd-knowledge/ - グローバル知識

**命名:**
- 小文字、ハイフン区切り
- 目的が明確
- バージョン番号・日付は不要

**整理:**
- 各コマンド実行時に自動作成
- 完了後はアーカイブ
- 定期的にクリーンアップ

この構造を守ることで、**プロジェクト間の移動がスムーズ**になる。
---

### eval/ - 自己評価ディレクトリ（v6）

**目的**: 固定3シナリオで自己評価し、履歴とグラフを保持

- `eval/scenarios/` : 評価シナリオ（固定）
- `eval/runs/<iteration_id>/.../score.json` : 採点結果
- `eval/history/*.json` : 履歴レコード（集計）
- `eval/summary.csv` : 時系列集計
- `eval/plots/` : 可視化（任意、matplotlib）

### templates/ - 生成テンプレート（v6）

**目的**: /init-task が docs や専門家エージェントを生成する際の土台

- `templates/team-roster.json` : task_type→specialists の辞書
- `templates/agents/*.md` : 専門家エージェントテンプレ
