"""
CitySync — Two-Step Verification Engine (Layer 5.5)
The only write path to status=Resolved goes through this service.
PG trigger enforcement: resolution_log_id FK must exist before Resolved write is allowed.

Endpoints:
  POST /api/verify/step1        — Field worker uploads after-photo
  POST /api/verify/step2        — Citizen confirms YES/NO/photo
  POST /api/verify/commissioner — Emergency commissioner override
  GET  /api/verify/{ticket_id}  — Verification status
"""
import asyncio
import base64
import sys
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from shared.config import settings
from shared.database import get_db
from shared.logging_config import configure_logging, get_logger, set_trace_id, set_ticket_id
from shared.auth import get_current_user, require_role
from shared.models import Ticket, VerificationSubmission, ResolutionLog
from shared.privacy import hmac_tokenize
from shared.redis_client import publish_event, Streams
from shared.schemas import Step1Request, Step1Response, Step2Request, Step2Response
from verification.vision import compare_before_after, verify_citizen_photo

configure_logging(settings.log_level)
log = get_logger("verification")

app = FastAPI(title="CitySync Verification Engine", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Step 1: Field worker photo verification ────────────────────────────────────
@app.post("/api/verify/step1", response_model=Step1Response)
async def step1_verify(
    ticket_id: str = Form(...),
    field_worker_token: str = Form(...),
    after_photo: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """
    Field worker marks issue as 'Work Complete' and uploads after-photo.
    Groq Qwen vision (or mock mode) compares before/after photos.
    ≥0.80 → auto-pass | 0.60-0.79 → supervisor review | <0.60 → reject
    """
    set_ticket_id(ticket_id)
    log.info("step1_started", ticket_id=ticket_id)

    # ── Fetch ticket ──────────────────────────────────────────────────────────
    async with get_db() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if ticket.status not in ("In Progress", "Pending"):
            raise HTTPException(
                status_code=409,
                detail=f"Ticket status is '{ticket.status}' — must be In Progress for verification"
            )
        before_image_key = ticket.image_key

    # ── Upload after photo to MinIO ────────────────────────────────────────────
    after_bytes = await after_photo.read()
    from shared.minio_client import upload_photo
    after_image_key = upload_photo(ticket_id, "after", after_bytes)

    # ── AI Vision comparison ───────────────────────────────────────────────────
    vision_result = await compare_before_after(
        before_image_key=before_image_key or "",
        after_image_bytes=after_bytes,
        ticket_id=ticket_id,
    )
    result = vision_result["result"]  # pass | fail | review
    confidence = vision_result["confidence"]

    # ── Write to verification_submissions ─────────────────────────────────────
    async with get_db() as session:
        submission = VerificationSubmission(
            id=str(uuid.uuid4()),
            ticket_id=ticket_id,
            image_key=after_image_key,
            submitter_token=field_worker_token,
            step=1,
            ai_score=confidence,
            result=result,
            notes=vision_result.get("reasoning"),
        )
        session.add(submission)

        # Update ticket status based on result
        new_status = {
            "pass": "Work Complete",
            "review": "In Progress",  # stays in progress pending supervisor
            "fail": "In Progress",    # sent back
        }.get(result, "In Progress")

        await session.execute(
            text("UPDATE tickets SET status = :status, updated_at = NOW() WHERE id = :id"),
            {"status": new_status, "id": ticket_id},
        )

    message_map = {
        "pass": "✓ Step 1 Passed. Citizen notification sent for confirmation.",
        "review": "⚠ Confidence 60-79% — supervisor review required before proceeding.",
        "fail": "✗ Verification failed. Please re-photograph the completed work and resubmit.",
    }

    # ── If Step 1 passes, notify citizen (Step 2) ─────────────────────────────
    if result == "pass":
        await _notify_citizen_for_step2(ticket_id, ticket.citizen_token)

    log.info("step1_complete", ticket_id=ticket_id, result=result, confidence=confidence)
    return Step1Response(result=result, confidence=confidence, message=message_map[result])


async def _notify_citizen_for_step2(ticket_id: str, citizen_token: str):
    """Send WhatsApp/SMS to citizen for Step 2 confirmation."""
    await publish_event(Streams.STATUS_UPDATES, {
        "ticket_id": ticket_id,
        "citizen_token": citizen_token,
        "status": "Work Complete",
        "action": "step2_confirmation_required",
        "updated_by": "AI Vision Engine",
        "note": "Field team submitted proof of work. Step 1 passed vision check.",
        "message": "Your complaint has been marked complete by the field team. Please confirm it is fixed. Reply YES or send a photo within 72 hours.",
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat(),
    })


# ── Step 2: Citizen confirmation ───────────────────────────────────────────────
@app.post("/api/verify/step2", response_model=Step2Response)
async def step2_verify(
    request: Step2Request,
    user: dict = Depends(get_current_user),
):
    """
    Citizen confirms (YES/photo) or rejects (NO/photo showing issue).
    YES or high-confidence confirming photo → resolution confirmed.
    NO or low-confidence photo → ticket reopened, priority bumped +10.
    """
    ticket_id = request.ticket_id
    set_ticket_id(ticket_id)
    log.info("step2_started", ticket_id=ticket_id)

    async with get_db() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if ticket.status not in ("Work Complete", "Solved"):
            raise HTTPException(
                status_code=409,
                detail=f"Ticket must be in 'Work Complete' or 'Solved' status for Step 2 (currently '{ticket.status}')"
            )

    citizen_response = request.citizen_response.strip().upper()
    confirmed = False
    confidence = 0.0
    reasoning = ""

    if citizen_response == "YES":
        confirmed = True
        confidence = 1.0
        reasoning = "Citizen explicitly confirmed resolution"
    elif citizen_response == "NO":
        confirmed = False
        confidence = 0.0
        reasoning = "Citizen explicitly rejected — issue persists"
    elif request.photo_base64:
        # Score confirmation photo with AI
        photo_bytes = base64.b64decode(request.photo_base64)
        vision_result = await verify_citizen_photo(photo_bytes, ticket_id)
        if vision_result.get("review_required"):
            async with get_db() as session:
                session.add(VerificationSubmission(
                    id=str(uuid.uuid4()),
                    ticket_id=ticket_id,
                    submitter_token=user.get("sub", "citizen"),
                    step=2,
                    ai_score=0.0,
                    result="review",
                    notes=vision_result["reasoning"],
                ))
            from shared.minio_client import upload_photo
            upload_photo(ticket_id, "reverify", photo_bytes)
            return Step2Response(
                result="review",
                resolution_method=None,
                message="Photo received. A supervisor must review it before the ticket can be resolved.",
            )
        confirmed = vision_result["confirmed"] and vision_result["confidence"] >= 0.75
        confidence = vision_result["confidence"]
        reasoning = vision_result["reasoning"]

        # Upload re-verify photo
        from shared.minio_client import upload_photo
        upload_photo(ticket_id, "reverify", photo_bytes)
    else:
        raise HTTPException(status_code=400, detail="Must provide citizen_response (YES/NO) or photo_base64")

    # ── Write verification submission record ──────────────────────────────────
    async with get_db() as session:
        submission = VerificationSubmission(
            id=str(uuid.uuid4()),
            ticket_id=ticket_id,
            submitter_token=user.get("sub", "citizen"),
            step=2,
            ai_score=confidence,
            result="pass" if confirmed else "fail",
            notes=reasoning,
        )
        session.add(submission)

    if confirmed:
        return await _resolve_ticket(ticket_id, ticket.citizen_token, confidence, reasoning)
    else:
        return await _reopen_ticket(ticket_id, ticket.citizen_token, reasoning)


async def _resolve_ticket(ticket_id: str, citizen_token: str, ai_score: float, reasoning: str) -> Step2Response:
    """
    Create resolution_log record + trigger-protected status=Resolved write.
    This is the ONLY path to Resolved status.
    """
    resolution_id = str(uuid.uuid4())
    log.info("resolving_ticket", ticket_id=ticket_id, resolution_id=resolution_id)

    async with get_db() as session:
        # 1. Write resolution_log first (trigger requires this FK to exist)
        resolution = ResolutionLog(
            id=resolution_id,
            ticket_id=ticket_id,
            resolution_method="verified",
            ai_score=ai_score,
            reason=reasoning,
        )
        session.add(resolution)
        await session.flush()  # Persist resolution_log before ticket update

        # 2. Now the trigger will accept status=Resolved (resolution_log_id FK is valid)
        await session.execute(
            text("""
                UPDATE tickets SET
                    status = 'Resolved',
                    resolution_log_id = :resolution_id,
                    updated_at = NOW()
                WHERE id = :ticket_id
            """),
            {"resolution_id": resolution_id, "ticket_id": ticket_id},
        )

    # ── Fire resolution.confirmed event ───────────────────────────────────────
    await publish_event(Streams.RESOLUTION_CONFIRMED, {
        "ticket_id": ticket_id,
        "resolution_id": resolution_id,
        "resolution_method": "verified",
        "citizen_token": citizen_token,
        "status": "Resolved",
        "updated_by": "Citizen",
        "note": "Resolution confirmed via verified.",
    })

    # ── Increment citizen trust score (future: +0.05) ─────────────────────────
    log.info("ticket_resolved", ticket_id=ticket_id, resolution_method="verified")

    return Step2Response(
        result="confirmed",
        resolution_method="verified",
        message="✓ Thank you for confirming! This complaint is now marked as Resolved.",
    )


async def _reopen_ticket(ticket_id: str, citizen_token: str, reasoning: str) -> Step2Response:
    """Reopen a ticket when citizen says the issue is not fixed."""
    async with get_db() as session:
        # Bump priority score +10
        await session.execute(
            text("""
                UPDATE tickets SET
                    status = 'In Progress',
                    priority_score = priority_score + 10,
                    updated_at = NOW()
                WHERE id = :ticket_id
            """),
            {"ticket_id": ticket_id},
        )

    log.info("ticket_reopened", ticket_id=ticket_id, reason=reasoning)

    await publish_event(Streams.STATUS_UPDATES, {
        "ticket_id": ticket_id,
        "citizen_token": citizen_token,
        "status": "In Progress",
        "action": "reopened",
        "updated_by": "Citizen",
        "note": "Citizen rejected resolution — reopening ticket.",
        "message": "The field team has been notified that the issue is not resolved. Priority bumped +10.",
    })

    return Step2Response(
        result="reopened",
        resolution_method=None,
        message="Thank you — we've notified the field team that the issue persists. Priority increased.",
    )


# ── Commissioner Override ──────────────────────────────────────────────────────
@app.post("/api/verify/commissioner")
async def commissioner_override(
    ticket_id: str,
    reason: str,
    user: dict = Depends(get_current_user),
):
    """
    Two-person commissioner override for emergency resolution.
    Requires two commissioner-level accounts. First call sets pending_override.
    Second call (different commissioner) confirms within 30 minutes.
    """
    if user.get("role") != "commissioner":
        raise HTTPException(status_code=403, detail="Commissioner role required")

    commissioner_token = user.get("sub")
    from shared.redis_client import get_redis as _get_redis
    r = await _get_redis()

    pending_key = f"citysync:override:pending:{ticket_id}"
    pending = await r.get(pending_key)

    if not pending:
        # First commissioner — set pending with 30-minute TTL
        await r.setex(pending_key, 1800, f"{commissioner_token}:{reason}")
        log.info("commissioner_override_pending", ticket_id=ticket_id, commissioner=commissioner_token)
        return {
            "status": "pending",
            "message": "Override pending. A second commissioner must approve within 30 minutes.",
        }
    else:
        # Second commissioner — verify it's a different person
        first_commissioner, _ = pending.split(":", 1)
        if first_commissioner == commissioner_token:
            raise HTTPException(
                status_code=409,
                detail="Cannot approve your own override request. A different commissioner must approve."
            )

        # Both commissioners approved — resolve the ticket
        resolution_id = str(uuid.uuid4())
        async with get_db() as session:
            resolution = ResolutionLog(
                id=resolution_id,
                ticket_id=ticket_id,
                resolution_method="commissioner_override",
                verifier_1_token=first_commissioner,
                verifier_2_token=commissioner_token,
                reason=reason,
            )
            session.add(resolution)
            await session.flush()

            await session.execute(
                text("""
                    UPDATE tickets SET
                        status = 'Resolved',
                        resolution_log_id = :resolution_id,
                        updated_at = NOW()
                    WHERE id = :ticket_id
                """),
                {"resolution_id": resolution_id, "ticket_id": ticket_id},
            )

        await r.delete(pending_key)
        log.info("commissioner_override_confirmed", ticket_id=ticket_id, resolution_id=resolution_id)
        return {
            "status": "resolved",
            "resolution_method": "commissioner_override",
            "resolution_id": resolution_id,
        }


# ── Verification Status ────────────────────────────────────────────────────────
@app.get("/api/verify/{ticket_id}")
async def get_verification_status(ticket_id: str):
    """Get verification submission history for a ticket."""
    async with get_db() as session:
        result = await session.execute(
            text("""
                SELECT id, step, result, ai_score, notes, submitted_at
                FROM verification_submissions
                WHERE ticket_id = :ticket_id
                ORDER BY submitted_at ASC
            """),
            {"ticket_id": ticket_id},
        )
        submissions = [
            {
                "id": str(row[0]),
                "step": row[1],
                "result": row[2],
                "ai_score": row[3],
                "notes": row[4],
                "submitted_at": row[5].isoformat() if row[5] else None,
            }
            for row in result.fetchall()
        ]
    return {"ticket_id": ticket_id, "submissions": submissions}


# ── 72h Timeout Auto-close ────────────────────────────────────────────────────
@app.on_event("startup")
async def start_timeout_checker():
    asyncio.create_task(timeout_checker_loop())


async def timeout_checker_loop():
    """Check every 30 minutes for Work Complete tickets past 72h window."""
    while True:
        await asyncio.sleep(1800)  # 30 minutes
        try:
            await auto_close_timed_out_tickets()
        except Exception as e:
            log.error("timeout_checker_error", error=str(e))


async def auto_close_timed_out_tickets():
    """Auto-close tickets where Step 2 window has expired (72h)."""
    async with get_db() as session:
        result = await session.execute(
            text("""
                SELECT id, citizen_token FROM tickets
                WHERE status IN ('Work Complete', 'Solved')
                  AND updated_at < NOW() - INTERVAL '72 hours'
            """)
        )
        timed_out = result.fetchall()

        for ticket_id, citizen_token in timed_out:
            resolution_id = str(uuid.uuid4())
            resolution = ResolutionLog(
                id=resolution_id,
                ticket_id=str(ticket_id),
                resolution_method="timeout",
                reason="Citizen did not respond within 72-hour window",
            )
            session.add(resolution)
            await session.flush()

            await session.execute(
                text("""
                    UPDATE tickets SET
                        status = 'Resolved',
                        resolution_log_id = :resolution_id,
                        updated_at = NOW()
                    WHERE id = :ticket_id
                """),
                {"resolution_id": resolution_id, "ticket_id": str(ticket_id)},
            )
            log.info("ticket_auto_closed_timeout", ticket_id=str(ticket_id))

    if timed_out:
        log.info("timeout_sweep_complete", closed_count=len(timed_out))


@app.get("/health")
async def health():
    return {"status": "ok", "service": "verification"}


@app.get("/api/verify/metrics")
async def get_verification_metrics():
    async with get_db() as session:
        result = await session.execute(text("""
            SELECT
                SUM(CASE WHEN step=1 AND result='pass' THEN 1 ELSE 0 END) as step1_pass,
                SUM(CASE WHEN step=1 AND result='fail' THEN 1 ELSE 0 END) as step1_fail,
                SUM(CASE WHEN step=1 AND result='review' THEN 1 ELSE 0 END) as step1_review,
                SUM(CASE WHEN step=2 AND result='pass' THEN 1 ELSE 0 END) as step2_pass,
                SUM(CASE WHEN step=2 THEN 1 ELSE 0 END) as step2_total
            FROM verification_submissions
        """))
        row = result.fetchone()
        step1_total = max((row[0] or 0) + (row[1] or 0) + (row[2] or 0), 1)
        return {
            "step1_pass_rate": round((row[0] or 0) / step1_total * 100, 1),
            "step1_rejection_rate": round((row[1] or 0) / step1_total * 100, 1),
            "step2_pass_rate": round((row[3] or 0) / max(row[4] or 0, 1) * 100, 1),
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("verification.main:app", host="0.0.0.0", port=settings.verification_port, reload=True)
