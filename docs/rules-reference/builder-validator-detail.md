# Builder/Validator Protocol - Builder/Validator協調プロトコル

## 目的
Builder AgentとValidator Agentの役割分担を厳格に定義し、両者の協調によって高品質な成果物を効率的に生成する。

## 基本原則

### 原則1: 完全分離（Separation of Concerns）
```
Builder  → 生成に専念（検証はしない）
Validator → 検証に専念（修正はしない）
```

この分離により:
- Builderは速度重視で生成できる
- Validatorは客観的に検証できる
- 「自分で書いたものを自分でチェック」の盲点を回避

### 原則2: 単方向フロー（Unidirectional Flow）
```
Builder → 成果物 → Validator → 検証レポート → Builder → 修正版 → Validator → ...
```

逆流は禁止:
- Validatorが直接修正してBuilderに渡す ✗
- BuilderがValidator結果を見る前に再修正 ✗

### 原則3: 明示的引き継ぎ（Explicit Handoff）
全ての引き継ぎは `.metadata.json` を通じて記録:
- Builderの作業内容
- Validatorの検証結果
- 修正履歴

---

## Builder Agent のルール

### Rule 1: 生成のみに専念
```
許可される行為:
  ✓ SKILL.mdに従って成果物を生成
  ✓ docs/を参照して要件を理解
  ✓ 前Phase成果物を活用
  ✓ 不明点をメインセッションに質問

禁止される行為:
  ✗ 「これで十分か」の判断（Validatorの仕事）
  ✗ 要件を満たしているかの自己検証
  ✗ 「もっと良く書ける」と何度も書き直し
  ✗ Validator結果を予測して事前修正
```

### Rule 2: 手順の忠実な実行
```
SKILL.mdに書かれていること:
  → 必ず実行

SKILL.mdに書かれていないこと:
  → 推測で追加しない、質問する

例:
  SKILL.md: "3社を比較"
  Builder: 3社分析する（2社でも4社でもない）
  
  SKILL.md: "詳細に分析"（曖昧）
  Builder: 「詳細とは？」と質問（推測で進めない）
```

### Rule 3: 成果物の完全性
Builder完了時に必ず作成:
```json
// outputs/phase-{N}/.metadata.json
{
  "builder_session_id": "uuid",
  "started_at": "timestamp",
  "completed_at": "timestamp",
  "skill_followed": "skills/phase-02/SKILL.md",
  "docs_referenced": ["docs/background.md", ...],
  "deliverables": [
    {
      "file": "report.md",
      "type": "document",
      "status": "pending_validation",
      "word_count": 1500,
      "sections": ["導入", "分析", "結論"]
    }
  ],
  "builder_notes": "SKILL.mdの全手順完了。Validatorに検証を依頼。"
}
```

### Rule 4: 修正時の最小変更
Validatorから修正指示が来た場合:
```
原則: 指摘された箇所のみ修正

NG例:
  Validator: 「Section 2に価格情報を追加」
  Builder: Section 2修正 + Section 3も「ついでに」改善
  → 予期せぬ変更で新たな問題を生む可能性

OK例:
  Validator: 「Section 2に価格情報を追加」
  Builder: Section 2のみ修正
  → 変更範囲が明確、再検証が容易
```

---

## Validator Agent のルール

### Rule 1: 検証のみに専念
```
許可される行為:
  ✓ docs/の要件と成果物を照合
  ✓ SKILL.mdの品質基準でチェック
  ✓ 問題箇所を特定
  ✓ 修正方法を具体的に提案

禁止される行為:
  ✗ 問題箇所を直接修正
  ✗ 代替案を書いて差し替え
  ✗ 「このくらいは自分で直せる」と判断
  ✗ ファイルへの書き込み（検証レポート以外）
```

### Rule 2: 要件ベースの判定
```
判定の根拠:
  1. docs/に明記された要件
  2. SKILL.mdのQuality Criteria
  3. 前Phase成果物との一貫性

判定の根拠にならないもの:
  ✗ Validatorの個人的好み
  ✗ docs/に書かれていない「暗黙の期待」
  ✗ 「普通はこうする」という慣習（docs/に明記されていなければ）
```

### Rule 3: 具体的な指摘
検証レポートの各Issueに必須:
```markdown
### Issue #{N}: {簡潔なタイトル}
- **Location**: {ファイル名} {行番号 or セクション}
- **Problem**: {何が問題か}
- **Required by**: {docs/XXX.md 要件Y} または {SKILL.md 品質基準Z}
- **Current state**: {現状}
- **Expected**: {期待される状態}
- **Fix**: {具体的な修正方法}
- **Priority**: Critical / Suggestion

例（良い指摘）:
  Location: comparison-table.md 行15-20
  Problem: B社とC社の価格情報が欠落
  Required by: docs/scope.md 要件3「全社の価格比較を含む」
  Current: A社のみ価格記載（月額3,000円）
  Expected: B社、C社の価格も記載
  Fix: docs/competitors.md Section 3からB社（5,000円）、C社（8,000円）を転記
  Priority: Critical

例（悪い指摘）:
  Problem: 表が不完全
  → どこが？何が？どう直す？が不明
```

