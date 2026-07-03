# Task Spec（改訂版）— v12資産のv14装填：専門エージェント実弾化 + eval_suite の severity 化

対象リポジトリ: `sdd_toolkit_v14`（コミット `538f1e6` 以降）
カテゴリ: `small_implementation`（ただし T-3/T-4 はコンテンツ執筆＋採点コア変更を含む中規模。下記「規模の実態」参照）
実行方針: Team mode 推奨。全タスク外部 API 不要でテスト可能（`_run_query` monkeypatch で完結）。

> **この改訂版について**：原案（Claude Fable 版）を実コードで精査した結果を反映した版です。
> 思想（機械は検証済みだが専門家の中身が薄い→実モードの所見が低品質、という問題設定）と
> 設計原則は妥当と確認できたため維持し、**事実と食い違う3点のみ**を修正しています。
> 原案からの差分は次節に明示します。

---

## 原案からの差分（なぜ変えたか）

| 箇所 | 原案 | 改訂 | 理由（実コード根拠） |
|---|---|---|---|
| **T-4 / AC-4.3** | eval_suite が `scripts/validate-outputs.py` を import して再利用（第6条） | **validate-outputs.py 依存を撤回**。severity 加重＋rubric.json 重み＋HIGH ゲート＋役割別メトリクスに限定 | validate-outputs.py は `outputs/phase-NN/` の**ファイル存在チェッカー**（argparse CLI・ハイフン名で import 困難・`--phase N`）。eval_suite が採点するのは worktree の artifact＋findings で**対象が別物**。第6条は「同一責務資産の再利用」が趣旨（第6条 Option A 改正の精神）であり、別問題を解くコードへの適用は無理な adapter を生む |
| **T-3 の位置づけ** | 「新規執筆ではなく既存資産の**再利用**が原則」 | 「**典拠付き執筆**」に再定義（validator を除く3体） | `validator.md` は542行の実弾だが、`security_reviewer.md`/`qa_test_engineer.md`/`software_architect.md` は**各26行の骨組み**（チェックリストは見出しだけの空枠）。`templates/fragments/quality-criteria/` は `citation`/`comparison` のみで**コードレビュー用基準は不在**。3体分は実質、SCORING_GUIDE.md と憲法を典拠にした執筆になる |
| **T-4 の重複** | 「HIGH finding 1件で閾値未達」を新規実装 | **既存機構の一般化**として実装 | eval_suite は既に `security_findings` があれば `regressed=True`（`harness/eval_suite.py` 採点コメント）。二重実装せず「任意 HIGH → regressed」へ拡張する |
| **T-1 の測定** | tag ＋ history スナップショット | ＋**同一 eval シナリオの前後実行**を明記 | tag は code を固定するだけ。A/B の効果測定には装填前後で同じ入力を eval に通した数値が要る |

---

## 規模の実態（見積り補正）

- **T-1 / T-2**：低リスク・高価値。ここまでで実モードの所見品質は大きく上がる（一行→役割別・根拠必須・severity 付き）。
- **T-3**：3体分は空枠への**執筆**。典拠（SCORING_GUIDE.md・憲法第10条 CWE/OWASP・validator.md の証拠ベース規約）はあるが「コピペ移植」ではない。
- **T-4**：採点コア（`harness/eval_suite.py`）と機械契約（`_parse_findings`）に触れる**最大リスク**。T-3 の severity 契約に依存するため後段。
- 推奨順序：`T-1 → T-2 → T-3 →（T-4）`。**T-2＋T-3 で実質価値の大半が取れる**ため、T-4 は独立判断で後追い可。

---

## 設計原則（全タスク共通）

1. **プロンプトはハードコードしない**。`graph/nodes.py` に文字列で埋めず、md から実行時ロードする
   （`BUILDER_SYS` が `.claude/agents/builder.md` から来るのと同じ流儀、第6条）。
2. **出力契約はコードが所有する**。`FINDING:` 行のパース仕様は `_parse_findings` が依存する機械契約。
   プロンプトファイルの内容に依存させず、nodes.py が「出力契約セクション」をロード済みプロンプトの
   末尾に**プログラム的に付加**する。**コンテンツ（何を見るか）と契約（どう出すか）を分離**する。
