# Tasks / Phases — sdd_toolkit_v14

各 Phase を v12 の 1 タスクとして扱い、`/run-phase` を Phase 0 から順に回す。
成果物は `outputs/phase-{N}/` に出力する。**同一 Phase 内の各タスクは互いに素なファイル集合**
を持つ(Team mode で二つのteammateが同じファイルを編集しないため)。
各タスクは「成果物 / 受入基準(AC)/ 依存」を持つ。AC は `02_spec.md` の FR に対応させている。

依存順の要点: 外殻(Phase 1)→ エージェント(Phase 2)→ コンテキスト(Phase 3)→
ハーネス(Phase 4)→ 憲法強制(Phase 5)→ 評価・観測(Phase 6)→ レビュー面(Phase 7)。
Phase 1 で最小ループを一周させ、以降はノード追加で積む。

---

## Phase 0 — Scaffold & baseline

- **T0.1 リポジトリ雛形**
  - 成果物: `03_plan.md` のディレクトリ構成、`pyproject.toml`(依存: `langgraph`, `langgraph-checkpoint-sqlite`, `claude-agent-sdk`, `chromadb`, `fastapi`, `uvicorn`, `langsmith`)
  - AC: 依存が pin され、`pip install` が通る。Python 3.10+。
  - 依存: なし
- **T0.2 v13 資産の取り込み**
  - 成果物: `scripts/mcp_server/handlers.py`、`.claude/agents/*`、`eval/`、`templates/team-roster.json` を配置し、パスを実環境に合わせる
  - AC: `handlers.py` が import 可能で、既存 KB ツールが動く。
  - 依存: T0.1

## Phase 1 — 最小グラフ(外殻)

目標: `spec_load → build → review(interrupt) → merge` が動き、**承認後だけ merge** される。

- **T1.1 状態スキーマ** — `graph/state.py`
  - 成果物: `TaskState`(`03_plan.md` の定義)
  - AC: 本文フィールドを持たない(第2条)。reducer 付き `verify_findings` を含む。
  - 依存: T0.1
- **T1.2 グラフ骨格** — `graph/build_graph.py`
  - 成果物: `StateGraph` + `SqliteSaver` コンパイル、`spec_load`/`build`(スタブ)/`review`/`merge` の最小ノードと条件エッジ
  - AC: FR-5.1 — 同一 `thread_id` で `Command(resume=...)` により再開できる。チェックポイントが `state.db` に残る。
  - 依存: T1.1
- **T1.3 review ノードと CLI resume** — `graph/nodes.py`(review 部)
  - 成果物: `interrupt()` を用いた `review`、CLI からの承認/却下 resume
  - AC: FR-5.3 — reject で merge されない。approve でのみ `merge_worktree` が呼ばれる(第3条)。
  - 依存: T1.2

> Phase 1 完了時点で「最小ループが動き、承認ゲートが機能する」ことを `/eval` 前に手動確認する(D2)。

## Phase 2 — エージェント(内側)

- **T2.1 エージェント定義** — `agents/definitions.py`
  - 成果物: `builder` の `ClaudeAgentOptions`、`.claude/agents/builder.md` を下敷きにした system prompt
  - AC: FR-3.1 — `build` ノードが Builder を **worktree 内**で実行し、ホスト作業ツリーを変更しない。
  - 依存: T1.2, Phase 4 の sandbox(worktree 切出し)に部分依存 → T4.2 を先行させるか、worktree を仮実装
- **T2.2 build ノード実装** — `graph/nodes.py`(build 部)
  - 成果物: スタブを実 Builder 呼び出しに置換、`build_artifact_ref` を状態へ
  - AC: 生成物が `outputs/phase-{N}/` 相当のパスに出力され、`build_artifact_ref` が参照する。
  - 依存: T2.1

## Phase 3 — コンテキストエンジニアリング

- **T3.1 context MCP** — `mcp_servers/context_server.py`
  - 成果物: ChromaDB retrieval（`docs/*.md`、ローカル決定論埋め込み）を `@tool`/`create_sdk_mcp_server` で in-process 公開。handlers の KB ロジックは再実装しない（別責務のため import 不要 — 第6条 改正済み）
  - AC: FR-2.1 — 返却チャンク数が仕様全体より小さい。`initialize`→`tools/list` で登録確認。
  - 依存: T0.2
- **T3.2 assemble_context ノード + 順序固定** — `graph/nodes.py`(context 部)
  - 成果物: `context_slice_ids` を状態へ、注入順序を「憲法先頭 → タスク固有後段」で固定
  - AC: FR-2.2 — 同一入力 2 回で先頭ブロックが一致(cache ヒット条件)。
  - 依存: T3.1, T1.1

## Phase 4 — ハーネス(隔離・並列・ガード)

