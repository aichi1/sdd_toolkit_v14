---
name: implementation-phase
type: skill-fragment
applicable_to: [small_implementation]
requires: [doc-requirements, doc-tech-stack]
tags: [implementation, coding, testing, script]
---

## 実装手順

### 前提
- docs/requirements.md に機能要件が定義されていること
- docs/tech-stack.md に使用技術が定義されていること

### 手順
1. docs/requirements.md を読み、機能要件・非機能要件を確認する
2. ディレクトリ構造を作成する（src/, tests/）
3. エントリポイントを実装する（CLI引数処理 or main関数）
4. コアロジックを実装する（入力バリデーション含む）
5. エラーハンドリングを実装する
6. テストを作成する（正常系 + 異常系）
7. テストを実行し全て PASS を確認
8. README.md を作成する

### コード構成指針
- エントリポイント（CLI引数処理）とロジック（処理本体）を分離
- 1ファイル 200行以下
- 入力バリデーションをロジック先頭で実施
- エラーは具体的メッセージを出す

### テスト構成指針
- 最低1つの正常系テスト
- 最低1つの異常系テスト
- pytest / unittest 等の標準フレームワーク使用

### 品質チェック
- [ ] README.md にインストール・実行手順がありコピペで動く
- [ ] テストが存在し PASS する
- [ ] コードがモジュール分割されている
- [ ] エラーハンドリングが実装されている

### 専門家エージェント
- **software_architect**: 設計・実装時に構成の妥当性を確認
- **qa_test_engineer**: テスト作成時にテスト観点の網羅性を確認
- **security_reviewer**: エラーハンドリング後にセキュリティ確認
