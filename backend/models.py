from __future__ import annotations
from typing import Literal, Optional, List
from pydantic import BaseModel, HttpUrl, field_validator
import uuid


class ReviewRequest(BaseModel):
    repo_url: str

    @field_validator("repo_url")
    @classmethod
    def validate_github_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if "github.com" not in v:
            raise ValueError("URL must be a GitHub repository URL")
        return v


class Finding(BaseModel):
    id: str = ""
    file: str
    line: Optional[int] = None
    issue: str
    severity: Literal["Critical", "High", "Medium", "Low"]
    reasoning: str
    agent: str = ""

    def model_post_init(self, __context):  # type: ignore[override]
        if not self.id:
            object.__setattr__(self, "id", str(uuid.uuid4())[:8])


class FixSuggestion(BaseModel):
    finding_id: str
    original_code: str
    suggested_fix: str
    explanation: str


class VerifiedFix(BaseModel):
    finding_id: str
    status: Literal["verified", "failed", "skipped"]
    final_fix: str
    original_code: str
    explanation: str
    iterations: int = 1


class CriticReport(BaseModel):
    summary: str
    findings: List[Finding]
    total_critical: int
    total_high: int
    total_medium: int
    total_low: int


class AgentPlan(BaseModel):
    agents_to_invoke: List[Literal["security", "quality", "dependency"]]
    security_files: List[str] = []
    quality_files: List[str] = []
    dependency_files: List[str] = []
    notes: str = ""


class FinalReport(BaseModel):
    repo_url: str
    repo_name: str
    summary: str
    total_critical: int
    total_high: int
    total_medium: int
    total_low: int
    findings: List[Finding]
    verified_fixes: List[VerifiedFix]
    agent_plan: Optional[AgentPlan] = None


class SSEEvent(BaseModel):
    event: str = "agent_update"
    data: dict
