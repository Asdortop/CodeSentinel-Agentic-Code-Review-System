"""
CodeSentinel — FastAPI backend with SSE streaming multi-agent orchestration.
"""
from __future__ import annotations

import asyncio
import json
import sys
import os
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# Add backend dir to path so imports work when run from project root
sys.path.insert(0, os.path.dirname(__file__))

from config import GOOGLE_API_KEY
from models import (
    FinalReport,
    ReviewRequest,
)
from tools.github_fetcher import fetch_repository
from agents.planner import run_planner
from agents.security import run_security_agent
from agents.quality import run_quality_agent
from agents.dependency import run_dependency_agent
from agents.critic import run_critic
from agents.fix_suggester import run_fix_suggester
from agents.re_evaluator import run_re_evaluator_batch

app = FastAPI(
    title="CodeSentinel",
    description="Agentic code review powered by Google Gemini",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _sse(event: str, data: dict) -> str:
    """Format a server-sent event string."""
    payload = json.dumps({"agent": data.get("agent", ""), **data})
    return f"event: {event}\ndata: {payload}\n\n"


def _agent_event(
    agent: str,
    status: str,
    message: str,
    extra: dict | None = None,
) -> str:
    data: dict = {
        "agent": agent,
        "status": status,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        data.update(extra)
    return _sse("agent_update", data)


# ---------------------------------------------------------------------------
# Orchestration pipeline (async generator for SSE)
# ---------------------------------------------------------------------------

async def run_pipeline(repo_url: str) -> AsyncGenerator[str, None]:
    """
    Full multi-agent pipeline as an async generator yielding SSE events.
    """
    if not GOOGLE_API_KEY:
        yield _sse("error", {"message": "GOOGLE_API_KEY is not configured on the server."})
        return

    # ── Step 1: Repo Fetcher ──────────────────────────────────────────────
    yield _agent_event("RepoFetcher", "running", f"Fetching repository: {repo_url}")
    try:
        owner, repo_name, files_dict = await fetch_repository(repo_url)
    except ValueError as e:
        yield _sse("error", {"message": str(e)})
        return
    except Exception as e:
        yield _sse("error", {"message": f"Failed to fetch repository: {str(e)}"})
        return

    file_count = len(files_dict)
    yield _agent_event(
        "RepoFetcher", "complete",
        f"Fetched {file_count} files from {owner}/{repo_name}",
        {"file_count": file_count, "files": list(files_dict.keys())},
    )

    if not files_dict:
        yield _sse("error", {"message": "No relevant source files found in this repository."})
        return

    # ── Step 2: Planner Agent ─────────────────────────────────────────────
    yield _agent_event("PlannerAgent", "running", "Analyzing repository structure...")
    try:
        plan = await run_planner(files_dict)
    except Exception as e:
        yield _sse("error", {"message": f"Planner failed: {str(e)}"})
        return

    agents_str = ", ".join(plan.agents_to_invoke)
    yield _agent_event(
        "PlannerAgent", "complete",
        f"Plan: invoking [{agents_str}] agents. {plan.notes}",
        {"plan": plan.model_dump()},
    )

    # ── Step 3: Parallel Specialist Agents ────────────────────────────────
    specialist_tasks = []
    specialist_names = []

    if "security" in plan.agents_to_invoke:
        specialist_tasks.append(run_security_agent(files_dict, plan.security_files))
        specialist_names.append("SecurityAgent")
    if "quality" in plan.agents_to_invoke:
        specialist_tasks.append(run_quality_agent(files_dict, plan.quality_files))
        specialist_names.append("QualityAgent")
    if "dependency" in plan.agents_to_invoke:
        specialist_tasks.append(run_dependency_agent(files_dict))
        specialist_names.append("DependencyAgent")

    # Emit "running" for all specialists
    for name in specialist_names:
        yield _agent_event(name, "running", "Analyzing code...")

    try:
        specialist_results = await asyncio.gather(*specialist_tasks, return_exceptions=True)
    except Exception as e:
        yield _sse("error", {"message": f"Specialist agents failed: {str(e)}"})
        return

    all_findings = []
    for name, result in zip(specialist_names, specialist_results):
        if isinstance(result, Exception):
            yield _agent_event(name, "error", f"Agent encountered an error: {str(result)}")
        else:
            count = len(result)
            all_findings.extend(result)
            yield _agent_event(
                name, "complete",
                f"Found {count} issue(s)",
                {"finding_count": count},
            )

    # ── Step 4: Critic Agent ──────────────────────────────────────────────
    yield _agent_event("CriticAgent", "running", f"Consolidating {len(all_findings)} findings...")
    try:
        critic_report = await run_critic(all_findings)
    except Exception as e:
        yield _sse("error", {"message": f"Critic agent failed: {str(e)}"})
        return

    yield _agent_event(
        "CriticAgent", "complete",
        f"Consolidated: {critic_report.total_critical} Critical, {critic_report.total_high} High, "
        f"{critic_report.total_medium} Medium, {critic_report.total_low} Low",
        {
            "total_critical": critic_report.total_critical,
            "total_high": critic_report.total_high,
            "total_medium": critic_report.total_medium,
            "total_low": critic_report.total_low,
        },
    )

    # ── Step 5: Fix Suggester ─────────────────────────────────────────────
    critical_high = [
        f for f in critic_report.findings
        if f.severity in ("Critical", "High")
    ]

    yield _agent_event(
        "FixSuggesterAgent", "running",
        f"Generating code fixes for {len(critical_high)} Critical/High findings...",
    )
    try:
        fixes = await run_fix_suggester(critical_high, files_dict)
    except Exception as e:
        fixes = []
        yield _agent_event("FixSuggesterAgent", "error", f"Fix generation failed: {str(e)}")

    if fixes:
        yield _agent_event(
            "FixSuggesterAgent", "complete",
            f"Generated {len(fixes)} fix suggestion(s)",
            {"fix_count": len(fixes)},
        )
    else:
        yield _agent_event("FixSuggesterAgent", "complete", "No fixes generated.")

    # ── Step 6: Re-evaluator ──────────────────────────────────────────────
    if fixes:
        yield _agent_event(
            "ReEvaluatorAgent", "running",
            f"Verifying {len(fixes)} fix(es) — may loop up to 2 iterations per finding...",
        )
        try:
            verified_fixes = await run_re_evaluator_batch(critical_high, fixes, files_dict)
        except Exception as e:
            verified_fixes = []
            yield _agent_event("ReEvaluatorAgent", "error", f"Verification failed: {str(e)}")

        if verified_fixes:
            verified_count = sum(1 for v in verified_fixes if v.status == "verified")
            multi_iter = sum(1 for v in verified_fixes if v.iterations > 1)
            yield _agent_event(
                "ReEvaluatorAgent", "complete",
                f"Verified {verified_count}/{len(verified_fixes)} fix(es). "
                f"{multi_iter} required a second iteration.",
                {
                    "verified_count": verified_count,
                    "total": len(verified_fixes),
                    "multi_iteration_count": multi_iter,
                },
            )
    else:
        verified_fixes = []
        yield _agent_event("ReEvaluatorAgent", "complete", "No fixes to verify.")

    # ── Step 7: Emit final report ─────────────────────────────────────────
    final_report = FinalReport(
        repo_url=repo_url,
        repo_name=f"{owner}/{repo_name}",
        summary=critic_report.summary,
        total_critical=critic_report.total_critical,
        total_high=critic_report.total_high,
        total_medium=critic_report.total_medium,
        total_low=critic_report.total_low,
        findings=critic_report.findings,
        verified_fixes=verified_fixes,
        agent_plan=plan,
    )

    yield _sse("report_complete", final_report.model_dump())


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/review")
async def review_repo(request: ReviewRequest):
    """
    POST /review — streams SSE events for the full agent pipeline.
    """
    return StreamingResponse(
        run_pipeline(request.repo_url),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/health")
async def health():
    from config import LLM_BACKEND, OLLAMA_MODEL, OLLAMA_BASE_URL, MODEL
    if LLM_BACKEND == "ollama":
        return {"status": "ok", "backend": "ollama", "model": OLLAMA_MODEL, "ollama_url": OLLAMA_BASE_URL}
    return {"status": "ok", "backend": "gemini", "model": MODEL, "api_key_set": bool(GOOGLE_API_KEY)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
