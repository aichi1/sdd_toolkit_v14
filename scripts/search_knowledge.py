#!/usr/bin/env python3
"""知識ベースを BM25 で検索する。

Usage:
    python3 search_knowledge.py "検索クエリ"
    python3 search_knowledge.py --top-k 5 --type skill "比較分析"
    python3 search_knowledge.py --json "技術調査"
"""

import argparse
import json
import os
import sys


def get_default_kb_dir() -> str:
    return os.path.expanduser("~/.sdd-knowledge")


def search(
    query: str,
    kb_dir: str,
    top_k: int = 10,
    type_filter: str | None = None,
    output_json: bool = False,
) -> list[dict]:
    """BM25 検索を実行する。

    Returns:
        検索結果のリスト。各要素は {id, name, type, description, score} を含む。
    """
    try:
        import bm25s
    except ImportError:
        print("Error: bm25s is not installed.", file=sys.stderr)
        print("Install with: pip install bm25s", file=sys.stderr)
        sys.exit(1)

    index_dir = os.path.join(kb_dir, "search-index")
    if not os.path.isdir(index_dir):
        print(
            "Error: Search index not found. Run build_search_index.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    meta_path = os.path.join(index_dir, "corpus_meta.json")
    if not os.path.exists(meta_path):
        print("Error: corpus_meta.json not found.", file=sys.stderr)
        sys.exit(1)

    # インデックスとメタデータを読み込み
    retriever = bm25s.BM25.load(index_dir)
    with open(meta_path, encoding="utf-8") as f:
        corpus_meta = json.load(f)

    # 検索実行
    tokens = bm25s.tokenize([query])
    results, scores = retriever.retrieve(tokens, k=min(top_k * 2, len(corpus_meta)))

    # 結果をフィルタリング・整形
    search_results = []
    for idx, score in zip(results[0], scores[0]):
        if score <= 0:
            continue
        meta = corpus_meta[idx]
        if type_filter and meta.get("type") != type_filter:
            continue
        search_results.append({
            "id": meta["id"],
            "name": meta.get("name", ""),
            "type": meta.get("type", ""),
            "description": meta.get("description", ""),
            "category_origin": meta.get("category_origin", ""),
            "score": round(float(score), 4),
        })
        if len(search_results) >= top_k:
            break

    return search_results


def main():
    parser = argparse.ArgumentParser(description="Search SDD knowledge base")
    parser.add_argument("query", nargs="*", help="Search query")
    parser.add_argument(
        "--kb-dir",
        default=get_default_kb_dir(),
        help="Knowledge base directory",
    )
    parser.add_argument(
        "--top-k", type=int, default=10, help="Number of results (default: 10)"
    )
    parser.add_argument(
        "--type",
        default=None,
        choices=["skill", "agent", "doc", "hook", "rule"],
        help="Filter by component type",
    )
    parser.add_argument(
        "--json", action="store_true", dest="output_json", help="Output as JSON"
    )
    args = parser.parse_args()

    query = " ".join(args.query) if args.query else input("Search query: ")
    if not query.strip():
        print("Error: Empty query", file=sys.stderr)
        sys.exit(1)

    results = search(
        query,
        args.kb_dir,
        top_k=args.top_k,
        type_filter=args.type,
        output_json=args.output_json,
    )

    if args.output_json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    elif not results:
        print("No results found.")
    else:
        print(f"Search results for: \"{query}\"\n")
        for i, r in enumerate(results, 1):
            print(f"  {i}. [{r['type']}] {r['name']} (score: {r['score']:.2f})")
            if r.get("description"):
                print(f"     {r['description'][:80]}")
            print()


if __name__ == "__main__":
    main()
