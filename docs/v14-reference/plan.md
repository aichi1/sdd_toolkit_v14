# Plan / Architecture — sdd_toolkit_v14

## 1. ターゲットアーキテクチャ

1 タスクは LangGraph の状態機械として実行される。ノードは上から下へ:

```
spec_load → assemble_context → build → verify → eval → review(interrupt) → merge/END
                                  ↑___________________________|
                                   fail / reject → 再build (attempt 上限で打切り)
```

- **外殻(決定論的)**: LangGraph `StateGraph` + `SqliteSaver` チェックポインター。
  ジョブのライフサイクル、条件分岐、リトライ、承認ゲートを担う。
- **内側(確率的)**: 各ノードの実処理は Claude Agent SDK のサブエージェント。
- **道具**: ChromaDB / 憲法取得を in-process MCP として提供。
- **基盤**: worktree + podman + cgroups(隔離)、LangSmith/OTel(観測)。

## 2. 技術スタックと選定理由

| 層 | 技術 | 理由 |
|---|---|---|
| 外殻オーケストレーション | LangGraph + SqliteSaver | 明示的な状態機械・HITL・チェックポイント。既存の LangGraph 資産と直結 |
| 承認ゲート | LangGraph `interrupt()` + FastAPI | shogun/ntfy 不要で単一プロセス完結。副作用を承認後に隔離できる |
| 各エージェント | Claude Agent SDK | Claude Code と同じループ・hooks・subagents・MCP を再利用。自作ハーネス不要 |
| コンテキスト | ChromaDB(in-process MCP) | 仕様スライスの選択注入。既存の埋め込み資産を再利用 |
| 隔離 | git worktree + podman rootless + cgroups v2 | 物理分離 + サンドボックス + リソース統治の三点 |
| 状態 | SQLite | 単一プロセスで十分。lean state 前提 |
| 観測 | LangSmith(第一候補)/ OTel | run トレース、コスト・トークン。LangChain 資産と直結 |

## 3. ディレクトリ構成

```
sdd_toolkit_v14/
├─ docs/                      # 本 pre-docs(spec/plan/tasks/constitution)
├─ specs/
│  ├─ constitution.md         # 配布用憲法(01 のサブセットを生成)
│  └─ <feature>/spec.md
├─ graph/                     # 外殻
│  ├─ state.py                # TaskState(lean)
│  ├─ nodes.py                # 各ノード関数
│  └─ build_graph.py          # StateGraph + SqliteSaver + 条件エッジ
├─ agents/
│  └─ definitions.py          # Agent SDK の agents={...}
├─ mcp_servers/               # ※ PyPI の `mcp`(claude-agent-sdk 依存)との名前衝突回避のため mcp/ から改名
│  ├─ context_server.py       # ChromaDB retrieval(仕様スライス)
│  └─ constitution_server.py  # 憲法条項取得・違反チェック
├─ harness/
│  ├─ hooks.py                # PreToolUse/PostToolUse/SubagentStop
│  ├─ sandbox.py              # worktree 切出し + podman 実行
│  └─ eval_suite.py           # 回帰検出・スコアリング
├─ review/
│  └─ app.py                  # FastAPI ローカルレビュー面
├─ scripts/mcp_server/        # v12 由来。handlers.py を再利用
│  └─ handlers.py             # (既存)KB ロジック層
├─ .claude/agents/            # v12 由来。builder.md/validator.md を流用・拡張
├─ eval/                      # v12 由来。7 軸評価を eval_suite から呼ぶ
├─ .mcp.json                  # MCP 自動検出(context/constitution/kb を登録)
└─ state.db                   # SqliteSaver + ジョブ状態
```

## 4. 状態スキーマ(lean)

本文を載せず、パスと ID のみ(第2条)。

```python
from typing import TypedDict, Annotated
import operator

class TaskState(TypedDict):
    task_id: str
    spec_path: str                 # 本文でなくパス
    constitution_digest: str       # 憲法の要点(短い)
    context_slice_ids: list[str]   # ChromaDB の該当チャンク ID
    worktree_path: str             # Builder の作業ツリー
    build_artifact_ref: str        # diff/PR のパス
    verify_findings: Annotated[list[str], reduce_findings]  # ラウンドリセット対応 reducer（Phase 4 / S1 解決）
    eval_score: float | None
    attempt: int                   # 再build 回数(上限で打切り)
    decision: str | None
```

`Annotated[..., reduce_findings]` の reducer が、`verify` の並列サブエージェント所見を
上書きなしにマージする鍵。**Phase 4 で `operator.add` から `reduce_findings` に変更（S1 解決）**：
`reduce_findings(old, None)→[]`（build がラウンド開始でリセット）、`reduce_findings(old, list)→old+list`
（同一ラウンド内は並列 append）。これにより reject→再build 時に前ラウンドの所見が累積しない。

## 5. MCP サーバ(既存様式の踏襲)

