"""
tests/test_security_checks.py — Phase 5 (T5.2) tests for harness/security_checks.py.

第10条: セキュリティは構築時から.
Each CWE/OWASP check must:
  (a) Detect a vulnerable code snippet (true-positive)
  (b) NOT trigger on clean code (false-positive guard)

CWE coverage:
  CWE-78  — OS Command Injection (shell=True, os.system)
  CWE-95  — Dynamic code evaluation (eval, exec)
  CWE-798 — Hard-coded credentials (password, secret, api_key, token)
  CWE-502 — Insecure deserialization (pickle.loads, yaml.load without SafeLoader)
  CWE-89  — SQL Injection (string concatenation / f-string with SQL keywords)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from harness.security_checks import Finding, scan_code


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cwe_ids(findings: list[Finding]) -> set[str]:
    """Extract the set of CWE IDs from a list of findings."""
    return {f.cwe_id for f in findings}


def _has_cwe(findings: list[Finding], cwe: str) -> bool:
    return any(f.cwe_id == cwe for f in findings)


# ---------------------------------------------------------------------------
# Fixtures: clean and vulnerable code snippets
# ---------------------------------------------------------------------------

CLEAN_CODE = """\
import re
import json
from pathlib import Path

def process_data(data: str) -> dict:
    return json.loads(data)

def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def add(a: int, b: int) -> int:
    return a + b

API_BASE_URL = "https://api.example.com"
"""

VULNERABLE_SHELL = """\
import subprocess
def run_cmd(cmd):
    subprocess.run(cmd, shell=True)
"""

VULNERABLE_OS_SYSTEM = """\
import os
def run_it(cmd):
    os.system(cmd)
"""

VULNERABLE_EVAL = """\
def dangerous(expr):
    return eval(expr)
"""

VULNERABLE_EXEC = """\
def dangerous(code):
    exec(code)
"""

VULNERABLE_HARDCODED_PASSWORD = """\
password = "supersecret123"
"""

VULNERABLE_HARDCODED_API_KEY = """\
api_key = "sk-1234567890abcdef"
"""

VULNERABLE_HARDCODED_SECRET = """\
secret = "my_very_secret_value"
"""

VULNERABLE_HARDCODED_TOKEN = """\
token = "Bearer eyJhbGciOiJIUzI1NiJ9.abc"
"""

VULNERABLE_PICKLE = """\
import pickle
def load_data(data):
    return pickle.loads(data)
"""

VULNERABLE_PICKLE_FILE = """\
import pickle
def load_from_file(f):
    return pickle.load(f)
"""

VULNERABLE_YAML_LOAD = """\
import yaml
def parse_config(text):
    return yaml.load(text)
"""

CLEAN_YAML_SAFE = """\
import yaml
def parse_config(text):
    return yaml.safe_load(text)
"""

VULNERABLE_SQL_FSTRING = """\
def get_user(name):
    query = f"SELECT * FROM users WHERE name = '{name}'"
    return db.execute(query)
"""

VULNERABLE_SQL_CONCAT = """\
def insert_record(table, value):
    sql = "INSERT INTO " + table + " VALUES (?)"
    db.execute(sql, value)
