"""
CitySync ΓÇö Submission Gateway (Layer 1 + 2)
Accepts citizen complaint submissions, rate-limits, assigns ticket IDs,
publishes to Redis Stream, and returns HTTP 202 in ~140ms.
All AI processing is async ΓÇö citizen is unblocked immediately.
"""
import base64
import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI, Depends, HTTPException, Request, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared.config import settings
from shared.logging_config import configure_logging, get_logger, set_trace_id, set_ticket_id
from shared.auth import (
    ROLE_HIERARCHY,
    verify_password,
    get_password_hash,
    create_token,
    department_categories_filter,
    field_worker_label,
    filter_ticket_fields,
    get_current_user,
    FIELD_WORKERS,
)
from shared.privacy import hmac_tokenize, strip_exif
from shared.redis_client import publish_event, get_redis, Streams, get_top_categories
from shared.schemas import (
    AssignTicketRequest,
    SubmitComplaintRequest,
    SubmitComplaintResponse,
    TicketListResponse,
    UserCreate,
    UserLogin,
    UserUpdate,
    UserOut,
    Token,
    LegacyTicketRequest,
    PatchStatusRequest
)
from shared.database import get_db
from shared.models import Ticket, User, NotificationLog
from gateway.rate_limiter import check_rate_limit
from sqlalchemy import select, and_, func
from geoalchemy2 import Geography
from ai_pipeline.classifier import classify_complaint

configure_logging(settings.log_level)
log = get_logger("gateway")

@asynccontextmanager
async def lifespan(app: FastAPI):
    from shared.redis_client import create_consumer_group, Streams
    # Ensure consumer groups exist for all streams
    for stream in [
        Streams.RAW_SUBMISSIONS, Streams.CLASSIFIED_COMPLAINTS,
        Streams.PRIORITY_BOOST, Streams.STATUS_UPDATES,
    ]:
        await create_consumer_group(stream, "citysync", start_id="$")
    log.info("gateway_started", port=settings.gateway_port)
    yield

# ΓöÇΓöÇ FastAPI app ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

app = FastAPI(
    title="CitySync Gateway",
    description="Citizen complaint submission gateway",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    import logging
    logging.getLogger('gateway').error(f'Validation Error: {exc.body} -> {exc.errors()}')
    return JSONResponse(status_code=422, content={'detail': exc.errors()})

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)


@sio.event
async def connect(sid, environ):
    log.info("websocket_connected", sid=sid)


@sio.event
async def disconnect(sid):
    log.info("websocket_disconnected", sid=sid)


@sio.event
async def subscribe_ward(sid, data):
    """Subscribe client to a ward room for real-time updates."""
    ward_id = data.get("ward_id")
    if ward_id:
        await sio.enter_room(sid, f"ward:{ward_id}")
        log.info("client_subscribed_ward", sid=sid, ward_id=ward_id)


@sio.event
async def subscribe_ticket(sid, data):
    """Subscribe client to a specific ticket room."""
    ticket_id = data.get("ticket_id")
    if ticket_id:
        await sio.enter_room(sid, f"ticket:{ticket_id}")


# ΓöÇΓöÇ Helper: generate ticket ID ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
def generate_ticket_id() -> str:
    """TKT-XXXXXXXXXX format ΓÇö 10 alphanumeric chars."""
    suffix = uuid.uuid4().hex[:10].upper()
    return f"TKT-{suffix}"


def _require_officer(user: dict) -> None:
    if ROLE_HIERARCHY.get(user.get("role"), -1) < ROLE_HIERARCHY["officer"]:
        raise HTTPException(status_code=403, detail="Officer role or higher required")


async def _fuzzed_lat_lng_for_ids(session, ticket_ids: list[str]) -> dict[str, tuple[float, float]]:
    """Read fuzzed map coordinates from PostGIS (officer map + citizen track)."""
    from sqlalchemy import bindparam, text

    if not ticket_ids:
        return {}
    stmt = text("""
        SELECT id::text AS tid,
            ST_Y(fuzzed_gps::geometry) AS lat,
            ST_X(fuzzed_gps::geometry) AS lng
        FROM tickets
        WHERE fuzzed_gps IS NOT NULL AND id IN :ids
    """).bindparams(bindparam("ids", expanding=True))
    rows = (await session.execute(stmt, {"ids": ticket_ids})).mappings().all()
    out: dict[str, tuple[float, float]] = {}
    for r in rows:
        if r["lat"] is not None and r["lng"] is not None:
            out[r["tid"]] = (float(r["lat"]), float(r["lng"]))
    return out


