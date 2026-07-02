#!/usr/bin/env python3
"""プロジェクトからコンポーネント候補を抽出し candidates.jsonl に追記する。

Usage:
    python3 extract_components.py <project_root> [--kb-dir PATH]
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime

# registry_utils を同ディレクトリからインポート
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from registry_utils import (
    extract_quality_criteria,
    extract_skill_description,
    extract_tags_from_content,
    generate_component_id,
    load_json_safe,
    now_iso,
)


def get_default_kb_dir() -> str:
    return os.path.expanduser("~/.sdd-knowledge")


def extract_skill_name_from_content(content: str, phase_num: str) -> str:
    """SKILL.md のコンテンツから意味のある名前を抽出する。"""
    # YAML frontmatter の name フィールド
    name_match = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
    if name_match:
        return name_match.group(1).strip().strip("'\"")

    # 最初の見出しから "Phase N: 説明" パターンを抽出
    heading_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if heading_match:
        heading = heading_match.group(1).strip()
        phase_desc = re.match(r"Phase\s+\d+[:\s]+(.+)", heading, re.IGNORECASE)
        if phase_desc:
            desc_part = phase_desc.group(1).strip()
            en_words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", desc_part.lower())
            if en_words:
                return "-".join(en_words[:4])

    return f"phase{phase_num}"


def extract_candidates_from_skills(project_root: str, project_name: str) -> list[dict]:
    """skills/phase-*/SKILL.md からスキル候補を抽出する。"""
    candidates = []
    skill_dirs = sorted(
        glob.glob(os.path.join(project_root, "skills", "phase-*"))
    )
    for phase_dir in skill_dirs:
        skill_path = os.path.join(phase_dir, "SKILL.md")
        if not os.path.exists(skill_path):
            continue
        with open(skill_path, encoding="utf-8") as f:
            content = f.read()
        if not content.strip():
            continue

        phase_num = os.path.basename(phase_dir).replace("phase-", "")
        tags = extract_tags_from_content(content)
        skill_name = extract_skill_name_from_content(content, phase_num)

        candidates.append({
            "timestamp": now_iso(),
            "source_project": project_name,
            "source_phase": int(phase_num),
            "component_type": "skill",
            "source_path": skill_path,
            "suggested_id": f"skill-{skill_name}-v1",
            "auto_tags": tags,
        })
    return candidates


def extract_candidates_from_agents(project_root: str, project_name: str) -> list[dict]:
    """エージェント定義から候補を抽出する。"""
    candidates = []
    agent_dirs = [
        os.path.join(project_root, ".claude", "agents", "generated"),
        os.path.join(project_root, ".claude", "agents"),
        os.path.join(project_root, "agents"),
    ]
    for agent_dir in agent_dirs:
        if not os.path.isdir(agent_dir):
            continue
        for agent_file in sorted(glob.glob(os.path.join(agent_dir, "*.md"))):
            with open(agent_file, encoding="utf-8") as f:
                content = f.read()
            if not content.strip():
                continue

            basename = os.path.basename(agent_file).replace(".md", "")
            tags = extract_tags_from_content(content)
            tags.append("agent")

            candidates.append({
                "timestamp": now_iso(),
                "source_project": project_name,
                "source_phase": 0,
                "component_type": "agent",
                "source_path": agent_file,
                "suggested_id": f"agent-{basename}-v1",
                "auto_tags": tags,
            })
    return candidates


def extract_candidates_from_hooks(project_root: str, project_name: str) -> list[dict]:
    """hooks 設定から候補を抽出する。"""
    candidates = []
    settings_path = os.path.join(project_root, ".claude", "settings.json")
    if not os.path.exists(settings_path):
        return candidates

    settings = load_json_safe(settings_path)
    if not settings or "hooks" not in settings:
        return candidates

    for event_type, hooks in settings["hooks"].items():
        for i, hook in enumerate(hooks):
            candidates.append({
                "timestamp": now_iso(),
                "source_project": project_name,
                "source_phase": 0,
                "component_type": "hook",
                "source_path": settings_path,
                "suggested_id": f"hook-{event_type}-{i}-v1",
                "auto_tags": [event_type, "hook", hook.get("type", "command")],
            })
    return candidates


def extract_candidates_from_rules(project_root: str, project_name: str) -> list[dict]:
    """ルールファイルから候補を抽出する。"""
    candidates = []
    rules_dir = os.path.join(project_root, ".claude", "rules")
    if not os.path.isdir(rules_dir):
        return candidates

    for rule_file in sorted(glob.glob(os.path.join(rules_dir, "*.md"))):
        with open(rule_file, encoding="utf-8") as f:
            content = f.read()
        if not content.strip():
            continue

        basename = os.path.basename(rule_file).replace(".md", "")
        tags = extract_tags_from_content(content)
        tags.append("rule")

        candidates.append({
            "timestamp": now_iso(),
            "source_project": project_name,
            "source_phase": 0,
            "component_type": "rule",
            "source_path": rule_file,
            "suggested_id": f"rule-{basename}-v1",
            "auto_tags": tags,
        })
    return candidates


def append_candidates(candidates: list[dict], kb_dir: str) -> int:
    """candidates.jsonl に追記する。"""
    candidates_path = os.path.join(kb_dir, "candidates.jsonl")
    os.makedirs(kb_dir, exist_ok=True)

    with open(candidates_path, "a", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    return len(candidates)


def main():
    parser = argparse.ArgumentParser(
        description="Extract component candidates from a project"
    )
    parser.add_argument("project_root", help="Path to project root directory")
    parser.add_argument(
        "--kb-dir",
        default=get_default_kb_dir(),
        help="Knowledge base directory (default: ~/.sdd-knowledge)",
    )
    parser.add_argument(
        "--project-name",
        default=None,
        help="Project name (default: directory name)",
    )
    args = parser.parse_args()

    project_root = os.path.abspath(args.project_root)
    if not os.path.isdir(project_root):
        print(f"Error: {project_root} is not a directory", file=sys.stderr)
        sys.exit(1)

    project_name = args.project_name or os.path.basename(project_root)

    print(f"Extracting components from: {project_root}")
    print(f"Project name: {project_name}")

    all_candidates = []

    skills = extract_candidates_from_skills(project_root, project_name)
    print(f"  Skills: {len(skills)} candidates")
    all_candidates.extend(skills)

    agents = extract_candidates_from_agents(project_root, project_name)
    print(f"  Agents: {len(agents)} candidates")
    all_candidates.extend(agents)

    hooks = extract_candidates_from_hooks(project_root, project_name)
    print(f"  Hooks: {len(hooks)} candidates")
    all_candidates.extend(hooks)

    rules = extract_candidates_from_rules(project_root, project_name)
    print(f"  Rules: {len(rules)} candidates")
    all_candidates.extend(rules)

    if all_candidates:
        count = append_candidates(all_candidates, args.kb_dir)
        print(f"\nTotal: {count} candidates appended to candidates.jsonl")
    else:
        print("\nNo candidates found.")


if __name__ == "__main__":
    main()
