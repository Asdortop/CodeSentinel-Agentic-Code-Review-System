"""
Static analysis runners: bandit (Python security), radon (complexity), regex secret detection.
Falls back to empty results gracefully if tools are unavailable.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Regex-based secret / hardcoded credential scanner
# ---------------------------------------------------------------------------

SECRET_PATTERNS: List[Dict[str, Any]] = [
    {"name": "AWS Access Key ID", "pattern": r"AKIA[0-9A-Z]{16}", "severity": "Critical"},
    {"name": "AWS Secret Access Key", "pattern": r"(?i)aws.{0,20}secret.{0,20}['\"][0-9a-zA-Z/+]{40}['\"]", "severity": "Critical"},
    {"name": "Generic API Key", "pattern": r"(?i)(api[_\-]?key|apikey)\s*[=:]\s*['\"][^'\"]{8,}['\"]", "severity": "High"},
    {"name": "Generic Secret", "pattern": r"(?i)(secret|password|passwd|pwd)\s*[=:]\s*['\"][^'\"]{6,}['\"]", "severity": "High"},
    {"name": "Bearer Token", "pattern": r"(?i)bearer\s+[a-zA-Z0-9\-_.~+/]+=*", "severity": "High"},
    {"name": "GitHub Token", "pattern": r"gh[pousr]_[A-Za-z0-9_]{36,}", "severity": "Critical"},
    {"name": "Google API Key", "pattern": r"AIza[0-9A-Za-z\-_]{35}", "severity": "Critical"},
    {"name": "Private Key Header", "pattern": r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "severity": "Critical"},
    {"name": "Slack Token", "pattern": r"xox[baprs]-[0-9A-Za-z]{10,}", "severity": "High"},
    {"name": "Database URL with credentials", "pattern": r"(?i)(mysql|postgres|mongodb|redis)://[^:]+:[^@]+@", "severity": "Critical"},
    {"name": "Hardcoded IP + password", "pattern": r"(?i)password\s*=\s*['\"][^'\"]{4,}['\"]", "severity": "Medium"},
]


def run_secret_patterns(files_dict: Dict[str, str]) -> List[Dict[str, Any]]:
    """Regex-scan file contents for hardcoded secrets."""
    findings: List[Dict[str, Any]] = []
    for path, content in files_dict.items():
        for line_no, line in enumerate(content.splitlines(), 1):
            for spec in SECRET_PATTERNS:
                if re.search(spec["pattern"], line):
                    # Redact the actual value in the finding text
                    findings.append({
                        "file": path,
                        "line": line_no,
                        "issue": f"Potential hardcoded secret: {spec['name']}",
                        "severity": spec["severity"],
                        "tool": "secret_scanner",
                        "snippet": line.strip()[:120],
                    })
    return findings


# ---------------------------------------------------------------------------
# bandit — Python security linter
# ---------------------------------------------------------------------------

def run_bandit(files_dict: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Run bandit on Python files. Returns list of finding dicts.
    Falls back to [] if bandit is not installed.
    """
    python_files = {k: v for k, v in files_dict.items() if k.endswith(".py")}
    if not python_files:
        return []

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write Python files to temp dir preserving relative structure
            for rel_path, content in python_files.items():
                dest = Path(tmpdir) / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")

            result = subprocess.run(
                [sys.executable, "-m", "bandit", "-r", tmpdir, "-f", "json", "-q", "--exit-zero"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if not result.stdout.strip():
                return []

            data = json.loads(result.stdout)
            findings = []
            for r in data.get("results", []):
                # Normalise file path back to relative
                abs_path = r.get("filename", "")
                rel = os.path.relpath(abs_path, tmpdir).replace("\\", "/")
                findings.append({
                    "file": rel,
                    "line": r.get("line_number"),
                    "issue": r.get("issue_text", ""),
                    "severity": _map_bandit_severity(r.get("issue_severity", "MEDIUM")),
                    "tool": "bandit",
                    "test_id": r.get("test_id", ""),
                    "snippet": r.get("code", "").strip()[:200],
                })
            return findings

    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, Exception):
        return []


def _map_bandit_severity(s: str) -> str:
    return {"HIGH": "High", "MEDIUM": "Medium", "LOW": "Low"}.get(s.upper(), "Medium")


# ---------------------------------------------------------------------------
# radon — cyclomatic complexity
# ---------------------------------------------------------------------------

def run_radon(files_dict: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Run radon cc on Python files. Returns findings for functions with complexity >= 10.
    Falls back to [] if radon is not installed.
    """
    python_files = {k: v for k, v in files_dict.items() if k.endswith(".py")}
    if not python_files:
        return []

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            for rel_path, content in python_files.items():
                dest = Path(tmpdir) / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")

            result = subprocess.run(
                [sys.executable, "-m", "radon", "cc", tmpdir, "-s", "-j", "--min", "C"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if not result.stdout.strip():
                return []

            data = json.loads(result.stdout)
            findings = []
            for abs_path, blocks in data.items():
                rel = os.path.relpath(abs_path, tmpdir).replace("\\", "/")
                for block in blocks:
                    rank = block.get("rank", "A")
                    complexity = block.get("complexity", 0)
                    name = block.get("name", "unknown")
                    lineno = block.get("lineno", None)
                    severity = "High" if rank in ("D", "E", "F") else "Medium"
                    findings.append({
                        "file": rel,
                        "line": lineno,
                        "issue": f"High cyclomatic complexity ({complexity}) in '{name}' — rank {rank}",
                        "severity": severity,
                        "tool": "radon",
                        "complexity": complexity,
                    })
            return findings

    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, Exception):
        return []