### Rule 4: 判定の明確化
検証完了時の判定:
```
PASS:
  - 全要件が満たされている
  - Critical Issueが0件
  - 次Phaseに進める状態

NEEDS_REVISION:
  - Critical Issueが1-5件程度
  - 修正は比較的容易（見積もり < 1時間）
  - Builderの再修正で解決可能

FAIL:
  - Critical Issueが多数（6件以上）
  - または根本的な設計ミス
  - SKILL.mdまたはdocs/の見直しが必要

判定基準の例外:
  - ユーザーが「この問題は承知で進む」と明示
    → PASSではないが次Phase進行可（"completed_with_issues"）
```

---

## 引き継ぎプロトコル

### Builder → Validator
Builder完了後、Validatorに渡す情報:

**必須情報:**
```
1. 成果物の場所
   outputs/phase-{N}/

2. メタデータ
   outputs/phase-{N}/.metadata.json
   - builder_session_id
   - deliverables リスト
   - 参照したdocs/ファイル
   - 実行したSKILL.mdの手順

3. Builder自身のメモ（任意）
   "comparison-table.mdは3社全て記載したが、
    D社の情報がdocs/になかったため除外"
```

**Validatorの確認事項:**
```
1. 全deliverables が存在するか
2. SKILL.mdで指定された形式か
3. docs/の要件リストを抽出
4. 検証準備完了 → 検証開始
```

### Validator → Builder（初回）
Validator検証後、Builderに返す情報:

**検証レポート:**
```
outputs/phase-{N}/.validation/report.md

内容:
  - Overall Status (PASS/NEEDS_REVISION/FAIL)
  - 要件チェックリスト（各要件の充足状況）
  - Critical Issues リスト
  - Suggestions リスト
  - 修正見積もり時間
```

**Status別の指示:**
```
PASS:
  → Builder: 何もしない、Phase完了

NEEDS_REVISION:
  → Builder: Critical Issuesのみ修正
  → 修正範囲を最小限に
  → 修正後、Validatorに再検証依頼

FAIL:
  → メインセッションに報告
  → SKILL.md or docs/の見直し検討
  → Builder再実行 or Phase設計変更
```

### Builder → Validator（修正後）
Builder修正完了後:

**修正記録:**
```json
// outputs/phase-{N}/.metadata.json (更新)
{
  ...
  "revision_history": [
    {
      "iteration": 2,
      "builder_session_id": "uuid-2",
      "timestamp": "...",
      "issues_addressed": [1, 3],  // Issue #1, #3を修正
      "changes": "comparison-tableに価格列追加、引用形式修正",
      "files_modified": ["comparison-table.md"]
    }
  ]
}
```

**Validatorの再検証:**
```
1. 前回のCritical Issuesを確認
2. 指摘箇所が修正されているか
3. 新たな問題が発生していないか（回帰チェック）
4. 再判定
```

---

## 修正サイクルルール

### サイクル上限
```
最大2回の修正サイクル:

Cycle 1: Builder生成 → Validator検証 → NEEDS_REVISION
  ↓
Cycle 2: Builder修正 → Validator再検証 → NEEDS_REVISION
  ↓
Cycle 3: Builder再修正 → Validator再検証 → (まだNEEDS_REVISION?)
  ↓
  → 自動修正を停止、メインセッションにエスカレーション
```

### エスカレーション基準
3回目の修正でも解決しない場合:
```
原因分析:
  1. SKILL.mdの手順が不適切
     → SKILL.md修正が必要
  
  2. docs/の要件が矛盾
     → docs/整理が必要
  
  3. Builder/Validatorの解釈が異なる
     → 要件の明確化が必要
  
  4. タスク自体に無理がある
     → Phase設計の見直しが必要

対処:
  - メインセッションに状況報告
  - 上記4点の分析結果提示
  - ユーザー判断を仰ぐ
```

---

## 協調パターン

### パターン1: スムーズな協調（理想形）
```
Builder:
  1. SKILL.md手順を実行
  2. 成果物を outputs/phase-02/ に保存
  3. .metadata.json作成
  4. 完了報告

Validator:
  5. 成果物を読む
  6. 要件チェックリスト作成
  7. 全て✓ → PASS
  8. 完了報告

結果: Phase 2完了（15分）
```

### パターン2: 1回修正で解決
```
Builder:
  1. 成果物生成（10分）
  
Validator:
  2. 検証 → NEEDS_REVISION（3件）
  3. 検証レポート作成（3分）

Builder:
  4. Issue #1-3修正（5分）
  5. 修正版を保存

Validator:
  6. 再検証 → PASS
  
結果: Phase 2完了（21分）
```

### パターン3: 2回修正で解決
```
Builder → Validator → NEEDS_REVISION (5件)
  ↓
Builder修正 → Validator → NEEDS_REVISION (2件残存)
  ↓
Builder再修正 → Validator → PASS

結果: Phase 2完了（35分）
```