# ΓöÇΓöÇ Routes ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
@app.get("/health")
async def health():
    r = await get_redis()
    redis_ok = await r.ping()
    return {
        "status": "ok",
        "service": "citysync-gateway",
        "redis": "ok" if redis_ok else "error",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Authentication Endpoints ───────────────────────────────────────────────────

@app.post("/api/auth/signup", response_model=UserOut)
async def signup(payload: UserCreate):
    async with get_db() as session:
        res = await session.execute(select(User).where(User.username == payload.username))
        if res.scalars().first():
            raise HTTPException(status_code=400, detail="Username already registered")
        
        # Validate that if user is officer/admin, they might need a dept_code
        # For this demo, we allow any role selection
        db_user = User(
            name=payload.name,
            phone=payload.phone or "",
            username=payload.username,
            password_hash=get_password_hash(payload.password),
            role=payload.role or "citizen",
            dept_code=payload.dept_code  # ROADS, SWD, FIRE, etc.
        )
        session.add(db_user)
        await session.commit()
        await session.refresh(db_user)
        return db_user

@app.post("/api/auth/login", response_model=Token)
async def login(payload: UserLogin):
    async with get_db() as session:
        res = await session.execute(select(User).where(User.username == payload.username))
        user = res.scalars().first()
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        access_token = create_token(user.id, role=user.role, extra={"name": user.name, "dept_code": user.dept_code})
        return {"access_token": access_token, "token_type": "bearer", "role": user.role}

@app.get("/api/auth/me", response_model=UserOut)
async def get_me(user_token: dict = Depends(get_current_user)):
    if user_token["role"] == "public":
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    async with get_db() as session:
        res = await session.execute(select(User).where(User.id == user_token["sub"]))
        user = res.scalars().first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

@app.put("/api/auth/me", response_model=UserOut)
async def update_me(payload: UserUpdate, user_token: dict = Depends(get_current_user)):
    if user_token["role"] == "public":
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    async with get_db() as session:
        res = await session.execute(select(User).where(User.id == user_token["sub"]))
        user = res.scalars().first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if payload.name:
            user.name = payload.name
        if payload.password:
            user.password_hash = get_password_hash(payload.password)
            
        await session.commit()
        await session.refresh(user)
        return user


@app.post("/api/submit", response_model=SubmitComplaintResponse, status_code=202)
async def submit_complaint(
    request: Request,
    payload: SubmitComplaintRequest,
    user: dict = Depends(get_current_user),
):
    """
    Citizen complaint submission endpoint.
    Returns 202 immediately (~140ms). All AI processing is async.
    """
    t_start = time.perf_counter()
    trace_id = set_trace_id()

    # ΓöÇΓöÇ 1. Extract citizen identity ΓåÆ HMAC token ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    # Use JWT sub, or fall back to IP address for anonymous citizens
    raw_identity = user.get("sub") or request.client.host
    citizen_token = hmac_tokenize(raw_identity)

    # ΓöÇΓöÇ 2. Rate limit check ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    try:
        await check_rate_limit(citizen_token)
    except HTTPException:
        r = await get_redis()
        await r.incr("citysync:metrics:rate_limit_hits")
        raise

    # ── 3. Coordinate Resolution (Moved up for deduplication) ──────────────────
    extracted_gps = None
    if payload.image_base64:
        try:
            image_bytes = base64.b64decode(payload.image_base64)
            _, extracted_gps = strip_exif(image_bytes)
        except Exception as e:
            log.warning("extract_gps_failed", error=str(e))
    
    lat = payload.latitude or (extracted_gps["lat"] if extracted_gps else None)
    lng = payload.longitude or (extracted_gps["lng"] if extracted_gps else None)

    # ── 4. Advanced Semantic + Spatial Duplicate Check ──────────────────────────
    try:
        classification = await classify_complaint(
            trace_id[:20], payload.description, payload.language, payload.image_base64
        )
    except Exception as e:
        log.warning("duplicate_check_ai_failed", error=str(e))
        classification = None

    async with get_db() as session:
        # 4a. Spatial + Trigram similarity check
        # Looks for tickets within 50m of the current location
        stmt = select(Ticket).where(
            func.similarity(Ticket.description, payload.description) > 0.3,
            Ticket.status.notin_(["Resolved", "Solved", "Rejected"])
        )
        
        if lat and lng:
            stmt = stmt.where(
                func.ST_DWithin(
                    Ticket.fuzzed_gps.cast(Geography),
                    func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326).cast(Geography),
                    50  # 50 meter radius
                )
            )

        if classification:
            stmt = stmt.where(Ticket.category == classification.category)

        stmt = stmt.order_by(func.similarity(Ticket.description, payload.description).desc()).limit(1)
        res = await session.execute(stmt)
        existing = res.scalars().first()

        if existing:
            # Resolved/Rejected = ignore/reject without change
            if existing.status in ("Resolved", "Solved", "Rejected"):
                log.info("duplicate_ignored_closed", ticket_id=existing.id, status=existing.status)
                return SubmitComplaintResponse(
                    ticket_id=existing.id,
                    status=existing.status,
                    message=f"💡 This problem was recently {existing.status.lower()}. If it reappeared, please wait 24h before re-reporting. ID: {existing.id}",
                    bearer_token=create_token(citizen_token, role="citizen", extra={"ticket_ref": existing.id})
                )

            # Active = upvote + boost score
            existing.upvote_count += 1
            existing.priority_score = min(existing.priority_score + 2.0, 100.0)
            await session.commit()
            
            msg = f"📈 Similar problem reported nearby! We've boosted the priority score. ID: {existing.id}"
            return SubmitComplaintResponse(
                ticket_id=existing.id,
                status="Processing",
                message=msg,
                bearer_token=create_token(citizen_token, role="citizen", extra={"ticket_ref": existing.id})
            )

    # ── 5. Assign ticket ID & Process Image ──────────────────────────────────────
    ticket_id = generate_ticket_id()
    set_ticket_id(ticket_id)
    image_key = None
    if payload.image_base64:
        try:
            image_bytes = base64.b64decode(payload.image_base64)
            clean_bytes, _ = strip_exif(image_bytes)
            from shared.minio_client import upload_photo
            image_key = upload_photo(ticket_id, "before", clean_bytes)
        except: pass

    # ── 6. Issue final bearer token ──────────────────────────────────────────────
    bearer_token = create_token(citizen_token, role="citizen", extra={"ticket_ref": ticket_id})

    # ΓöÇΓöÇ 7. Publish to Redis Stream raw.submissions ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    event_data = {
        "ticket_id": ticket_id,
        "trace_id": trace_id,
        "citizen_token": citizen_token,
        "description": payload.description,
        "language": payload.language,
        "raw_lat": str(lat) if lat else "",
        "raw_lng": str(lng) if lng else "",
        "image_key": image_key or "",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }

    await publish_event(Streams.RAW_SUBMISSIONS, event_data)
    log.info("event_published", stream=Streams.RAW_SUBMISSIONS, ticket_id=ticket_id)

    # Immediately push a STATUS_UPDATE so they get standard SMS
    await publish_event(
        Streams.STATUS_UPDATES,
        {
            "ticket_id": ticket_id,
            "citizen_token": citizen_token,
            "status": "Pending",
            "message": "Complaint received. Our AI is classifying and routing it now.",
        },
    )

    # ΓöÇΓöÇ 8. Track metrics ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    r = await get_redis()
    await r.incr("citysync:metrics:request_count")
    latency_ms = (time.perf_counter() - t_start) * 1000
    await r.lpush("citysync:metrics:latencies", round(latency_ms))
    await r.ltrim("citysync:metrics:latencies", 0, 999)  # keep last 1000

    log.info("complaint_accepted", ticket_id=ticket_id, latency_ms=round(latency_ms, 1))

    return SubmitComplaintResponse(
        ticket_id=ticket_id,
        status="Pending",
        message="Complaint received. Our AI is classifying and routing it now.",
        bearer_token=bearer_token,
        estimated_processing_ms=400,
    )



