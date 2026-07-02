# Tech Stack — sdd_toolkit_v14

`docs/plan.md` セクション2の選定を実装者向けに一覧化したもの。詳細な理由は `docs/plan.md` を参照。

## 言語・ランタイム
- Python 3.10+（型ヒント必須、I/O は async 基本 — `docs/conventions.md`）
- 実行環境: WSL2/Ubuntu 単一プロセス。クラウド API に暗黙依存しない（N4）。

## 依存（`pyproject.toml` で pin）
| 層 | パッケージ | 用途 |
|---|---|---|
| 外殻オーケストレーション | `langgraph` | StateGraph・条件エッジ・HITL |
| チェックポイント | `langgraph-checkpoint-sqlite` | SqliteSaver（`state.db`） |
| 各エージェント | `claude-agent-sdk` | Builder/専門エージェント・hooks・in-process MCP |
| コンテキスト検索 | `chromadb` | 仕様スライスの retrieval |
| レビュー面 | `fastapi`, `uvicorn` | 承認ゲート UI（`/review`） |
| 観測 | `langsmith`（第一候補）/ OTel | run トレース・コスト・トークン |

## 隔離・基盤（システム依存、pip 外）
- `git worktree` — エージェント作業の物理分離
- `podman`（rootless）— テスト/コード実行のサンドボックス（読取専用マウント、egress 遮断）
- `cgroups v2` — 各実行体への `MemoryMax` 割当（WSL2 全体 OOM 防止）
- `SQLite` — SqliteSaver + ジョブ状態

## 再利用資産（新規追加しない — 第6条）
| 資産 | 所在 | v14 での用途 |
|---|---|---|
| KB ロジック層 | `scripts/mcp_server/handlers.py` | context/constitution サーバが import |
| FastMCP stdio 様式 | `scripts/mcp_server/`, `.mcp.json` | 新 MCP サーバの実装・登録様式 |
| Builder/Validator 定義 | `.claude/agents/builder.md`, `validator.md` | Agent SDK の system prompt 下敷き |
| 7 軸評価 | `eval/` | `eval_suite` が呼ぶ回帰ベースライン |
| 専門家ロスター | `templates/team-roster.json` | `agents={}` の初期選定 |

## 明示的に使わないもの（`docs/conventions.md` やらないことリスト）
- multi-agent-shogun（オーケストレーションは LangGraph 自作 — N1）
- ntfy / Telegram（承認は `interrupt()` + ローカル面のみ — N2）
- Temporal（初版は SqliteSaver で十分 — N3）
