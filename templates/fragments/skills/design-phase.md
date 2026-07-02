---
name: design-phase
type: skill-fragment
applicable_to: [small_implementation, internal_proposal]
requires: [doc-requirements]
tags: [design, architecture, structure, planning]
---

## 設計・構造化手順

### 前提
- 要件が明確であること
- 制約が把握されていること

### 手順
1. 要件からコンポーネント/モジュールを特定する
2. コンポーネント間の依存関係を整理する
3. インターフェース（入出力）を定義する
4. ディレクトリ構造を設計する
5. 設計判断とその根拠を記録する

### 品質チェック
- [ ] 全要件がコンポーネントにマッピングされている
- [ ] 依存関係が循環していない
- [ ] インターフェースが明確に定義されている
- [ ] 設計判断の根拠が記録されている

### 専門家エージェント
- **software_architect**: 設計レビュー
