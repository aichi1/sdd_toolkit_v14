# docs/とskills/の関係性ルール

## 目的
docs/（何を作るか）とskills/（どう作るか）の役割を明確に分離し、両者の一貫性を保つルールを定義する。

## 基本原則

### 原則1: 役割の分離
```
docs/  = What（何を作るか）
  - 背景、目的、制約
  - 要件、スコープ
  - ターゲット、形式
  - 成功基準

skills/ = How（どう作るか）
  - 手順、プロセス
  - ツール、技法
  - 品質チェック方法
  - タイムライン
```

**具体例:**
```
docs/scope.md（What）:
  「3社の競合を機能、価格、コミュニティ規模で比較する」
  
skills/phase-02/SKILL.md（How）:
  「Step 1: docs/competitors.mdから3社の情報を抽出
   Step 2: 比較表を作成（Markdown表形式）
   Step 3: 各軸でスコアリング（1-5点）
   Step 4: 総合評価を記載」
```

### 原則2: docs/が上位、skills/が従属
```
docs/の変更 → skills/も変更が必要な場合あり
skills/の変更 → docs/は変更不要（手順の最適化）

例:
  docs/scope.md: 「5社比較」に変更
  → skills/phase-02/SKILL.md: 5社分の手順に更新が必要
  
  skills/phase-02/SKILL.md: 「表形式をCSVに変更」
  → docs/は変更不要（How の改善）
```

### 原則3: 1対多の関係
```
1つのdocs/ファイル → 複数のskills/で参照される

例:
  docs/scope.md
    ↓ 参照
  ├─ skills/phase-01/SKILL.md（調査範囲の確認）
  ├─ skills/phase-02/SKILL.md（比較対象の確定）
  └─ skills/phase-03/SKILL.md（報告書の範囲設定）
```

---

## docs/の構造と役割

### docs/に書くべきこと

**1. 背景と目的（background.md）**
```markdown
- なぜこのプロジェクトが必要か
- どのような課題を解決するか
- 誰のため（ステークホルダー）
- どのような状況で使われるか

例:
「現在のWebアプリケーションの処理速度が遅く、
 ユーザー離脱率が15%に達している。
 WebAssembly採用により、処理速度を3倍に改善し、
 離脱率を5%以下に抑えることを目指す。」
```

**2. スコープと制約（scope.md）**
```markdown
- 何を含むか（境界線）
- 何を含まないか（除外事項）
- 制約条件（予算、期限、技術的制約）

例:
「調査対象: Blazor, Yew, Emscripten の3つに限定
 調査範囲: 機能、性能、学習コスト、コミュニティ
 除外: サーバーサイドWASM、WASI関連は対象外
 制約: 調査期間2週間、予算なし（OSS情報のみ）」
```

**3. 要件（requirements.md, criteria.md等）**
```markdown
- 必須要件（Must have）
- 推奨要件（Should have）
- オプション（Nice to have）
- 評価基準

例:
「必須:
 - 各フレームワークの機能比較表
 - 性能ベンチマーク結果
 - 学習コストの評価
 
 推奨:
 - 実装例（Hello Worldレベル）
 
 オプション:
 - 将来性の考察」
```

**4. ターゲットオーディエンス（audience.md）**
```markdown
- 誰が読むか
- 読者の前提知識
- 読者が求める情報
- 適切な表現レベル

例:
「主読者: CTO、技術リード（非WASMエキスパート）
 前提知識: Web開発の基礎、JavaScriptは理解
 求める情報: 意思決定のための材料
 表現: 専門用語は注釈付き、図表を多用」
```

**5. 成果物形式（format.md）**
```markdown
- 文書形式（Markdown, PDF, プレゼン等）
- 構成（章立て）
- 長さ（ページ数、文字数）
- スタイル（フォーマル、カジュアル）

例:
「形式: Markdown（後でPDF変換）
 構成: 
   1. エグゼクティブサマリー
   2. 各フレームワーク詳細
   3. 比較表
   4. 推奨案
 長さ: 10-15ページ（A4想定）
 スタイル: ビジネス文書、客観的」
```

### docs/に書かないこと

**手順やプロセス:**
```
✗ 「まずGitHubでスター数を調べ、次に...」
  → これは skills/phase-01/SKILL.md に書く

✓ 「各フレームワークのコミュニティ規模を調査する」
  → What（何を）だけ、How（どう）はskills/
```

**ツールの指定:**
```
✗ 「Pythonスクリプトでベンチマークを実行」
  → これは skills/phase-02/SKILL.md に書く

✓ 「3つのフレームワークで性能ベンチマークを実施」
  → 何をするかだけ、ツールはskills/で決める
```

**実装の詳細:**
```
✗ 「関数Xを呼び出して結果をYに格納」
  → これは skills/のコード例に書く

✓ 「Hello Worldレベルの実装例を含める」
  → 含めるべき要素、実装方法はskills/
```

---

## skills/の構造と役割

### skills/に書くべきこと