- **T4.1 hooks** — `harness/hooks.py`
  - 成果物: `PreToolUse` guard(禁止操作拒否)、監査ログ、`SubagentStop`
  - AC: 第5条 — `rm -rf`/`git push`/`.env` 読取りが拒否される。
  - 依存: T2.1
- **T4.2 sandbox** — `harness/sandbox.py`
  - 成果物: worktree 切出し、podman rootless 実行(読取専用マウント、egress 遮断)、cgroups `MemoryMax`
  - AC: NFR-3 — コード実行が worktree+podman 内、egress 既定遮断。ホスト直接実行パスがない。
  - 依存: T0.1
- **T4.3 verify ノード(並列専門エージェント)** — `graph/nodes.py`(verify 部)
  - 成果物: Validator + Tester + Reviewer + Security の並列展開、`verify_findings` マージ
  - AC: FR-3.2 / FR-3.3 — 並列で所見が上書きされない。専門エージェントが `Task` を持たない。
  - 依存: T2.1, T4.1, T4.2

## Phase 5 — Constitutional 強制

- **T5.1 憲法配布版とサーバ** — `specs/constitution.md`, `mcp_servers/constitution_server.py`
  - 成果物: `01_constitution.md` からビルド専用記述を除いた配布版、条項取得 MCP
  - AC: FR-1.2 — 条項一覧/個別取得ツールが登録される。`spec_load` が `constitution_digest` を載せる(FR-1.1)。
  - 依存: T0.2, T1.2
- **T5.2 security 検査の接続**
  - 成果物: security サブエージェントと `eval_suite` の CWE/OWASP 検査項目
  - AC: 第10条 — 既知脆弱性クラスの検査が存在し、意図的な脆弱入力で検出される。
  - 依存: T4.3, Phase 6(eval_suite)と相互依存 → T6.1 と並走

## Phase 6 — 評価ハーネス + 可観測性

- **T6.1 eval_suite** — `harness/eval_suite.py`
  - 成果物: 回帰検出 + スコア、`eval/` の 7 軸を呼ぶ
  - AC: FR-4.1 — 退行入力で `build` への条件エッジが発火。
  - 依存: T4.3
- **T6.2 eval ノード + 条件エッジ** — `graph/nodes.py`(eval 部), `build_graph.py`
  - 成果物: `eval` ノード、pass→review / fail→build の分岐、attempt 上限
  - AC: `eval_score` 閾値で分岐。`attempt` 上限で打切り。
  - 依存: T6.1, T1.2
- **T6.3 観測** — トレース配線
  - 成果物: LangSmith/OTel への run トレース、`total_cost_usd`・トークン保存
  - AC: FR-4.2 — run ごとにコスト・トークンが残る。
  - 依存: T2.2

## Phase 7 — レビュー面(FastAPI)

- **T7.1 レビュー UI** — `review/app.py`
  - 成果物: `/review`(diff・所見・スコア表示)、承認/却下ボタンが `Command(resume=...)` を送る
  - AC: FR-5.2 — ntfy/Telegram を介さずローカルで承認でき、CLI resume も併存。
  - 依存: T1.3

## Phase 8 — 統合・退行確認・finalize

- **T8.1 エンドツーエンド**
  - 成果物: 実タスク 1 件を spec_load〜merge まで通す統合テスト
  - AC: D1〜D3 — 全 FR が AC を満たし、承認後だけ merge。
  - 依存: 全 Phase
- **T8.2 ベースライン比較 → finalize**
  - 成果物: `/eval` で v13 との 7 軸比較、`/finalize`
  - AC: D4 — 退行なし(同等以上)。D5 — 憲法違反入力が検出される。
  - 依存: T8.1

---

## 実行メモ

- コード系フェーズ(Phase 1,2,4,6,7)は **Team mode + require plan approval** を推奨。
  Builder のプランが当該 Phase の AC を満たす場合のみ承認する。
- ドキュメント寄りフェーズ(Phase 5 の憲法配布版など)は Solo mode でも可。
- 各 Phase 完了ごとに `/eval` を挟み、退行を早期に検出する(第7条)。
- Phase 2 と Phase 4 は worktree 依存で相互に絡むため、T4.2(sandbox)を Phase 2 の前に
  前倒しするか、Phase 2 では worktree を仮実装して Phase 4 で本実装に差し替える。
  - **【実装決定 2026-07-01】T4.2 を分割し worktree を前倒しする（仮実装しない）**:
    - **T4.2a（worktree 隔離）** = `harness/sandbox.py` の `carve_worktree()`/`merge_worktree()`（**git worktree のみ**）→ **Phase 1 で実装**（merge が実 worktree を扱う）、Phase 2 の build で使用。
    - **T4.2b（実行サンドボックス）** = podman rootless + cgroups `MemoryMax`（テスト/コード実行の隔離）→ **Phase 4 のまま**（verify/tester が使用）。
    - AC は不変（第4条の worktree+podman はいずれも満たす）。実装順序のみ変更。
