#!/usr/bin/env python3
"""タスク記述に基づいてアクティブコンテキストを生成する。

Usage:
    python3 generate_context.py "技術調査レポート WebAssembly フレームワーク比較"
    python3 generate_context.py --output ./active-context.md "検索クエリ"
"""

import argparse
import json
import os
import sys

# 同ディレクトリのモジュールを再利用
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def get_default_kb_dir() -> str:
    return os.path.expanduser("~/.sdd-knowledge")


def load_retrospective_lessons(kb_dir: str) -> list[dict]:
    """retrospectives/summary.json からクロスカテゴリパターンを取得する。"""
    summary_path = os.path.join(kb_dir, "retrospectives", "summary.json")
    if not os.path.exists(summary_path):
        return []

    try:
        with open(summary_path, encoding="utf-8") as f:
            summary = json.load(f)
        return summary.get("cross_category_patterns", [])
    except (json.JSONDecodeError, IOError):
        return []


def load_category_lessons(kb_dir: str, category: str) -> list[str]:
    """特定カテゴリのレトロスペクティブから教訓を抽出する。"""
    retro_dir = os.path.join(kb_dir, "retrospectives")
    if not os.path.isdir(retro_dir):
        return []

    lessons = []
    import glob

    for retro_file in glob.glob(os.path.join(retro_dir, "*.json")):
        if os.path.basename(retro_file) == "summary.json":
            continue
        try:
            with open(retro_file, encoding="utf-8") as f:
                retro = json.load(f)
            if retro.get("category") == category:
                for lesson in retro.get("lessons", []):
                    if isinstance(lesson, dict):
                        lessons.append(lesson.get("description", str(lesson)))
                    else:
                        lessons.append(str(lesson))
        except (json.JSONDecodeError, IOError):
            continue
    return lessons


def generate_context(
    task_description: str,
    kb_dir: str,
    max_components: int = 10,
    content_limit: int = 500,
) -> str:
    """タスク記述から関連知識コンテキストを生成する。

    Returns:
        Markdown 形式のアクティブコンテキスト文字列。
    """
    lines = [
        "# Active Knowledge Context",
        "",
        f"**Task**: {task_description}",
        "",
    ]

    # BM25 検索で関連コンポーネントを取得
    try:
        from search_knowledge import search

        results = search(task_description, kb_dir, top_k=max_components)
    except (ImportError, SystemExit):
        results = []
        lines.append("> Warning: Search index not available. Run build_search_index.py first.")
        lines.append("")

    if results:
        lines.append("## Relevant Components")
        lines.append("")
        for r in results:
            lines.append(f"### [{r['type']}] {r['name']} (relevance: {r['score']:.2f})")
            if r.get("description"):
                lines.append(f"_{r['description']}_")

            # コンポーネントの content を取得（制限あり）
            comp_path = os.path.join(kb_dir, f"components/{r['id']}.json")
            if os.path.exists(comp_path):
                try:
                    with open(comp_path, encoding="utf-8") as f:
                        comp = json.load(f)
                    content = comp.get("content", "")
                    if len(content) > content_limit:
                        content = content[:content_limit] + "..."
                    lines.append(f"\n```\n{content}\n```")
                except (json.JSONDecodeError, IOError):
                    pass
            lines.append("")

    # レトロスペクティブからの教訓
    patterns = load_retrospective_lessons(kb_dir)
    if patterns:
        lines.append("## Cross-Category Lessons")
        lines.append("")
        for p in patterns:
            occurrences = p.get("occurrences", "?")
            pattern_text = p.get("pattern", str(p))
            lines.append(f"- {pattern_text} ({occurrences} occurrences)")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate active knowledge context for a task"
    )
    parser.add_argument("task", nargs="*", help="Task description")
    parser.add_argument("--kb-dir", default=get_default_kb_dir())
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path (default: ~/.sdd-knowledge/active-context.md)",
    )
    parser.add_argument(
        "--max-components", type=int, default=10, help="Max components to include"
    )
    args = parser.parse_args()

    task = " ".join(args.task) if args.task else input("Task description: ")
    if not task.strip():
        print("Error: Empty task description", file=sys.stderr)
        sys.exit(1)

    context = generate_context(task, args.kb_dir, max_components=args.max_components)

    output_path = args.output or os.path.join(args.kb_dir, "active-context.md")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(context)

    print(f"Active context written to {output_path}")
    print(f"  Components included: {context.count('### [')}")


if __name__ == "__main__":
    main()
