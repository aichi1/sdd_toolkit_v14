#!/usr/bin/env python3
"""candidates.jsonl の候補を registry.json + components/ に昇格する。

重複排除し、意味のある名前を付けてコンポーネントとして登録する。
既に登録済みの ID はメトリクスのみ更新する。

Usage:
    python3 promote_candidates.py [--kb-dir PATH] [--dry-run]
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from registry_utils import (
    check_duplicate,
    extract_quality_criteria,
    extract_tags_from_content,
    load_json_safe,
    now_iso,
    save_json,
    today_str,
    validate_component,
)


def get_default_kb_dir() -> str:
    return os.path.expanduser("~/.sdd-knowledge")


def extract_meaningful_name(content: str, component_type: str, fallback_id: str) -> str:
    """コンテンツから意味のある名前を抽出する。

    Skills: YAML frontmatter の name か、最初の見出しから抽出
    Agents: YAML frontmatter の name フィールドから抽出
    """
    # YAML frontmatter から name を抽出
    name_match = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
    if name_match:
        name = name_match.group(1).strip().strip("'\"")
        return name

    # description フィールドから抽出（agents 用）
    if component_type == "agent":
        desc_match = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)
        if desc_match:
            desc = desc_match.group(1).strip()
            # 短い英語名に変換
            en_words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", desc.lower())
            if en_words:
                return "-".join(en_words[:4])

    # 最初の # 見出しから抽出
    heading_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if heading_match:
        heading = heading_match.group(1).strip()
        # "Phase N: 説明" パターンから説明部分を抽出
        phase_desc = re.match(r"Phase\s+\d+[:\s]+(.+)", heading, re.IGNORECASE)
        if phase_desc:
            desc_part = phase_desc.group(1).strip()
            # 英語部分を抽出
            en_words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", desc_part.lower())
            if en_words:
                return "-".join(en_words[:4])
            # 日本語のみの場合はフォールバック
        else:
            en_words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", heading.lower())
            if en_words:
                return "-".join(en_words[:4])

    # フォールバック: suggested_id からプロジェクト名部分を除去
    return fallback_id


def extract_description(content: str, component_type: str) -> str:
    """コンテンツから説明文を抽出する。"""
    # YAML frontmatter の description
    desc_match = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)
    if desc_match:
        return desc_match.group(1).strip()

    # 最初の見出し
    heading_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if heading_match:
        return heading_match.group(1).strip()

    return f"Unknown {component_type}"


def generate_component_id(name: str, component_type: str) -> str:
    """意味のある名前からコンポーネント ID を生成する。"""
    safe_name = re.sub(r"[^a-z0-9-]", "-", name.lower())
    safe_name = re.sub(r"-+", "-", safe_name).strip("-")
    if not safe_name:
        safe_name = "unknown"
    return f"{component_type}-{safe_name}-v1"


def resolve_source_content(candidate: dict, kb_dir: str) -> str | None:
    """候補のソースファイルの内容を解決する。

    source_path → docs-archive 内のフォールバック の順で試行。
    """
    source_path = candidate.get("source_path", "")

    # 直接パスを試行
    if os.path.exists(source_path):
        with open(source_path, encoding="utf-8") as f:
            return f.read()

    # docs-archive 内で同名ファイルを探す
    archive_dir = os.path.join(kb_dir, "docs-archive")
    if not os.path.isdir(archive_dir):
        return None

    basename = os.path.basename(source_path)
    # source_project からアーカイブディレクトリを特定
    project = candidate.get("source_project", "")
    for entry in os.listdir(archive_dir):
        entry_path = os.path.join(archive_dir, entry)
        if not os.path.isdir(entry_path):
            continue
        # プロジェクト名がディレクトリ名に含まれるか確認
        if project and project.replace("_", "-") not in entry.replace("_", "-"):
            continue
        # スキルの場合: skills/phase-XX/SKILL.md を探す
        if candidate.get("component_type") == "skill":
            phase = candidate.get("source_phase", 0)
            skill_path = os.path.join(
                entry_path, "skills", f"phase-{phase:02d}", "SKILL.md"
            )
            if os.path.exists(skill_path):
                with open(skill_path, encoding="utf-8") as f:
                    return f.read()
        # エージェントの場合
        elif candidate.get("component_type") == "agent":
            for search_dir in [
                os.path.join(entry_path, "agents"),
                os.path.join(entry_path, ".claude", "agents", "generated"),
            ]:
                agent_path = os.path.join(search_dir, basename)
                if os.path.exists(agent_path):
                    with open(agent_path, encoding="utf-8") as f:
                        return f.read()
        # その他（hook, rule）
        else:
            candidate_path = os.path.join(entry_path, basename)
            if os.path.exists(candidate_path):
                with open(candidate_path, encoding="utf-8") as f:
                    return f.read()

    return None


def load_candidates(kb_dir: str) -> list[dict]:
    """candidates.jsonl を読み込む。"""
    candidates_path = os.path.join(kb_dir, "candidates.jsonl")
    if not os.path.exists(candidates_path):
        return []

    candidates = []
    with open(candidates_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                candidates.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"  Warning: Invalid JSON at line {line_num}, skipping")
    return candidates


def deduplicate_candidates(candidates: list[dict]) -> dict[str, dict]:
    """suggested_id でグループ化し、最新の候補を返す。"""
    by_id: dict[str, dict] = {}
    for c in candidates:
        sid = c.get("suggested_id", "")
        if not sid:
            continue
        # component_type が不明なものはスキップ
        if c.get("component_type") not in ("skill", "agent", "hook", "rule"):
            continue
        # 同一 ID は最新（後に出現したもの）が勝つ
        by_id[sid] = c
    return by_id


def promote(kb_dir: str, dry_run: bool = False) -> dict:
    """候補を registry.json に昇格する。"""
    registry_path = os.path.join(kb_dir, "registry.json")
    components_dir = os.path.join(kb_dir, "components")

    registry = load_json_safe(registry_path)
    if registry is None:
        registry = {
            "version": "1.0",
            "last_updated": now_iso(),
            "stats": {"total_components": 0, "by_type": {}},
            "components": [],
        }

    os.makedirs(components_dir, exist_ok=True)

    print("Loading candidates.jsonl...")
    candidates = load_candidates(kb_dir)
    print(f"  Total candidates: {len(candidates)}")

    unique = deduplicate_candidates(candidates)
    print(f"  Unique candidates (after dedup): {len(unique)}")

    stats = {"promoted": 0, "updated": 0, "skipped_no_content": 0, "skipped_invalid": 0}
    by_type = {"skill": 0, "agent": 0, "hook": 0, "rule": 0}

    for suggested_id, candidate in sorted(unique.items()):
        comp_type = candidate["component_type"]

        # ソースコンテンツを取得
        content = resolve_source_content(candidate, kb_dir)
        if not content or not content.strip():
            stats["skipped_no_content"] += 1
            continue

        # 意味のある名前を生成
        name = extract_meaningful_name(content, comp_type, suggested_id)
        comp_id = generate_component_id(name, comp_type)
        description = extract_description(content, comp_type)
        tags = candidate.get("auto_tags", [])
        if not tags:
            tags = extract_tags_from_content(content)
        project_name = candidate.get("source_project", "unknown")

        # 重複チェック
        if check_duplicate(registry, comp_id):
            # メトリクスを更新（used_in_projects, confidence）
            for entry in registry["components"]:
                if entry["id"] == comp_id:
                    # 別プロジェクトからの候補なら使用回数を増加
                    prov_project = entry.get("metrics", {}).get("_source_project", "")
                    if prov_project != project_name:
                        metrics = entry.setdefault("metrics", {})
                        used = metrics.get("used_in_projects", 1) + 1
                        metrics["used_in_projects"] = used
                        metrics["confidence"] = min(0.95, 0.5 + 0.1 * used)
                        metrics["last_used"] = today_str()
                        stats["updated"] += 1
                    break
            continue

        # コンポーネント JSON を作成
        quality_criteria = extract_quality_criteria(content) if comp_type == "skill" else []

        component = {
            "id": comp_id,
            "type": comp_type,
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

        errors = validate_component(component)
        if errors:
            print(f"  Warning: {comp_id} validation errors: {errors}")
            stats["skipped_invalid"] += 1
            continue

        # レジストリエントリを作成
        entry = {
            "id": comp_id,
            "name": name,
            "type": comp_type,
            "version": "1.0.0",
            "description": description,
            "tags": tags,
            "category_origin": project_name,
            "dependencies": {"required": [], "recommended": []},
            "metrics": {
                "used_in_projects": 1,
                "avg_effectiveness": 0.5,
                "confidence": 0.5,
                "last_used": today_str(),
                "_source_project": project_name,
            },
            "path": f"components/{comp_id}.json",
        }

        if not dry_run:
            save_json(component, os.path.join(components_dir, f"{comp_id}.json"))
            registry["components"].append(entry)

        by_type[comp_type] = by_type.get(comp_type, 0) + 1
        stats["promoted"] += 1

    # 統計を更新
    type_counts: dict[str, int] = {}
    for comp in registry["components"]:
        t = comp["type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    registry["stats"] = {
        "total_components": len(registry["components"]),
        "by_type": type_counts,
    }
    registry["last_updated"] = now_iso()

    if not dry_run:
        save_json(registry, registry_path)

    # サマリー出力
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Promotion Summary:")
    print(f"  New components promoted: {stats['promoted']}")
    for t, c in sorted(by_type.items()):
        if c > 0:
            print(f"    {t}: {c}")
    print(f"  Existing components updated: {stats['updated']}")
    print(f"  Skipped (no content found): {stats['skipped_no_content']}")
    print(f"  Skipped (validation errors): {stats['skipped_invalid']}")
    print(f"  Registry total: {registry['stats']['total_components']} components")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Promote candidates from candidates.jsonl to registry.json"
    )
    parser.add_argument(
        "--kb-dir",
        default=get_default_kb_dir(),
        help="Knowledge base directory (default: ~/.sdd-knowledge)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be promoted without making changes",
    )
    args = parser.parse_args()

    promote(args.kb_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
