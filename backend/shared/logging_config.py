"""
CitySync — structlog configuration with trace_id propagation.
Every log line carries ticket_id and trace_id for end-to-end correlation.
"""
import logging
import sys
import uuid
from contextvars import ContextVar

import structlog

# ── Context vars (request-scoped) ─────────────────────────────────────────────
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
_ticket_id_var: ContextVar[str] = ContextVar("ticket_id", default="")


def set_trace_id(trace_id: str | None = None) -> str:
    """Set trace_id in context. Generates one if not provided."""
    tid = trace_id or str(uuid.uuid4())
    _trace_id_var.set(tid)
    return tid


def set_ticket_id(ticket_id: str) -> None:
    _ticket_id_var.set(ticket_id)


def get_trace_id() -> str:
    return _trace_id_var.get()


def get_ticket_id() -> str:
    return _ticket_id_var.get()


# ── Context processor ─────────────────────────────────────────────────────────
def add_context(logger, method, event_dict):
    """Inject trace_id and ticket_id into every log line."""
    trace_id = _trace_id_var.get()
    ticket_id = _ticket_id_var.get()
    if trace_id:
        event_dict["trace_id"] = trace_id
    if ticket_id:
        event_dict["ticket_id"] = ticket_id
    return event_dict


# ── Configure structlog ────────────────────────────────────────────────────────
def configure_logging(log_level: str = "INFO"):
    """Call once at service startup."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_context,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer() if sys.stdout.isatty() else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Also configure stdlib logging to forward to structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.getLevelName(log_level.upper()),
    )


def get_logger(name: str):
    return structlog.get_logger(name)


# ── Audit event helper ────────────────────────────────────────────────────────
async def write_audit_event(
    action: str,
    citizen_token: str | None,
    ticket_id: str | None,
    extra: dict | None = None,
):
    """Write an audit event to Redis Stream citysync:audit.events."""
    from shared.redis_client import publish_event, Streams

    event_data = {
        "trace_id": get_trace_id(),
        "action": action,
        "citizen_token": citizen_token or "anonymous",
        "ticket_id": ticket_id or "",
        "timestamp": str(__import__("datetime").datetime.utcnow().isoformat()),
    }
    if extra:
        event_data.update({k: str(v) for k, v in extra.items()})

    await publish_event(Streams.AUDIT_EVENTS, event_data)
