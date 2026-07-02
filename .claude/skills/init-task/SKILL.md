# init-task（v6） - SDDプロジェクト初期化

## 目的
- タスクを分類し、必要な **docs / skills / agents** の最小セットを用意する
- 汎用エージェント（planner / builder / validator / researcher）は維持しつつ、タスクに合わせた **専門家エージェント** を都度召喚（生成）する
- 後続の `/run-phase` が迷いなく走る状態を作る
- 過去プロジェクトの学び（利用可能な場合）を活用する

## 前提条件
- `~/.sdd-knowledge/` のディレクトリ構造が存在する
- ユーザーがタスク記述を提供している

## 入力
- タスク記述（自由形式テキスト、または構造化アウトライン）
- 任意：カテゴリのヒント（例：「research_report」「small_implementation」「internal_proposal」）

## 出力
- 仕様ファイルを含む `./docs/` ディレクトリ（`_manifest.json` 含む）
- `./docs/team.md`（チーム編成・専門家エージェントの役割とタイミング）
- フェーズ別の `SKILL.md` を含む `./skills/` ディレクトリ
- `.claude/agents/generated/` に専門家エージェント
- `./CLAUDE.md`（プロジェクト仕様）
- `./metadata.json`（プロジェクトメタデータ）

## ワークフロー

### フェーズ0：スターター検出

**ステップ0.0：アクティブコンテキスト生成**
1. タスク記述が提供されたら、即座にアクティブコンテキストを生成する:
   ```bash
   python3 scripts/generate_context.py "{task_description}"
   ```
2. `~/.sdd-knowledge/active-context.md` が生成される
3. アクティブコンテキストの内容をユーザーに要約提示:
   ```
   過去の知識ベースから以下の関連情報が見つかりました:
     - [skill] {name} (relevance: X.XX)
     - [agent] {name} (relevance: X.XX)

   過去のプロジェクトからの教訓:
     - {lesson1}
     - {lesson2}

   これらを参考にプロジェクトを設計しますか？ [Y/n]
   ```
4. ユーザーが承認した場合:
   - 関連コンポーネントを SKILL.md テンプレートの参考として使用
   - 教訓を Quality Criteria や Common Pitfalls に反映

**ステップ0.1：スターター検索**
1. `~/.sdd-knowledge/starters/` を確認し、関連テンプレートを探す
2. タスク記述を分析してカテゴリを判定する
3. 判断：
   - 一致するスターターが存在する（確信度 > 0.7）の場合：
     - スターター構造を現在のプロジェクトへコピーする
     - フェーズ2（カスタマイズ）へジャンプする
   - 一致するスターターがない場合：
     - フェーズ1（フルセットアップ）へ進む

### フェーズ1：フルセットアップ（スターターが利用できない場合）

**ステップ1.1：タスク分類（task_type）& スコープ分析**
ユーザーのタスクを、次のいずれかに分類する（不明なら最も近いもの）：
- `research_report`
- `small_implementation`
- `internal_proposal`

さらに：
- 主要な成果物（deliverables）を特定
- フェーズ数を決定（通常 3〜5）
- ドメイン固有の要件を抽出

分類結果は `docs/team.md` に記録する。

**ステップ1.2：docs/ 構造設計**
タスクカテゴリに基づいて仕様ファイルを作成します。
全カテゴリ共通で以下を必ず含める：
- `docs/requirements.md`（目的、スコープ、非目的、制約、成功条件）
- `docs/plan.md`（Phase構成、成果物、進め方）
- `docs/team.md`（チーム編成と役割）

加えて、カテゴリ固有のファイルを追加：

investigation-report の場合：
```text
docs/
├── background.md      # 背景・動機
├── scope.md           # 範囲・目的
├── sources.md         # 情報ソース一覧
├── audience.md        # 想定読者とニーズ
└── format.md          # 出力フォーマット要件
```

technical-proposal の場合：
```text
docs/
├── problem.md          # 課題定義
├── requirements.md     # 機能/非機能要件
├── constraints.md      # 技術/ビジネス制約
├── stakeholders.md     # 意思決定者・レビューア
└── success-criteria.md # 受け入れ条件（成功基準）
```

small-implementation の場合：
```text
docs/
├── requirements.md     # 機能要件・非機能要件（共通で作成済み）
├── tech-stack.md       # 使用言語・フレームワーク・依存関係
├── io-spec.md          # 入出力仕様（入力形式、出力形式、エラー時の振る舞い）
└── constraints.md      # 技術的制約（対応OS、実行環境、外部依存制限）
```

network-design の場合：
```text
docs/
├── requirements.md    # ネットワーク要件
├── topology.md        # トポロジの希望
├── constraints.md     # 予算・納期・既存インフラ
├── security.md        # セキュリティ要件
└── scalability.md     # 成長（拡張）見込み
```

