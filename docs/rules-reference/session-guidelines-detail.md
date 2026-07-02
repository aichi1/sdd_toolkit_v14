# Starter Evolution Guidelines

セッション開始時の進化的アプローチ - 「いつも同じ開始儀式」から「状況に応じた最適な立ち上がり」へ

## 目的

- コンテキスト復元の時間を最小化（10分→3分以下）
- 前回の終了状態から最適な次タスクを自動推薦
- セッション目標の明確化と実行可能性の検証
- Claude Codeとの協働効率を段階的に向上

## セッション開始の進化レベル

### Level 0: マニュアル復元（初期状態）
```
時間: 10〜15分
手順:
1. CLAUDE.mdを開いて全体を読む
2. 前回何をやったか思い出す
3. カリキュラムのチェックボックスを見る
4. 今日何をするか考える
5. Claudeに指示を出す
```
**課題**: 毎回のオーバーヘッドが大きい、再現性が低い

### Level 1: チェックリスト化（現在推奨）
```
時間: 5〜7分
手順:
1. ✅ "Next Session Starter"セクションを読む（1分）
2. ✅ Git status / git log -1 で前回コミット確認（30秒）
3. ✅ Tests実行で現状把握（pytest / npm test）（1分）
4. ✅ 今日のゴールを1文で定義（1分）
5. ✅ Plan Modeでタスク分割と順序確認（2分）
```
**改善点**: 手順が明確、再現可能

### Level 2: 自動コンテキスト復元（次の目標）
```
時間: 2〜3分
手順:
1. ✅ claude code resume（前回の状態を自動ロード）
2. ✅ /quick-sync コマンド実行（次タスク候補を自動提示）
3. ✅ 提案から選択 or カスタマイズ（30秒）
4. ✅ Go! （即実行開始）
```
**実現に必要なもの**:
- Next Session Starterの構造化（JSON/YAML）
- Slash Commandの整備（/quick-sync, /suggest-next）
- Git hooks / Pre-session script

### Level 3: 適応的セッション設計（理想形）
```
時間: 1〜2分
特徴:
- 前回の振り返りから改善点を自動反映
- 学習進捗と所要時間から次タスクの難易度調整
- Claude Codeが「今日は○○から始めますか？」と提案
- セッション途中でも目標を動的調整
```

## Quick Sync Protocol（Level 1〜2で使用）

### 3分でできるコンテキスト復元

```markdown
## Quick Sync Checklist

### 1. Read Last Session (30秒)
- [ ] CLAUDE.md → "Next Session Starter"を読む
- [ ] 前回の終了コミットIDを確認

### 2. Verify Current State (1分)
- [ ] `git status` → 未コミット変更の有無
- [ ] `git log -1` → 最終コミットメッセージ
- [ ] Tests実行 → 現在のgreen/red状態
  ```bash
  # Backend
  cd backend && pytest -v
  
  # Frontend
  cd frontend && npm test
  ```

### 3. Define Today's Goal (1分)
**One-sentence Goal:**
> 例: FEでタスク一覧表示コンポーネントを作成し、BE APIと疎通確認まで

**Success Criteria (DoD):**
- [ ] 〇〇が動作する
- [ ] テストが△△件追加され、全てgreen
- [ ] □□をCLAUDE.mdに記録

### 4. Plan Tasks (30秒)
**Prompt to Claude:**
```
今日のゴール: [上記のOne-sentence Goal]
前回の終了状態: [コミットID, テスト状態]

まず「計画だけ」を5〜15分粒度のタスクリストで出して。
各タスクに所要時間見積もりと前提条件も。
私が承認してから実装を開始して。
```

### 5. Confirm & Go (30秒)
- [ ] 計画を確認して調整
- [ ] 最初のタスクを開始
```

## Slash Command Templates for Quick Start

### /quick-sync
```markdown
#title Quick Sync - Session Starter
前回のセッション終了状態から自動的にコンテキストを復元し、次タスクを提案。

**実行内容:**
1. CLAUDE.mdの"Next Session Starter"を読み込み
2. Git履歴（最終コミット、ブランチ、未コミット変更）を確認
3. テスト実行結果を取得
4. 次の論理的なステップを3〜5個提案
5. 所要時間と前提条件を明記

**出力形式:**
- 現在の状態サマリ（コミット、テスト、進捗）
- 推奨タスク（優先度順）
- 各タスクの所要時間見積もり
- 開始前の確認事項
```

