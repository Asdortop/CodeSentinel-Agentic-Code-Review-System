"""
Planner Agent — analyzes repo structure and decides which specialist agents to invoke.
Uses Gemini 2.0 Flash via google-genai.
"""
from __future__ import annotations

import json
import re
from typing import Dict

from google import genai
from google.genai import types

from config import GOOGLE_API_KEY, MODEL
from models import AgentPlan
from gemini_client import get_client


def _summarize_repo(files_dict: Dict[str, str]) -> str:
    """Build a compact summary: language counts + file listing."""
    from collections import Counter
    import os

    ext_counter: Counter = Counter()
    for path in files_dict:
        _, ext = os.path.splitext(path)
        if ext:
            ext_counter[ext.lower()] += 1

    summary_lines = ["## File tree (relevant files)\n"]
    for path in sorted(files_dict.keys()):
        summary_lines.append(f"  {path}")

    summary_lines.append("\n## Language composition")
    for ext, count in ext_counter.most_common():
        summary_lines.append(f"  {ext}: {count} file(s)")

    return "\n".join(summary_lines)


PLANNER_SYSTEM = """You are PlannerAgent, the orchestrator of an agentic code review system.

Given a repository file tree and language composition, your job is to decide which specialist agents
to invoke and which files each agent should focus on.

Available specialists:
- security: checks for hardcoded secrets, SQL injection, unsafe code patterns, insecure configs
- quality: checks cyclomatic complexity, dead code, missing error handling, long functions, poor naming
- dependency: checks requirements.txt, package.json, pyproject.toml for outdated/vulnerable packages

Rules:
1. Always invoke at minimum 1 agent.
2. Invoke `security` if ANY of these are present: .py, .js, .ts, .java, .go, .env* files, OR if secrets-related filenames exist.
3. Invoke `quality` if ANY source code files (.py, .js, .ts, .java, .go) exist.
4. Invoke `dependency` ONLY if requirements.txt, package.json, pyproject.toml, Pipfile, or go.mod exist.
5. For each agent, list the specific files it should focus on (max 20 files per agent).
6. Prefer to assign security-sensitive files (auth, db, api, config) to `security`.

Respond ONLY with valid JSON in exactly this format:
{
  "agents_to_invoke": ["security", "quality", "dependency"],
  "security_files": ["path/to/file1.py", "..."],
  "quality_files": ["path/to/file2.py", "..."],
  "dependency_files": ["requirements.txt", "package.json"],
  "notes": "Brief explanation of your reasoning (1-2 sentences)"
}
"""


async def run_planner(files_dict: Dict[str, str]) -> AgentPlan:
    """
    Calls Gemini to decide agent routing.
    Returns an AgentPlan with agent list and per-agent file lists.
    """
    repo_summary = _summarize_repo(files_dict)

    response = get_client().models.generate_content(
        model=MODEL,
        contents=f"Analyze this repository and decide which agents to invoke:\n\n{repo_summary}",
        config=types.GenerateContentConfig(
            system_instruction=PLANNER_SYSTEM,
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )

    raw = response.text.strip()

    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
        plan = AgentPlan(
            agents_to_invoke=data.get("agents_to_invoke", ["security", "quality"]),
            security_files=data.get("security_files", []),
            quality_files=data.get("quality_files", []),
            dependency_files=data.get("dependency_files", []),
            notes=data.get("notes", ""),
        )
    except (json.JSONDecodeError, Exception):
        # Fallback: invoke all relevant agents based on file presence
        plan = _fallback_plan(files_dict)

    return plan


def _fallback_plan(files_dict: Dict[str, str]) -> AgentPlan:
    """Deterministic fallback if Gemini response can't be parsed."""
    import os

    agents = []
    security_files = []
    quality_files = []
    dependency_files = []

    dep_names = {"requirements.txt", "package.json", "pyproject.toml", "Pipfile", "go.mod"}
    source_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go"}

    for path in files_dict:
        basename = os.path.basename(path)
        _, ext = os.path.splitext(path)
        if basename in dep_names:
            dependency_files.append(path)
        if ext.lower() in source_exts or basename.startswith(".env"):
            security_files.append(path)
            quality_files.append(path)

    if security_files:
        agents.append("security")
    if quality_files:
        agents.append("quality")
    if dependency_files:
        agents.append("dependency")
    if not agents:
        agents = ["security"]

    return AgentPlan(
        agents_to_invoke=agents,
        security_files=security_files[:20],
        quality_files=quality_files[:20],
        dependency_files=dependency_files,
        notes="Fallback plan (LLM parse failed) — applied heuristic routing.",
    )