@app.get("/api/tickets/history")
async def get_my_tickets(user: dict = Depends(get_current_user)):
    """Fetch ticket history for the logged-in citizen."""
    if user.get("role") not in ("citizen", "admin"):
        raise HTTPException(status_code=403, detail="Only citizens can view their history")
    
    from sqlalchemy import select
    from shared.database import get_db
    from shared.models import Ticket
    from shared.privacy import hmac_tokenize

    my_token = hmac_tokenize(user["sub"])
    async with get_db() as session:
        result = await session.execute(
            select(Ticket)
            .where(Ticket.citizen_token == my_token)
            .order_by(Ticket.submitted_at.desc())
        )
        tickets = result.scalars().all()
        coord_map = await _fuzzed_lat_lng_for_ids(session, [t.id for t in tickets])

    history = []
    for t in tickets:
        lat_lng = coord_map.get(t.id)
        td = {
            "ticket_id": t.id,
            "category": t.category,
            "severity_tier": t.severity_tier,
            "status": t.status,
            "description": t.description,
            "submitted_at": t.submitted_at.isoformat() if t.submitted_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }
        if lat_lng:
            td["raw_lat"], td["raw_lng"] = lat_lng[0], lat_lng[1]
        history.append(td)
        
    return {"tickets": history}


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(
    ticket_id: str,
    user: dict = Depends(get_current_user),
):
    """Get ticket status ΓÇö response fields filtered by caller role."""
    from sqlalchemy import select
    from shared.database import get_db
    from shared.models import Ticket

    async with get_db() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
        dept_cats = department_categories_filter(user)
        if dept_cats is not None and ticket.category not in dept_cats:
            raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
        coord_map = await _fuzzed_lat_lng_for_ids(session, [ticket_id])
    lat_lng = coord_map.get(ticket_id)

    from shared.auth import CATEGORY_TO_DEPT

    role = user.get("role", "public")
    ticket_dict = {
        "ticket_id": ticket.id,
        "category": ticket.category,
        "dept_code": CATEGORY_TO_DEPT.get(ticket.category),
        "severity": ticket.severity,
        "severity_tier": ticket.severity_tier,
        "priority_score": ticket.priority_score,
        "status": ticket.status,
        "description": ticket.description,
        "ward_id": ticket.ward_id,
        "submitted_at": ticket.submitted_at.isoformat() if ticket.submitted_at else None,
        "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
        "upvote_count": ticket.upvote_count,
        "citizen_token": ticket.citizen_token,
        "assigned_worker_id": ticket.assigned_worker_id,
        "assigned_worker_label": field_worker_label(ticket.assigned_worker_id),
    }
    if lat_lng:
        ticket_dict["raw_lat"], ticket_dict["raw_lng"] = lat_lng[0], lat_lng[1]
    return filter_ticket_fields(ticket_dict, role)


