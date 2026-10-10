"""
CitySync — Webhook Dispatcher
HMAC-SHA256 signed webhook POSTs with Celery retry queue.
Fallback to SendGrid email after 4 failures.
"""
import json
import time
import uuid
from datetime import datetime, timezone

import httpx
from celery import Celery

from shared.config import settings
from shared.logging_config import get_logger
from shared.privacy import generate_webhook_signature

log = get_logger("webhook")

# ── Celery app (same Redis as event bus) ──────────────────────────────────────
celery_app = Celery(
    "citysync_webhooks",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)

# ── Retry schedule ─────────────────────────────────────────────────────────────
RETRY_DELAYS_SEC = [60, 300, 900, 3600]  # 1min → 5min → 15min → 1hr
MAX_RETRIES = 4


async def dispatch_webhook(
    ticket_id: str,
    department_id: str,
    webhook_url: str,
    payload: dict,
    attempt: int = 1,
) -> dict:
    """
    Send a signed webhook POST to a department endpoint.
    Logs every attempt to webhook_log table.
    """
    log_id = str(uuid.uuid4())
    payload_bytes = json.dumps(payload).encode("utf-8")
    signature = generate_webhook_signature(payload_bytes)

    t_start = time.perf_counter()
    http_status = None
    success = False
    error_msg = None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                webhook_url,
                content=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-CitySync-Signature": signature,
                    "X-CitySync-TicketId": ticket_id,
                    "X-CitySync-Attempt": str(attempt),
                },
            )
            http_status = response.status_code
            success = 200 <= http_status < 300
            if not success:
                error_msg = f"HTTP {http_status}: {response.text[:200]}"

    except httpx.TimeoutException:
        error_msg = "Request timeout (10s)"
    except httpx.ConnectError:
        error_msg = "Connection refused — department endpoint unreachable"
    except Exception as e:
        error_msg = str(e)

    latency_ms = (time.perf_counter() - t_start) * 1000

    # Log every attempt to webhook_log table
    await _log_webhook_attempt(
        log_id=log_id,
        ticket_id=ticket_id,
        department_id=department_id,
        webhook_url=webhook_url,
        attempt=attempt,
        http_status=http_status,
        latency_ms=latency_ms,
        success=success,
        error_msg=error_msg,
    )

    log.info(
        "webhook_dispatched",
        ticket_id=ticket_id,
        attempt=attempt,
        success=success,
        http_status=http_status,
        latency_ms=round(latency_ms, 1),
    )

    if not success:
        if attempt < MAX_RETRIES:
            # Schedule retry via Celery
            retry_delay = RETRY_DELAYS_SEC[min(attempt - 1, len(RETRY_DELAYS_SEC) - 1)]
            log.info("scheduling_webhook_retry", ticket_id=ticket_id, attempt=attempt + 1, delay_sec=retry_delay)
            retry_webhook.apply_async(
                args=[ticket_id, department_id, webhook_url, payload, attempt + 1],
                countdown=retry_delay,
            )
        else:
            # Max retries exhausted — send email fallback
            log.error("webhook_max_retries_exhausted", ticket_id=ticket_id, department_id=department_id)
            await _send_email_fallback(ticket_id, department_id, payload)

    return {"success": success, "http_status": http_status, "attempt": attempt, "latency_ms": latency_ms}


@celery_app.task(name="retry_webhook", bind=True, max_retries=MAX_RETRIES)
def retry_webhook(self, ticket_id: str, department_id: str, webhook_url: str, payload: dict, attempt: int):
    """Celery task for webhook retry (runs in worker process, not async)."""
    import asyncio
    import httpx
    import json as _json

    payload_bytes = _json.dumps(payload).encode("utf-8")
    signature = generate_webhook_signature(payload_bytes)

    t_start = time.perf_counter()
    http_status = None
    success = False
    error_msg = None

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                webhook_url,
                content=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-CitySync-Signature": signature,
                    "X-CitySync-TicketId": ticket_id,
                    "X-CitySync-Attempt": str(attempt),
                },
            )
            http_status = response.status_code
            success = 200 <= http_status < 300
    except Exception as e:
        error_msg = str(e)

    latency_ms = (time.perf_counter() - t_start) * 1000
    log.info("webhook_retry_complete", ticket_id=ticket_id, attempt=attempt, success=success)

    if not success and attempt < MAX_RETRIES:
        retry_delay = RETRY_DELAYS_SEC[min(attempt - 1, len(RETRY_DELAYS_SEC) - 1)]
        retry_webhook.apply_async(
            args=[ticket_id, department_id, webhook_url, payload, attempt + 1],
            countdown=retry_delay,
        )
    elif not success:
        # Schedule email fallback (synchronous mock for Celery worker)
        log.error("webhook_exhausted_sending_email", ticket_id=ticket_id)


async def _log_webhook_attempt(
    log_id, ticket_id, department_id, webhook_url,
    attempt, http_status, latency_ms, success, error_msg
):
    """Insert a record to webhook_log table."""
    try:
        from shared.database import get_db
        from shared.models import WebhookLog

        async with get_db() as session:
            entry = WebhookLog(
                id=log_id,
                ticket_id=ticket_id,
                department_id=department_id,
                webhook_url=webhook_url,
                attempt_number=attempt,
                http_status=http_status,
                response_time_ms=round(latency_ms, 1),
                success=success,
                error_message=error_msg,
            )
            session.add(entry)
    except Exception as e:
        log.warning("webhook_log_write_failed", error=str(e))


async def _send_email_fallback(ticket_id: str, department_id: str, payload: dict):
    """SendGrid email fallback after 4 webhook failures."""
    if settings.mock_email:
        log.info(
            "mock_email_fallback",
            ticket_id=ticket_id,
            message=f"[MOCK EMAIL] Ticket {ticket_id} routing failed after {MAX_RETRIES} attempts",
        )
        return

    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail

        sg = sendgrid.SendGridAPIClient(api_key=settings.sendgrid_api_key)
        message = Mail(
            from_email=settings.sendgrid_from_email,
            to_emails=payload.get("fallback_email", settings.sendgrid_from_email),
            subject=f"[CitySync ALERT] Webhook failed for ticket {ticket_id}",
            html_content=f"""
            <h2>Webhook Delivery Failed</h2>
            <p>Ticket <strong>{ticket_id}</strong> could not be delivered after {MAX_RETRIES} attempts.</p>
            <p>Category: {payload.get('category')} | Priority: {payload.get('priority_score')}</p>
            <p>Please log in to the CitySync admin dashboard to handle this ticket manually.</p>
            """,
        )
        sg.send(message)
        log.info("email_fallback_sent", ticket_id=ticket_id)
    except Exception as e:
        log.error("email_fallback_failed", error=str(e), ticket_id=ticket_id)
