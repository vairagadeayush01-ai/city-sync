"""
CitySync — Notification Service
Sends WhatsApp/SMS via Twilio with automatic fallback and reliability logging.
Consumes status.updates and resolution.confirmed Redis Streams.
"""
import asyncio
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.config import settings
from shared.logging_config import configure_logging, get_logger
from shared.redis_client import read_events, ack_event, create_consumer_group, Streams
from shared.database import get_db
from shared.models import User, Ticket, NotificationLog
from sqlalchemy import select, update
from shared.privacy import hmac_tokenize

configure_logging(settings.log_level)
log = get_logger("notifications")

CONSUMER_GROUP = "notifications"
CONSUMER_NAME = "notifier-1"

# ── Notifications Utility ──────────────────────────────────────────────────────

async def get_user_data_from_token(citizen_token: str):
    """Fetch user name and phone for a given citizen_token."""
    async with get_db() as session:
        users_result = await session.execute(select(User))
        for u in users_result.scalars():
            if hmac_tokenize(u.id) == citizen_token:
                return u.name, u.phone
    return "Citizen", ""

def format_track_record_message(ticket: Ticket, user_name: str) -> str:
    """Format the precise WhatsApp/SMS track record message required by specification."""
    history_str = ""
    for entry in ticket.status_history:
        status = entry.get("status", "Unknown")
        ts = entry.get("timestamp", "")
        note = entry.get("note", "N/A")
        history_str += f"  ✅ {status} — {ts}\n     🗒 Note: {note}\n"

    created_at = ticket.submitted_at.strftime("%Y-%m-%d %H:%M:%S") if ticket.submitted_at else "N/A"
    
    return (
        f"🎫 *Ticket Update – #{ticket.id}*\n\n"
        f"📋 *Title:* {ticket.category}\n"
        f"👤 *Raised by:* {user_name}\n"
        f"📅 *Created:* {created_at}\n\n"
        f"🔄 *Current Status:* {ticket.status}\n\n"
        f"📊 *Full Track Record:*\n"
        f"{history_str}\n"
        f"For queries, reply to this message or contact support."
    )

async def log_notification(ticket_id: str, phone: str, channel: str, status: str, success: bool, error: str = None):
    """Save record of notification attempt to DB."""
    async with get_db() as session:
        log_entry = NotificationLog(
            ticket_id=ticket_id,
            phone=phone,
            channel=channel,
            status_triggered=status,
            success=success,
            error_message=error
        )
        session.add(log_entry)
        await session.commit()

async def send_twilio_message(to: str, body: str, is_whatsapp: bool = False):
    """Standard Twilio dispatch."""
    if settings.mock_notifications and not settings.twilio_account_sid:
        log.info("mock_notification", channel="whatsapp" if is_whatsapp else "sms", to=to)
        return True

    from twilio.rest import Client
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    
    from_number = settings.twilio_whatsapp_number if is_whatsapp else settings.twilio_from_number
    target_to = f"whatsapp:{to}" if is_whatsapp else to

    try:
        client.messages.create(body=body, from_=from_number, to=target_to)
        return True
    except Exception as e:
        log.error("twilio_send_error", channel="whatsapp" if is_whatsapp else "sms", error=str(e))
        return False, str(e)

async def send_with_fallback(ticket_id: str, phone: str, body: str, status_str: str):
    """Try WhatsApp first, fallback to SMS after 30s delay if failed."""
    # Attempt 1: WhatsApp
    success = await send_twilio_message(phone, body, is_whatsapp=True)
    if isinstance(success, bool) and success:
        await log_notification(ticket_id, phone, "whatsapp", status_str, True)
        return

    # If failed, log failure and retry SMS after 30s
    error_msg = success[1] if isinstance(success, tuple) else "Unknown WhatsApp Error"
    await log_notification(ticket_id, phone, "whatsapp", status_str, False, error_msg)
    
    log.warning("whatsapp_failed_retrying_sms", ticket_id=ticket_id, delay=30)
    await asyncio.sleep(30)
    
    # Attempt 2: SMS fallback
    success_sms = await send_twilio_message(phone, body, is_whatsapp=False)
    if isinstance(success_sms, bool) and success_sms:
        await log_notification(ticket_id, phone, "sms", status_str, True)
    else:
        err = success_sms[1] if isinstance(success_sms, tuple) else "Unknown SMS Error"
        await log_notification(ticket_id, phone, "sms", status_str, False, err)

# ── Event Processors ───────────────────────────────────────────────────────────

async def process_status_change(data: dict):
    """Main logic for appending history and notifying."""
    ticket_id = data.get("ticket_id")
    new_status = data.get("status")
    note = data.get("note") or data.get("message") or "Updated via system"
    updated_by = data.get("updated_by") or "System"

    if not ticket_id: return

    async with get_db() as session:
        # 1. Fetch Ticket
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            log.warning("ticket_not_found", ticket_id=ticket_id)
            return

        # 2. Append to history if it's not already there for this status
        history = list(ticket.status_history or [])
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        history.append({
            "status": new_status,
            "timestamp": timestamp,
            "updated_by": updated_by,
            "note": note
        })
        
        # 3. Update DB
        ticket.status = new_status
        ticket.status_history = history
        await session.commit()
        await session.refresh(ticket)

        # 4. Notify
        user_name, phone = await get_user_data_from_token(ticket.citizen_token)
        if not phone:
            log.warning("no_phone_for_notification", ticket_id=ticket_id)
            return

        formatted_msg = format_track_record_message(ticket, user_name)
        await send_with_fallback(ticket_id, phone, formatted_msg, new_status)

# ── Main Loop ─────────────────────────────────────────────────────────────────

async def consume_loop(stream: str):
    await create_consumer_group(stream, CONSUMER_GROUP, start_id="0")
    while True:
        try:
            events = await read_events(stream, CONSUMER_GROUP, CONSUMER_NAME)
            for msg_id, data in events:
                await process_status_change(data)
                await ack_event(stream, CONSUMER_GROUP, msg_id)
        except Exception as e:
            log.exception("notification_consumer_error", stream=stream, error=str(e))
            await asyncio.sleep(1)

async def main():
    log.info("notification_service_starting")
    # Both streams trigger the same history-appender and track-record notifier
    await asyncio.gather(
        consume_loop(Streams.STATUS_UPDATES),
        consume_loop(Streams.RESOLUTION_CONFIRMED)
    )

if __name__ == "__main__":
    asyncio.run(main())

