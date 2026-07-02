"""
harness/security_checks.py — CWE/OWASP-mapped static security checks.

第10条: セキュリティは構築時から
──────────────────────────────────
security 専門エージェントと eval_suite が CWE/OWASP マッピングに沿って走査する。
この モジュールは `verify` ノードの security サブエージェントと Phase 6 `eval_suite`
の両方から呼ばれる共通チェックバンクである。

Usage
─────
    from harness.security_checks import scan_code, Finding

    findings = scan_code("code text here")
    # or
    findings = scan_code("/path/to/file.py")

    for f in findings:
        print(f.cwe_id, f.description, f.location)

Finding format
──────────────
Each Finding has:
  cwe_id      : str — e.g. "CWE-78"
  owasp_cat   : str — OWASP category shorthand, e.g. "A03:2021"
  description : str — human-readable explanation
  location    : str — line number or pattern that matched

Checks implemented
──────────────────
  CWE-78  (OS Command Injection)   — subprocess shell=True, os.system()
  CWE-95  (Improper Neutralization of Directives in Eval)
                                   — eval(), exec() calls
  CWE-798 (Use of Hard-coded Credentials)
                                   — password/secret/api_key = "..." literals
  CWE-502 (Deserialization of Untrusted Data) — pickle.loads(), yaml.load() without SafeLoader
  CWE-89  (SQL Injection)          — SQL string concatenation patterns
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# Finding data model
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    """
    A single security finding from scan_code().

    Attributes
    ──────────
    cwe_id      : CWE identifier, e.g. "CWE-78"
    owasp_cat   : OWASP Top 10 2021 category, e.g. "A03:2021 - Injection"
    description : Human-readable description of the vulnerability
    location    : Line number (1-based) and matched content excerpt,
                  e.g. "line 42: 'os.system(cmd)'"
    severity    : "Critical", "High", "Medium", or "Low"
    """
    cwe_id: str
    owasp_cat: str
    description: str
    location: str
    severity: str = "High"


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------

CheckFn = Callable[[list[str]], list[Finding]]


def _check_cwe78_command_injection(lines: list[str]) -> list[Finding]:
    """
    CWE-78: Improper Neutralization of Special Elements used in an OS Command.

    Patterns detected:
      - subprocess(... shell=True ...)
      - os.system(
      - os.popen(

    These allow user-controlled data to be executed as shell commands.
    OWASP A03:2021 - Injection
    """
    findings: list[Finding] = []
    patterns = [
        re.compile(r"\bsubprocess\b.*\bshell\s*=\s*True"),
        re.compile(r"\bos\.system\s*\("),
        re.compile(r"\bos\.popen\s*\("),
    ]
    for lineno, line in enumerate(lines, start=1):
        for pat in patterns:
            if pat.search(line):
                findings.append(Finding(
                    cwe_id="CWE-78",
                    owasp_cat="A03:2021 - Injection",
                    description=(
                        "OS Command Injection: shell=True or os.system/os.popen "
                        "allows command injection if input is user-controlled."
                    ),
                    location=f"line {lineno}: {line.strip()[:120]!r}",
                    severity="Critical",
                ))
                break  # one finding per line is enough
    return findings


def _check_cwe95_eval_exec(lines: list[str]) -> list[Finding]:
    """
    CWE-95: Improper Neutralization of Directives in Dynamically Evaluated Code.

    Patterns detected:
      - eval(
      - exec(

    Dynamic code evaluation with untrusted input enables arbitrary code execution.
    OWASP A03:2021 - Injection
    """
    findings: list[Finding] = []
    # Match eval( or exec( that are not inside comments or strings (best-effort)
    patterns = [
        re.compile(r"\beval\s*\("),
        re.compile(r"\bexec\s*\("),
    ]
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        # Skip comment lines (simple heuristic)
        if stripped.startswith("#"):
            continue
        for pat in patterns:
            if pat.search(line):
                findings.append(Finding(
                    cwe_id="CWE-95",
                    owasp_cat="A03:2021 - Injection",
                    description=(
                        "Dynamic code evaluation (eval/exec) can execute arbitrary "
                        "code if the argument contains untrusted user input."
                    ),
                    location=f"line {lineno}: {stripped[:120]!r}",
                    severity="Critical",
                ))
                break
    return findings


def _check_cwe798_hardcoded_credentials(lines: list[str]) -> list[Finding]:
    """
    CWE-798: Use of Hard-coded Credentials.

    Patterns detected (case-insensitive):
      - password = "..."
      - passwd = "..."
      - secret = "..."
      - api_key = "..."
      - token = "..."  (when followed by a non-empty quoted string)

    Variable names that suggest credentials assigned to non-empty string literals.
    OWASP A07:2021 - Identification and Authentication Failures
    """
    findings: list[Finding] = []
    # Pattern: credential-like variable name = "non-empty-value"
    # Groups: (variable_name, quote_char, value)
    pattern = re.compile(
        r"""(?i)\b(password|passwd|secret|api[_-]?key|token|auth[_-]?token)\s*=\s*(['"]).+?\2""",
        re.IGNORECASE,
    )
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        m = pattern.search(line)
        if m:
            findings.append(Finding(
                cwe_id="CWE-798",
                owasp_cat="A07:2021 - Identification and Authentication Failures",
                description=(
                    f"Hard-coded credential detected: variable {m.group(1)!r} "
                    "appears to contain a literal secret value."
                ),
                location=f"line {lineno}: {stripped[:120]!r}",
                severity="Critical",
            ))
    return findings


def _check_cwe502_insecure_deserialization(lines: list[str]) -> list[Finding]:
    """
    CWE-502: Deserialization of Untrusted Data.

    Patterns detected:
      - pickle.loads(      — arbitrary Python object deserialization
      - pickle.load(       — same, from file handle
      - yaml.load(         — full YAML load without SafeLoader
                             (yaml.safe_load is acceptable)

    OWASP A08:2021 - Software and Data Integrity Failures
    """
    findings: list[Finding] = []
    pickle_patterns = [
        re.compile(r"\bpickle\.loads\s*\("),
        re.compile(r"\bpickle\.load\s*\("),
    ]
    # yaml.load( is dangerous; yaml.safe_load( is fine
    yaml_pattern = re.compile(r"\byaml\.load\s*\(")
    yaml_safe_pattern = re.compile(r"\byaml\.safe_load\s*\(")

    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        for pat in pickle_patterns:
            if pat.search(line):
                findings.append(Finding(
                    cwe_id="CWE-502",
                    owasp_cat="A08:2021 - Software and Data Integrity Failures",
                    description=(
                        "Insecure deserialization: pickle.load/loads can execute "
                        "arbitrary Python code when deserializing untrusted data."
                    ),
                    location=f"line {lineno}: {stripped[:120]!r}",
                    severity="High",
                ))
                break

        # yaml.load( without SafeLoader — but not if it's yaml.safe_load
        if yaml_pattern.search(line) and not yaml_safe_pattern.search(line):
            findings.append(Finding(
                cwe_id="CWE-502",
                owasp_cat="A08:2021 - Software and Data Integrity Failures",
                description=(
                    "Insecure YAML deserialization: yaml.load() without SafeLoader "
                    "can execute arbitrary code. Use yaml.safe_load() instead."
                ),
                location=f"line {lineno}: {stripped[:120]!r}",
                severity="High",
            ))

    return findings


def _check_cwe89_sql_injection(lines: list[str]) -> list[Finding]:
    """
    CWE-89: Improper Neutralization of Special Elements used in an SQL Command.

    Patterns detected (best-effort static):
      - f-string with SQL keywords + variable interpolation `{...}`
        e.g.: f"SELECT * FROM users WHERE name = '{name}'"
      - String concatenation with SQL keyword prefix
        e.g.: "INSERT INTO " + table + " VALUES ..."

    OWASP A03:2021 - Injection
    """
    findings: list[Finding] = []
    # Detect f-strings: line has f"..." or f'...', a SQL keyword, and a {variable}
    _sql_fstring_start = re.compile(r"""\bf['""]""")
    _sql_keyword = re.compile(r"(?i)\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|WHERE)\b")
    _fstring_interp = re.compile(r"\{[^}]+\}")

    # Detect string concatenation: "SQL_KEYWORD ... " + variable or + identifier
    sql_concat = re.compile(
        r"""(?i)["']\s*(SELECT|INSERT|UPDATE|DELETE|DROP|UNION)\b[^"']*["']\s*\+""",
    )

    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        matched = False
        # Check f-string pattern: has f-string prefix + SQL keyword + {interpolation}
        if (
            _sql_fstring_start.search(line)
            and _sql_keyword.search(line)
            and _fstring_interp.search(line)
        ):
            matched = True
        # Check concatenation pattern
        elif sql_concat.search(line):
            matched = True

        if matched:
            findings.append(Finding(
                cwe_id="CWE-89",
                owasp_cat="A03:2021 - Injection",
                description=(
                    "SQL Injection risk: SQL query constructed via string "
                    "concatenation or f-string with user-controlled variables. "
                    "Use parameterized queries instead."
                ),
                location=f"line {lineno}: {stripped[:120]!r}",
                severity="Critical",
            ))

    return findings


# ---------------------------------------------------------------------------
# Check registry
# ---------------------------------------------------------------------------

_CHECK_BANK: list[CheckFn] = [
    _check_cwe78_command_injection,
    _check_cwe95_eval_exec,
    _check_cwe798_hardcoded_credentials,
    _check_cwe502_insecure_deserialization,
    _check_cwe89_sql_injection,
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_code(text_or_path: str | Path) -> list[Finding]:
    """
    Run all CWE/OWASP security checks over code text or a file path.

    Args:
        text_or_path: Either:
          - A string of source code text to scan directly, OR
          - A Path (or path string pointing to an existing file) to read and scan.

    Returns:
        List of Finding objects.  Empty list if no issues found.

    The distinction between "text" and "path" is:
      - If the argument is a Path instance, it is always treated as a file path.
      - If it is a str and names an existing file, it is treated as a file path.
      - Otherwise the str itself is scanned as source code.

    第10条: This function is the shared check bank called by both the `security`
    specialist sub-agent and the Phase 6 eval_suite.
    """
    # Resolve to text
    if isinstance(text_or_path, Path):
        # Always treat Path objects as file paths
        code_text = text_or_path.read_text(encoding="utf-8", errors="replace")
    elif isinstance(text_or_path, str):
        # Try to treat as a file path, but catch OSError for long strings or
        # strings that cannot be valid paths (e.g., file-name-too-long).
        try:
            p = Path(text_or_path)
            if p.is_file():
                code_text = p.read_text(encoding="utf-8", errors="replace")
            else:
                code_text = text_or_path
        except OSError:
            # Long strings cause OSError("File name too long") — treat as text
            code_text = text_or_path
    else:
        code_text = str(text_or_path)

    lines = code_text.splitlines()

    findings: list[Finding] = []
    for check in _CHECK_BANK:
        findings.extend(check(lines))

    return findings
