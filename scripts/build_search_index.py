#!/usr/bin/env python3
"""registry.json から BM25 検索インデックスを構築する。

Usage:
    python3 build_search_index.py [--kb-dir PATH]
"""

import argparse
import json
import os
import sys


def get_default_kb_dir() -> str:
    return os.path.expanduser("~/.sdd-knowledge")


def build_index(kb_dir: str) -> int:
    """BM25 検索インデックスを構築する。

    Returns:
        インデックスに追加されたドキュメント数。
    """
    try:
        import bm25s
    except ImportError:
        print("Error: bm25s is not installed.", file=sys.stderr)
        print("Install with: pip install bm25s", file=sys.stderr)
        sys.exit(1)

    registry_path = os.path.join(kb_dir, "registry.json")
    if not os.path.exists(registry_path):
        print(f"Error: registry.json not found at {registry_path}", file=sys.stderr)
        print("Run init_registry.py first.", file=sys.stderr)
        sys.exit(1)

    with open(registry_path, encoding="utf-8") as f:
        registry = json.load(f)

    components = registry.get("components", [])
    if not components:
        print("Warning: No components in registry.json")
        return 0

    index_dir = os.path.join(kb_dir, "search-index")
    os.makedirs(index_dir, exist_ok=True)

    # コーパスとメタデータを構築
    corpus = []
    corpus_meta = []

    for comp in components:
        # コンポーネント実体からコンテンツを取得
        comp_file = os.path.join(kb_dir, comp.get("path", ""))
        content_text = ""
        if os.path.exists(comp_file):
            try:
                with open(comp_file, encoding="utf-8") as f:
                    comp_data = json.load(f)
                content_text = comp_data.get("content", "")
            except (json.JSONDecodeError, IOError):
                pass

        # 検索対象テキスト: description + tags + content
        text = (
            f"{comp.get('description', '')} "
            f"{' '.join(comp.get('tags', []))} "
            f"{content_text}"
        )
        corpus.append(text)
        corpus_meta.append({
            "id": comp["id"],
            "name": comp.get("name", ""),
            "type": comp.get("type", ""),
            "description": comp.get("description", ""),
            "category_origin": comp.get("category_origin", ""),
        })

    print(f"Building index from {len(corpus)} documents...")

    # BM25 インデックスを構築
    tokens = bm25s.tokenize(corpus)
    retriever = bm25s.BM25()
    retriever.index(tokens)
    retriever.save(index_dir)

    # メタデータを保存
    meta_path = os.path.join(index_dir, "corpus_meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(corpus_meta, f, indent=2, ensure_ascii=False)

    print(f"Search index built: {len(corpus)} documents")
    print(f"  Index: {index_dir}/")
    print(f"  Metadata: {meta_path}")

    return len(corpus)


def main():
    parser = argparse.ArgumentParser(
        description="Build BM25 search index from registry"
    )
    parser.add_argument(
        "--kb-dir",
        default=get_default_kb_dir(),
        help="Knowledge base directory (default: ~/.sdd-knowledge)",
    )
    args = parser.parse_args()
    build_index(args.kb_dir)


if __name__ == "__main__":
    main()