"""


# ---------------------------------------------------------------------------
# Tests: CWE-78 — OS Command Injection
# ---------------------------------------------------------------------------

class TestCWE78CommandInjection:
    """第10条: CWE-78 must be detected on vulnerable input; no FP on clean code."""

    def test_shell_true_detected(self):
        """subprocess(..., shell=True) must trigger CWE-78."""
        findings = scan_code(VULNERABLE_SHELL)
        assert _has_cwe(findings, "CWE-78"), (
            f"CWE-78 not detected in shell=True code; findings: {findings}"
        )

    def test_os_system_detected(self):
        """os.system() must trigger CWE-78."""
        findings = scan_code(VULNERABLE_OS_SYSTEM)
        assert _has_cwe(findings, "CWE-78"), (
            f"CWE-78 not detected in os.system(); findings: {findings}"
        )

    def test_clean_code_no_cwe78(self):
        """Clean code must NOT produce CWE-78 false positive."""
        findings = scan_code(CLEAN_CODE)
        assert not _has_cwe(findings, "CWE-78"), (
            f"CWE-78 false positive on clean code; findings: {findings}"
        )

    def test_finding_has_severity_critical(self):
        """CWE-78 findings must be marked Critical."""
        findings = scan_code(VULNERABLE_SHELL)
        cwe78 = [f for f in findings if f.cwe_id == "CWE-78"]
        assert all(f.severity == "Critical" for f in cwe78), (
            f"CWE-78 findings should be Critical; got {[f.severity for f in cwe78]}"
        )

    def test_finding_has_owasp_category(self):
        """CWE-78 findings must have OWASP A03 category."""
        findings = scan_code(VULNERABLE_SHELL)
        cwe78 = [f for f in findings if f.cwe_id == "CWE-78"]
        assert all("A03" in f.owasp_cat for f in cwe78)

    def test_finding_has_location(self):
        """Each CWE-78 finding must include location info."""
        findings = scan_code(VULNERABLE_SHELL)
        for f in findings:
            if f.cwe_id == "CWE-78":
                assert f.location.startswith("line "), (
                    f"location must start with 'line '; got {f.location!r}"
                )


# ---------------------------------------------------------------------------
# Tests: CWE-95 — Dynamic Code Evaluation
# ---------------------------------------------------------------------------

class TestCWE95EvalExec:
    """第10条: CWE-95 must be detected on eval()/exec() calls."""

    def test_eval_detected(self):
        """eval() must trigger CWE-95."""
        findings = scan_code(VULNERABLE_EVAL)
        assert _has_cwe(findings, "CWE-95"), (
            f"CWE-95 not detected for eval(); findings: {findings}"
        )

    def test_exec_detected(self):
        """exec() must trigger CWE-95."""
        findings = scan_code(VULNERABLE_EXEC)
        assert _has_cwe(findings, "CWE-95"), (
            f"CWE-95 not detected for exec(); findings: {findings}"
        )

    def test_clean_code_no_cwe95(self):
        """Clean code must NOT produce CWE-95 false positive."""
        findings = scan_code(CLEAN_CODE)
        assert not _has_cwe(findings, "CWE-95"), (
            f"CWE-95 false positive on clean code; findings: {findings}"
        )

    def test_commented_eval_not_detected(self):
        """eval() in a comment line must not trigger CWE-95."""
        code_with_comment = "# do not use eval(user_input)\nx = 1\n"
        findings = scan_code(code_with_comment)
        assert not _has_cwe(findings, "CWE-95"), (
            "CWE-95 must not trigger on commented-out eval()"
        )


# ---------------------------------------------------------------------------
# Tests: CWE-798 — Hard-coded Credentials
# ---------------------------------------------------------------------------

class TestCWE798HardcodedCredentials:
    """第10条: CWE-798 must detect hard-coded passwords/secrets/keys."""

    def test_password_detected(self):
        """password = 'value' must trigger CWE-798."""
        findings = scan_code(VULNERABLE_HARDCODED_PASSWORD)
        assert _has_cwe(findings, "CWE-798"), (
            f"CWE-798 not detected for password=; findings: {findings}"
        )

    def test_api_key_detected(self):
        """api_key = 'value' must trigger CWE-798."""
        findings = scan_code(VULNERABLE_HARDCODED_API_KEY)
        assert _has_cwe(findings, "CWE-798"), (
            f"CWE-798 not detected for api_key=; findings: {findings}"
        )

    def test_secret_detected(self):
        """secret = 'value' must trigger CWE-798."""
        findings = scan_code(VULNERABLE_HARDCODED_SECRET)
        assert _has_cwe(findings, "CWE-798"), (
            f"CWE-798 not detected for secret=; findings: {findings}"
        )

    def test_token_detected(self):
        """token = 'value' must trigger CWE-798."""
        findings = scan_code(VULNERABLE_HARDCODED_TOKEN)
        assert _has_cwe(findings, "CWE-798"), (
            f"CWE-798 not detected for token=; findings: {findings}"
        )

    def test_clean_code_no_cwe798(self):
        """Clean code must NOT produce CWE-798 false positive."""
        findings = scan_code(CLEAN_CODE)
        assert not _has_cwe(findings, "CWE-798"), (
            f"CWE-798 false positive on clean code; findings: {findings}"
        )

    def test_url_variable_no_false_positive(self):
        """API_BASE_URL = '...' must NOT trigger CWE-798 (not a credential name)."""
        code = 'API_BASE_URL = "https://api.example.com"\n'
        findings = scan_code(code)
        assert not _has_cwe(findings, "CWE-798"), (
            "CWE-798 false positive: API_BASE_URL is not a credential variable"
        )

    def test_finding_severity_critical(self):
        """CWE-798 findings must be marked Critical."""
        findings = scan_code(VULNERABLE_HARDCODED_PASSWORD)
        cwe798 = [f for f in findings if f.cwe_id == "CWE-798"]
        assert all(f.severity == "Critical" for f in cwe798)


# ---------------------------------------------------------------------------
# Tests: CWE-502 — Insecure Deserialization
# ---------------------------------------------------------------------------

class TestCWE502Deserialization:
    """第10条: CWE-502 must detect pickle.loads, yaml.load without SafeLoader."""

    def test_pickle_loads_detected(self):
        """pickle.loads() must trigger CWE-502."""
        findings = scan_code(VULNERABLE_PICKLE)
        assert _has_cwe(findings, "CWE-502"), (
            f"CWE-502 not detected for pickle.loads(); findings: {findings}"
        )

    def test_pickle_load_detected(self):
        """pickle.load() must trigger CWE-502."""
        findings = scan_code(VULNERABLE_PICKLE_FILE)
        assert _has_cwe(findings, "CWE-502"), (
            f"CWE-502 not detected for pickle.load(); findings: {findings}"
        )

    def test_yaml_load_without_safeloader_detected(self):
        """yaml.load() without SafeLoader must trigger CWE-502."""
        findings = scan_code(VULNERABLE_YAML_LOAD)
        assert _has_cwe(findings, "CWE-502"), (
            f"CWE-502 not detected for yaml.load(); findings: {findings}"
        )

    def test_yaml_safe_load_no_false_positive(self):
        """yaml.safe_load() must NOT trigger CWE-502."""
        findings = scan_code(CLEAN_YAML_SAFE)
        assert not _has_cwe(findings, "CWE-502"), (
            f"CWE-502 false positive on yaml.safe_load(); findings: {findings}"
        )

    def test_clean_code_no_cwe502(self):
        """Clean code must NOT produce CWE-502 false positive."""
        findings = scan_code(CLEAN_CODE)
        assert not _has_cwe(findings, "CWE-502"), (
            f"CWE-502 false positive on clean code; findings: {findings}"
        )

    def test_json_loads_no_false_positive(self):
        """json.loads() must NOT trigger CWE-502 (not a dangerous deserializer)."""
        code = "import json\ndata = json.loads(raw)\n"
        findings = scan_code(code)
        assert not _has_cwe(findings, "CWE-502"), (
            "CWE-502 false positive: json.loads is safe"
        )


# ---------------------------------------------------------------------------
# Tests: CWE-89 — SQL Injection
# ---------------------------------------------------------------------------

class TestCWE89SqlInjection:
    """第10条: CWE-89 must detect SQL string concatenation and f-string patterns."""

    def test_sql_fstring_detected(self):
        """f-string with SQL keywords must trigger CWE-89."""
        findings = scan_code(VULNERABLE_SQL_FSTRING)
        assert _has_cwe(findings, "CWE-89"), (
            f"CWE-89 not detected for SQL f-string; findings: {findings}"
        )

    def test_sql_concat_detected(self):
        """SQL string concatenation must trigger CWE-89."""
        findings = scan_code(VULNERABLE_SQL_CONCAT)
        assert _has_cwe(findings, "CWE-89"), (
            f"CWE-89 not detected for SQL concatenation; findings: {findings}"
        )

    def test_clean_code_no_cwe89(self):
        """Clean code must NOT produce CWE-89 false positive."""
        findings = scan_code(CLEAN_CODE)
        assert not _has_cwe(findings, "CWE-89"), (
            f"CWE-89 false positive on clean code; findings: {findings}"
        )

    def test_parameterized_query_no_false_positive(self):
        """Parameterized query must NOT trigger CWE-89."""
        code = 'cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))\n'
        findings = scan_code(code)
        assert not _has_cwe(findings, "CWE-89"), (
            "CWE-89 false positive: parameterized query is safe"
        )


# ---------------------------------------------------------------------------
# Tests: scan_code() API contract
# ---------------------------------------------------------------------------

class TestScanCodeApi:
    """Tests for the scan_code() public function contract."""

    def test_returns_list(self):
        """scan_code() always returns a list."""
        result = scan_code(CLEAN_CODE)
        assert isinstance(result, list)

    def test_returns_finding_objects(self):
        """Non-empty scan results must be Finding instances."""
        result = scan_code(VULNERABLE_SHELL)
        for item in result:
            assert isinstance(item, Finding), (
                f"Expected Finding, got {type(item)}: {item!r}"
            )

    def test_finding_has_required_fields(self):
        """Every Finding must have cwe_id, owasp_cat, description, location, severity."""
        findings = scan_code(VULNERABLE_SHELL)
        for f in findings:
            assert f.cwe_id, "cwe_id must be non-empty"
            assert f.owasp_cat, "owasp_cat must be non-empty"
            assert f.description, "description must be non-empty"
            assert f.location, "location must be non-empty"
            assert f.severity in ("Critical", "High", "Medium", "Low"), (
                f"severity must be one of the standard levels; got {f.severity!r}"
            )

    def test_scan_code_from_path(self, tmp_path: Path):
        """scan_code(Path) reads from file when given a Path object."""
        vuln_file = tmp_path / "vuln.py"
        vuln_file.write_text(VULNERABLE_SHELL, encoding="utf-8")
        findings = scan_code(vuln_file)
        assert _has_cwe(findings, "CWE-78")

    def test_scan_code_from_path_string(self, tmp_path: Path):
        """scan_code('/path/to/file.py') reads file when path string points to existing file."""
        vuln_file = tmp_path / "vuln.py"
        vuln_file.write_text(VULNERABLE_SHELL, encoding="utf-8")
        findings = scan_code(str(vuln_file))
        assert _has_cwe(findings, "CWE-78")

    def test_scan_code_from_text_string(self):
        """scan_code(text) scans the text directly when it's not a file path."""
        findings = scan_code(VULNERABLE_SHELL)
        assert isinstance(findings, list)
        assert _has_cwe(findings, "CWE-78")

    def test_empty_code_no_findings(self):
        """Empty code string must return empty findings list."""
        findings = scan_code("")
        assert findings == []

    def test_multiple_cwes_in_one_file(self):
        """A file with multiple vulnerability patterns must trigger multiple CWEs."""
        combined = (
            VULNERABLE_SHELL
            + VULNERABLE_EVAL
            + VULNERABLE_HARDCODED_PASSWORD
        )
        findings = scan_code(combined)
        detected = _cwe_ids(findings)
        assert "CWE-78" in detected
        assert "CWE-95" in detected
        assert "CWE-798" in detected

    def test_clean_code_zero_findings(self):
        """The clean code fixture must produce zero findings."""
        findings = scan_code(CLEAN_CODE)
        assert len(findings) == 0, (
            f"Expected 0 findings on clean code; got {len(findings)}: "
            f"{[(f.cwe_id, f.location) for f in findings]}"
        )
