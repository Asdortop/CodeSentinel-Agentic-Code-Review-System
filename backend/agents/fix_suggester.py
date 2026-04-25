"""
Fix Suggester Agent — generates concrete before/after code fix suggestions.
Processes ONE finding at a time to avoid Mistral's unpredictable JSON formatting.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Dict, List, Optional

from google.genai import types

from config import MODEL
from models import Finding, FixSuggestion
from gemini_client import call_with_retry

FIX_SUGGESTER_SYSTEM = """You are an expert software engineer who writes production-quality code fixes.

You will be given ONE security or code quality finding. Respond with a single JSON object (not an array):

{
  "original_code": "the exact vulnerable/bad code snippet",
  "suggested_fix": "the corrected code that fixes the issue",
  "explanation": "clear explanation of what changed and why"
}

Rules:
- Provide ACTUAL code, not pseudocode or vague suggestions
- Keep fixes minimal — change only what is necessary
- Preserve existing code style, indentation, and variable names
- If no specific file code is shown, write a realistic example fix for the issue type
- Do NOT wrap in markdown. Return ONLY the JSON object."""


async def _fix_one(finding: Finding, files_dict: Dict[str, str], feedback: str = "") -> FixSuggestion:
    """Generate a fix for a single finding — one LLM call, one JSON object back."""
    file_content = files_dict.get(finding.file, "")
    snippet = _extract_snippet(file_content, finding.line or 1) if file_content else ""

    feedback_section = f"\n\nReviewer feedback to incorporate:\n{feedback}" if feedback else ""

    prompt = (
        f"Finding to fix:\n"
        f"- File: {finding.file}\n"
        f"- Line: {finding.line or 'unknown'}\n"
        f"- Issue: {finding.issue}\n"
        f"- Severity: {finding.severity}\n"
        f"- Reasoning: {finding.reasoning}\n"
    )
    if snippet:
        prompt += f"\nCode context:\n```\n{snippet}\n```"
    prompt += feedback_section
    prompt += "\n\nRespond with ONLY a JSON object containing original_code, suggested_fix, explanation."

    result = call_with_retry(
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
    raw = re.sub(r"\s*```$", "", raw).strip()

    print(f"[FixSuggester:{finding.id}] Raw (first 200): {raw[:200]}")

    # Parse — handle all Mistral quirks
    try:
        data = _robust_parse(raw)
    except Exception as e:
        print(f"[FixSuggester:{finding.id}] Parse failed: {e}")
        data = {}

    # Field aliases — Mistral uses many different names
    ALIASES = {
        "original_code": ["original_code", "before", "original", "vulnerable_code",
                          "code_before", "bad_code", "insecure_code"],
        "suggested_fix": ["suggested_fix", "fixed_code", "fix", "after", "corrected_code",
                          "code_after", "solution", "patched_code", "secure_code", "fixed"],
        "explanation":   ["explanation", "description", "reason", "details", "rationale",
                          "analysis", "summary"],
    }

    def _get(field: str) -> str:
        if isinstance(data, dict):
            item_lower = {k.lower(): v for k, v in data.items()}
            for alias in ALIASES.get(field, [field]):
                if alias in item_lower and item_lower[alias]:
                    return str(item_lower[alias])
        return ""

    original = _get("original_code")
    fix_code = _get("suggested_fix")
    explanation = _get("explanation")

    print(f"[FixSuggester:{finding.id}] original={bool(original)} fix={bool(fix_code)}")

    return FixSuggestion(
        finding_id=finding.id,
        original_code=original,
        suggested_fix=fix_code,
        explanation=explanation,
    )


def _robust_parse(raw: str):
    """Parse JSON, handling all of Mistral's quirks."""
    # Try direct parse first
    try:
        data = json.loads(raw)
        # If we got a list, unwrap the first item (shouldn't happen for single-object prompt)
        if isinstance(data, list) and data:
            return data[0]
        # If we got a dict with a wrapper key like {"fixes": [{...}]}, unwrap
        if isinstance(data, dict):
            data_lower = {k.lower(): v for k, v in data.items()}
            for wrapper in ("fix", "result", "fixes", "data", "output", "response"):
                if wrapper in data_lower:
                    val = data_lower[wrapper]
                    if isinstance(val, list) and val:
                        return val[0]
                    if isinstance(val, dict):
                        return val
        return data
    except json.JSONDecodeError:
        pass

    # Try to find a JSON object {...} anywhere in the string
    match = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass

    # Try to find JSON array [...] and take first element
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if match:
        try:
            arr = json.loads(match.group())
            if isinstance(arr, list) and arr:
                return arr[0]
        except Exception:
            pass

    # Check if any KEY of a parsed dict is itself a JSON string (Mistral's bizarre pattern)
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            for k in data.keys():
                stripped = k.strip()
                if stripped.startswith('{') or stripped.startswith('['):
                    try:
                        parsed_key = json.loads(stripped)
                        if isinstance(parsed_key, list) and parsed_key:
                            return parsed_key[0]
                        if isinstance(parsed_key, dict):
                            return parsed_key
                    except Exception:
                        pass
    except Exception:
        pass

    return {}


async def run_fix_suggester(
    findings: List[Finding],
    files_dict: Dict[str, str],
    feedback: Optional[str] = None,
) -> List[FixSuggestion]:
    """
    For each finding, generate a concrete code fix.
    Processes findings individually (one LLM call each) to avoid ID-matching issues.
    If feedback is provided (from re-evaluator), applies to all findings.
    """
    if not findings:
        return []

    fb = feedback or ""
    tasks = [_fix_one(f, files_dict, fb) for f in findings]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    suggestions = []
    for finding, result in zip(findings, results):
        if isinstance(result, Exception):
            print(f"[FixSuggester] Error for {finding.id}: {result}")
            suggestions.append(FixSuggestion(
                finding_id=finding.id,
                original_code="",
                suggested_fix="",
                explanation=f"Fix generation failed: {result}",
            ))
        else:
            suggestions.append(result)

    print(f"[FixSuggesterAgent] Generated {len(suggestions)} fix(es)")
    return suggestions


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
