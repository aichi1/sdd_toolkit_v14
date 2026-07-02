#!/usr/bin/env python3
"""
test_validate_outputs.py: validate-outputs.py のカテゴリ別除外ルールテスト

テストケース:
- 正常系: mkdocs カテゴリで src/tests/README がスキップされる
- 正常系: generic カテゴリで全チェックが実行される
- 異常系: 不明カテゴリでエラーが返る
- 異常系: YAML 不在時に WARNING + generic 動作
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# validate-outputs.py はハイフン入りなので importlib で読み込む
import importlib.util
spec = importlib.util.spec_from_file_location(
    "validate_outputs",
    str(Path(__file__).parent / "validate-outputs.py")
)
validate_outputs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate_outputs)


class TestLoadValidateRules(unittest.TestCase):
    """validate_rules.yaml の読み込みテスト"""

    def test_rules_file_not_found(self):
        """YAML ファイルが存在しない場合は None を返す"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_outputs.load_validate_rules(Path(tmpdir))
            self.assertIsNone(result)

    def test_rules_file_loads_successfully(self):
        """正常な YAML ファイルを読み込める"""
        try:
            import yaml
        except ImportError:
            self.skipTest("pyyaml が未インストール")

        with tempfile.TemporaryDirectory() as tmpdir:
            rules_path = Path(tmpdir) / "validate_rules.yaml"
            rules_path.write_text(
                "categories:\n"
                "  mkdocs:\n"
                "    description: test\n"
                "    skip_checks:\n"
                "      - 'src/tests/README'\n"
                "    required_checks:\n"
                "      - 'mkdocs.yml'\n"
                "  generic:\n"
                "    description: default\n"
                "    skip_checks: []\n"
                "    required_checks: []\n",
                encoding="utf-8"
            )
            result = validate_outputs.load_validate_rules(Path(tmpdir))
            self.assertIsNotNone(result)
            self.assertIn("categories", result)
            self.assertIn("mkdocs", result["categories"])


class TestGetProjectTypeRules(unittest.TestCase):
    """プロジェクトタイプ別ルール取得のテスト"""

    def setUp(self):
        self.rules_data = {
            "categories": {
                "mkdocs": {
                    "skip_checks": ["src/tests/README", "test_*.py"],
                    "required_checks": ["mkdocs.yml"],
                },
                "python": {
                    "skip_checks": [],
                    "required_checks": ["src/", "tests/"],
                },
                "generic": {
                    "skip_checks": [],
                    "required_checks": [],
                },
            }
        }

    def test_known_category_returns_rules(self):
        """既知のカテゴリでルールが返る"""
        rules = validate_outputs.get_project_type_rules(self.rules_data, "mkdocs")
        self.assertIsNotNone(rules)
        self.assertIn("src/tests/README", rules["skip_checks"])
        self.assertIn("mkdocs.yml", rules["required_checks"])

    def test_unknown_category_returns_none(self):
        """不明なカテゴリで None が返る"""
        rules = validate_outputs.get_project_type_rules(self.rules_data, "unknown_type")
        self.assertIsNone(rules)

    def test_generic_category_has_empty_rules(self):
        """generic カテゴリは空のルールを返す"""
        rules = validate_outputs.get_project_type_rules(self.rules_data, "generic")
        self.assertIsNotNone(rules)
        self.assertEqual(rules["skip_checks"], [])
        self.assertEqual(rules["required_checks"], [])

    def test_none_rules_data_returns_empty(self):
        """rules_data が None の場合は空のルールを返す"""
        rules = validate_outputs.get_project_type_rules(None, "mkdocs")
        self.assertEqual(rules["skip_checks"], [])
        self.assertEqual(rules["required_checks"], [])


class TestShouldSkipCheck(unittest.TestCase):
    """チェックスキップ判定のテスト"""

    def test_exact_match(self):
        """完全一致でスキップされる"""
        self.assertTrue(
            validate_outputs.should_skip_check("src/tests/README", ["src/tests/README"])
        )

    def test_fnmatch_pattern(self):
        """fnmatch パターンでスキップされる"""
        self.assertTrue(
            validate_outputs.should_skip_check("test_validate.py", ["test_*.py"])
        )

    def test_no_match(self):
        """一致しない場合はスキップされない"""
        self.assertFalse(
            validate_outputs.should_skip_check("README.md", ["src/tests/README", "test_*.py"])
        )

    def test_empty_patterns(self):
        """空のパターンリストではスキップされない"""
        self.assertFalse(
            validate_outputs.should_skip_check("anything", [])
        )

    def test_partial_match(self):
        """部分一致でもスキップされる"""
        self.assertTrue(
            validate_outputs.should_skip_check("src/tests/README.md", ["src/tests/README"])
        )


class TestCategoryRequiredSectionsWithSkip(unittest.TestCase):
    """カテゴリ必須セクションチェックのスキップテスト"""

    def test_mkdocs_skips_src_tests(self):
        """mkdocs タイプで src/ と tests/ がスキップされる"""
        with tempfile.TemporaryDirectory() as tmpdir:
            phase_dir = Path(tmpdir)
            # README.md を作成（存在チェック用）
            (phase_dir / "README.md").write_text("# Test", encoding="utf-8")

            skip_patterns = ["src/tests/README", "test_*.py", "src/", "tests/"]
            issues = validate_outputs.check_category_required_sections(
                phase_dir, "small_implementation", skip_patterns
            )

            # src/ と tests/ はスキップされるべき
            skipped_checks = [
                i for i in issues
                if "スキップ" in i["message"] and "project-type" in i["message"]
            ]
            self.assertGreater(len(skipped_checks), 0,
                              "mkdocs タイプで src/ または tests/ がスキップされるべき")

            # README はスキップされないべき
            readme_issues = [i for i in issues if "README" in i["check"]]
            for issue in readme_issues:
                self.assertNotIn("スキップ", issue["message"],
                                "README はスキップされてはいけない")

    def test_generic_skips_nothing(self):
        """generic タイプではスキップなし"""
        with tempfile.TemporaryDirectory() as tmpdir:
            phase_dir = Path(tmpdir)
            (phase_dir / "README.md").write_text("# Test", encoding="utf-8")

            issues = validate_outputs.check_category_required_sections(
                phase_dir, "small_implementation", []
            )

            skipped_checks = [
                i for i in issues
                if "スキップ" in i.get("message", "")
            ]
            self.assertEqual(len(skipped_checks), 0,
                           "generic タイプではスキップされるチェックがないべき")


class TestBackwardCompatibility(unittest.TestCase):
    """後方互換性のテスト"""

    def test_no_project_type_works(self):
        """--project-type 未指定時に従来通り動作する"""
        # check_category_required_sections を skip_patterns なしで呼ぶ
        with tempfile.TemporaryDirectory() as tmpdir:
            phase_dir = Path(tmpdir)
            (phase_dir / "README.md").write_text("# Test", encoding="utf-8")
            (phase_dir / "report.md").write_text("# Report\nリスク分析", encoding="utf-8")

            # skip_patterns=None（デフォルト）で呼び出し
            issues = validate_outputs.check_category_required_sections(
                phase_dir, "small_implementation"
            )

            # src/ と tests/ のチェックが実行される（スキップされない）
            all_checks = [i["check"] for i in issues]
            self.assertIn("required_section_src/", all_checks)
            self.assertIn("required_section_tests/", all_checks)


if __name__ == "__main__":
    unittest.main()
