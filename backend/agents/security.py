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
from gemini_client import get_client, call_with_retry

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

    model = call_with_retry(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SECURITY_SYSTEM,
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )

    raw_text = model.text
    print(f"[SecurityAgent] Raw response (first 500 chars):\n{raw_text[:500]}\n---")
    return _parse_findings(raw_text, agent="security")


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
    """Parse LLM JSON output into Finding objects.
    Handles:
    - Raw arrays: [...]
    - Wrapped objects (any case): {"Findings": [...]}, {"findings": [...]}, {"results": [...]}
    - Mistral field aliases: Vulnerability→issue, Description→reasoning, etc.
    """
    raw = raw.strip()
    # Strip markdown code fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[{agent}] JSON parse error: {e}\nRaw: {raw[:300]}")
        return []

    # ── Unwrap object envelopes ─────────────────────────────────────────
    if isinstance(data, dict):
        # Case-insensitive search for list values
        # Priority order: common list keys first
        list_keys = [
            "findings", "results", "issues", "vulnerabilities",
            "data", "items", "observations", "errors", "warnings",
        ]
        found_list = None

        # Try lowercase match first
        data_lower = {k.lower(): v for k, v in data.items()}
        for key in list_keys:
            if key in data_lower and isinstance(data_lower[key], list):
                found_list = data_lower[key]
                break

        # If still not found, check if any VALUE is a JSON string containing an array
        if found_list is None:
            for v in data.values():
                if isinstance(v, str) and v.strip().startswith('['):
                    try:
                        parsed = json.loads(v)
                        if isinstance(parsed, list):
                            found_list = parsed
                            break
                    except Exception:
                        pass

        # Mistral's bizarre pattern: JSON array embedded AS A DICT KEY
        if found_list is None:
            for k in data.keys():
                stripped = k.strip()
                if stripped.startswith('['):
                    try:
                        parsed = json.loads(stripped)
                        if isinstance(parsed, list):
                            found_list = parsed
                            print(f"[{agent}] Extracted array from dict KEY (Mistral quirk)")
                            break
                    except Exception:
                        pass

        if found_list is not None:
            data = found_list
        elif "issue" in data_lower or "severity" in data_lower or "vulnerability" in data_lower:
            data = [data]
        else:
            print(f"[{agent}] Unexpected dict format, keys: {list(data.keys())} — returning empty")
            return []

    if not isinstance(data, list):
        print(f"[{agent}] Expected list, got {type(data).__name__}")
        return []

    # ── Field alias map (handles Mistral's non-standard names) ──────────
    # Maps our expected field → list of aliases the model might use
    FIELD_ALIASES = {
        "file":      ["file", "filename", "path", "filepath", "location", "module"],
        "line":      ["line", "line_number", "lineno", "line_no"],
        "issue":     ["issue", "vulnerability", "title", "name", "problem",
                      "vuln_name", "finding", "check", "message"],
        "severity":  ["severity", "risk", "risk_level", "criticality", "priority", "impact"],
        "reasoning": ["reasoning", "description", "details", "explanation",
                      "detail", "reason", "rationale", "solution",
                      "recommendation", "remediation", "info"],
    }

    SEVERITY_NORMALIZE = {
        "critical": "Critical", "crit": "Critical", "p1": "Critical",
        "high": "High", "p2": "High",
        "medium": "Medium", "med": "Medium", "moderate": "Medium", "p3": "Medium",
        "low": "Low", "minor": "Low", "info": "Low", "informational": "Low", "p4": "Low",
    }

    def _get(item: dict, field: str, default=None):
        """Case-insensitive field lookup with aliases."""
        item_lower = {k.lower(): v for k, v in item.items()}
        for alias in FIELD_ALIASES.get(field, [field]):
            if alias in item_lower:
                return item_lower[alias]
        return default

    findings = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            raw_severity = str(_get(item, "severity", "Medium") or "Medium")
            severity = SEVERITY_NORMALIZE.get(raw_severity.lower().strip(), "Medium")

            # Build issue text — combine title + description for richer context
            issue = str(_get(item, "issue", "") or "")
            reasoning = str(_get(item, "reasoning", "") or "")

            # If issue is empty but reasoning has content, swap
            if not issue and reasoning:
                issue = reasoning[:120]

            if not issue:
                continue  # skip items with no discernible issue text

            findings.append(Finding(
                file=str(_get(item, "file", "(unknown file)") or "(unknown file)"),
                line=_get(item, "line"),
                issue=issue,
                severity=severity,
                reasoning=reasoning or issue,
                agent=agent,
            ))
        except Exception as e:
            print(f"[{agent}] Skipping malformed item: {e} — {item}")
            continue

    print(f"[{agent}] Parsed {len(findings)} finding(s)")
    return findings