**ステップ1.3：構造化仕様収集（インテーク → 深掘り）**
`templates/intake/` のカテゴリ別インテークテンプレートを使用し、初回で基本情報を一括収集した上で、回答に応じて必要なだけ深掘り質問を行う。

| task_type | インテークテンプレート |
|-----------|----------------------|
| research_report | `templates/intake/research_report.md` |
| small_implementation | `templates/intake/small_implementation.md` |
| internal_proposal | `templates/intake/internal_proposal.md` |

**手順：**

**ラウンド1（インテーク）：基本情報の一括収集**
1. カテゴリに対応するインテークテンプレートを読む
2. テンプレートの質問セットを **1回のメッセージで** ユーザーに提示する
3. ユーザーの一括回答を受け取る

**ラウンド2以降（深掘り）：回答に応じた適応的質問**
4. ラウンド1の回答を分析し、以下の観点で深掘りが必要な箇所を特定する：
   - 曖昧な回答（「適切に」「いい感じに」等 → 具体化を求める）
   - 暗黙の要件（回答から推測される未言及の前提 → 確認する）
   - 矛盾する情報（スコープと制約の不整合等 → 解消する）
   - 重要だが薄い領域（成功条件が1行のみ等 → 掘り下げる）
5. 深掘り質問を提示し、回答を得る
6. docs/ に十分な情報が揃ったと判断できるまで、必要に応じて繰り返す

**ラウンド最終：docs/ 一括生成**
7. テンプレートの「回答→docs/ マッピング」に従い、全 docs/ ファイルを一括生成する
8. 生成した docs/ の要約をユーザーに提示し、認識齟齬がないか確認する

**効率化ポイント**：
- 初回はインテークテンプレートで全体像を掴む（旧方式のファイルごと個別質問は非効率）
- 深掘りは回答内容に応じて適応的に行う（機械的に全項目を聞き直さない）
- 任意項目が未回答の場合はデフォルト値で仮置きし、確認を求める（テンプレート記載のデフォルト値参照）
- 対応するインテークテンプレートがないカテゴリの場合は、最も近いテンプレートを参考にしつつ、8-10問に絞って初回質問する

**ステップ1.4：フェーズ分解**
成果物に基づいてフェーズを設計します：
- 各フェーズ＝主要成果物 1つ
- フェーズは順序性を持つ（後続フェーズは前のフェーズに依存して構築される）
- 典型構造：
  - フェーズ1：調査／分析
  - フェーズ2：設計／構造化
  - フェーズ3：詳細コンテンツ作成
  - フェーズ4：レビュー／磨き込み（任意）

**ステップ1.5：skills/ 作成**
各フェーズについて `skills/phase-{N}/SKILL.md` を作成します。

**重要：カテゴリ別テンプレートを使用すること。**
`templates/skills/` にカテゴリ別のテンプレートが用意されています。
必ず task_type に対応するテンプレートをベースに SKILL.md を作成してください：

| task_type | テンプレート |
|-----------|-------------|
| research_report | `templates/skills/research_report.md` |
| small_implementation | `templates/skills/small_implementation.md` |
| internal_proposal | `templates/skills/internal_proposal.md` |

テンプレートには以下が含まれています：
- **必須セクション構成**（成果物に含めるべきセクションの順序と内容）
- **Quality Criteria**（チェックリスト項目に対応する品質基準）
- **Procedure**（専門家エージェントの呼び出しタイミングを含む具体的手順）
- **Common Pitfalls**（カテゴリ固有のよくある問題）
- **Examples**（具体的な記述例）

テンプレートのプレースホルダー `{...}` を、実際のプロジェクト情報に置換してください。
docs/ の内容に応じて手順の追加・調整は可能ですが、必須セクション構成と Quality Criteria は削除しないでください。

対応するテンプレートがない task_type の場合は、以下の汎用テンプレートを使用：
```markdown
# Phase {N}: {Phase Name}

## Objective
{このフェーズが生み出すものの明確な記述}

## Input Requirements
{必要な docs/ ファイルと、前フェーズの出力}

## Output Specification
{成果物のフォーマットと内容の詳細}

## Quality Criteria
{出力が要件を満たすことを検証する方法}

## Procedure
1. {手順をステップバイステップで}
2. {ツール、フォーマット、構造を具体的に}
3. {検証チェックポイントを含める}

## Common Pitfalls
{過去のふりかえりがあればそれを踏まえ、避けるべき既知の落とし穴}

## Examples
{該当する場合、参照例やテンプレート}
```



### docs/_manifest.json を作成する（自動検証用）

`/init-task` の最後に、選んだカテゴリに応じた **必須ファイル一覧** を `docs/_manifest.json` に保存します。

- 例:
```json
{
  "category": "technical-proposal",
  "required_files": [
    "problem.md",
    "requirements.md",
    "constraints.md",
    "stakeholders.md",
    "success-criteria.md"
  ]
}
```