3. **防御境界を後退させない**。`templates/agents/*.md` の frontmatter `tools:`（例: security_reviewer.md は
   `Bash` を含む）は v12 team-roster の名残で、**v14 では無視する**。許可ツールは引き続き
   `SPECIALIST_TOOLS` のみが決定する（F-2 の決定を維持、第4/5条）。
4. **関心の分離**。4体が同じ指摘を重複して返すと findings がノイズ化する。各プロンプトに
   「自分の関心外（他 specialist の領分）は指摘しない」を明記する。
5. **（改訂追加）第6条の再利用は同一責務に限る**。プロンプト（役割定義）と rubric（採点アンカー）は
   同一責務の再利用。**フェーズ出力チェッカー（validate-outputs.py）を findings スコアラーに転用しない**。

---

## T-1: ベースライン凍結（A/B 実験の前提 — 先行必須）

**目的**：装填「前」の状態を保存し、後続 A/B 実験で「装填の効果」自体を測定可能にする。

**作業**：
1. 現 HEAD（`538f1e6`＝防御境界修正済み・装填前）に git tag `v14-pre-loading` を付与する。
2. `eval/history/` に装填前スナップショットを1件追加する（`iteration_id: v14-pre-loading`、既存 v14 エントリと
   同形式、`meta.note` に「装填前ベースライン。A/B 比較の対照群」と明記）。
3. **A/B 用の固定 eval シナリオを1本以上確定**し（既存 `eval/scenarios/` を流用、無ければ最小1本を追加）、
   装填前の状態でそれを eval に通した**数値スコア（軸別・finding 数）をスナップショットに含める**。
   ※これが無いと tag は「コードの凍結」に留まり効果測定にならない。
4. `docs/CHANGELOG.md`（無ければ新規）に凍結の事実を1行記録する。

**受入基準**：
- AC-1.1: `git tag` に `v14-pre-loading` が存在する。
- AC-1.2: `eval/history/` に対応 JSON が存在し、既存スキーマに適合する。
- AC-1.3: スナップショットに固定シナリオの装填前スコア（軸別 or 総合）が含まれる。

---

## T-2: プロンプトのファイルロード機構

**対象**：`graph/nodes.py`（`_invoke_specialist` 周辺）、新規 `agents/prompts.py`

**作業**：
1. `agents/prompts.py` に `load_specialist_prompt(specialist_name) -> str` を実装：
   - 既定マッピング：
     - `security`  → `templates/agents/security_reviewer.md`
     - `tester`    → `templates/agents/qa_test_engineer.md`
     - `reviewer`  → `templates/agents/software_architect.md`
     - `validator` → `.claude/agents/validator.md`
   - 環境変数 `SDD_SPECIALIST_PROMPT_DIR` で差し替え可能（下流プロジェクトが自前の役割定義を持てる）。
   - frontmatter（先頭 `---` ブロック）は除去してロード。`tools:` は読まない（設計原則3）。
   - **ファイル不在時は現行の一行プロンプトにフォールバックし、WARNING を監査ログ**
     （`SDD_AUDIT_LOG`、既定 `logs/audit.jsonl`）に残す（クラッシュさせない）。
2. `_invoke_specialist` の system_prompt 組立を変更：
   `load_specialist_prompt(name)`（コンテンツ）＋ 固定の「出力契約セクション」（契約、T-3 で定義）を結合。
   契約セクションは**コード側の定数**として nodes.py に置き、プロンプトファイルから独立させる（設計原則2）。
3. `_SPECIALIST_CONCERN` は「関心外の抑制」文へ転用するか、プロンプトファイル側に吸収して削除する
   （二重管理を残さない、第6条）。

**受入基準**：
- AC-2.1: テスト — `_run_query` を monkeypatch し、渡された options の system_prompt に
  (a) ロード元ファイルの識別可能な文字列、(b) `FINDING:` 出力契約、の両方が含まれることを**4体すべて**で検証。
- AC-2.2: テスト — プロンプトファイル不在時にフォールバックが機能し、例外にならない（監査ログに WARNING）。
- AC-2.3: テスト — frontmatter の `tools:` が `options.allowed_tools` に影響しないこと
  （`SPECIALIST_TOOLS` のみが決める）を固定する。
