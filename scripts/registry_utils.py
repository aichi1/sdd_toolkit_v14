#!/usr/bin/env python3
"""レジストリ操作ユーティリティ。
コンポーネントの抽出・ID生成・重複チェック・バリデーションを提供。
"""

import json
import os
import re
from datetime import datetime


def extract_tags_from_content(content: str) -> list[str]:
    """Markdown コンテンツからタグ候補を抽出する。

    ヘッディングから英語キーワード、日本語キーフレーズの両方を抽出。
    """
    headings = re.findall(r"^#+\s+(.+)$", content, re.MULTILINE)
    tags = set()
    for h in headings:
        # 英語キーワード（4文字以上）
        en_words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", h.lower())
        tags.update(w for w in en_words if len(w) > 3)
    return sorted(tags)[:10]


def generate_component_id(
    category: str, phase_num: str, comp_type: str, version: str = "v1"
) -> str:
    """コンポーネント ID を生成する。

    形式: {type}-{category}-phase{num}-{version}
    """
    safe_category = re.sub(r"[^a-z0-9-]", "-", category.lower())
    return f"{comp_type}-{safe_category}-phase{phase_num}-{version}"


def check_duplicate(registry: dict, comp_id: str) -> bool:
    """レジストリ内の重複をチェックする。"""
    return any(c["id"] == comp_id for c in registry.get("components", []))


def validate_component(comp: dict) -> list[str]:
    """コンポーネント JSON のスキーマを検証する。

    Returns:
        エラーメッセージのリスト。空なら valid。
    """
    errors = []
    required_fields = ["id", "type", "version", "content"]
    for field in required_fields:
        if field not in comp:
            errors.append(f"Missing required field: {field}")

    if "provenance" in comp:
        prov = comp["provenance"]
        if "created_from" not in prov:
            errors.append("provenance.created_from is required")
        if "created_at" not in prov:
            errors.append("provenance.created_at is required")

    valid_types = {"skill", "agent", "doc", "hook", "rule"}
    if comp.get("type") not in valid_types:
        errors.append(f"Invalid type: {comp.get('type')}. Must be one of {valid_types}")

    return errors


def validate_registry_entry(entry: dict) -> list[str]:
    """レジストリエントリ（registry.json 内）のスキーマを検証する。"""
    errors = []
    required_fields = ["id", "name", "type", "version", "description", "tags", "path"]
    for field in required_fields:
        if field not in entry:
            errors.append(f"Missing required field: {field}")

    if not isinstance(entry.get("tags"), list):
        errors.append("tags must be a list")

    if "metrics" in entry:
        metrics = entry["metrics"]
        for mf in ["used_in_projects", "avg_effectiveness", "confidence", "last_used"]:
            if mf not in metrics:
                errors.append(f"metrics.{mf} is required")

    return errors


def extract_quality_criteria(content: str) -> list[str]:
    """SKILL.md から Quality Criteria チェックリスト項目を抽出する。"""
    criteria = []
    in_qc_section = False
    for line in content.split("\n"):
        if re.match(r"^##\s+Quality Criteria", line):
            in_qc_section = True
            continue
        if in_qc_section:
            if re.match(r"^##\s+", line):
                break
            match = re.match(r"^-\s+\[[ x]\]\s+(.+)$", line)
            if match:
                criteria.append(match.group(1).strip())
    return criteria


def extract_skill_description(content: str) -> str:
    """SKILL.md の先頭ヘッディングから説明を抽出する。"""
    match = re.match(r"^#\s+(.+)$", content.strip(), re.MULTILINE)
    return match.group(1).strip() if match else "Unknown skill"


def load_json_safe(path: str) -> dict | None:
    """JSON ファイルを安全に読み込む。エラー時は None を返す。"""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError, PermissionError):
        return None


def save_json(data: dict, path: str) -> None:
    """JSON ファイルを保存する。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {path}")


def now_iso() -> str:
    """現在時刻の ISO 8601 文字列を返す。"""
    return datetime.now().astimezone().isoformat()


def today_str() -> str:
    """今日の日付文字列を返す。"""
    return datetime.now().strftime("%Y-%m-%d")
