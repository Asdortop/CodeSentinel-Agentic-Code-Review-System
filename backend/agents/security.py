"""
Security Agent — finds security vulnerabilities using static analysis + Gemini reasoning.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List

from google import genai
from google.genai import types

from config import GOOGLE_API_KEY, MODEL
from models import Finding
from tools.code_runner import run_bandit, run_secret_patterns
from gemini_client import get_client

SECURITY_SYSTEM = """You are SecurityAgent, a world-class application security expert conducting a code review.

You will receive:
1. Static analysis results from automated tools (bandit, secret scanner)
2. The actual source code of the relevant files

Your job:
- Review the static analysis findings and the code
- Identify additional security issues the tools may have missed:
  * SQL injection (string concatenation in queries)
  * Command injection (os.system, subprocess with user input)
  * Insecure deserialization (pickle.loads, yaml.load without Loader)
  * Missing authentication/authorization checks
  * CORS misconfiguration
  * Insecure direct object references
  * Missing input validation
  * Unsafe use of eval/exec
  * Insecure cryptography (MD5, SHA1 for passwords, weak key sizes)
  * Path traversal vulnerabilities

For each finding, assign severity:
- Critical: Direct exploitability, data breach, RCE possible
- High: Significant risk, requires attacker access
- Medium: Indirect risk
- Low: Minor concern, best practice violation

Respond ONLY with valid JSON array:
[
  {
    "file": "path/to/file.py",
    "line": 42,
    "issue": "Clear description of the vulnerability",
    "severity": "Critical|High|Medium|Low",
    "reasoning": "Why this is a security risk and how it could be exploited"
  }
]

Return [] if no issues found. Do not include markdown, only JSON.
"""


async def run_security_agent(files_dict: Dict[str, str], context_files: List[str]) -> List[Finding]:
    """
    Run bandit + secret scanner, then call Gemini to reason about findings.
    Returns list of Finding objects tagged with agent="security".
    """
    # Filter to context files
    focused = {k: v for k, v in files_dict.items() if k in context_files}
    if not focused:
        focused = files_dict  # use all if context is empty

    # Run static analysis tools
    bandit_findings = run_bandit(focused)
    secret_findings = run_secret_patterns(focused)

    tool_results_text = _format_tool_results(bandit_findings + secret_findings)
    code_text = _format_code(focused)

    prompt = f"""## Static Analysis Results
{tool_results_text}

## Source Code Under Review
{code_text}

Analyze the above and return your security findings as a JSON array.
"""

    model = get_client().models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SECURITY_SYSTEM,
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )

    return _parse_findings(model.text, agent="security")


def _format_tool_results(results: list) -> str:
    if not results:
        return "(No automated tool findings)"
    lines = []
    for r in results:
        lines.append(
            f"- [{r.get('tool', 'tool')}] {r['file']} line {r.get('line', '?')}: "
            f"{r['issue']} (severity: {r['severity']})"
        )
    return "\n".join(lines)


def _format_code(files_dict: Dict[str, str]) -> str:
    parts = []
    for path, content in files_dict.items():
        parts.append(f"### {path}\n```\n{content}\n```")
    return "\n\n".join(parts)


def _parse_findings(raw: str, agent: str) -> List[Finding]:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        findings = []
        for item in data:
            try:
                findings.append(Finding(
                    file=item.get("file", "unknown"),
                    line=item.get("line"),
                    issue=item.get("issue", ""),
                    severity=item.get("severity", "Medium"),
                    reasoning=item.get("reasoning", ""),
                    agent=agent,
                ))
            except Exception:
                continue
        return findings
    except (json.JSONDecodeError, Exception):
        return []
