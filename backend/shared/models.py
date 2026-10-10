"""
CitySync ΓÇö SQLAlchemy ORM Models
All 9 PostgreSQL tables defined here with proper types, constraints, and relationships.
PostGIS geography columns use GeoAlchemy2.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from geoalchemy2 import Geography
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Users ───────────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="citizen")  # citizen, officer, admin
    dept_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # ROADS, SWD, etc.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ΓöÇΓöÇ Tickets ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # TKT-XXXXXXXXXX
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    severity_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(
        String(30),
        default="Pending",
        nullable=False,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(Text)
    citizen_token: Mapped[str] = mapped_column(String(64), nullable=False)
    image_key: Mapped[Optional[str]] = mapped_column(String(200))
    ward_id: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    department_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("departments.id"), nullable=True
    )
    cluster_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("ticket_clusters.id"), nullable=True
    )
    resolution_log_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("resolution_log.id"), nullable=True
    )
    # PostGIS geography ΓÇö stores fuzzed coordinates (raw GPS never written here)
    fuzzed_gps: Mapped[Optional[object]] = mapped_column(Geography("POINT", srid=4326))
    # Raw GPS stored temporarily in Redis for dedup processing ΓÇö never in DB
    intent: Mapped[Optional[str]] = mapped_column(String(30))
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    upvote_count: Mapped[int] = mapped_column(Integer, default=0)
    trust_modifier: Mapped[float] = mapped_column(Float, default=0.0)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    routed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Officer dispatch ΓÇö JWT `sub` of the assigned field worker (demo: field_worker_demo_001)
    assigned_worker_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    officer_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status_history: Mapped[list] = mapped_column(JSONB, server_default='[]', default=list, nullable=False)

    __table_args__ = (
        CheckConstraint("severity BETWEEN 1 AND 10", name="ck_tickets_severity"),
        CheckConstraint(
            "status IN ('Submitted','Pending','Processing','In Progress','Under Review','Solved','Work Complete','Resolved','Completed','Rejected','Human Review')",
            name="ck_tickets_status",
        ),
    )


# ΓöÇΓöÇ Departments ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class Department(Base):
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(200))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ΓöÇΓöÇ Ticket Clusters ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class TicketCluster(Base):
    __tablename__ = "ticket_clusters"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    cluster_centroid: Mapped[object] = mapped_column(Geography("POINT", srid=4326), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    canonical_ticket_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("tickets.id"), nullable=False
    )
    member_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ΓöÇΓöÇ Ticket Upvotes ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class TicketUpvote(Base):
    __tablename__ = "ticket_upvotes"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id: Mapped[str] = mapped_column(String(20), ForeignKey("tickets.id"), nullable=False)
    citizen_token: Mapped[str] = mapped_column(String(64), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("ticket_id", "citizen_token", name="uq_upvote_per_citizen"),
    )


# ΓöÇΓöÇ Ward Boundaries ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class Ward(Base):
    __tablename__ = "wards"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    boundary: Mapped[Optional[object]] = mapped_column(Geography("POLYGON", srid=4326))


# ΓöÇΓöÇ Department Routes ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class DepartmentRoute(Base):
    __tablename__ = "department_routes"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    ward_id: Mapped[Optional[str]] = mapped_column(String(20))  # NULL = all wards
    primary_department_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("departments.id"), nullable=False
    )
    # Array of CC department IDs (PostgreSQL native array)
    cc_department_ids: Mapped[Optional[list]] = mapped_column(ARRAY(String))
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500))
    fallback_email: Mapped[Optional[str]] = mapped_column(String(200))

    __table_args__ = (
        UniqueConstraint("category", "ward_id", name="uq_route_category_ward"),
    )


# ΓöÇΓöÇ Severity Overrides ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class SeverityOverride(Base):
    __tablename__ = "severity_overrides"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    min_severity: Mapped[int] = mapped_column(Integer, nullable=False)
    department_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("departments.id"), nullable=False
    )
    bypass_ward: Mapped[bool] = mapped_column(Boolean, default=True)
    reason: Mapped[Optional[str]] = mapped_column(String(200))


# ΓöÇΓöÇ Webhook Log ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class WebhookLog(Base):
    __tablename__ = "webhook_logs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    department_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("departments.id"))
    ticket_id: Mapped[str] = mapped_column(String(20), ForeignKey("tickets.id"))
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    response_status: Mapped[Optional[int]] = mapped_column(Integer)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ΓöÇΓöÇ Notification Logs ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class NotificationLog(Base):
    """Tracks success/failures for automatic Twilio SMS and WhatsApp broadcasts."""
    __tablename__ = "notification_logs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id: Mapped[str] = mapped_column(String(20), ForeignKey("tickets.id"), index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False) # 'whatsapp' or 'sms'
    status_triggered: Mapped[str] = mapped_column(String(50), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ΓöÇΓöÇ Verification Submissions ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class VerificationSubmission(Base):
    __tablename__ = "verification_submissions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id: Mapped[str] = mapped_column(String(20), ForeignKey("tickets.id"), nullable=False, index=True)
    image_key: Mapped[Optional[str]] = mapped_column(String(200))
    submitter_token: Mapped[str] = mapped_column(String(64), nullable=False)
    step: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 or 2
    ai_score: Mapped[Optional[float]] = mapped_column(Float)
    result: Mapped[str] = mapped_column(String(20), default="pending")  # pending/pass/fail/review
    notes: Mapped[Optional[str]] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ΓöÇΓöÇ Resolution Log ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class ResolutionLog(Base):
    __tablename__ = "resolution_log"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id: Mapped[str] = mapped_column(String(20), ForeignKey("tickets.id"), nullable=False)
    resolution_method: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # verified | timeout | commissioner_override
    verifier_1_token: Mapped[Optional[str]] = mapped_column(String(64))
    verifier_2_token: Mapped[Optional[str]] = mapped_column(String(64))
    ai_score: Mapped[Optional[float]] = mapped_column(Float)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        CheckConstraint(
            "resolution_method IN ('verified','timeout','commissioner_override')",
            name="ck_resolution_method",
        ),
    )


# ΓöÇΓöÇ Model Call Log ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
class ModelCall(Base):
    __tablename__ = "model_calls"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id: Mapped[Optional[str]] = mapped_column(String(20), ForeignKey("tickets.id"), nullable=True)
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    latency_ms: Mapped[Optional[float]] = mapped_column(Float)
    result_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    called_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
