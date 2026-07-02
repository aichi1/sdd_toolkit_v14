#!/usr/bin/env python3
"""既存の docs-archive/ からコンポーネントを抽出し registry.json を初期化する。

Usage:
    python3 init_registry.py [--kb-dir PATH]
"""

import argparse
import glob
import json
import os
import sys

from registry_utils import (
    check_duplicate,
    extract_quality_criteria,
    extract_skill_description,
    extract_tags_from_content,
    generate_component_id,
    load_json_safe,
    now_iso,
    save_json,
    today_str,
    validate_component,
    validate_registry_entry,
)


def get_default_kb_dir() -> str:
    return os.path.expanduser("~/.sdd-knowledge")


def extract_skill(
    phase_dir: str, project_meta: dict, project_name: str
) -> tuple[dict | None, dict | None]:
    """SKILL.md からスキルコンポーネントとレジストリエントリを抽出する。

    Returns:
        (component_json, registry_entry) or (None, None)
    """
    skill_path = os.path.join(phase_dir, "SKILL.md")
    if not os.path.exists(skill_path):
        return None, None

    with open(skill_path, encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        return None, None

    phase_num = os.path.basename(phase_dir).replace("phase-", "")
    category = project_meta.get("category", "unknown")
    comp_id = generate_component_id(category, phase_num, "skill")

    description = extract_skill_description(content)
    tags = extract_tags_from_content(content)
    if category not in tags:
        tags.append(category)
    quality_criteria = extract_quality_criteria(content)

    component = {
        "id": comp_id,
        "type": "skill",
        "version": "1.0.0",
        "content": content,
        "placeholders": [],
        "quality_criteria": quality_criteria,
        "provenance": {
            "created_from": project_name,
            "created_at": today_str(),
            "updated_from": [],
            "updated_at": today_str(),
        },
        "adaptation_notes": "",
    }

    entry = {
        "id": comp_id,
        "name": f"{category}-phase{phase_num}",
        "type": "skill",
        "version": "1.0.0",
        "description": description,
        "tags": tags,
        "category_origin": category,
        "dependencies": {"required": [], "recommended": []},
        "metrics": {
            "used_in_projects": 1,
            "avg_effectiveness": 0.5,
            "confidence": 0.5,
            "last_used": today_str(),
        },
        "path": f"components/{comp_id}.json",
    }

    return component, entry


def extract_agent(
    agent_path: str, project_meta: dict, project_name: str
) -> tuple[dict | None, dict | None]:
    """エージェント定義からコンポーネントとレジストリエントリを抽出する。"""
    if not os.path.exists(agent_path):
        return None, None

    with open(agent_path, encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        return None, None

    basename = os.path.basename(agent_path).replace(".md", "")
    category = project_meta.get("category", "unknown")
    comp_id = f"agent-{basename}-v1"

    tags = extract_tags_from_content(content)
    tags.append(category)
    tags.append("agent")

    # YAML frontmatter から description を抽出
    description = basename
    desc_match = __import__("re").search(
        r"^description:\s*(.+)$", content, __import__("re").MULTILINE
    )
    if desc_match:
        description = desc_match.group(1).strip()

    component = {
        "id": comp_id,
        "type": "agent",
        "version": "1.0.0",
        "content": content,
        "placeholders": [],
        "quality_criteria": [],
        "provenance": {
            "created_from": project_name,
            "created_at": today_str(),
            "updated_from": [],
            "updated_at": today_str(),
        },
        "adaptation_notes": "",
    }

    entry = {
        "id": comp_id,
        "name": basename,
        "type": "agent",
        "version": "1.0.0",
        "description": description,
        "tags": tags,
        "category_origin": category,
        "dependencies": {"required": [], "recommended": []},
        "metrics": {
            "used_in_projects": 1,
            "avg_effectiveness": 0.5,
            "confidence": 0.5,
            "last_used": today_str(),
        },
        "path": f"components/{comp_id}.json",
    }

    return component, entry


def init_registry(kb_dir: str) -> dict:
    """docs-archive/ を走査し、registry.json を初期化する。"""
    archive_dir = os.path.join(kb_dir, "docs-archive")
    components_dir = os.path.join(kb_dir, "components")
    os.makedirs(components_dir, exist_ok=True)

    registry = {
        "version": "1.0",
        "last_updated": now_iso(),
        "stats": {"total_components": 0, "by_type": {}},
        "components": [],
    }

    if not os.path.isdir(archive_dir):
        print(f"Warning: docs-archive not found at {archive_dir}")
        save_json(registry, os.path.join(kb_dir, "registry.json"))
        return registry

    project_dirs = sorted(glob.glob(os.path.join(archive_dir, "*/")))
    if not project_dirs:
        print("Warning: No projects found in docs-archive/")
        save_json(registry, os.path.join(kb_dir, "registry.json"))
        return registry

    print(f"Scanning {len(project_dirs)} projects...")

    for project_dir in project_dirs:
        project_dir = project_dir.rstrip("/")
        project_name = os.path.basename(project_dir)

        # metadata.json を探す（ルートまたは meta/ 配下）
        meta = load_json_safe(os.path.join(project_dir, "metadata.json"))
        if meta is None:
            meta = load_json_safe(os.path.join(project_dir, "meta", "metadata.json"))
        if meta is None:
            print(f"  Skipping {project_name}: no metadata.json found")
            continue

        print(f"\n  Project: {project_name}")
        print(f"    Category: {meta.get('category', 'unknown')}")

        # skills/phase-*/SKILL.md を走査
        skill_dirs = sorted(
            glob.glob(os.path.join(project_dir, "skills", "phase-*"))
        )
        for phase_dir in skill_dirs:
            comp, entry = extract_skill(phase_dir, meta, project_name)
            if comp and entry:
                if not check_duplicate(registry, entry["id"]):
                    errors = validate_component(comp)
                    if errors:
                        print(f"    Warning: {entry['id']} has validation errors: {errors}")
                    else:
                        save_json(comp, os.path.join(components_dir, f"{comp['id']}.json"))
                        registry["components"].append(entry)
                        print(f"    Extracted skill: {entry['id']}")
                else:
                    print(f"    Skipping duplicate: {entry['id']}")

        # agents を走査（.claude/agents/generated/ または agents/）
        agent_dirs = [
            os.path.join(project_dir, ".claude", "agents", "generated"),
            os.path.join(project_dir, "agents"),
        ]
        for agent_dir in agent_dirs:
            if os.path.isdir(agent_dir):
                for agent_file in sorted(glob.glob(os.path.join(agent_dir, "*.md"))):
                    comp, entry = extract_agent(agent_file, meta, project_name)
                    if comp and entry:
                        if not check_duplicate(registry, entry["id"]):
                            save_json(
                                comp,
                                os.path.join(components_dir, f"{comp['id']}.json"),
                            )
                            registry["components"].append(entry)
                            print(f"    Extracted agent: {entry['id']}")

    # 統計を更新
    type_counts: dict[str, int] = {}
    for comp in registry["components"]:
        t = comp["type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    registry["stats"] = {
        "total_components": len(registry["components"]),
        "by_type": type_counts,
    }

    # 保存
    registry_path = os.path.join(kb_dir, "registry.json")
    save_json(registry, registry_path)
    print(f"\nRegistry initialized: {len(registry['components'])} components")
    return registry


def main():
    parser = argparse.ArgumentParser(
        description="Initialize component registry from docs-archive"
    )
    parser.add_argument(
        "--kb-dir",
        default=get_default_kb_dir(),
        help="Knowledge base directory (default: ~/.sdd-knowledge)",
    )
    args = parser.parse_args()

    registry = init_registry(args.kb_dir)

    print(f"\nSummary:")
    print(f"  Total components: {registry['stats']['total_components']}")
    for comp_type, count in registry["stats"].get("by_type", {}).items():
        print(f"    {comp_type}: {count}")


if __name__ == "__main__":
    main()
