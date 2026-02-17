from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class RiskClass(str, Enum):
    CODE = "code"
    DEPS = "deps"
    INFRA = "infra"
    SECRETS = "secrets"
    DESTRUCTIVE = "destructive"


class ModelProfile(str, Enum):
    TRIAGE = "triage"
    BUILD = "build"
    REVIEW = "review"


class ApprovalAction(str, Enum):
    MERGE = "merge"
    INFRA = "infra"
    SECRETS = "secrets"
    DESTRUCTIVE = "destructive"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class Caps(BaseModel):
    max_minutes: int = Field(default=45, ge=1, le=180)
    max_iterations: int = Field(default=8, ge=1, le=100)
    max_usd: float = Field(default=3.0, ge=0.0, le=50.0)


DEFAULT_ARTIFACT_CONTRACT = [
    "plan.md",
    "patch.diff",
    "test.log",
    "review.md",
    "cost.json",
    "run.jsonl",
]


class JobSpecV1(BaseModel):
    job_id: UUID = Field(default_factory=uuid4)
    repo: str
    issue_number: int = Field(ge=1)
    base_branch: str = "main"
    risk_class: RiskClass = RiskClass.CODE
    allowed_paths: list[str] = Field(default_factory=list)
    acceptance_commands: list[str] = Field(default_factory=list)
    caps: Caps = Field(default_factory=Caps)
    model_profile: ModelProfile = ModelProfile.BUILD
    requires_approval: list[ApprovalAction] = Field(default_factory=lambda: [ApprovalAction.MERGE])
    artifact_contract: list[str] = Field(default_factory=lambda: list(DEFAULT_ARTIFACT_CONTRACT))
    created_by: str = "system"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class JobCreateRequest(BaseModel):
    repo: str
    issue_number: int = Field(ge=1)
    base_branch: str = "main"
    risk_class: RiskClass = RiskClass.CODE
    model_profile: ModelProfile = ModelProfile.BUILD
    created_by: str = "operator"
    allowed_paths: list[str] = Field(default_factory=list)
    acceptance_commands: list[str] = Field(default_factory=list)
    caps: Caps | None = None


class JobResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    repo: str
    issue_number: int
    risk_class: RiskClass
    current_stage: str | None = None
    pr_url: str | None = None
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    cost_usd: float


class ApprovalRequest(BaseModel):
    action: ApprovalAction
    actor: str
    reason: str | None = None


class RejectRequest(BaseModel):
    actor: str
    reason: str


class WebhookResult(BaseModel):
    accepted: bool
    message: str
    job_id: UUID | None = None