**1. Phase目的（Objective）**
```markdown
このPhaseで何を達成するか

例:
「Phase 2の目的: 3つのフレームワークを評価軸に基づいて
 比較し、推奨案を提示する」
```

**2. 入力要件（Input Requirements）**
```markdown
- 必要なdocs/ファイル
- 前Phase成果物
- 外部情報源

例:
「必要なdocs/:
 - docs/scope.md（調査対象の確認）
 - docs/criteria.md（評価軸の定義）
 
 前Phase成果物:
 - outputs/phase-01/framework-data.md
 
 外部情報源:
 - 各フレームワークの公式ドキュメント」
```

**3. 手順（Procedure）**
```markdown
ステップバイステップの具体的な手順

例:
「Step 1: docs/criteria.mdから評価軸を抽出
   → 機能性、性能、学習コスト、コミュニティ
   
 Step 2: Phase 1データを各軸で評価
   → 各軸5段階スコアリング
   
 Step 3: 比較表作成（Markdown表形式）
   | フレームワーク | 機能性 | 性能 | 学習 | コミュ | 合計 |
   
 Step 4: 推奨案を記載（スコアと要件から導出）」
```

**4. 出力仕様（Output Specification）**
```markdown
生成すべきファイルと内容

例:
「成果物:
 - comparison-table.md: 比較表（4軸×3フレームワーク）
 - recommendation.md: 推奨案と理由（2-3段落）
 
 形式:
 - Markdown
 - 表はGitHub Flavored Markdown形式
 - 各評価の根拠をdocs/phase-01/から引用」
```

**5. 品質基準（Quality Criteria）**
```markdown
成果物が満たすべき基準

例:
「品質基準:
 □ 全評価軸がカバーされている
 □ 各スコアに根拠が明記されている
 □ 推奨案が評価結果と整合している
 □ docs/audience.mdのレベルに適合
 □ データソースが全て引用されている」
```

### skills/に書かないこと

**要件:**
```
✗ 「3社を比較する」
  → これは docs/scope.md に書く

✓ 「docs/scope.mdで指定された社数を比較する」
  → docs/を参照する形で書く
```

**背景・理由:**
```
✗ 「なぜこの調査が必要か...」
  → これは docs/background.md に書く

✓ 「docs/background.mdの課題を踏まえて調査を実施」
  → docs/を参照、背景自体はskills/に書かない
```

**ターゲット情報:**
```
✗ 「読者は経営層なので...」
  → これは docs/audience.md に書く

✓ 「docs/audience.mdで定義された読者レベルに合わせる」
  → docs/を参照、ターゲット情報はskills/に書かない
```

---

## 整合性の保ち方

### Rule 1: docs/変更時のskills/更新

**トリガー:**
```
docs/の変更で以下に影響がある場合:
  - 成果物の内容
  - 調査対象の数や範囲
  - 評価基準
  - ターゲット読者レベル
  - 成果物形式
```

**更新手順:**
```
1. 変更されたdocs/を特定
   例: docs/scope.md で「3社→5社」

2. 影響を受けるskills/を特定
   例: phase-01（調査範囲）, phase-02（比較対象）

3. skills/を更新
   例: phase-02/SKILL.md の手順を「5社分」に変更

4. CLAUDE.mdの見積もり更新
   例: Phase 2の見積もり 2.5h → 3.5h
```

**自動検出:**
```
docs/変更後に以下をチェック:
  - skills/内の「docs/XXX.md」参照箇所
  - 数値（3社、5軸等）の整合性
  - 成果物リストの整合性
```

### Rule 2: 矛盾の検出

**よくある矛盾パターン:**
```
パターン1: 数の不一致
  docs/scope.md: 「5社を調査」
  skills/phase-01/SKILL.md: 「3社分のデータ収集」
  → 検出: skills/を5社に更新

パターン2: 形式の不一致
  docs/format.md: 「PDF形式で納品」
  skills/phase-03/SKILL.md: 「Markdownファイル生成」
  → 検出: skills/にPDF変換手順を追加

パターン3: レベルの不一致
  docs/audience.md: 「非技術者向け」
  skills/phase-02/SKILL.md: 「専門用語を多用して記載」
  → 検出: skills/に「平易な表現」を追記
```

**検出タイミング:**
```
1. init-task完了時
   → Planner Agentが初期チェック

2. run-phase実行前
   → 該当Phaseのskills/とdocs/の整合性確認

3. Validator検証時
   → docs/要件とskills/手順の矛盾を検出
```

### Rule 3: 参照の明示

**skills/からdocs/への参照:**
```
明示的に記載:

✓ 良い例:
  「docs/scope.mdで指定された調査対象（3社）について...」
  「docs/criteria.mdの評価軸（機能性、性能、学習コスト）を使用」

✗ 悪い例:
  「3社について調査」（どこに書かれている？）
  「評価軸を使用」（どの評価軸？）
```

**benefits:**
```
- docs/とskills/の依存関係が明確
- docs/変更時の影響範囲が特定しやすい
- Validatorがdocs/要件を追跡しやすい
```

