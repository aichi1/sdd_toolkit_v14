# sdd_toolkit_v14

スペック駆動開発（SDD）ツールキット v14 — v13（実 stdio MCP + Agent Teams）を土台に、次の4層を追加した世代です。

1. **コンテキストエンジニアリング** — 仕様書を丸ごと渡さず、ChromaDB で関連スライスだけを注入（`mcp_servers/context_server.py`）
2. **PEV ハーネス** — Plan→Execute→Verify を LangGraph の状態機械として制度化。隔離実行（git worktree + podman）・ガードレール（hooks）・可観測性で囲う（`graph/`, `harness/`）
3. **マルチエージェント・オーケストレーション** — Builder に加え Validator/Tester/Reviewer/Security を並列展開（`agents/definitions.py`, `verify` ノード）
4. **Constitutional SDD** — 安全・非機能制約を「憲法」（原則＋強制点）として仕様に埋め込み、評価で機械的に強制（`specs/constitution.md`, `mcp_servers/constitution_server.py`）

アーキテクチャ: **LangGraph 外殻（決定論的）+ Claude Agent SDK 内側（確率的）+ SqliteSaver 状態 + interrupt() 承認ゲート + FastAPI ローカルレビュー面**。multi-agent-shogun / ntfy / Telegram は使いません。

## 使い方（他バージョンと同じ）

```bash
# 1. このフォルダを新プロジェクトとしてコピー
cp -r ~/sdd_toolkit_v14 ~/my_new_project && cd ~/my_new_project

# 2. 依存をインストール（pin 済み）
pip install -e .

# 3. Claude Code を起動し、SDD ワークフローを回す
#    /init-task "タスクの説明"   → docs/ + skills/ + 専門家エージェント生成
#    /run-phase 1               → Builder → pre-check → Validator
#    /finalize → /retrospective
```

### v14 ランタイムを直接使う

```bash
# テスト（415件）で動作確認
python3 -m pytest tests/ -q

# 承認レビュー面（localhost:8765）
python3 -m review.app

# グラフ起動（Python から）
python3 -c "
from graph.build_graph import build_graph
g = build_graph()   # state.db に永続化、interrupt で停止 → /review or CLI で resume
"
```

## ディレクトリ構成

```
├─ .claude/            # v12 由来のワークフロー（commands/skills/agents/hooks/rules）
├─ scripts/            # KB・検証スクリプト（handlers.py = KB ロジック層）
├─ templates/          # init-task 用テンプレート（intake/skills/agents/team-roster）
├─ eval/               # 7軸評価資産（rubric・aggregate・履歴ベースライン）
├─ graph/              # 外殻: TaskState(lean) / nodes / StateGraph+SqliteSaver
├─ agents/             # Agent SDK 定義（builder + 4専門家、専門家は Task 非保持）
├─ mcp_servers/        # in-process MCP: ctx(仕様スライス) / law(憲法条項)
├─ harness/            # hooks(PreToolUse guard) / sandbox(worktree+podman) /
│                      # security_checks(CWE) / eval_suite(回帰+スコア) / observability
├─ review/             # FastAPI 承認面（/review /approve /reject、副作用なし）
├─ specs/              # 配布版憲法（constitution.md）
├─ tests/              # 415テスト（E2E: spec_load〜merge 一気通貫 + D5 負のスイープ）
├─ docs/               # ツールキット文書 + v14-reference/（v14 自身の設計書）
├─ pyproject.toml      # 依存 pin（langgraph / claude-agent-sdk / chromadb / fastapi / langsmith）
└─ .mcp.json           # ctx / law の MCP 登録
```

## 実行環境の要件

| 要件 | 必須度 | 備考 |
|---|---|---|
| Python 3.10+ | 必須 | 依存は `pyproject.toml` で pin |
| git | 必須 | worktree 隔離（第4条）に使用 |
| podman (rootless) | 推奨 | コード実行の隔離。無い場合 `run_in_sandbox` は**ホスト実行せず拒否**する設計 |
| コンテナイメージ | podman 使用時 | `printf 'FROM docker.io/library/alpine:3.20\nRUN apk add --no-cache curl\n' \| podman build -t localhost/sdd-runner:latest -` |
| cgroups v2 (systemd) | 任意 | `--memory` 実強制に必要（WSL2 は `/etc/wsl.conf` に `[boot] systemd=true` + WSL 再起動） |

主要な環境変数: `SDD_BASE_REPO`（worktree の対象リポジトリ）/ `SDD_CONSTITUTION_PATH`（解決順: env → `docs/constitution.md`（プロジェクト憲法、あれば優先）→ `specs/constitution.md`（配布既定））/ `SDD_DOCS_DIR`（スライス対象、既定 `docs`）/ `SDD_OBS_STORE`（観測 JSONL）/ `SDD_RUN_REAL_BUILDER`・`SDD_RUN_REAL_VERIFY`（実 Agent SDK 呼び出しの opt-in gate）。

## 憲法（Constitutional SDD）

`specs/constitution.md` が配布版の既定憲法です（10条、各条項は**原則＋強制点**のセット）。プロジェクト固有の憲法は `/init-task` 後に `docs/constitution.md` として整備し、改正は「仕様変更として扱い、更新→再検証」の手続きを踏みます。強制点の実例は `tests/test_e2e.py::TestE2ENegativeSweep`（違反入力6種の検出）を参照。

## 実 Agent SDK モード（post-v14 で配線済み）

- **実配線済み**: `SDD_RUN_REAL_VERIFY=1` で verify の4専門家（validator/tester/reviewer/security）を Claude Agent SDK で並列実行し、`FINDING:` 行を所見化。`SDD_RUN_REAL_BUILDER=1` で build を実 Builder 実行（`.sdd/artifact_manifest.json` の `primary_artifact` を成果物とし、無ければ `artifact.txt`）。
- **実コスト計測**: 各実呼び出しの `ResultMessage.total_cost_usd`/トークンを観測ストアに `agent_call` 行として記録。`eval_node` の run 行はそれらの実合算値を残す（FR-4.2 が実値に）。
- **認証**: `ANTHROPIC_API_KEY` 未設定なら Claude Code のログイン（Pro/Max サブスク）を流用（課金は API でなくサブスク枠）。設定されていると API 従量課金になるので注意。
- **スモーク**: `python3 -m harness.smoke_real_sdk` で最小 query と総コストを表示（手動 opt-in）。
- 既定（env gate 未設定）ではオフライン stub のまま。`pytest tests/ -q` は実 API 0 で全 green（433 tests）。

## 既知の制約（誠実な開示）

- 実モードは配線済みだが、専門家プロンプト・所見品質のチューニングは今後の課題（まず配線が完了した段階）。
- LangSmith/OTel 送信は default-off の best-effort（ローカル JSONL が主シンク）。
- `review/app.py` を async 化する場合、build/verify ノードの `asyncio.run()` は実行中イベントループと衝突するため注意（P3 既知）。
- 詳細は `docs/v14-reference/`、`.steering/20260703-real-agent-sdk-wiring/`、構築記録アーカイブ `~/.sdd-knowledge/docs-archive/2026-07-02_small_implementation_sdd_toolkit_v14/` を参照。

---
Built by dogfooding: **v12 の SDD ワークフローで v14 自身を構築**（9フェーズ、D1〜D5 全 PASS、7軸 4.000 vs v6.4 3.571）。実 Agent SDK 配線は post-v14 の `/add-feature` で追加（433 tests）。
