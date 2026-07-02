#!/usr/bin/env python3
"""knowledge-curator のロジック（テスト用スタンドアロン版）。

レトロスペクティブ JSON を処理し、コンポーネントの改善候補を生成する。

Usage:
    python3 knowledge_curator.py <retrospective.json> [--kb-dir PATH]
"""

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from registry_utils import load_json_safe, now_iso


def get_default_kb_dir() -> str:
    return os.path.expanduser("~/.sdd-knowledge")


def find_related_components(
    registry: dict, category: str, lesson_keywords: list[str]
) -> list[dict]:
    """レッスンに関連するコンポーネントをレジストリから検索する。"""
    related = []
    for comp in registry.get("components", []):
        # カテゴリ一致
        if comp.get("category_origin") == category:
            related.append(comp)
            continue
        # タグマッチ
        comp_tags = set(comp.get("tags", []))
        if comp_tags & set(lesson_keywords):
            related.append(comp)
    return related


def extract_lesson_keywords(lesson: dict) -> list[str]:
    """レッスンからキーワードを抽出する。"""
    import re

    text = ""
    if isinstance(lesson, dict):
        text = f"{lesson.get('description', '')} {lesson.get('context', '')}"
    else:
        text = str(lesson)

    # 英語キーワード（4文字以上）
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", text.lower())
    return [w for w in words if len(w) > 3]


def generate_improvement_candidates(
    retro: dict, registry: dict
) -> list[dict]:
    """レトロスペクティブから改善候補を生成する。"""
    candidates = []
    category = retro.get("category", "unknown")
    lessons = retro.get("lessons", [])

    for lesson in lessons:
        keywords = extract_lesson_keywords(lesson)
        related = find_related_components(registry, category, keywords)

        lesson_desc = (
            lesson.get("description", str(lesson))
            if isinstance(lesson, dict)
            else str(lesson)
        )
        priority = (
            lesson.get("priority", "medium")
            if isinstance(lesson, dict)
            else "medium"
        )

        for comp in related:
            candidates.append({
                "timestamp": now_iso(),
                "action": "update_metadata",
                "component_id": comp["id"],
                "component_name": comp.get("name", ""),
                "lesson_source": retro.get("project_name", "unknown"),
                "lesson_description": lesson_desc,
                "suggested_changes": {
                    "add_tags": keywords[:3],
                    "update_quality_criteria": lesson_desc
                    if priority == "high"
                    else None,
                    "adjust_effectiveness": -0.05
                    if priority == "high"
                    else 0.0,
                },
                "priority": priority,
            })

    return candidates


def append_curator_candidates(candidates: list[dict], kb_dir: str) -> int:
    """改善候補を candidates.jsonl に追記する。"""
    path = os.path.join(kb_dir, "candidates.jsonl")
    os.makedirs(kb_dir, exist_ok=True)

    with open(path, "a", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return len(candidates)


def update_curator_memory(
    memory_lines: list[str], retro_name: str, candidate_count: int
) -> list[str]:
    """curator の MEMORY.md を更新する（200行制限対策付き）。

    Returns:
        更新後の行リスト。
    """
    MAX_LINES = 180  # 安全マージン付き

    new_entry = (
        f"- [{datetime.now().strftime('%Y-%m-%d')}] "
        f"Processed {retro_name}: {candidate_count} candidates generated"
    )

    # 処理履歴セクションを見つけるか新規追加
    history_idx = -1
    for i, line in enumerate(memory_lines):
        if "## Processing History" in line:
            history_idx = i
            break

    if history_idx < 0:
        memory_lines.append("\n## Processing History")
        memory_lines.append(new_entry)
    else:
        memory_lines.insert(history_idx + 1, new_entry)

    # 履歴エントリ数を制限（200行制限への対策）
    max_history = 20  # 最新20件のみ保持
    trimmed = []
    in_history = False
    history_count = 0

    for line in memory_lines:
        if "## Processing History" in line:
            in_history = True
            trimmed.append(line)
            continue
        if in_history and line.startswith("- ["):
            history_count += 1
            if history_count <= max_history:
                trimmed.append(line)
            continue
        if in_history and not line.startswith("- ["):
            in_history = False
        trimmed.append(line)

    memory_lines = trimmed

    return memory_lines


def main():
    parser = argparse.ArgumentParser(
        description="Process retrospective and generate improvement candidates"
    )
    parser.add_argument("retrospective", help="Path to retrospective JSON file")
    parser.add_argument("--kb-dir", default=get_default_kb_dir())
    args = parser.parse_args()

    # レトロスペクティブを読み込み
    retro = load_json_safe(args.retrospective)
    if retro is None:
        print(f"Error: Cannot read {args.retrospective}", file=sys.stderr)
        sys.exit(1)

    # レジストリを読み込み
    registry_path = os.path.join(args.kb_dir, "registry.json")
    registry = load_json_safe(registry_path)
    if registry is None:
        print(f"Warning: No registry.json at {registry_path}")
        registry = {"components": []}

    # 改善候補を生成
    candidates = generate_improvement_candidates(retro, registry)
    print(f"Generated {len(candidates)} improvement candidates")

    if candidates:
        count = append_curator_candidates(candidates, args.kb_dir)
        print(f"Appended {count} candidates to candidates.jsonl")

        # サマリー表示
        for c in candidates:
            print(f"  - [{c['priority']}] {c['component_id']}: {c['lesson_description'][:60]}")


if __name__ == "__main__":
    main()
