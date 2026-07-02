---
name: research-phase
type: skill-fragment
applicable_to: [research_report, internal_proposal]
requires: [doc-scope, doc-sources]
tags: [research, survey, data-collection, analysis]
---

## 情報収集・分析手順

### 前提
- docs/sources.md または docs/requirements.md に情報ソースが定義されていること
- 調査対象と評価軸が明確であること

### 手順
1. docs/ を読み、調査対象と評価軸を確認する
2. 各対象について情報を収集・整理する
3. 収集時に出典（情報源、取得日）を逐次記録する
4. 収集データを構造化する（表形式推奨）

### 品質チェック
- [ ] 全データに出典が明記されている
- [ ] 情報源の信頼性が確認されている
- [ ] 収集データが調査対象を網羅している

### 専門家エージェント
- **citations_researcher**: 出典整理時に呼び出し、引用の網羅性と正確性を確認
- **domain_sme**: 分析時に呼び出し、ドメイン固有の妥当性を確認