@app.get("/api/tickets", response_model=TicketListResponse)
async def list_tickets(
    request: Request,
    ward_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    page: int = 1,
    page_size: int = 20,
    user: dict = Depends(get_current_user),
):
    """List tickets with optional filters. Results filtered by caller role."""
    from sqlalchemy import select
    from shared.database import get_db
    from shared.models import Ticket

    page_size = min(page_size, 100)
    offset = (page - 1) * page_size

    async with get_db() as session:
        query = select(Ticket)
        if ward_id:
            query = query.where(Ticket.ward_id == ward_id)
        if status:
            if "," in status:
                parts = [s.strip() for s in status.split(",") if s.strip()]
                if len(parts) == 1:
                    query = query.where(Ticket.status == parts[0])
                else:
                    query = query.where(Ticket.status.in_(parts))
            else:
                query = query.where(Ticket.status == status.strip())
        if category:
            query = query.where(Ticket.category == category)
            
        # Specific requirement: Filter by phone number
        phone = request.query_params.get("phone")
        if phone:
            # Find user by phone to get their token
            user_res = await session.execute(select(User).where(User.phone == phone))
            matched_user = user_res.scalars().first()
            if matched_user:
                token = hmac_tokenize(matched_user.id)
                query = query.where(Ticket.citizen_token == token)
            else:
                return {"tickets": [], "total": 0, "page": page, "page_size": page_size}

        dept_cats = department_categories_filter(user)
        if dept_cats is not None:
            query = query.where(Ticket.category.in_(dept_cats))
        query = query.order_by(Ticket.priority_score.desc()).offset(offset).limit(page_size)
        result = await session.execute(query)
        tickets = result.scalars().all()
        coord_map = await _fuzzed_lat_lng_for_ids(session, [t.id for t in tickets])

    from shared.auth import CATEGORY_TO_DEPT

    role = user.get("role", "public")
    filtered = []
    for t in tickets:
        td = {
            "ticket_id": t.id,
            "category": t.category,
            "dept_code": CATEGORY_TO_DEPT.get(t.category),
            "severity": t.severity,
            "severity_tier": t.severity_tier,
            "priority_score": t.priority_score,
            "status": t.status,
            "description": t.description,
            "ward_id": t.ward_id,
            "submitted_at": t.submitted_at.isoformat() if t.submitted_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            "upvote_count": t.upvote_count,
            "citizen_token": t.citizen_token,
            "assigned_worker_id": t.assigned_worker_id,
            "assigned_worker_label": field_worker_label(t.assigned_worker_id),
        }
        if t.id in coord_map:
            td["raw_lat"], td["raw_lng"] = coord_map[t.id][0], coord_map[t.id][1]
        filtered.append(filter_ticket_fields(td, role))

    return {"tickets": filtered, "page": page, "page_size": page_size, "total": len(filtered)}


