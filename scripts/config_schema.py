#!/usr/bin/env python3
"""config.json の初期生成スクリプト。

知識ベースの設定（閾値段階化、検索設定、抽出設定）を定義する。
"""

import json
import os
import sys

DEFAULT_CONFIG = {
    "version": "1.0",
    "registry": {
        "auto_extract": True,
        "confidence_threshold": {
            "partial_apply": 0.3,
            "standard_apply": 0.5,
            "full_apply": 0.7,
        },
        "pruning": {
            "enabled": False,
            "min_effectiveness": 0.3,
            "min_usage_count": 0,
        },
    },
    "search": {
        "engine": "bm25",
        "top_k": 20,
        "rerank_with_claude": True,
    },
    "extraction": {
        "auto_tag": True,
        "require_approval": True,
    },
}


def get_kb_dir() -> str:
    """知識ベースディレクトリのパスを返す。"""
    return os.path.expanduser("~/.sdd-knowledge")


def generate_config(kb_dir: str | None = None) -> dict:
    """デフォルトの config.json を生成する。"""
    return DEFAULT_CONFIG.copy()


def save_config(config: dict, kb_dir: str | None = None) -> str:
    """config.json を保存する。既に存在する場合は上書きしない。"""
    if kb_dir is None:
        kb_dir = get_kb_dir()

    config_path = os.path.join(kb_dir, "config.json")

    if os.path.exists(config_path):
        print(f"config.json already exists at {config_path}")
        print("Use --force to overwrite.")
        return config_path

    os.makedirs(kb_dir, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"config.json created at {config_path}")
    return config_path


def main():
    force = "--force" in sys.argv
    kb_dir = get_kb_dir()
    config_path = os.path.join(kb_dir, "config.json")

    if os.path.exists(config_path) and not force:
        print(f"config.json already exists at {config_path}")
        print("Use --force to overwrite.")
        sys.exit(0)

    config = generate_config()
    os.makedirs(kb_dir, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"config.json created at {config_path}")
    print(f"\nConfidence thresholds:")
    for level, val in config["registry"]["confidence_threshold"].items():
        print(f"  {level}: {val}")


if __name__ == "__main__":
    main()