### パターン4: エスカレーション
```
Builder → Validator → NEEDS_REVISION (多数)
  ↓
Builder修正 → Validator → NEEDS_REVISION (ほぼ同じ)
  ↓
Builder再修正 → Validator → NEEDS_REVISION (変わらず)
  ↓
  停止 → メインセッションに報告
  
「SKILL.md Phase 2の手順が曖昧すぎます。
 『詳細に分析』とあるが、何をもって詳細とするか
 基準が不明確です。SKILL.md修正を推奨。」
```

---

## 禁止パターン

### NG1: Validatorが修正を実行
```
✗ ダメな例:
  Validator: 「価格列が欠落している」
  Validator: （自分で価格列を追加してファイル保存）
  Validator: PASS判定

理由:
  - Validatorの客観性が損なわれる
  - Builderの学習機会を奪う
  - 修正履歴が不明確

✓ 正しい例:
  Validator: 「価格列が欠落している」
  Validator: レポートに「Fix: 価格列を追加」と記載
  Builder: レポートを見て価格列追加
```

### NG2: Builderが勝手に再修正
```
✗ ダメな例:
  Builder: 成果物生成
  Builder: 「あ、ここ間違えた」→ 自分で直す
  Builder: もう一度確認 → また修正
  Builder: 最終版を Validator に渡す

理由:
  - 「自分で書いたものを自分でチェック」の盲点
  - Validatorの仕事を奪っている
  - 時間の無駄

✓ 正しい例:
  Builder: 成果物生成
  Builder: すぐに Validator に渡す
  Validator: 問題を指摘
  Builder: 指摘箇所を修正
```

### NG3: 範囲外の修正
```
✗ ダメな例:
  Validator: 「Section 2に価格情報追加」
  Builder: Section 2修正
  Builder: 「ついでにSection 3も読みやすく修正」
  Builder: 「Section 1の誤字も直した」

理由:
  - Validatorが検証していない変更を加えている
  - 新たな問題を生む可能性
  - 変更範囲が不明確

✓ 正しい例:
  Validator: 「Section 2に価格情報追加」
  Builder: Section 2のみ修正
  Builder: 他のセクションは触らない
```

### NG4: 曖昧な指摘
```
✗ ダメな例:
  Validator: 「文章が分かりにくい」
  Validator: 「もっと詳しく書いて」
  Validator: 「全体的に改善が必要」

理由:
  - Builderが何を直すべきか不明
  - 修正しても再びNEEDS_REVISIONの可能性
  - 時間の無駄

✓ 正しい例:
  Validator: 「Section 2.3 行15-18の因果関係が不明確。
            『Aのため』とあるが、Aと結果Bの関係が
            docs/background.mdのロジックと矛盾。
            修正: AではなくA'（背景のロジックに沿った理由）
            を記載すべき。」
```

---

## トラブルシューティング

### 問題: BuilderとValidatorの解釈が異なる
```
症状:
  Builder: 「要件を満たしたはず」
  Validator: 「要件Xが未達」
  Builder修正: また指摘される

原因:
  docs/の要件が曖昧

対処:
  1. メインセッションに報告
  2. docs/の該当箇所を明確化
  3. Builder/Validatorで合意
  4. 修正後に再実行
```

### 問題: Validatorの指摘が多すぎる
```
症状:
  Validator: Critical Issue 15件

原因:
  - SKILL.mdの手順が不適切
  - Builderが手順を誤解
  - docs/が過剰に詳細

対処:
  1. Issueをカテゴリ分け
  2. 根本原因を特定
  3. SKILL.md or docs/を修正
  4. Phase再実行
```

### 問題: 修正が終わらない
```
症状:
  3回修正してもNEEDS_REVISION

原因:
  - 要件の矛盾
  - 不可能なタスク
  - Builder/Validatorの誤動作

対処:
  1. エスカレーション
  2. メインセッションで原因分析
  3. SKILL.md/docs//Phase設計の見直し
```

---

## 成功の指標

### 良好な協調:
- [ ] 初回でPASS、または1回修正でPASS
- [ ] Validatorの指摘が具体的
- [ ] Builderの修正が的確
- [ ] 修正履歴が明確
- [ ] エスカレーションが不要

### 改善が必要な協調:
- [ ] 3回以上の修正サイクル
- [ ] Validatorの指摘が曖昧
- [ ] Builderが範囲外を修正
- [ ] 同じ問題が繰り返される
- [ ] エスカレーション頻発

→ このような場合、SKILL.mdやdocs/の品質に問題がある可能性

---

## まとめ

Builder/Validator分離の本質は**「責任の明確化」**。

**Builder:**
- 生成に専念
- 検証はしない
- 指摘を素直に受け入れる

**Validator:**
- 検証に専念
- 修正はしない
- 具体的に指摘する

**両者の協調:**
- 明示的な引き継ぎ
- 証拠ベースの議論
- 最小限の修正サイクル

このプロトコルを守ることで、**速度と品質を両立**できる。