@app.get("/api/me")
async def who_am_i(user: dict = Depends(get_current_user)):
    """Non-sensitive JWT claims for the UI (demo department scope, etc.)."""
    return {
        "sub": user.get("sub"),
        "role": user.get("role", "public"),
        "dept_code": user.get("dept_code"),
        "dept_name": user.get("dept_name"),
    }


@app.get("/api/field-workers")
async def list_field_workers(user: dict = Depends(get_current_user)):
    """Demo roster for officer dispatch ΓÇö production would query HR/workforce DB."""
    _require_officer(user)
    return {"workers": FIELD_WORKERS}


@app.post("/api/tickets/{ticket_id}/assign")
async def assign_ticket_to_worker(
    ticket_id: str,
    body: AssignTicketRequest,
    user: dict = Depends(get_current_user),
):
    """Officer assigns a Pending (or reassigns In Progress) ticket to a field worker."""
    from sqlalchemy import text

    _require_officer(user)
    allowed = {w["worker_id"] for w in FIELD_WORKERS}
    if body.assignee_id not in allowed:
        raise HTTPException(status_code=400, detail="Unknown assignee_id ΓÇö not in field worker roster")

    async with get_db() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        dept_cats = department_categories_filter(user)
        if dept_cats is not None and ticket.category not in dept_cats:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if ticket.status not in ("Pending", "In Progress"):
            raise HTTPException(
                status_code=409,
                detail=f"Tickets can only be assigned from the dispatch queue (status Pending or In Progress). Current: '{ticket.status}'",
            )

        await session.execute(
            text(
                """
                UPDATE tickets SET
                    status = 'In Progress',
                    assigned_worker_id = :aid,
                    updated_at = NOW()
                WHERE id = :tid
                """
            ),
            {"aid": body.assignee_id, "tid": ticket_id},
        )
        await session.refresh(ticket)

    await publish_event(
        Streams.STATUS_UPDATES,
        {
            "ticket_id": ticket_id,
            "citizen_token": ticket.citizen_token,
            "status": "In Progress",
            "category": ticket.category or "",
            "severity_tier": ticket.severity_tier or "",
            "priority_score": str(ticket.priority_score or 0),
            "ward_id": ticket.ward_id or "",
            "message": f"Assigned to {field_worker_label(body.assignee_id)} ΓÇö field work has started.",
        },
    )

    ward_id = ticket.ward_id or ""
    await emit_ticket_update(
        ticket_id,
        ward_id,
        {
            "ticket_id": ticket.id,
            "category": ticket.category,
            "severity_tier": ticket.severity_tier,
            "priority_score": ticket.priority_score,
            "status": "In Progress",
            "ward_id": ward_id,
            "upvote_count": ticket.upvote_count,
            "assigned_worker_id": body.assignee_id,
            "assigned_worker_label": field_worker_label(body.assignee_id),
        },
    )

    role = user.get("role", "public")
    ticket_dict = {
        "ticket_id": ticket.id,
        "category": ticket.category,
        "severity": ticket.severity,
        "severity_tier": ticket.severity_tier,
        "priority_score": ticket.priority_score,
        "status": ticket.status,
        "description": ticket.description,
        "ward_id": ticket.ward_id,
        "submitted_at": ticket.submitted_at.isoformat() if ticket.submitted_at else None,
        "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
        "upvote_count": ticket.upvote_count,
        "citizen_token": ticket.citizen_token,
        "assigned_worker_id": ticket.assigned_worker_id,
        "assigned_worker_label": field_worker_label(ticket.assigned_worker_id),
    }
    async with get_db() as session:
        cmap = await _fuzzed_lat_lng_for_ids(session, [ticket_id])
    if ticket_id in cmap:
        ticket_dict["raw_lat"], ticket_dict["raw_lng"] = cmap[ticket_id][0], cmap[ticket_id][1]

    return {"ok": True, "ticket": filter_ticket_fields(ticket_dict, role)}


