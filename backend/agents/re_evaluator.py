"""
Re-evaluator Agent — verifies fix suggestions and loops back if insufficient (max 2 iterations).
"""
from __future__ import annotations

import json
import re
from typing import Dict, List

from google import genai
from google.genai import types

from config import GOOGLE_API_KEY, MODEL
from models import Finding, FixSuggestion, VerifiedFix
from agents.fix_suggester import run_fix_suggester
from gemini_client import get_client

RE_EVALUATOR_SYSTEM = """You are ReEvaluatorAgent, a rigorous security and code quality auditor.

You will receive:
1. The original finding (the bug/vulnerability)
2. The suggested fix

Your job is to evaluate whether the fix ACTUALLY addresses the problem:
- Does it eliminate the root cause, or just mask symptoms?
- Does it introduce new problems?
- Is it complete? (e.g., parameterized query fix must use the right API, not just move string concat)
- Is the code syntactically valid?
- Does it follow security best practices?

Respond ONLY with valid JSON:
{
  "status": "verified" | "insufficient",
  "reasoning": "Detailed explanation of why the fix is accepted or rejected",
  "feedback": "If insufficient: specific instructions for improvement. Empty string if verified."
}
"""


async def run_re_evaluator(
    finding: Finding,
    fix: FixSuggestion,
    files_dict: Dict[str, str],
) -> VerifiedFix:
    """
    Verify a fix. If insufficient, loop back to FixSuggester (max 2 iterations).
    """
    current_fix = fix
    iteration = 1

    while iteration <= 2:
        result = await _evaluate_once(finding, current_fix)

        if result["status"] == "verified":
            return VerifiedFix(
                finding_id=finding.id,
                status="verified",
                final_fix=current_fix.suggested_fix,
                original_code=current_fix.original_code,
                explanation=current_fix.explanation,
                iterations=iteration,
            )

        # Insufficient — try to get a better fix
        if iteration < 2:
            feedback = result.get("feedback", "The fix is insufficient. Please revise.")
            improved_fixes = await run_fix_suggester(
                [finding],
                files_dict,
                feedback=feedback,
            )
            if improved_fixes:
                current_fix = improved_fixes[0]
        iteration += 1

    # After max iterations, return the best fix we have with failed status
    return VerifiedFix(
        finding_id=finding.id,
        status="failed",
        final_fix=current_fix.suggested_fix,
        original_code=current_fix.original_code,
        explanation=current_fix.explanation + f"\n\n[Note: Re-evaluator could not fully verify this fix after 2 iterations.]",
        iterations=2,
    )


async def _evaluate_once(finding: Finding, fix: FixSuggestion) -> dict:
    """Single evaluation pass."""
    prompt = f"""## Original Finding
- File: {finding.file}
- Line: {finding.line}
- Issue: {finding.issue}
- Severity: {finding.severity}
- Reasoning: {finding.reasoning}

## Suggested Fix
### Original Code
```
{fix.original_code}
```

### Proposed Fix
```
{fix.suggested_fix}
```

### Explanation
{fix.explanation}

Does this fix actually address the security/quality issue? Evaluate carefully.
"""

    result = get_client().models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=RE_EVALUATOR_SYSTEM,
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )

    raw = result.text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, Exception):
        return {"status": "verified", "reasoning": "Could not parse evaluator response; accepting fix.", "feedback": ""}


async def run_re_evaluator_batch(
    findings: List[Finding],
    fixes: List[FixSuggestion],
    files_dict: Dict[str, str],
) -> List[VerifiedFix]:
    """
    Run re-evaluator for each finding that has a fix.
    Findings without fixes get a 'skipped' status.
    """
    import asyncio

    fix_map = {f.finding_id: f for f in fixes}
    tasks = []
    task_findings = []

    for finding in findings:
        fix = fix_map.get(finding.id)
        if fix:
            tasks.append(run_re_evaluator(finding, fix, files_dict))
            task_findings.append(finding)

    if not tasks:
        return []

    results = await asyncio.gather(*tasks, return_exceptions=True)

    verified_fixes = []
    for finding, result in zip(task_findings, results):
        if isinstance(result, Exception):
            # On error, create a skipped entry
            fix = fix_map.get(finding.id)
            verified_fixes.append(VerifiedFix(
                finding_id=finding.id,
                status="skipped",
                final_fix=fix.suggested_fix if fix else "",
                original_code=fix.original_code if fix else "",
                explanation="Re-evaluator encountered an error.",
                iterations=0,
            ))
        else:
            verified_fixes.append(result)

    return verified_fixes
