"""Groq Qwen 3.8 27B image verification and mock implementations via Portkey."""
import base64
import time

from shared.config import settings
from shared.logging_config import get_logger

log = get_logger("vision")

STEP1_SYSTEM_PROMPT = """You are CitySync's verification AI. Compare the BEFORE photo
(the original civic issue) with the AFTER photo (claimed fix). Decide whether the
issue has been resolved. Respond in strict JSON with resolved (boolean), confidence
(0.0-1.0), reasoning, and concerns."""

STEP2_SYSTEM_PROMPT = """You are CitySync's citizen verification AI. Determine whether
the submitted photo shows that the civic issue is genuinely fixed. Respond in strict
JSON with confirmed (boolean), confidence (0.0-1.0), and reasoning."""


async def compare_before_after(before_image_key: str, after_image_bytes: bytes, ticket_id: str) -> dict:
    """Compare the original issue photo with the field worker's after photo."""
    if settings.mock_ai:
        return _mock_step1_verify(ticket_id, after_image_bytes)

    try:
        before_b64 = await _load_image_from_minio(before_image_key)
        after_b64 = base64.b64encode(after_image_bytes).decode("utf-8")
        return await _groq_step1_verify(before_b64, after_b64, ticket_id)
    except Exception as exc:
        log.error("groq_step1_vision_failed", error=str(exc), ticket_id=ticket_id)
        return {
            "result": "review",
            "confidence": 0.0,
            "reasoning": "Automated photo comparison failed. A supervisor must review the photos.",
            "concerns": "Vision model request failed.",
        }


async def verify_citizen_photo(photo_bytes: bytes, ticket_id: str) -> dict:
    """Check whether the citizen's photo confirms that the issue is resolved."""
    if settings.mock_ai:
        return _mock_step2_verify(ticket_id)

    try:
        photo_b64 = base64.b64encode(photo_bytes).decode("utf-8")
        return await _groq_step2_verify(photo_b64, ticket_id)
    except Exception as exc:
        log.error("groq_step2_vision_failed", error=str(exc), ticket_id=ticket_id)
        return {
            "confirmed": False,
            "confidence": 0.0,
            "review_required": True,
            "reasoning": "Automated photo verification failed. A human must review the photo.",
        }


def _mock_step1_verify(ticket_id: str, after_image_bytes: bytes) -> dict:
    """Deterministic mock result based on the submitted image hash."""
    import hashlib

    img_hash = hashlib.md5(after_image_bytes[:100] if after_image_bytes else b"mock").hexdigest()
    hash_val = int(img_hash[:2], 16)
    if hash_val > 50:
        confidence, result = 0.82 + (hash_val / 2550), "pass"
    elif hash_val > 25:
        confidence, result = 0.70, "review"
    else:
        confidence, result = 0.45, "fail"
    log.info("mock_step1_result", ticket_id=ticket_id, result=result, confidence=confidence)
    return {
        "result": result,
        "confidence": round(confidence, 2),
        "reasoning": f"[MOCK] Visual comparison: issue appears {'resolved' if result == 'pass' else 'not fully resolved'}",
        "concerns": None if result == "pass" else "Some visible damage remains",
    }


def _mock_step2_verify(ticket_id: str) -> dict:
    """Return a simulated citizen photo confirmation."""
    import random

    confirmed = random.random() > 0.15
    confidence = 0.88 if confirmed else 0.72
    log.info("mock_step2_result", ticket_id=ticket_id, confirmed=confirmed)
    return {
        "confirmed": confirmed,
        "confidence": confidence,
        "reasoning": "[MOCK] Citizen photo " + ("confirms resolution" if confirmed else "shows issue persists"),
    }


async def _groq_step1_verify(before_b64: str, after_b64: str, ticket_id: str) -> dict:
    import json
    from shared.groq_client import create_chat_completion
    started = time.perf_counter()
    response = await create_chat_completion(
        feature="before_after_verification",
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": STEP1_SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": "BEFORE photo (original issue):"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{before_b64}"}},
                {"type": "text", "text": "AFTER photo (claimed fix):"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{after_b64}"}},
                {"type": "text", "text": "Is the issue resolved? Respond in JSON only."},
            ]},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_completion_tokens=400,
    )
    data = json.loads(response.choices[0].message.content)
    if not isinstance(data, dict) or not {"resolved", "confidence"}.issubset(data):
        raise ValueError("Photo comparison returned an incomplete structured response")
    confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
    resolved = bool(data.get("resolved", False))
    result = "pass" if resolved and confidence >= 0.8 else "review" if confidence >= 0.6 else "fail"
    log.info("groq_step1_result", ticket_id=ticket_id, result=result, confidence=confidence,
             latency_ms=round((time.perf_counter() - started) * 1000, 1))
    return {
        "result": result,
        "confidence": round(confidence, 2),
        "reasoning": data.get("reasoning", ""),
        "concerns": data.get("concerns"),
    }


async def _groq_step2_verify(photo_b64: str, ticket_id: str) -> dict:
    import json
    from shared.groq_client import create_chat_completion
    response = await create_chat_completion(
        feature="citizen_photo_verification",
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": STEP2_SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": "Citizen verification photo:"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{photo_b64}"}},
                {"type": "text", "text": "Is the issue fixed? JSON only."},
            ]},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_completion_tokens=300,
    )
    data = json.loads(response.choices[0].message.content)
    if not isinstance(data, dict) or not {"confirmed", "confidence"}.issubset(data):
        raise ValueError("Citizen photo verification returned an incomplete structured response")
    confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
    log.info("groq_step2_result", ticket_id=ticket_id, confidence=confidence)
    return {
        "confirmed": bool(data.get("confirmed", False)),
        "confidence": confidence,
        "reasoning": data.get("reasoning", ""),
    }


async def _load_image_from_minio(image_key: str) -> str:
    """Load a stored image and return its base64 representation."""
    from shared.minio_client import _get_client

    client = _get_client()
    response = client.get_object(settings.minio_bucket, image_key)
    return base64.b64encode(response.read()).decode("utf-8")