@app.post("/api/tickets/{ticket_id}/resolve")
async def resolve_ticket(
    ticket_id: str,
    user: dict = Depends(get_current_user),
):
    """Officer marks a ticket as solved/resolved directly."""
    from sqlalchemy import text
    _require_officer(user)

    async with get_db() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        dept_cats = department_categories_filter(user)
        if dept_cats is not None and ticket.category not in dept_cats:
            raise HTTPException(status_code=404, detail="Ticket not found in your department domain")
        if ticket.status == "Resolved" or ticket.status == "Rejected":
            raise HTTPException(status_code=400, detail=f"Ticket is already {ticket.status}")

        await session.execute(
            text(
                """
                UPDATE tickets SET
                    status = 'Solved',
                    updated_at = NOW()
                WHERE id = :tid
                """
            ),
            {"tid": ticket_id},
        )
        await session.refresh(ticket)

    await publish_event(
        Streams.STATUS_UPDATES,
        {
            "ticket_id": ticket_id,
            "citizen_token": ticket.citizen_token,
            "status": "Solved",
            "category": ticket.category or "",
            "severity_tier": ticket.severity_tier or "",
            "priority_score": str(ticket.priority_score or 0),
            "ward_id": ticket.ward_id or "",
            "message": "Marked as Solved by field crew officer.",
        },
    )

    ward_id = ticket.ward_id or ""
    role = user.get("role", "public")
    
    ticket_dict = {
        "ticket_id": ticket.id,
        "category": ticket.category,
        "severity": ticket.severity,
        "severity_tier": ticket.severity_tier,
        "priority_score": ticket.priority_score,
        "status": ticket.status,
        "description": ticket.description,
        "ward_id": ticket.ward_id,
        "submitted_at": ticket.submitted_at.isoformat() if ticket.submitted_at else None,
        "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
        "upvote_count": ticket.upvote_count,
        "citizen_token": ticket.citizen_token,
        "assigned_worker_id": ticket.assigned_worker_id,
        "assigned_worker_label": field_worker_label(ticket.assigned_worker_id),
    }

    async with get_db() as session:
        cmap = await _fuzzed_lat_lng_for_ids(session, [ticket_id])
    if ticket_id in cmap:
        ticket_dict["raw_lat"], ticket_dict["raw_lng"] = cmap[ticket_id][0], cmap[ticket_id][1]

    filtered = filter_ticket_fields(ticket_dict, role)
    await emit_ticket_update(ticket_id, ward_id, filtered)

    return {"ok": True, "ticket": filtered}

# ── Specified Overhaul Endpoints ──────────────────────────────────────────────

@app.post("/api/tickets", response_model=SubmitComplaintResponse, status_code=202)
async def create_ticket_legacy(
    payload: LegacyTicketRequest,
    user: dict = Depends(get_current_user),
):
    """Spec-compliant ticket creation with track history initialization."""
    ticket_id = generate_ticket_id()
    
    # Map legacy fields to existing models
    # Note: user_phone and user_name from payload are used to build history, 
    # but actual citizen_token comes from the authenticated user for privacy continuity.
    citizen_token = hmac_tokenize(user["sub"])
    
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    history = [{
        "status": "Submitted",
        "timestamp": timestamp,
        "updated_by": payload.user_name,
        "note": "Initial ticket submission"
    }]

    async with get_db() as session:
        ticket = Ticket(
            id=ticket_id,
            category=payload.title,
            description=payload.description,
            status="Submitted",
            severity=5, # Default
            severity_tier="Medium", # Default
            citizen_token=citizen_token,
            status_history=history
        )
        session.add(ticket)
        await session.commit()
    
    # Trigger notification worker
    await publish_event(Streams.STATUS_UPDATES, {
        "ticket_id": ticket_id,
        "status": "Submitted",
        "citizen_token": citizen_token,
        "message": f"Confirmation: Ticket #{ticket_id} has been submitted."
    })

    # Trigger AI Pipeline for ward resolution, priority, and coordinates
    await publish_event(Streams.RAW_SUBMISSIONS, {
        "ticket_id": ticket_id,
        "description": payload.description,
        "language": "en",
        "citizen_token": citizen_token,
        "raw_lat": str(payload.latitude) if payload.latitude is not None else "",
        "raw_lng": str(payload.longitude) if payload.longitude is not None else "",
        "trace_id": str(uuid.uuid4())
    })

    return SubmitComplaintResponse(
        ticket_id=ticket_id,
        status="Submitted",
        message="Confirmation SMS/WhatsApp sent.",
        bearer_token=create_token(citizen_token, role="citizen")
    )