---

## 典型的なdocs/とskills/の組み合わせ

### Investigation Report の例

**docs/:**
```
docs/
├── background.md      # なぜこの調査か
├── scope.md           # 調査対象（3社、4軸）
├── sources.md         # 情報源リスト
├── criteria.md        # 評価基準
├── audience.md        # 読者（経営層）
└── format.md          # 報告書形式

→ What を定義
```

**skills/:**
```
skills/
├── phase-01/SKILL.md  # 調査・データ収集の手順
│   → docs/scope.mdの3社を公式サイト・GitHubで調査
│   → docs/sources.mdのリストから情報収集
│
├── phase-02/SKILL.md  # 比較・評価の手順
│   → docs/criteria.mdの4軸でスコアリング
│   → 比較表作成（Markdown表形式）
│
└── phase-03/SKILL.md  # 報告書作成の手順
    → docs/format.mdの構成に従って執筆
    → docs/audience.mdのレベルで表現

→ How を定義
```

### Technical Proposal の例

**docs/:**
```
docs/
├── problem.md         # 解決すべき課題
├── requirements.md    # 必須要件・推奨要件
├── constraints.md     # 技術的・予算的制約
├── stakeholders.md    # 意思決定者
└── success-criteria.md # 成功の定義

→ What を定義
```

**skills/:**
```
skills/
├── phase-01/SKILL.md  # 課題分析の手順
│   → docs/problem.mdを構造化
│   → 根本原因の特定プロセス
│
├── phase-02/SKILL.md  # 解決策設計の手順
│   → docs/requirements.mdを全て満たす設計
│   → docs/constraints.md内で実現可能な案
│
└── phase-03/SKILL.md  # 提案書作成の手順
    → docs/stakeholders.mdの関心事に対応
    → docs/success-criteria.mdに基づくKPI設定

→ How を定義
```

---

## ベストプラクティス

### 推奨1: docs/を先に完成させる
```
順序:
  1. init-taskでdocs/とskills/の骨組み作成
  2. docs/を先に詳細化（ユーザーとの対話）
  3. docs/確定後にskills/を詳細化
  4. run-phase実行

理由:
  - What が決まらないと How が決められない
  - docs/変更によるskills/手戻りを避ける
```

### 推奨2: skills/でdocs/を繰り返さない
```
✗ 悪い例:
  docs/scope.md: 「3社を機能、性能、コストで比較」
  skills/phase-02/SKILL.md:
    「3社（Blazor, Yew, Emscripten）を
     機能、性能、コストで比較する。
     機能は...、性能は...、コストは...」
  → docs/の内容を繰り返している

✓ 良い例:
  skills/phase-02/SKILL.md:
    「docs/scope.mdで定義された調査対象と評価軸を使用。
     Step 1: docs/scope.mdから対象と軸を抽出
     Step 2: 各対象を各軸で評価
     Step 3: 比較表作成」
  → docs/を参照、重複を避ける
```

### 推奨3: 変更履歴を記録
```
docs/を変更した場合:
  - CLAUDE.mdの「変更履歴」セクションに記録
  - 影響を受けたskills/をリストアップ
  - 見積もり時間を再計算

例:
「2026-02-05: docs/scope.md更新（3社→5社）
 影響: phase-01, phase-02 の見積もりを各+1h
 phase-01: 2.0h → 3.0h
 phase-02: 2.5h → 3.5h」
```

---

## トラブルシューティング

### 問題: docs/とskills/で内容が矛盾
```
症状:
  docs/: 「3社比較」
  skills/: 「5社について...」
  → Builder が混乱

対処:
  1. どちらが正しいか確認
  2. 正しい方に合わせて他方を修正
  3. 矛盾検出の仕組みを強化
```

### 問題: skills/が docs/を無視
```
症状:
  docs/に明記された要件をskills/が参照していない
  → Builder が要件を見落とす

対処:
  1. skills/のInput Requirementsに該当docs/を追加
  2. Procedureに「docs/XXX.mdを確認」ステップを追加
  3. Quality Criteriaに「docs/の要件を満たす」を追加
```

### 問題: docs/が変わったのにskills/が古いまま
```
症状:
  docs/更新後、skills/未更新で run-phase 実行
  → 古い仕様で成果物生成

対処:
  1. run-phase実行前に整合性チェック
  2. 不整合を検出したら警告
  3. ユーザーに更新を促す
```

---

## まとめ

docs/とskills/の関係は**「仕様と実装」**の関係。

**docs/:（仕様）**
- What を定義
- 変更されると skills/にも影響
- ユーザーと合意する内容

**skills/:（実装）**
- How を定義
- docs/を参照して手順化
- 効率化・最適化が可能

**整合性維持:**
- docs/優先、skills/は従属
- 変更時は影響範囲を確認
- 参照を明示して依存関係を明確化

この関係を守ることで、**柔軟かつ一貫性のある開発**が実現できる。