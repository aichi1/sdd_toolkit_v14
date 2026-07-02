# Specification — sdd_toolkit_v14

## 1. 背景とスコープ

v12/v13 は「仕様 → Builder/Validator → 段階出力(`outputs/phase-{N}/`)→ 知見蓄積」の
サイクルを Claude Code に定着させるツールキットである。v13 で実 stdio MCP サーバと
Agent Teams(Builder ⇄ Validator の直接メッセージング)を導入した。

v14 は、この土台に 4 つの層を足して「単一エージェント + 逐次ハンドオフ」から
「決定論的オーケストレーション + 隔離された並列エージェント + 評価ゲート」へ拡張する。
狙いは、AI 生成コードの **ドリフト**(仕様と実装の静かな乖離)と
**再現性・監査性の欠如**を構造的に潰すことにある。

対象の 5 層(下から上へ実行基盤、上から下へ生成フロー):

1. SDD + Constitutional 制約
2. コンテキストエンジニアリング
3. PEV ハーネス(Plan → Execute → Verify)
4. 評価ハーネス + 可観測性
5. ランタイム基盤

## 2. ゴール / 非ゴール

### ゴール

- G1. 1 タスク = 1 `thread_id` として、クラッシュ後も同じ地点から再開できる。
- G2. 仕様書を丸ごとではなく関連スライスだけをエージェントに注入する。
- G3. Builder/Validator に加え、Tester・Reviewer・Security を並列展開できる。
- G4. 不可逆操作の前に人間承認ゲートを挟み、承認後だけ副作用を実行する。
- G5. 憲法(非機能・安全・規制制約)を評価ゲートとして機械的に強制する。
- G6. すべての run をトレースし、コスト・トークンを記録する。
- G7. v12/v13 の資産(`handlers.py`、Builder/Validator 定義、`eval/`)を再利用する。

### 非ゴール

- N1. **multi-agent-shogun を使わない**。オーケストレーションは LangGraph で自作する。
- N2. **ntfy/Telegram を使わない**。承認は `interrupt()` + ローカル面で完結させる。
- N3. 初版で Temporal を導入しない。多日待ちのクラッシュ耐性が必要になるまで SqliteSaver で十分。
- N4. クラウド前提にしない。単一の常時稼働 PC(WSL2/Ubuntu)で完結する。

## 3. 機能要件(層ごと・受入基準つき)

各要件は ID を持ち、Validator は受入基準(AC)を証拠として引用する。

### FR-1 SDD + Constitutional 層

- **FR-1.1** `spec_load` ノードが仕様パスと憲法ダイジェストを状態に載せる。
  - AC: `TaskState.spec_path` と `constitution_digest` が非空で、本文は状態に載っていない。
- **FR-1.2** 憲法条項を取得する MCP ツールが存在する。
  - AC: `constitution_server` が条項一覧と個別条項取得のツールを公開し、`initialize`→`tools/list` で登録が確認できる。

### FR-2 コンテキストエンジニアリング層

- **FR-2.1** ChromaDB を用いた in-process MCP が「タスクに関連する仕様スライス」を返す。
  - AC: `assemble_context` ノードが `context_slice_ids` を状態に載せ、返却チャンク数が仕様全体より小さい(選択が効いている)。
- **FR-2.2** 注入順序が固定される(不変の大ブロックが先頭、タスク固有スライスが後段)。
  - AC: 同一入力で 2 回実行したとき、注入プロンプトの先頭ブロックが一致する(prompt cache ヒット条件)。

### FR-3 PEV ハーネス層

- **FR-3.1** `build` ノードが Builder サブエージェントを worktree 内で実行する。
  - AC: 生成物が `worktree_path` 配下に出力され、ホスト作業ツリーを直接変更しない。
- **FR-3.2** `verify` ノードが Validator + Tester + Reviewer + Security を並列展開する。
  - AC: `verify_findings` が reducer でマージされ、並列実行で所見が上書きされない。
- **FR-3.3** 専門サブエージェントは `Task`(Agent)ツールを持たない。
  - AC: 各専門エージェント定義の許可ツールに `Task` が含まれない。

### FR-4 評価ハーネス + 可観測性層

- **FR-4.1** `eval` ノードが回帰検出とスコア判定を行い、閾値未満なら `build` へ戻す。
  - AC: 意図的に退行させた入力で `build` への条件エッジが発火する。
- **FR-4.2** 各 run のコスト・トークンが記録される。
  - AC: run ごとに `total_cost_usd` と使用トークンが観測ストアに残る。

### FR-5 承認ゲート(ランタイム基盤)

- **FR-5.1** `review` ノードが `interrupt()` で停止し、diff と所見をペイロードとして提示する。
  - AC: SqliteSaver 上に状態が保存され、`Command(resume=...)` で同一 `thread_id` から再開できる。
- **FR-5.2** 承認は ntfy/Telegram を介さず、ローカルのレビュー面(FastAPI)から返す。
  - AC: `/review` がペイロードを表示し、承認ボタンが `Command(resume={"action":"approve"})` を送る。CLI からの resume も可能。
- **FR-5.3** 承認時のみ merge が実行される。
  - AC: reject/未承認では main に反映されない(第3条の強制)。

## 4. 非機能要件

- **NFR-1 性能**: SqliteSaver のチェックポイント書込みは通常 15ms 以下(状態 10KB 未満)。
- **NFR-2 再開性**: プロセス再起動後、同一 `thread_id` で途中から再開できる。
- **NFR-3 隔離**: すべてのコード実行が worktree + podman 内で行われ、egress は既定で遮断。
- **NFR-4 コスト管理**: `max_turns` 等でオーケストレーターの暴走コストに上限を設ける。
- **NFR-5 互換**: v12 の `/init-task` `/run-phase` `/finalize` `/eval` フローから利用できる。

## 5. スコープ外

- 分散マルチインスタンス(PostgresSaver 化)は将来課題。初版は単一プロセス。
- GUI ダッシュボードは最小限(レビュー面のみ)。フル可視化は LangSmith に委譲。

## 6. 完了の定義(Definition of Done)

- D1. `04_tasks.md` の全フェーズが `/run-phase` を PASS で通過している。
- D2. 最小グラフ(spec_load → build → review → merge)が実際に動き、承認後だけ merge される。
- D3. 5 層すべての FR が受入基準を満たす。
- D4. `/eval` の 7 軸で v13 ベースラインに対し退行がない(同等以上)。
- D5. `01_constitution.md` の各条項に対応する強制点が実装され、意図的な違反入力で検出される。