@app.patch("/api/tickets/{ticket_id}/status")
async def patch_ticket_status(
    ticket_id: str,
    payload: PatchStatusRequest,
    user: dict = Depends(get_current_user),
):
    """Spec-compliant ticket status update with history appending and notification."""
    _require_officer(user)
    
    # Priority order for forward-moving validation
    STATUS_ORDER = ["Submitted", "Pending", "Processing", "In Progress", "Under Review", "Solved", "Work Complete", "Resolved", "Completed"]
    
    async with get_db() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        # Validate status exists in our order list
        if payload.new_status not in STATUS_ORDER:
            raise HTTPException(status_code=400, detail=f"Invalid status: {payload.new_status}")

        # Validate forward movement (optional but requested)
        try:
            old_idx = STATUS_ORDER.index(ticket.status)
            new_idx = STATUS_ORDER.index(payload.new_status)
            if new_idx < old_idx:
                raise HTTPException(status_code=400, detail=f"Cannot transition backwards from {ticket.status} to {payload.new_status}")
        except ValueError:
            pass # Use default handling if current status is weird (e.g. Rejected)

        # Trigger notification worker (which handles history appending to DB)
        await publish_event(Streams.STATUS_UPDATES, {
            "ticket_id": ticket_id,
            "status": payload.new_status,
            "updated_by": payload.updated_by,
            "note": payload.note or f"Updated status to {payload.new_status}",
            "citizen_token": ticket.citizen_token
        })
        
        return {"status": "update_triggered", "ticket_id": ticket_id, "target_status": payload.new_status}

@app.get("/api/tickets/{ticket_id}/notifications")
async def get_ticket_notifications(
    ticket_id: str,
    user: dict = Depends(get_current_user),
):
    """List all notification logs (Twilio metadata) for a specific ticket."""
    _require_officer(user)
    async with get_db() as session:
        res = await session.execute(
            select(NotificationLog)
            .where(NotificationLog.ticket_id == ticket_id)
            .order_by(NotificationLog.created_at.desc())
        )
        return {"logs": res.scalars().all()}

@app.post("/api/upvote")
async def upvote_ticket(
    ticket_id: str,
    user: dict = Depends(get_current_user),
):
    """Citizen 'me too' upvote ΓÇö one per citizen per ticket."""
    from shared.database import get_db
    from shared.models import Ticket, TicketUpvote
    from shared.auth import create_token
    import sqlalchemy.exc

    citizen_token = user.get("sub", "anonymous")

    async with get_db() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        try:
            upvote = TicketUpvote(ticket_id=ticket_id, citizen_token=citizen_token)
            session.add(upvote)
            ticket.upvote_count = (ticket.upvote_count or 0) + 1
            await session.commit()
        except sqlalchemy.exc.IntegrityError:
            raise HTTPException(status_code=409, detail="You have already upvoted this ticket")

    # Fire priority boost event
    await publish_event(Streams.PRIORITY_BOOST, {
        "ticket_id": ticket_id, "reason": "upvote", "upvote_count": str(ticket.upvote_count)
    })

    return {"message": "Upvote recorded", "ticket_id": ticket_id, "upvote_count": ticket.upvote_count}


@app.get("/api/stats/gateway")
async def get_metrics():
    """Gateway metrics ΓÇö polled by admin dashboard every 5 seconds."""
    r = await get_redis()

    request_count = int(await r.get("citysync:metrics:request_count") or 0)
    rate_limit_hits = int(await r.get("citysync:metrics:rate_limit_hits") or 0)

    latencies = await r.lrange("citysync:metrics:latencies", 0, -1)

    p95 = 0.0
    if latencies:
        sorted_l = sorted([float(x) for x in latencies])
        idx = int(len(sorted_l) * 0.95)
        p95 = sorted_l[min(idx, len(sorted_l) - 1)]

    top_categories = await get_top_categories(10)

    return {
        "service": "gateway",
        "request_count": request_count,
        "rate_limit_hits": rate_limit_hits,
        "p95_latency_ms": round(p95, 1),
        "error_rate": 0.0,  # TODO: track errors
        "top_categories": [{"key": k, "count": int(v)} for k, v in top_categories],
    }


