"""
CitySync — Routing Service (Layer 3.5)
Consumes classified.complaints, looks up department routing table,
dispatches webhooks, updates ticket status.

In-memory routing table refreshed every 60 seconds from PostgreSQL.
O(1) lookup by (category, ward_id).

Run: python -m routing.main  (from backend/ directory)
"""
import asyncio
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from shared.config import settings
from shared.database import get_db
from shared.logging_config import configure_logging, get_logger, set_trace_id, set_ticket_id
from shared.auth import get_current_user
from shared.redis_client import (
    read_events, ack_event, create_consumer_group, publish_event, get_redis, Streams
)
from shared.models import Ticket
from routing.webhook import dispatch_webhook

configure_logging(settings.log_level)
log = get_logger("routing")

# ── In-memory routing table ────────────────────────────────────────────────────
# Loaded from PostgreSQL at startup + refreshed every 60s
# Key: (category, ward_id) or (category, None) for all-ward defaults
# Value: {"primary_dept_id": ..., "webhook_url": ..., "fallback_email": ..., "cc_dept_ids": [...]}
_routing_table: dict = {}
_severity_overrides: list = []
_departments: dict = {}  # dept_id → {name, code, webhook_url, email}


async def refresh_routing_table():
    """Load routing table and severity overrides from PostgreSQL into memory."""
    global _routing_table, _severity_overrides, _departments

    async with get_db() as session:
        # Load department routes
        result = await session.execute(
            text("""
                SELECT dr.category, dr.ward_id, dr.primary_department_id,
                       dr.cc_department_ids, d.webhook_url, dr.fallback_email
                FROM department_routes dr
                JOIN departments d ON d.id = dr.primary_department_id
            """)
        )
        new_table = {}
        for row in result.fetchall():
            key = (row[0], row[1])  # (category, ward_id)
            new_table[key] = {
                "primary_dept_id": str(row[2]),
                "cc_dept_ids": row[3] or [],
                "webhook_url": row[4],
                "fallback_email": row[5],
            }
        _routing_table = new_table

        # Load severity overrides
        result = await session.execute(
            text("SELECT category, min_severity, department_id, bypass_ward, reason FROM severity_overrides")
        )
        _severity_overrides = [
            {
                "category": row[0],
                "min_severity": row[1],
                "department_id": str(row[2]),
                "bypass_ward": row[3],
                "reason": row[4],
            }
            for row in result.fetchall()
        ]

        # Load departments
        result = await session.execute(
            text("SELECT id, name, code, webhook_url, email FROM departments")
        )
        _departments = {
            str(row[0]): {"name": row[1], "code": row[2], "webhook_url": row[3], "email": row[4]}
            for row in result.fetchall()
        }

    log.info(
        "routing_table_refreshed",
        routes=len(_routing_table),
        overrides=len(_severity_overrides),
        departments=len(_departments),
    )


def lookup_route(category: str, ward_id: str | None, severity: int) -> dict | None:
    """
    O(1) route lookup.
    Priority order:
    1. Severity override (emergency bypass)
    2. Category + ward match
    3. Category + any ward (NULL ward = default)
    4. None (unroutable)
    """
    # 1. Check severity overrides first
    for override in _severity_overrides:
        if override["category"] == category and severity >= override["min_severity"]:
            dept_id = override["department_id"]
            dept = _departments.get(dept_id, {})
            log.info("severity_override_applied", category=category, severity=severity, dept=dept.get("code"))
            return {
                "primary_dept_id": dept_id,
                "webhook_url": dept.get("webhook_url"),
                "cc_dept_ids": [],
                "fallback_email": dept.get("email"),
                "bypass_ward": override["bypass_ward"],
            }

    # 2. Exact category + ward match
    if ward_id:
        route = _routing_table.get((category, ward_id))
        if route:
            return route

    # 3. Default route for category (ward_id = NULL)
    route = _routing_table.get((category, None))
    if route:
        return route

    # 4. Fall back to 'Other' → Roads department
    return _routing_table.get(("Other", None))


