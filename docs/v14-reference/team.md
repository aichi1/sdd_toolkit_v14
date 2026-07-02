# Team — sdd_toolkit_v14

## task_type 分類
- **task_type**: `small_implementation`（規模は大きいが、成果物はコード。カテゴリは実装系）
- **スコープ**: LangGraph 外殻 + Claude Agent SDK 内側 + in-process MCP + 隔離ハーネス + 評価/承認ゲート
- **フェーズ数**: 9（Phase 0〜8）。各 Phase = `docs/tasks.md` の 1 Phase = `/run-phase` の 1 単位
- **実行モード**: コード系フェーズ（Phase 1,2,4,6,7）は **Team mode + require plan approval**。ドキュメント寄り（Phase 5 の憲法配布版）は Solo 可

## 常設エージェント（汎用）
| エージェント | 役割 | 定義 |
|---|---|---|
| planner | カテゴリ選定・WBS・方針 | `.claude/agents/planner.md` |
| builder | SKILL.md/spec に忠実な生成 | `.claude/agents/builder.md` |
| validator | 受入基準・憲法照合の検証（読取専用） | `.claude/agents/validator.md` |
| researcher | 過去スターター・教訓の再利用探索 | `.claude/agents/researcher.md` |

## 召喚した専門家（`.claude/agents/generated/`）
`small_implementation` ロスター（`templates/team-roster.json`）から選定。v14 仕様（`docs/requirements.md` FR-3.2）の verify 並列エージェント（Validator + Tester + Reviewer + Security）に対応させる。

| 専門家 | v14 対応ロール | いつ呼ぶか | 何のために |
|---|---|---|---|
| `sdd-software-architect` | reviewer | Phase 1,2,6（設計・実装時） | LangGraph 状態機械・ノード境界・lean state（第2条/第9条）の整合レビュー |
| `sdd-qa-test-engineer` | tester | 全コードフェーズのテスト作成時 | ノード単体（状態入出力）・統合（spec_load〜merge）・負のテスト網羅 |
| `sdd-security-reviewer` | security | Phase 4,5（hooks/sandbox/憲法強制後） | 禁止操作拒否・egress 遮断・CWE/OWASP 走査（第4/5/10条） |
| `sdd-doc-editor` | doc editor | 各 Phase の README/metadata 作成時 | 読みやすさ・用語統一・トレーサビリティ記述の整備 |

## 呼び出しタイミング（Phase 別）
- **Phase 0**: software_architect（ディレクトリ構成・依存の妥当性）
- **Phase 1**: software_architect（lean state / interrupt 副作用配置 = 第2/3条）, qa_test_engineer（resume 再開テスト）
- **Phase 2**: software_architect（worktree 実行境界）, security_reviewer（Task ツール除外の確認）
- **Phase 3**: software_architect（注入順序固定 = cache ヒット条件）
- **Phase 4**: security_reviewer（hooks 拒否・sandbox egress 遮断 = 第4/5条）, qa_test_engineer（負のテスト）
- **Phase 5**: security_reviewer（CWE/OWASP 検査項目 = 第10条）, doc_editor（配布版憲法の記述）
- **Phase 6**: qa_test_engineer（退行入力で条件エッジ発火）, software_architect（観測配線）
- **Phase 7**: software_architect（interrupt ペイロード ↔ UI 整合）
- **Phase 8**: 全専門家（E2E・退行・憲法違反入力検出）

## メモ
- 専門エージェントは読取 + 限定ツールのみ。`Task`（Agent）を持たない＝再帰しない（FR-3.3 / `docs/conventions.md`）。
- 所見は reducer（`operator.add`）でマージされる前提。他エージェントの状態に依存しない出力を返す。