@app.get("/api/frequency/leaderboard")
async def get_frequency_leaderboard():
    """Top 10 complaint category+ward combinations by volume."""
    top = await get_top_categories(10)
    results = []
    for item, score in top:
        parts = item.split(":")
        results.append({
            "category": parts[0] if len(parts) > 0 else item,
            "ward_id": parts[1] if len(parts) > 1 else "unknown",
            "count": int(score),
        })
    return {"leaderboard": results}


@app.get("/api/demo-tokens")
async def get_demo_tokens():
    """Demo tokens for hackathon testing. Remove in production."""
    from shared.auth import DEMO_TOKENS, create_token
    import secrets as s
    citizen_token = create_token(hmac_tokenize(s.token_hex(8)), role="citizen")
    return {
        "note": "For demo/testing only ΓÇö remove in production",
        "citizen": citizen_token,
        **DEMO_TOKENS,
    }


# ΓöÇΓöÇ Internal Webhook Storage ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Stores incoming POST webhooks in Redis since the standalone dept-portal got dropped.
@app.post("/api/webhook/{dept_code}")
async def receive_webhook(dept_code: str, request: Request):
    """Fallback native webhook receptor."""
    r = await get_redis()
    raw_body = await request.body()
    try:
        import json
        payload = json.loads(raw_body)
    except:
        payload = {"error": "Invalid json"}
    
    entry = {
        "id": int(time.time() * 1000),
        "dept_code": dept_code,
        "ticket_id": request.headers.get("x-citysync-ticketid", "unknown"),
        "signature_valid": bool(request.headers.get("x-citysync-signature")),
        "attempt": int(request.headers.get("x-citysync-attempt", 1)),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload
    }
    
    await r.lpush("citysync:webhooks", json.dumps(entry))
    await r.ltrim("citysync:webhooks", 0, 199)
    log.info("webhook_received", dept=dept_code, ticket_id=entry["ticket_id"])
    return {"status": "accepted", "ticket_id": entry["ticket_id"]}

@app.get("/api/stats/webhooks")
async def get_webhooks(user: dict = Depends(get_current_user)):
    """Fetch stored webhooks for native dashboard. Officers only see their dept."""
    r = await get_redis()
    import json
    raw_logs = await r.lrange("citysync:webhooks", 0, -1)
    logs = [json.loads(x) for x in raw_logs]
    
    # Isolation filter
    is_officer = user.get("role") == "officer"
    target_dept = user.get("dept_code")
    
    tickets = []
    filtered_logs = []
    
    # Convert webhooks to pseudo-tickets for the UI
    for log_item in logs:
        p = log_item.get("payload", {})
        item_dept = log_item.get("dept_code")
        
        # If officer, only show their dept's logs
        if is_officer and target_dept and item_dept != target_dept:
            continue
            
        filtered_logs.append(log_item)
        tickets.append({
            "ticket_id": p.get("ticket_id"),
            "dept_code": item_dept,
            "category": p.get("category", "Other"),
            "severity_tier": p.get("severity_tier", "Low"),
            "priority_score": float(p.get("priority_score") or 0),
            "ward_id": p.get("ward_id"),
            "status": "Accepted",
            "received_at": log_item.get("received_at")
        })
        
    tickets.sort(key=lambda t: t["priority_score"], reverse=True)
    return {"log": filtered_logs, "tickets": tickets}


# ΓöÇΓöÇ Socket.io emit helpers (called by other services) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
async def emit_ticket_update(ticket_id: str, ward_id: str, data: dict):
    """Emit status update to both the ticket room and ward room."""
    await sio.emit("ticket.update", data, room=f"ticket:{ticket_id}")
    if ward_id:
        await sio.emit("ticket.update", data, room=f"ward:{ward_id}")


# ΓöÇΓöÇ Entry point ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "gateway.main:socket_app",
        host="0.0.0.0",
        port=settings.gateway_port,
        reload=True,
    )