### /suggest-next
```markdown
#title Suggest Next Task
カリキュラム進捗と前回の学びから、次に取り組むべきタスクを提案。

**判断基準:**
1. カリキュラムの順序（未完了の次のステップ）
2. 前回のProblem/Discovery（学習効果の高い順）
3. 依存関係（ブロッカーの解消優先）
4. 時間制約（残り時間で完結可能か）

**出力:**
- タスク候補3つ（理由付き）
- 各タスクの学習価値・リスク・所要時間
- 推奨順位と選択のトレードオフ
```

### /health-check
```markdown
#title Health Check - Environment & Dependencies
環境・依存関係・設定の健全性を素早くチェック。

**実行項目:**
- [ ] Node.js / Python バージョン確認
- [ ] 依存パッケージのインストール状態
- [ ] Docker / WSL2 の起動状態
- [ ] .envファイルの存在と必須変数
- [ ] テストスイートの実行可能性
- [ ] CLAUDE.mdの必須セクション存在確認

**出力:**
✅ OK / ⚠️ Warning / ❌ Error を明示し、Errorがあれば修正手順も。
```

## 状況別の最適スタート戦略

### ケース1: 前回から数日空いた
```
優先度:
1. /health-check で環境確認（依存関係が古い可能性）
2. /quick-sync で振り返り（記憶の再構築）
3. 軽めのタスクでウォームアップ（テスト追加など）
```

### ケース2: 前回エラーで終了した
```
優先度:
1. git log + エラーログの再確認
2. 小さく切り分けてデバッグ（TDD思考で）
3. 修正後、すぐにテスト追加（再発防止）
```

### ケース3: 新フェーズ突入（BE→FE など）
```
優先度:
1. 新領域の骨組み生成（Artifactsやテンプレ活用）
2. Plan Modeで全体像の合意
3. 最小限の動作確認（Hello World的なもの）
```

### ケース4: 順調に進んでいる
```
優先度:
1. /suggest-next で効率的なタスク選択
2. チャレンジングなタスクに挑戦（学習効果↑）
3. リファクタや改善タスクを織り交ぜる
```

## 進化のための継続的改善

### 毎セッション後にチェック
```markdown
## Starter Efficiency Metrics

**今回のセッション開始:**
- コンテキスト復元時間: __分
- 最初のコミットまでの時間: __分
- 計画と実績の差異: [想定より早い/遅い/ほぼ同じ]

**改善アクション:**
- [ ] Next Session Starterの記載を改善
- [ ] 新しいSlash Commandを追加
- [ ] ドキュメント構成の見直し
```

### 月次でのガイドライン見直し
- 各レベルの滞在時間と移行条件
- 自動化できるステップの洗い出し
- Slash Commandの実効性評価

## 自動化への道筋

### Phase 1: スクリプト化（即実装可能）
```bash
#!/bin/bash
# quick-sync.sh

echo "=== Quick Sync ==="
echo ""
echo "📝 Last Commit:"
git log -1 --oneline
echo ""
echo "🧪 Test Status:"
cd backend && pytest --tb=no -q
cd ../frontend && npm test -- --run
echo ""
echo "📋 Next Session Starter:"
grep -A 20 "Next Session Starter" CLAUDE.md
```

### Phase 2: Slash Command実装
- repo/.claude/commands/ にコマンド追加
- CLAUDE.mdの構造化（YAML frontmatter）
- テンプレート変数の活用

### Phase 3: AI駆動の提案
- 学習履歴の分析（所要時間、成功率）
- コンテキストベースの推薦（類似タスク）
- 適応的難易度調整

## まとめ: 進化の指針

| 段階 | 焦点 | 時間 | 次のステップ |
|-----|------|------|------------|
| Level 0 | 手探り | 10〜15分 | チェックリスト作成 |
| Level 1 | 再現性 | 5〜7分 | Slash Command整備 |
| Level 2 | 自動化 | 2〜3分 | AI提案の精度向上 |
| Level 3 | 適応化 | 1〜2分 | - |

**進化の原則:**
1. **計測する**: 開始時間を毎回記録
2. **小さく改善**: 1セッションで1つの改善
3. **テンプレ化**: うまくいったパターンはSlash Commandに
4. **柔軟性**: 完璧を求めず、状況に応じて調整

> 開始儀式は「作業」ではなく「加速装置」。
> 毎回少しずつ改善し、本質的な学習に時間を使う。