"""
Fix Suggester Agent — generates concrete before/after code fix suggestions.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from google import genai
from google.genai import types

from config import GOOGLE_API_KEY, MODEL
from models import Finding, FixSuggestion
from gemini_client import get_client

FIX_SUGGESTER_SYSTEM = """You are FixSuggesterAgent, an expert software engineer who writes concrete, production-quality code fixes.

For each security or quality finding, you must produce:
1. The EXACT original code snippet (copy it precisely from the source)
2. A corrected version that fixes the issue
3. A clear explanation of what changed and why

Rules:
- Provide ACTUAL code, not pseudocode or vague suggestions
- Keep fixes minimal — change only what's necessary to address the finding
- Preserve surrounding code style, indentation, and variable names
- If the original code is not available (e.g., config issue), provide example corrected code
- For dependency issues, provide the updated version specifier

Respond ONLY with valid JSON array:
[
  {
    "finding_id": "abc12345",
    "original_code": "exact original code snippet",
    "suggested_fix": "corrected code snippet",
    "explanation": "What was wrong and how the fix addresses it"
  }
]

Do not include markdown, only JSON. One entry per finding.
"""


async def run_fix_suggester(
    findings: List[Finding],
    files_dict: Dict[str, str],
    feedback: Optional[str] = None,
) -> List[FixSuggestion]:
    """
    For each Critical/High finding, generate a concrete code fix.
    If feedback is provided (from re-evaluator), it's included to improve the fix.
    """
    if not findings:
        return []

    # Build context: relevant file snippets around each finding
    findings_context = []
    for f in findings:
        file_content = files_dict.get(f.file, "")
        snippet = _extract_snippet(file_content, f.line or 1)
        findings_context.append({
            "id": f.id,
            "file": f.file,
            "line": f.line,
            "issue": f.issue,
            "severity": f.severity,
            "reasoning": f.reasoning,
            "agent": f.agent,
            "code_context": snippet,
        })

    findings_json = json.dumps(findings_context, indent=2)

    feedback_section = ""
    if feedback:
        feedback_section = f"\n\n## Reviewer Feedback (improve fixes based on this)\n{feedback}"

    prompt = f"""Generate concrete code fixes for these findings:

```json
{findings_json}
```
{feedback_section}

Return a JSON array with one fix per finding_id.
"""

    result = get_client().models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=FIX_SUGGESTER_SYSTEM,
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )

    raw = result.text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
        suggestions = []
        for item in data:
            try:
                suggestions.append(FixSuggestion(
                    finding_id=item.get("finding_id", ""),
                    original_code=item.get("original_code", ""),
                    suggested_fix=item.get("suggested_fix", ""),
                    explanation=item.get("explanation", ""),
                ))
            except Exception:
                continue
        return suggestions
    except (json.JSONDecodeError, Exception):
        return []


def _extract_snippet(file_content: str, line: int, context_lines: int = 10) -> str:
    """Extract a snippet of code around a specific line number."""
    if not file_content:
        return ""
    lines = file_content.splitlines()
    start = max(0, line - context_lines - 1)
    end = min(len(lines), line + context_lines)
    snippet_lines = []
    for i, l in enumerate(lines[start:end], start=start + 1):
        marker = ">>>" if i == line else "   "
        snippet_lines.append(f"{marker} {i:4d} | {l}")
    return "\n".join(snippet_lines)
