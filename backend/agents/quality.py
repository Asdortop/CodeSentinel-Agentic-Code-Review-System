"""
Quality Agent — finds code quality issues using radon complexity + Gemini reasoning.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List

from google import genai
from google.genai import types

from config import GOOGLE_API_KEY, MODEL
from models import Finding
from tools.code_runner import run_radon
from agents.security import _format_code, _parse_findings, _format_tool_results
from gemini_client import get_client

QUALITY_SYSTEM = """You are QualityAgent, a senior software engineer conducting a code quality review.

You will receive:
1. Cyclomatic complexity results from radon
2. The actual source code of the relevant files

Your job is to identify code quality issues:
- Functions with cyclomatic complexity >= 10 (already flagged by radon, confirm and add context)
- Functions longer than 50 lines
- Missing docstrings on public functions/classes
- Missing error handling (bare except, no try/except where I/O happens)
- Dead code (unreachable code, unused variables/imports)
- Poor naming (single-letter variables outside loops, meaningless names like `foo`, `tmp`, `x`)
- No logging or observability in critical paths
- God objects / classes doing too much
- Repeated code blocks (DRY violations)
- Missing type annotations on public APIs (Python/TypeScript)

Severity guidelines:
- High: Severely impacts maintainability, complexity >= 15, functions > 100 lines
- Medium: Moderate impact, complexity 10-14, missing error handling, functions 50-100 lines
- Low: Minor style issues, missing docstrings, poor naming

Respond ONLY with valid JSON array:
[
  {
    "file": "path/to/file.py",
    "line": 42,
    "issue": "Clear description of the quality issue",
    "severity": "High|Medium|Low",
    "reasoning": "Why this is a problem and its impact on maintainability/reliability"
  }
]

Return [] if no issues found. Do not include markdown, only JSON.
"""


async def run_quality_agent(files_dict: Dict[str, str], context_files: List[str]) -> List[Finding]:
    """
    Run radon, then call Gemini to reason about quality findings.
    Returns list of Finding objects tagged with agent="quality".
    """
    focused = {k: v for k, v in files_dict.items() if k in context_files}
    if not focused:
        focused = files_dict

    radon_findings = run_radon(focused)
    tool_results_text = _format_tool_results(radon_findings)
    code_text = _format_code(focused)

    prompt = f"""## Complexity Analysis Results (radon)
{tool_results_text}

## Source Code Under Review
{code_text}

Analyze the above and return your code quality findings as a JSON array.
"""

    result = get_client().models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=QUALITY_SYSTEM,
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )

    return _parse_findings(result.text, agent="quality")