async def process_classified_complaint(msg_id: str, data: dict):
    """Route a classified complaint to the correct department."""
    ticket_id = data.get("ticket_id", "")
    trace_id = data.get("trace_id", "")

    set_trace_id(trace_id)
    set_ticket_id(ticket_id)

    category = data.get("category", "Other")
    severity = int(data.get("severity", 5))
    severity_tier = data.get("severity_tier", "Medium")
    priority_score = float(data.get("priority_score", 0))
    ward_id = data.get("ward_id") or None
    description = data.get("description", "")
    citizen_token = data.get("citizen_token", "")

    log.info("routing_complaint", ticket_id=ticket_id, category=category, ward_id=ward_id, severity=severity)

    route = lookup_route(category, ward_id, severity)
    if not route:
        log.error("no_route_found", ticket_id=ticket_id, category=category, ward_id=ward_id)
        return

    dept_id = route["primary_dept_id"]
    webhook_url = route.get("webhook_url") or f"{settings.dept_portal_url}/{category.lower().replace(' ', '_')}"

    # ── Build CitySync Webhook Spec v1 payload (no PII) ───────────────────────
    from shared.schemas import WebhookPayload
    payload = {
        "ticket_id": ticket_id,
        "category": category,
        "severity": severity,
        "severity_tier": severity_tier,
        "priority_score": priority_score,
        "upvote_count": 0,
        "ward_id": ward_id,
        "department_id": dept_id,
        "description": description,
        "status": "Pending",
        "routed_at": datetime.now(timezone.utc).isoformat(),
    }

    # ── Update ticket with department_id + routed_at ──────────────────────────
    async with get_db() as session:
        await session.execute(
            text("UPDATE tickets SET department_id = :dept_id, routed_at = NOW(), updated_at = NOW() WHERE id = :ticket_id"),
            {"dept_id": dept_id, "ticket_id": ticket_id},
        )

    # ── Dispatch webhook ──────────────────────────────────────────────────────
    result = await dispatch_webhook(ticket_id, dept_id, webhook_url, payload)

    dept_info = _departments.get(dept_id, {})
    log.info(
        "webhook_result",
        ticket_id=ticket_id,
        dept_code=dept_info.get("code"),
        success=result["success"],
        http_status=result.get("http_status"),
    )

    # ── CC departments (read-only notifications) ──────────────────────────────
    for cc_dept_id in route.get("cc_dept_ids", []):
        cc_dept = _departments.get(cc_dept_id, {})
        if cc_dept.get("webhook_url"):
            payload_cc = dict(payload)
            payload_cc["notification_type"] = "cc"
            await dispatch_webhook(ticket_id, cc_dept_id, cc_dept["webhook_url"], payload_cc)


async def routing_refresh_loop():
    """Refresh routing table every 60 seconds."""
    while True:
        await asyncio.sleep(60)
        try:
            await refresh_routing_table()
        except Exception as e:
            log.error("routing_table_refresh_failed", error=str(e))


async def main():
    """Routing service main loop."""
    log.info("routing_service_starting")
    await refresh_routing_table()
    await create_consumer_group(Streams.CLASSIFIED_COMPLAINTS, "routing", start_id="0")

    await asyncio.gather(
        _consume_classified_complaints(),
        routing_refresh_loop(),
    )


async def _consume_classified_complaints():
    log.info("routing_consumer_ready")
    while True:
        try:
            events = await read_events(Streams.CLASSIFIED_COMPLAINTS, "routing", "router-1")
            for msg_id, data in events:
                await process_classified_complaint(msg_id, data)
                await ack_event(Streams.CLASSIFIED_COMPLAINTS, "routing", msg_id)
        except Exception as e:
            log.exception("routing_consumer_error", error=str(e))
            await asyncio.sleep(1)


# ── FastAPI for status/metrics ─────────────────────────────────────────────────
app = FastAPI(title="CitySync Routing", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "routing", "routes": len(_routing_table)}


@app.get("/api/routing/table")
async def get_routing_table(user: dict = Depends(get_current_user)):
    if user.get("role") not in ("admin", "commissioner"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Admin only")
    return {"routes": {f"{k[0]}:{k[1]}": v for k, v in _routing_table.items()}, "overrides": _severity_overrides}


@app.get("/api/routing/metrics")
async def get_routing_metrics():
    from shared.models import WebhookLog
    from sqlalchemy import select, func
    async with get_db() as session:
        result = await session.execute(
            text("""
                SELECT
                    COUNT(*) as total_attempts,
                    SUM(CASE WHEN response_status BETWEEN 200 AND 299 THEN 1 ELSE 0 END) as successes,
                    NULL as avg_latency
                FROM webhook_logs
                WHERE created_at > NOW() - INTERVAL '1 hour'
            """)
        )
        row = result.fetchone()
        total = row[0] or 0
        success_count = row[1] or 0
        success_rate = (success_count / total * 100) if total > 0 else 100.0

    return {
        "service": "routing",
        "webhook_success_rate": round(success_rate, 1),
        "total_webhooks_1h": total,
        "routes_loaded": len(_routing_table),
        "overrides_loaded": len(_severity_overrides),
    }


if __name__ == "__main__":
    asyncio.run(main())
