# Agents & Conventions — sdd_toolkit_v14 build

v14 を実装する間、Builder/Validator/専門エージェントが従う規約。
`01_constitution.md` が「何を守るか」なら、本書は「どう書くか」。
v12 の Builder/Validator ルールを踏襲し、v14 固有の制約を足している。

## 言語・ランタイム

- Python 3.10 以上。型ヒント必須。I/O は async を基本とする。
- 依存はすべて pin する(`pyproject.toml`)。Agent SDK・LangGraph は API が動くので特に固定。
- 環境は WSL2/Ubuntu 単一プロセス前提。クラウド API に暗黙依存しない。

## Builder の規約(v12 踏襲 + 追加)

1. **SKILL.md / spec を正確に follow** — 手順の省略・独自追加をしない。
2. **品質を自己判断しない** — それは Validator の責務。生成して即ハンドオフ。
3. **曖昧なら訊く** — 要件が曖昧なまま推測しない。
4. **最小修正のみ** — Validator 指摘の修正は、指摘箇所だけを変更する。
5. **出力**: 成果物は `outputs/phase-{N}/` + `.metadata.json`(セッション情報・成果物一覧)。
6. **(追加)状態を汚さない** — 本文を `TaskState` に載せない。ディスク(worktree)に置きパスだけ状態へ(第2条)。
7. **(追加)副作用を interrupt の前に置かない** — 不可逆操作は承認分岐の内側だけ(第3条)。

## Validator の規約(v12 踏襲)

1. **読み取り専用** — 成果物を変更せず、検証レポートのみ書く。
2. **証拠ベース** — すべての指摘は `docs/`(spec/constitution)または SKILL.md の
   Quality Criteria の具体条項を引用する。
3. **具体的な指摘** — 各指摘は Location / Problem / Required by / Current / Expected / Fix / Priority を持つ。
4. **(追加)憲法照合** — `01_constitution.md` の各条項の強制点が実装されているかを確認し、
   未実装・違反は FAIL とする。

## 専門エージェント(v14 追加)

- reviewer / security / tester は読み取り + 限定ツールのみ。`Task`(Agent)を持たない(再帰禁止)。
- 各エージェントは独自コンテキストで並列実行される。所見は reducer 経由でマージされる前提で、
  他エージェントの状態に依存しない出力を返す。

## コーディング標準(v14 固有)

- **lean state**: `TaskState` に本文・生ログ・大きな中間物を載せない。パス/ID のみ。
- **決定論的外殻**: 状態遷移はグラフのエッジで明示する。エージェント内部の非決定性を
  制御フローに漏らさない(第9条)。
- **再利用優先**: 既存 `handlers.py` のロジックを import する。同じ責務を再実装しない(第6条)。
  MCP サーバは薄いファサードに徹する。
- **隔離既定**: コード実行を書くときは worktree + podman 経由にする。ホスト直接実行の
  ショートカットを書かない(第4条)。
- **冪等性**: ノードは resume で頭から再実行され得る。interrupt 前は副作用ゼロにする。

## Definition of Done(成果物単位)

各成果物は以下を満たして初めて完了:

- 対応する `04_tasks.md` の AC を満たす。
- 対応する `02_spec.md` の FR に紐づく(トレーサビリティ)。
- `01_constitution.md` のいずれの条項にも違反しない。
- テストが付く(コード成果物の場合)。`small_implementation` 相当はテストカバレッジ必須。
- `.metadata.json` に成果物と根拠(どの FR/AC を満たすか)を記録する。

## テスト方針

- ユニット: ノード関数は状態入出力で検証する(モックエージェント可)。
- 統合: 最小グラフ(Phase 1)と全体(Phase 8)で spec_load〜merge を通す。
- 退行: 各 Phase 完了時に `/eval` を回し、v13 ベースラインと比較する。
- 負のテスト: 禁止操作・脆弱入力・状態肥大を意図的に入れ、hooks/security/計測が検出することを確認する。

## やらないことリスト(明示的禁止)

- multi-agent-shogun を使う実装(オーケストレーションは LangGraph で自作)。
- ntfy/Telegram への通知・承認(承認は `interrupt()` + ローカル面のみ)。
- `TaskState` への本文・生ログの格納。
- interrupt より前への不可逆な副作用の配置。
- 既存 `handlers.py` ロジックの再実装(二重化)。
- ホストでのコード直接実行(worktree/podman を迂回する実装)。
- 評価を通さないプロンプト/モデル変更のマージ。