`context_server` / `constitution_server` は、SDK の `create_sdk_mcp_server` 様式に従う薄いファサードにする(第6条)。
**既存責務を扱うサーバは `handlers.py` を import して再利用する**が、`context_server` の spec-slicing は
**ChromaDB × `docs/*.md`（現プロジェクト仕様）という新規責務**であり handlers(BM25×KB) とは別コーパスのため、
handlers の import は不要（第6条 改正済み、下記擬似コードの `kb_retrieve` は当初想定で、実装は ChromaDB retrieval）。

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool("spec_slice", "タスクに関連する仕様スライスを返す", {"task_id": str, "query": str, "k": int})
async def spec_slice(args):
    ids, chunks = chroma_retrieve(args["query"], k=args["k"])  # docs/*.md の ChromaDB retrieval（ローカル決定論埋め込み）
    return {"content": [{"type": "text", "text": render_ordered(chunks)}]}

context_server = create_sdk_mcp_server(name="ctx", version="1.0.0", tools=[spec_slice])
```

注入順序は「不変ブロック(憲法)を先頭 → タスク固有スライスを後段」で固定(FR-2.2)。

## 6. エージェント定義

```python
options = ClaudeAgentOptions(
    agents={
        "builder":  {"description": "spec 準拠の実装", "prompt": BUILDER_SYS},
        "reviewer": {"description": "アーキ整合レビュー", "tools": ["Read", "Grep"]},
        "security": {"description": "CWE/OWASP 走査",    "tools": ["Read", "Grep"]},
        "tester":   {"description": "テスト実行と結果報告", "tools": ["Read", "Bash"]},
    },
    mcp_servers={"ctx": context_server, "law": constitution_server},
    hooks={"PreToolUse": [HookMatcher(matcher="Bash", hooks=[guard])]},
    allowed_tools=["Read", "Grep", "Bash", "Task"],  # Write/Edit は外す
)
```

- 専門エージェントの許可ツールに `Task` を入れない(サブエージェントは再帰しない)。
- 親権限は継承されないため、`PreToolUse` フックで安全ツールを自動承認して承認氾濫を防ぐ。

## 7. ガードレールと隔離

- **ソフト(hooks)**: `PreToolUse` が `rm -rf` / `git push` / `.env` 読取り等を拒否。
  hooks は他のどの権限チェックより先に走るので、機密読取りブロックと監査ログに最適。
- **ハード(podman/cgroups)**: テスト実行は podman rootless(読取専用マウント、egress 遮断)。
  cgroups v2 で各実行体に `MemoryMax` を割り当て、暴走テストによる WSL2 全体 OOM を防ぐ。

## 8. 承認ゲート(ntfy/Telegram の代替)

```python
def review(state: TaskState):
    decision = interrupt({                    # ここで停止・状態保存
        "kind": "merge_approval",
        "diff_ref": state["build_artifact_ref"],
        "findings": state["verify_findings"],
        "eval_score": state["eval_score"],
    })
    if decision["action"] == "approve":       # ← 再開後にしか走らない
        merge_worktree(state["worktree_path"]) # 副作用は承認後だけ(第3条)
        return Command(goto=END, update={"decision": "approved"})
    return Command(goto="build", update={"decision": "rejected",
                                         "attempt": state["attempt"] + 1})
```

レビュー面(`review/app.py`)は FastAPI で薄く作る。`/review` が interrupt ペイロード
(diff と所見)を表示し、承認ボタンが `graph.invoke(Command(resume=...), config)` を叩く。
`interrupt_before` ではなく `interrupt()` を使うのは、構造化ペイロードを UI に出せるため。

## 9. 評価と可観測性

`eval` ノードは `verify_findings` に加え、再実行可能な `eval_suite`(pytest 的な回帰検出
\+ スコア)を回して合否を条件エッジで決める。可観測性は SDK が素で助けになり、
`ResultMessage` の `total_cost_usd` とトークン(サブエージェントはモデル別内訳)を
LangSmith/OTel に流す。回帰ベースラインは `eval/` の 7 軸資産を再利用する。

## 10. v12/v13 資産の再利用マッピング

| v12/v13 資産 | v14 での用途 |
|---|---|
| `scripts/mcp_server/handlers.py` | `context_server` / `constitution_server` が import するロジック層 |
| FastMCP stdio 様式・`.mcp.json` | 新 MCP サーバの実装・登録様式をそのまま踏襲 |
| `.claude/agents/builder.md` / `validator.md` | Agent SDK の `builder` / `reviewer` 定義の下敷き |
| Builder/Validator の Quality Criteria | 各ノードの受入基準(`verify` の照合項目) |
| `eval/`(7 軸レーダー) | `eval_suite` から呼ぶ回帰ベースライン |
| `outputs/phase-{N}/` + `.metadata.json` | LangGraph の成果物参照(`build_artifact_ref`)の出力先 |
| `templates/team-roster.json` | 専門エージェント選定(`agents={}`)の初期ロスター |
| Team mode / hooks(TaskCompleted, TeammateIdle) | ハーネスの hooks 設計の参考。gate は `Status: FAIL` キーで判定 |

## 11. 主要な設計判断とトレードオフ

- **LangGraph vs Temporal**: 初版は LangGraph + SqliteSaver。多日待ちの HITL と
  完全なクラッシュ耐性が必要になった時点で Temporal を外殻に追加検討(N3)。
- **状態の薄さ vs 利便性**: 本文を状態に載せれば実装は楽だが第2条に反する。パス参照を徹底する。
- **interrupt() vs interrupt_before**: 構造化ペイロードでレビュー UI を作るため `interrupt()` を採用。
