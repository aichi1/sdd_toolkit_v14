#!/usr/bin/env python3
"""
validate-outputs.py: Builder 成果物の自動プリチェック

Validator エージェント起動前に実行し、機械的に検証可能な項目を自動チェックする。
手動の Validator レビューの前段として、明らかな欠落を早期検出する。

Usage:
    python3 scripts/validate-outputs.py --phase 1
    python3 scripts/validate-outputs.py --phase 1 --category research_report
    python3 scripts/validate-outputs.py --phase 1 --project-type mkdocs
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_validate_rules(project_dir):
    """validate_rules.yaml を読み込む。存在しない/パースエラー時は None を返す。"""
    rules_path = project_dir / "validate_rules.yaml"
    if not rules_path.is_file():
        # scripts/ 配下も探す（配置場所の柔軟性）
        rules_path = project_dir / "scripts" / "validate_rules.yaml"
    if not rules_path.is_file():
        # config/ 配下も探す
        rules_path = project_dir / "config" / "validate_rules.yaml"
    if not rules_path.is_file():
        return None

    try:
        import yaml
    except ImportError:
        print("WARNING: pyyaml が未インストールのため validate_rules.yaml を読み込めません。"
              " generic カテゴリとして続行します。")
        print("  → pip install pyyaml でインストールしてください。")
        return None

    try:
        with open(rules_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data
    except Exception as e:
        print("WARNING: validate_rules.yaml のパースに失敗しました: {}".format(e))
        print("  → generic カテゴリとして続行します。")
        return None


def get_project_type_rules(rules_data, project_type):
    """指定されたプロジェクトタイプのルールを取得する。"""
    if rules_data is None:
        return {"skip_checks": [], "required_checks": []}

    categories = rules_data.get("categories", {})
    if project_type not in categories:
        return None  # 不明なカテゴリ

    cat_rules = categories[project_type]
    return {
        "skip_checks": cat_rules.get("skip_checks", []),
        "required_checks": cat_rules.get("required_checks", []),
    }


def should_skip_check(check_name, skip_patterns):
    """チェック名がスキップパターンに一致するかを判定する。"""
    import fnmatch
    for pattern in skip_patterns:
        if fnmatch.fnmatch(check_name, pattern):
            return True
        # パターンがチェック名に含まれるかも確認（部分一致）
        if pattern in check_name:
            return True
    return False


def get_valid_phases(metadata):
    """
    metadata.json から有効なフェーズ番号リストを返す。

    - iterations[] がある場合: 全イテレーションのフェーズを統合
    - iterations[] がない場合: 1〜phase_count の連番
    """
    if "iterations" in metadata and metadata["iterations"]:
        valid = []
        for iter_data in metadata["iterations"]:
            valid.extend(iter_data.get("phases", []))
        return sorted(set(valid))

    phase_count = metadata.get("phase_count", 0)
    return list(range(1, phase_count + 1))


def check_file_existence(outputs_dir, phase):
    """成果物ディレクトリとメタデータの存在チェック"""
    issues = []
    phase_dir = outputs_dir / "phase-{:02d}".format(phase)

    if not phase_dir.is_dir():
        issues.append({
            "check": "phase_dir_exists",
            "status": "fail",
            "message": "outputs/phase-{:02d}/ ディレクトリが存在しない".format(phase)
        })
        return issues, phase_dir

    issues.append({
        "check": "phase_dir_exists",
        "status": "pass",
        "message": "outputs/phase-{:02d}/ ディレクトリが存在する".format(phase)
    })

    metadata_path = phase_dir / ".metadata.json"
    if not metadata_path.is_file():
        issues.append({
            "check": "metadata_exists",
            "status": "fail",
            "message": ".metadata.json が存在しない"
        })
    else:
        issues.append({
            "check": "metadata_exists",
            "status": "pass",
            "message": ".metadata.json が存在する"
        })
        try:
            meta = load_json(metadata_path)
            for field in ["phase", "deliverables"]:
                if field not in meta:
                    issues.append({
                        "check": "metadata_field_{}".format(field),
                        "status": "fail",
                        "message": ".metadata.json に必須フィールド '{}' がない".format(field)
                    })
        except (json.JSONDecodeError, Exception) as e:
            issues.append({
                "check": "metadata_valid_json",
                "status": "fail",
                "message": ".metadata.json の JSON パースエラー: {}".format(e)
            })

    # 成果物ファイルが1つ以上あるか
    content_files = [f for f in phase_dir.iterdir()
                     if f.is_file() and not f.name.startswith(".")]
    if not content_files:
        issues.append({
            "check": "has_deliverables",
            "status": "fail",
            "message": "成果物ファイルが1つもない（隠しファイル以外）"
        })
    else:
        issues.append({
            "check": "has_deliverables",
            "status": "pass",
            "message": "成果物ファイル {} 件".format(len(content_files))
        })

    return issues, phase_dir


def check_skill_quality_criteria(phase_dir, skills_dir, phase):
    """SKILL.md の Quality Criteria を成果物と照合"""
    issues = []
    skill_path = skills_dir / "phase-{:02d}".format(phase) / "SKILL.md"

    if not skill_path.is_file():
        issues.append({
            "check": "skill_md_exists",
            "status": "fail",
            "message": "skills/phase-{:02d}/SKILL.md が存在しない".format(phase)
        })
        return issues

    skill_text = skill_path.read_text(encoding="utf-8")

    # Quality Criteria セクションを抽出
    criteria_match = re.search(
        r"## Quality Criteria\s*\n(.*?)(?=\n## |\Z)",
        skill_text, re.DOTALL
    )
    if not criteria_match:
        issues.append({
            "check": "has_quality_criteria",
            "status": "warn",
            "message": "SKILL.md に Quality Criteria セクションがない"
        })
        return issues

    criteria_text = criteria_match.group(1)
    criteria_items = re.findall(r"- \[ \] (.+)", criteria_text)

    if not criteria_items:
        issues.append({
            "check": "has_quality_criteria",
            "status": "warn",
            "message": "Quality Criteria にチェック項目がない"
        })
        return issues

    issues.append({
        "check": "has_quality_criteria",
        "status": "pass",
        "message": "Quality Criteria: {} 項目".format(len(criteria_items))
    })

    # 成果物テキストを結合して簡易チェック
    all_output_text = ""
    for f in phase_dir.iterdir():
        if f.is_file() and f.suffix == ".md" and not f.name.startswith("."):
            all_output_text += f.read_text(encoding="utf-8") + "\n"

    # 必須セクションキーワードの簡易存在チェック
    section_keywords = {
        "TL;DR": ["tl;dr", "tldr", "エグゼクティブサマリー", "executive summary"],
        "比較軸": ["比較軸", "評価軸", "comparison", "criteria"],
        "出典": ["出典", "参考文献", "references", "sources"],
        "不確実性": ["不確実性", "留意点", "limitation", "caveat", "注意事項"],
        "リスク": ["リスク", "risk"],
        "次アクション": ["次アクション", "next action", "ロードマップ", "roadmap"],
        "選択肢": ["選択肢", "案a", "案b", "option", "alternative"],
        "テスト": ["test", "pytest", "unittest"],
    }

    for criterion in criteria_items:
        criterion_lower = criterion.lower()
        found_keyword = False
        for label, keywords in section_keywords.items():
            if any(kw in criterion_lower for kw in keywords):
                if any(kw in all_output_text.lower() for kw in keywords):
                    found_keyword = True
                    break
        # We don't mark fail here since this is a heuristic;
        # just record what we found for the Validator to use

    return issues


def check_category_required_sections(phase_dir, category, skip_patterns=None):
    """カテゴリテンプレートの必須セクション存在チェック"""
    issues = []
    if skip_patterns is None:
        skip_patterns = []

    required_sections = {
        "research_report": [
            ("TL;DR", ["tl;dr", "tldr", "エグゼクティブサマリー", "executive summary"]),
            ("比較軸", ["比較軸", "評価軸", "比較の観点"]),
            ("不確実性・留意点", ["不確実性", "留意点", "limitation", "注意事項"]),
            ("出典・参考文献", ["出典", "参考文献", "references", "sources"]),
        ],
        "small_implementation": [
            ("README", []),  # README.md existence check instead
            ("src/", []),    # Directory existence check
            ("tests/", []),  # Directory existence check
        ],
        "internal_proposal": [
            ("目的と成功条件", ["目的", "成功条件", "objective", "success"]),
            ("選択肢比較", ["選択肢", "案a", "案b", "option", "alternative"]),
            ("リスクと対策", ["リスク", "対策", "risk", "mitigation"]),
            ("次アクション", ["次アクション", "next action", "ロードマップ", "roadmap", "担当"]),
        ],
    }

    if category not in required_sections:
        return issues

    # Collect all output text
    all_output_text = ""
    for f in phase_dir.iterdir():
        if f.is_file() and f.suffix == ".md" and not f.name.startswith("."):
            all_output_text += f.read_text(encoding="utf-8") + "\n"
    all_lower = all_output_text.lower()

    for section_name, keywords in required_sections[category]:
        # Check if this section should be skipped by project-type rules
        if should_skip_check(section_name, skip_patterns):
            issues.append({
                "check": "required_section_{}".format(section_name),
                "status": "pass",
                "message": "スキップ: {} (project-type ルールにより除外)".format(section_name)
            })
            continue

        if category == "small_implementation" and not keywords:
            # Special: check directory/file existence
            target = phase_dir / section_name.rstrip("/")
            if section_name == "README":
                target = phase_dir / "README.md"
            exists = target.exists()
            issues.append({
                "check": "required_section_{}".format(section_name),
                "status": "pass" if exists else "fail",
                "message": "{}: {}".format("存在" if exists else "欠落", section_name)
            })
        elif keywords:
            found = any(kw in all_lower for kw in keywords)
            issues.append({
                "check": "required_section_{}".format(section_name),
                "status": "pass" if found else "warn",
                "message": "{}: {} (キーワードベースの簡易チェック)".format(
                    "検出" if found else "未検出", section_name)
            })

    return issues


def main():
    ap = argparse.ArgumentParser(description="Builder 成果物の自動プリチェック")
    ap.add_argument("--phase", type=int, required=True, help="対象フェーズ番号")
    ap.add_argument("--category", type=str, default="",
                     help="タスクカテゴリ (research_report, small_implementation, internal_proposal)")
    ap.add_argument("--project-type", type=str, default="",
                     help="プロジェクトタイプ (mkdocs, python, nodejs, generic)")
    ap.add_argument("--project-dir", type=str, default=".", help="プロジェクトルート")
    args = ap.parse_args()

    project = Path(args.project_dir).resolve()
    outputs_dir = project / "outputs"
    skills_dir = project / "skills"

    # Auto-detect category from metadata.json if not specified
    category = args.category
    if not category:
        meta_path = project / "metadata.json"
        if meta_path.is_file():
            try:
                meta = load_json(meta_path)
                category = meta.get("category", "")
            except Exception:
                pass

    # Load project-type rules
    project_type = args.project_type
    skip_patterns = []
    rules_data = None

    if project_type:
        rules_data = load_validate_rules(project)
        if rules_data is not None:
            type_rules = get_project_type_rules(rules_data, project_type)
            if type_rules is None:
                print("ERROR: 不明なプロジェクトタイプ '{}' が指定されました。".format(project_type))
                if rules_data and "categories" in rules_data:
                    valid_types = list(rules_data["categories"].keys())
                    print("  有効なタイプ: {}".format(", ".join(valid_types)))
                sys.exit(1)
            skip_patterns = type_rules["skip_checks"]
            print("[INFO] Project type: {}".format(project_type))
            if skip_patterns:
                print("[INFO] Skipped checks: {}".format(", ".join(skip_patterns)))
        else:
            print("[WARNING] validate_rules.yaml が見つかりません。generic として続行します。")
            project_type = "generic"

    # フェーズ番号の妥当性チェック（イテレーション認識）
    meta_path = project / "metadata.json"
    if meta_path.is_file():
        try:
            project_meta = load_json(meta_path)
            valid_phases = get_valid_phases(project_meta)
            if valid_phases and args.phase not in valid_phases:
                print("Warning: Phase {} は metadata.json の有効フェーズ "
                      "({}) に含まれていません。".format(args.phase, valid_phases))
        except Exception:
            pass  # メタデータ読み取り失敗時はスキップ（後方互換）

    all_issues = []

    # Check 1: File existence
    file_issues, phase_dir = check_file_existence(outputs_dir, args.phase)
    all_issues.extend(file_issues)

    if not phase_dir.is_dir():
        print_report(all_issues, args.phase, category, project_type, skip_patterns)
        sys.exit(1)

    # Check 2: SKILL.md Quality Criteria
    skill_issues = check_skill_quality_criteria(phase_dir, skills_dir, args.phase)
    all_issues.extend(skill_issues)

    # Check 3: Category-specific required sections (with skip patterns applied)
    if category:
        section_issues = check_category_required_sections(
            phase_dir, category, skip_patterns)
        all_issues.extend(section_issues)

    print_report(all_issues, args.phase, category, project_type, skip_patterns)

    # Exit code: 1 if any fail, 0 otherwise
    has_fail = any(i["status"] == "fail" for i in all_issues)
    sys.exit(1 if has_fail else 0)


def print_report(issues, phase, category, project_type="", skip_patterns=None):
    """プリチェック結果を表示"""
    if skip_patterns is None:
        skip_patterns = []

    pass_count = sum(1 for i in issues if i["status"] == "pass")
    warn_count = sum(1 for i in issues if i["status"] == "warn")
    fail_count = sum(1 for i in issues if i["status"] == "fail")

    print("=== Pre-Validation: Phase {} ===".format(phase))
    if category:
        print("Category: {}".format(category))
    if project_type:
        print("Project type: {}".format(project_type))
    if skip_patterns:
        skipped_count = sum(
            1 for i in issues
            if "スキップ" in i.get("message", "") and "project-type" in i.get("message", "")
        )
        if skipped_count:
            print("Skipped checks: {} ({} checks skipped by project-type rules)".format(
                ", ".join(skip_patterns), skipped_count))
    print()

    for issue in issues:
        icon = {"pass": "✓", "warn": "⚠", "fail": "✗"}[issue["status"]]
        print("  {} [{}] {}".format(icon, issue["check"], issue["message"]))

    print()
    print("Result: {} pass, {} warn, {} fail".format(pass_count, warn_count, fail_count))

    if fail_count > 0:
        print("Status: FAIL - Validator 実行前に修正が必要")
    elif warn_count > 0:
        print("Status: WARN - Validator で詳細確認を推奨")
    else:
        print("Status: PASS - Validator 実行可能")


if __name__ == "__main__":
    main()