- AC-2.4: テスト — `SDD_SPECIALIST_PROMPT_DIR` で差し替え先が優先されること。

---

## T-3: 4本のプロンプト内容の整備（典拠付き執筆）

**対象**：T-2 のマッピング先 md 4ファイル。元を直接書き換えるか `templates/agents/v14/` に調整版を置くかは
Builder が判断し、選定理由をコミットメッセージに記す。

> **位置づけ**：`validator.md`（542行）は実弾なので**適合調整（verify 文脈化）**。
> security/tester/reviewer の3体は26行の空枠なので、下記の典拠を用いた**執筆**になる：
> `eval/SCORING_GUIDE.md`（7軸アンカー）・`docs/constitution.md`/`specs/constitution.md` 第10条（CWE/OWASP）・
> `.claude/agents/validator.md` の証拠ベース規約（4体共通の作法の手本）。

**作業**：
1. **チェックリストの具体化（執筆）**：各役割の担当観点を、SCORING_GUIDE の軸定義と憲法の強制点から
   具体項目に落とす。空枠の見出しを埋める。
2. **重要度の契約化**：High/Med/Low を出力契約に写像する。契約セクション（T-2 の固定部・コード所有）に
   次を定義：
   ```
   FINDING: [HIGH|MED|LOW] <説明> (根拠: <ファイルパス/該当箇所 or 条項>)
   ```
   `_parse_findings` を拡張し、重要度と根拠を抽出して findings 文字列に保持する
   （**状態スキーマは変更しない**＝findings は `list[str]` のまま、第2条）。
   **後方互換必須**：旧形式 `FINDING: <説明>`（重要度・根拠なし）も従来どおりパースできること
   （既定 severity は例えば `MED` 相当として扱う。既存テストの `FINDING: example issue` を壊さない）。
3. **関心の分離の明文化**：各プロンプトに担当範囲と「指摘しない範囲」を明記：
   - `validator`: 仕様/受入基準との照合のみ（設計の良し悪しは reviewer の領分）
   - `tester`: テストの存在・網羅・未検証パスのみ（**実行はしない＝読み取り専門、F-2**）
   - `reviewer`: 設計・境界・保守性のみ（脆弱性は security の領分）
   - `security`: 脆弱性・秘密情報・危険操作のみ（CWE/OWASP 参照を維持、第10条）
4. **根拠必須の維持**：validator 規約の「証拠ベース」（ファイルパス/条項引用のない指摘は無効）を4体に適用。

**受入基準**：
- AC-3.1: 4ファイルすべてに (a) 担当チェックリスト、(b) 関心外の抑制、(c) 根拠必須、のセクションが存在する
  （構造チェックのテストで検証）。
- AC-3.2: `_parse_findings` が `FINDING: [HIGH] ... (根拠: ...)` から**重要度と根拠を抽出**するユニットテストが通る。
- AC-3.3: **後方互換** — 旧形式 `FINDING: <説明>` もパースでき、既存 verify テストが無改変で通る。

---

## T-4: eval_suite の severity 化（rescoped — validate-outputs.py 非依存）

**対象**：`harness/eval_suite.py`、`eval/rubric.json`、`harness/observability.py`

> **改訂の要点**：原案の「validate-outputs.py を import して再利用」は**撤回**（対象オブジェクトが別物・第6条の誤適用）。
> 価値ある核（severity 加重・重みの外部化・HIGH ゲート・メトリクス）だけを、既存機構の**一般化**として実装する。

**作業**：
1. **重みの外部化**：現在ハードコードの減点定数（`_DEDUCT_FINDING_CORRECTNESS` 等）を `eval/rubric.json` に
   移し、コードから読み込む（重みのハードコード禁止＝調整を仕様変更として扱えるように）。
   severity 別の重み（HIGH/MED/LOW）を rubric.json に定義する。
2. **severity 加重採点**：
   - `HIGH` の finding は**1件で `regressed=True`**（=eval_node が `build` へ差し戻し）。
     これは既存の「`security_findings` あれば regressed」機構の**一般化**として実装する（二重実装しない）。
   - `MED`/`LOW` は合格率スコアへの減点（重みは rubric.json）。