この manifest は、hooks（`check-docs-exist.py`）が「仕様が揃っているか」を過剰な誤警告なしでチェックするために使います。

### ステップ1.6：専門家エージェントを召喚（generated agents）
`templates/team-roster.json` を読み、task_type に対応する specialists を `.claude/agents/generated/` に生成する。

- 生成元テンプレ：`templates/agents/<specialist_key>.md`
- 生成先：`.claude/agents/generated/<specialist_key>.md`
- 生成時に、YAML frontmatter の description に「今回タスクの要点」を1行追記して良い
- 既に同名がある場合は上書きせず、差分提案として提示

生成後、`docs/team.md` に「いつ/何のために呼ぶか」も明記する（例：Phase 1でレビュー、Phase 2で監査など）。

### フェーズ2：カスタマイズ（スターターを利用する場合）

**ステップ2.1：スターター適用**
- コピーしたスターター構造をレビューする
- プレースホルダー（例：`{project_name}`、`{target_audience}`）を特定する
- プレースホルダーを埋めるために必要な情報だけを質問する

**ステップ2.2：差分質問（Delta Questions）**
- スターターの `docs/` と現在タスク要件を比較する
- スターターでカバーされていない固有点について質問する
- 本当に必要な場合にのみ、新しい `docs/` ファイルを追加する

**ステップ2.3：フェーズ調整**
- スターターのフェーズ構造をレビューする
- フェーズ数と成果物が現在タスクに合っていることを確認する
- 必要に応じて `skills/` を調整する（成熟したスターターでは稀）

### フェーズ3：仕上げ（両パス共通）

**ステップ3.1：CLAUDE.md の作成**
```markdown
# {Project Name}

## Metadata
- Category: {category}
- Start Date: {date}
- Estimated Duration: {hours}
- Phase Count: {N}

## Objective
{1段落の要約}

## Deliverables
| Phase | Deliverable | Format | Estimated Time |
|-------|-------------|--------|----------------|
| 1     | {name}      | {fmt}  | {hours}        |
| ...   | ...         | ...    | ...            |

## Specification Files
- docs/background.md - {purpose}
- docs/scope.md - {purpose}
- ...

## Skills Structure
- skills/phase-01/SKILL.md - {what it does}
- skills/phase-02/SKILL.md - {what it does}
- ...

## Next Steps
1. docs/ の網羅性をレビューする
2. Phase 1 を開始するには `/run-phase 1` を実行する
3. フル自動実行は `/run-phase all` を使う
```

**ステップ3.2：metadata.json の作成**
```json
{
  "project_name": "{name}",
  "category": "{category}",
  "created_at": "{ISO timestamp}",
  "phase_count": {N},
  "starter_used": {boolean},
  "starter_version": "{version if applicable}",
  "estimated_hours": {hours},
  "status": "initialized"
}
```

**ステップ3.3：確認チェックリスト**
ユーザーに提示：
```text
✓ docs/ 作成: {N} files
✓ skills/ 作成: {N} phases
✓ CLAUDE.md 作成済み
✓ metadata.json 作成済み

Phase 1 に進みますか？
Commands:
  /run-phase 1      - Phase 1 のみ実行
  /run-phase all    - 全フェーズを実行
  /run-phase 1-3    - Phase 1〜3 を実行
```

## 品質ゲート（Quality Gates）

init-task を完了する前に：
- [ ] すべての成果物に対応するフェーズがある
- [ ] すべてのフェーズに明確な入力要件がある
- [ ] docs/ ファイルが簡潔かつ十分である（lorem ipsum がない）
- [ ] skills/ の SKILL.md に実行可能な手順がある
- [ ] CLAUDE.md がプロジェクト構造を正確に反映している

## 過去の学びとの統合

**このカテゴリに対するふりかえりが存在する場合：**
1. 同カテゴリの `~/.sdd-knowledge/retrospectives/*.json` を読む
2. よく不足する `docs/` ファイルを抽出する
3. それらについて前もって積極的に質問する
4. `skills/` の SKILL.md に共通の落とし穴（pitfalls）を含める

**レッスン（lessons）が利用可能な場合：**
1. 内部的に `/lessons {category}` を実行する
2. レッスンを `docs/` 構造に適用する
3. ユーザーにレッスンを言及する：
   「過去プロジェクトでは、X も仕様化しておくと良いことが分かっています」

## 出力フォーマット（最後のメッセージ）
ユーザーに以下を案内する：
- task_type
- 生成/更新したファイル一覧
- 召喚した専門家一覧（役割とタイミング）
- 次に実行するコマンド（例：`/run-phase 1`）

案内の順序：
1. docs/ をざっと確認（特に requirements と team）
2. `/run-phase 1` を実行
3. 必要なら `/update-docs` で修正
4. 完了時に `/finalize`

## 対話例

```text
User: Create a technical investigation report for evaluating WebAssembly frameworks
```
