# Phase {N}: {Phase Name}

> このテンプレートは small_implementation カテゴリ用です。
> プレースホルダー `{...}` を実際の値に置換してください。

## Objective
{このフェーズが生み出すものの明確な記述}

## Input Requirements
- docs/requirements.md（目的・スコープ・成功条件）
- docs/plan.md（Phase構成）
- {前フェーズの出力があれば記載}

## Output Specification
成果物ディレクトリ: `outputs/phase-{N}/`

### 必須ファイル構成
```
outputs/phase-{N}/
├── README.md          # インストール・実行手順
├── src/               # ソースコード
│   ├── {main_module}  # エントリポイント
│   └── {modules...}   # 機能モジュール（分割）
└── tests/             # テストコード
    └── test_{name}.py # 最低1つの自動テスト
```

### README.md の必須セクション
1. **概要**（何をするツール/スクリプトか、1-2行）
2. **前提条件**（必要なランタイム、バージョン）
3. **インストール手順**（依存関係含む、コピペで実行可能に）
4. **使い方**（基本的なコマンド例、入出力サンプル）
5. **エラー時の対処**（よくあるエラーと対応）

### ソースコードの構成指針
- エントリポイント（CLI引数処理）とロジック（処理本体）を分離する
- 1ファイルが 200行を超える場合はモジュール分割を検討
- 入力バリデーションをロジックの先頭で行う
- エラーは具体的なメッセージを出して適切に処理する（静かに無視しない）

### テストの構成指針
- 最低1つの正常系テスト（期待入力→期待出力）
- 最低1つの異常系テスト（不正入力→適切なエラー）
- テストは `pytest` / `unittest` 等の標準フレームワークを使用

## Quality Criteria
- [ ] README.md にインストール・実行手順があり、コピペで動く
- [ ] 入力エラーや例外の扱いがコード内で実装され、README にも説明がある
- [ ] 最低1つの自動テストがあり、実行して PASS する
- [ ] コードがモジュール分割され、各ファイルの責務が明確
- [ ] docs/requirements.md の成功条件を全て満たしている

## Procedure
1. docs/requirements.md を読み、機能要件・非機能要件を確認する
2. ディレクトリ構造を作成する（src/, tests/）
3. エントリポイントを実装する（CLI引数処理 or main関数）
4. コアロジックを実装する（入力バリデーション含む）
5. エラーハンドリングを実装する（不正入力、ファイル不在等）
6. テストを作成する（正常系1つ + 異常系1つ以上）
7. テストを実行し全て PASS することを確認する
8. README.md を作成する（上記必須セクション）
9. outputs/phase-{N}/ に保存し .metadata.json を作成する

### 専門家エージェントの活用（該当する場合）
- **software_architect**: Step 2-4 の設計・実装時に呼び出し、構成の妥当性を確認
- **qa_test_engineer**: Step 6 のテスト作成時に呼び出し、テスト観点の網羅性を確認
- **security_reviewer**: Step 5 のエラーハンドリング後に呼び出し、セキュリティ上の問題を確認

## Common Pitfalls
- README にインストール手順を書き忘れる → Step 8 で必ず作成
- テストを後回しにして省略 → Step 6 は省略不可
- エラー処理が雑（bare except, 無言の pass）→ 具体的メッセージを出す
- 全ロジックを1ファイルに詰める → 200行超えたら分割

## Troubleshooting

### よくある問題

| 症状 | 原因 | 対処法 | 再開ポイント |
|------|------|--------|------------|
| `ModuleNotFoundError` でインポートエラー | 依存パッケージが未インストール | `pip install {package}` を実行。requirements.txt があれば `pip install -r requirements.txt` | Step 3 から再開 |
| テストが FAIL する（`AssertionError`） | 実装ロジックのバグ、またはテストの期待値が不正 | エラーメッセージを確認し、実装とテストのどちらが誤りか特定する。`pytest -v --tb=long` で詳細を確認 | Step 6 から再開 |
| `PermissionError` でファイルに書き込めない | 出力先ディレクトリの権限不足 | `ls -la` で権限を確認。必要なら `chmod` で修正。または別の出力先を指定 | Step 4 から再開 |
| Docker コンテナが起動しない | ポート競合、ボリュームマウントエラー、設定ファイル不備 | `docker logs <container>` でエラーを確認。`docker compose down -v` で完全リセット後に再起動 | Step 3 から再開 |

## Examples
```python
# src/main.py - エントリポイント
import sys
from .converter import convert

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m src.main <input.csv>", file=sys.stderr)
        sys.exit(1)
    # ...
```
