"""
CitySync ΓÇö Pydantic request/response schemas.
"""
import re
from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


# ΓöÇΓöÇ Submission ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class SubmitComplaintRequest(BaseModel):
    description: str = Field(..., min_length=5, max_length=2000)
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    image_base64: Optional[str] = None
    sha256_hash: Optional[str] = None
    language: str = Field("en", max_length=10)

    @field_validator("description")
    @classmethod
    def clean_description(cls, v):
        return v.strip()


class SubmitComplaintResponse(BaseModel):
    ticket_id: str
    status: str
    message: str
    bearer_token: str
    estimated_processing_ms: int = 400

class LegacyTicketRequest(BaseModel):
    user_name: str
    user_phone: str = Field(..., pattern=r"^\+?[\d\s-]{10,20}$")
    title: str
    description: str
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)


# ΓöÇΓöÇ Ticket ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class TicketStatus(BaseModel):
    ticket_id: str
    category: Optional[str]
    severity: Optional[int]
    severity_tier: Optional[str]
    priority_score: float
    status: str
    description: Optional[str]
    ward_id: Optional[str]
    submitted_at: datetime
    updated_at: datetime
    upvote_count: int
    status_history: list[dict] = []
    # GPS coordinates depend on caller's role ΓÇö may be fuzzed or omitted
    location: Optional[dict] = None  # {"lat": ..., "lng": ..., "fuzz_level": "officer|public"}
    cluster_info: Optional[dict] = None  # {"cluster_id": ..., "member_count": ...}


class TicketListResponse(BaseModel):
    tickets: list[TicketStatus]
    total: int
    page: int
    page_size: int


class AssignTicketRequest(BaseModel):
    """Officer assigns a queued ticket to a field worker (dispatch)."""

    assignee_id: str = Field(..., min_length=4, max_length=80)

class PatchStatusRequest(BaseModel):
    new_status: str
    updated_by: str
    note: Optional[str] = None


# ΓöÇΓöÇ Classification ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class ClassificationResult(BaseModel):
    intent: str  # valid_complaint | query | spam | abuse
    category: str
    severity: int  # 1-10
    location_mention: Optional[str]
    confidence: float  # 0.0 - 1.0
    reasoning: Optional[str]


# ΓöÇΓöÇ Dedup / Cluster ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class ClusterResult(BaseModel):
    is_duplicate: bool
    cluster_id: Optional[str]
    canonical_ticket_id: Optional[str]
    member_count: int
    distance_meters: Optional[float]


# ΓöÇΓöÇ Priority ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class PriorityResult(BaseModel):
    score: float
    tier: str  # Critical | High | Medium | Low
    breakdown: dict  # Score components for transparency


# ΓöÇΓöÇ Routing ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class WebhookPayload(BaseModel):
    """CitySync Webhook Spec v1 ΓÇö no PII, fuzzed coordinates only."""
    ticket_id: str
    category: str
    severity: int
    severity_tier: str
    priority_score: float
    upvote_count: int
    ward_id: Optional[str]
    department_id: str
    description: str
    status: str
    routed_at: str
    # No phone, no raw GPS, no citizen identity


# ΓöÇΓöÇ Verification ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class Step1Request(BaseModel):
    ticket_id: str
    field_worker_token: str
    after_image_base64: str


class Step1Response(BaseModel):
    result: str  # pass | fail | review
    confidence: float
    message: str


class Step2Request(BaseModel):
    ticket_id: str
    citizen_response: str  # YES | NO
    photo_base64: Optional[str] = None


class Step2Response(BaseModel):
    result: str  # confirmed | rejected | reopened
    resolution_method: Optional[str]
    message: str


class CommissionerOverrideRequest(BaseModel):
    ticket_id: str
    commissioner_token: str
    reason: str


# ΓöÇΓöÇ Upvote ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class UpvoteRequest(BaseModel):
    ticket_id: str
    citizen_token: str


# ΓöÇΓöÇ Metrics ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class GatewayMetrics(BaseModel):
    request_count: int
    rate_limit_hits: int
    p95_latency_ms: float
    error_rate: float
    active_tickets: int
    pending_count: int
    in_progress_count: int

class PipelineMetrics(BaseModel):
    gpt4o_calls: int
    avg_latency_ms: float
    human_review_queue_depth: int
    cluster_match_rate: float
    webhook_success_rate: float
    retry_queue_depth: int
    step1_pass_rate: float
    timeout_rate: float


# ── User Schemas ────────────────────────────────────────────────────────────────
class UserRole(str, Enum):
    CITIZEN = "citizen"
    OFFICER = "officer"
    ADMIN = "admin"

class UserBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone: Optional[str] = Field(None, pattern=r"^\+?[\d\s-]{10,20}$")
    username: str = Field(..., min_length=3, max_length=50)

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    role: Optional[UserRole] = UserRole.CITIZEN
    dept_code: Optional[str] = None

class UserLogin(BaseModel):
    username: str
    password: str

class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    password: Optional[str] = Field(None, min_length=8)

class UserOut(UserBase):
    id: str
    role: str
    dept_code: Optional[str]

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
