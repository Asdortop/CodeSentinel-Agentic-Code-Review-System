"""
Critic Agent — deduplicates, re-ranks, and summarizes all specialist findings.
"""
from __future__ import annotations

import json
import re
from typing import List

from google import genai
from google.genai import types

from config import GOOGLE_API_KEY, MODEL
from models import CriticReport, Finding
from gemini_client import get_client

CRITIC_SYSTEM = """You are CriticAgent, a senior principal engineer and security architect.

You will receive findings from multiple specialist agents (security, quality, dependency).
Your responsibilities:
1. DEDUPLICATE: If multiple agents found the same issue in the same file at the same location, merge them into one finding. Keep the most severe severity.
2. RE-RANK SEVERITY: Re-evaluate severity with full context. Example: a "Missing error handling" Medium in authentication code should become High. A quality issue in test code can be downgraded.
3. EXECUTIVE SUMMARY: Write 3-5 sentences summarizing the overall security posture and code quality of the repository.
4. SORT: Return findings sorted by severity: Critical first, then High, Medium, Low.

Respond ONLY with valid JSON in this exact format:
{
  "summary": "3-5 sentence executive summary of the codebase security and quality...",
  "findings": [
    {
      "id": "(preserve original id if present, else generate short unique id)",
      "file": "path/to/file.py",
      "line": 42,
      "issue": "Clear description",
      "severity": "Critical|High|Medium|Low",
      "reasoning": "Updated reasoning with full context",
      "agent": "security|quality|dependency"
    }
  ],
  "total_critical": 0,
  "total_high": 0,
  "total_medium": 0,
  "total_low": 0
}
"""


async def run_critic(all_findings: List[Finding]) -> CriticReport:
    """
    Consolidate all specialist findings into a ranked, deduplicated report.
    """
    if not all_findings:
        return CriticReport(
            summary="No significant issues were found in this repository. The codebase appears clean.",
            findings=[],
            total_critical=0,
            total_high=0,
            total_medium=0,
            total_low=0,
        )

    findings_json = json.dumps(
        [f.model_dump() for f in all_findings],
        indent=2,
    )

    prompt = f"""Review and consolidate these findings from specialist agents:

```json
{findings_json}
```

Return the deduplicated, re-ranked findings with an executive summary as JSON.
"""

    result = get_client().models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=CRITIC_SYSTEM,
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )

    raw = result.text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
        findings_out = []
        for item in data.get("findings", []):
            try:
                findings_out.append(Finding(
                    id=item.get("id", ""),
                    file=item.get("file", "unknown"),
                    line=item.get("line"),
                    issue=item.get("issue", ""),
                    severity=item.get("severity", "Medium"),
                    reasoning=item.get("reasoning", ""),
                    agent=item.get("agent", ""),
                ))
            except Exception:
                continue

        # Recalculate totals from actual findings
        totals = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
        for f in findings_out:
            totals[f.severity] = totals.get(f.severity, 0) + 1

        return CriticReport(
            summary=data.get("summary", "Review complete."),
            findings=findings_out,
            total_critical=data.get("total_critical", totals["Critical"]),
            total_high=data.get("total_high", totals["High"]),
            total_medium=data.get("total_medium", totals["Medium"]),
            total_low=data.get("total_low", totals["Low"]),
        )

    except (json.JSONDecodeError, Exception):
        # Fallback: return raw findings sorted by severity
        SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        sorted_findings = sorted(all_findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 4))
        totals = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
        for f in sorted_findings:
            totals[f.severity] = totals.get(f.severity, 0) + 1

        return CriticReport(
            summary="Multiple issues found across security, quality, and dependency dimensions.",
            findings=sorted_findings,
            total_critical=totals["Critical"],
            total_high=totals["High"],
            total_medium=totals["Medium"],
            total_low=totals["Low"],
        )
