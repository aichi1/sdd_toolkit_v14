#!/usr/bin/env python3
"""
PreToolUse hook: outputs/ にファイルを書き込む前に docs/ の存在と最低限の仕様ファイルを確認する。

- docs/ が存在しない → 警告（ブロックはしない）
- docs/_manifest.json がある → required_files を検証し、不足があれば警告
- manifest がない → docs/ に Markdown が1つでもあればOK（空なら警告）
"""
import json
import sys
import os
import glob

MANIFEST = "_manifest.json"

def _warn(message: str):
    json.dump({"message": message}, sys.stdout)

def main():
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    # outputs/ 配下に書き込む操作だけ対象にする（Write / Edit 共通）
    if not isinstance(file_path, str) or not file_path.startswith("outputs/"):
        sys.exit(0)

    cwd = data.get("cwd", os.getcwd())
    docs_dir = os.path.join(cwd, "docs")
    manifest_path = os.path.join(docs_dir, MANIFEST)

    if not os.path.isdir(docs_dir):
        _warn("⚠️ SDD警告: docs/ ディレクトリが存在しません。仕様なしで成果物を生成しています。先に /init-task で仕様を定義することを推奨します。")
        sys.exit(0)

    # manifest がある場合は required_files を検証
    if os.path.isfile(manifest_path):
        try:
            manifest = json.load(open(manifest_path, "r", encoding="utf-8"))
            required = manifest.get("required_files", []) or []
            missing = [p for p in required if not os.path.isfile(os.path.join(docs_dir, p))]
            if missing:
                _warn("⚠️ SDD警告: docs/ に不足ファイルがあります（" + ", ".join(missing) + "）。/init-task の仕様ファイル作成が未完了か、削除された可能性があります。")
            sys.exit(0)
        except Exception:
            _warn("⚠️ SDD警告: docs/_manifest.json の読み取りに失敗しました。仕様ファイルの整合性を確認してください。")
            sys.exit(0)

    # manifest がない場合は、docs/ に Markdown が1つでもあればOK（空なら警告）
    md_files = glob.glob(os.path.join(docs_dir, "*.md"))
    if len(md_files) == 0:
        _warn("⚠️ SDD警告: docs/ は存在しますが仕様ファイル（*.md）が見つかりません。先に /init-task で仕様を定義することを推奨します。")
        sys.exit(0)

    sys.exit(0)

if __name__ == "__main__":
    main()