3. **回帰メトリクス**：`sum_agent_costs` と同じ観測ストア（`SDD_OBS_STORE`）に、run ごとの
   **役割別 finding 数・重要度分布**を1レコード（例 `record_type="eval_breakdown"`）で記録する。
   直前 run との比較で「**新規 HIGH の出現**」を regressed 判定に加える。
4. **（任意・stretch）カテゴリ規則の限定再利用**：`validate_rules.yaml` の**規則データ**（YAML）を、
   カテゴリが artifact 内容に写像できる範囲でのみ参照してよい。ただし**script のファイル検査ロジックは呼ばない**。
   実施する場合はカテゴリを spec 側（`docs/` の task 定義）から解決する。**不要なら省略可**（DoD に含めない）。

**受入基準**：
- AC-4.1: テスト — `HIGH` finding 1件を含む入力で eval_node が `build` へルーティングする
  （既存 Command ルーティングテストの拡張）。
- AC-4.2: 重みを `rubric.json` で変更するとスコアが追随する（ハードコードなし）。
- AC-4.3:（**改訂**）観測ストアに役割別 finding 数・重要度分布が記録され、新規 HIGH が regressed に反映される。
- AC-4.4:（**改訂**）`harness/eval_suite.py` が `scripts/validate-outputs.py` を import していないこと
  （＝別責務コードの転用が無いことを Validator が確認）。※原案 AC-4.3 の反転。

---

## T-5: テスト・文書の整合

**作業**：
1. `tests/test_specialist_prompts.py`（新規）に AC-2/AC-3 系を集約。
2. `graph/nodes.py` モジュール docstring の該当箇所を更新（一行プロンプト→ファイルロード方式への変更を反映。
   **F-4 の教訓：実装変更と同一コミットで docstring を直す**）。
3. README の「実 Agent SDK モード」節に、装填済み specialist の**担当範囲表**（4体×担当/非担当）を追記する。

**受入基準**：
- AC-5.1: テストスイート全件パス（件数は増加のみ）。
- AC-5.2: `grep -n "quality issues in the artifact" graph/nodes.py` が 0件、
  またはフォールバック文としてのみ残存（汎用一行プロンプトが主経路から消えている）。

---

## 完了の定義（全体）

- 全 AC を満たし、テスト全件パス（実 API 0）。
- 4体の system prompt が md からのファイルロードでコンテンツを持ち、**出力契約はコード側が付加**している
  （コンテンツと契約の分離）。
- `_parse_findings` が severity＋根拠を抽出し、**旧形式も後方互換**でパースする（機械契約の非破壊拡張）。
- `HIGH` finding が評価ゲートを実際に閉じる（AC-4.1）。既存の security→regressed の**一般化**として実装。
- 重み・severity 加重は `rubric.json` にあり、コードにハードコードされていない（AC-4.2）。
- `eval_suite.py` が `validate-outputs.py` を転用していない（AC-4.4、第6条の正しい適用）。
- 第4/5条の防御境界に後退がない（`SPECIALIST_TOOLS` 支配の維持、frontmatter `tools:` 無視、AC-2.3）。
- `v14-pre-loading` タグ＋固定シナリオの前後スコアにより、装填前後の A/B 比較が実施可能。

## 実施メモ

- Team mode 推奨。T-2/T-5（コード）と T-3（コンテンツ）は互いに素なファイル集合なので並行可能。
  T-4 は T-3 の重要度契約に依存するため後段。
- 全タスクとも外部 API 不要でテスト可能（`_run_query` monkeypatch で完結）。
- **装填後の実 API スモーク**（`python3 -m harness.smoke_real_sdk` または実 verify）を最後に**手元で1回**実施し、
  実際の finding が **重要度・根拠つき**で返ること、監査ログに4専門家のツール呼び出しが記録されることを目視確認する
  （`ANTHROPIC_API_KEY` 空＝サブスク枠であることの確認込み）。
- 本タスク完了後の次スペックは A/B 実証実験（対照群: `v14-pre-loading` / 素の Claude Code、
  処置群: 装填済み v14）。実験計画は別 md として起こす。
- 制作構造≠配布構造のため、コード変更は**ビルド元 `building_sdd_v14_by_v12` と配布版 `sdd_toolkit_v14` の
  両方にミラーし、両方でテスト green** を確認する（片方だけ直す事故を防止）。
