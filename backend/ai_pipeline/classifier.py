"""
CitySync — AI Classifier
Single Groq API call → intent + category + severity + location + confidence.
MOCK_AI=true mode uses deterministic keyword matching — no API key needed.
"""
import json
import time
import re
from typing import Optional

from shared.config import settings
from shared.logging_config import get_logger
from shared.schemas import ClassificationResult

log = get_logger("classifier")

# ── Valid label sets (closed — prevents hallucination) ────────────────────────
VALID_INTENTS = {"valid_complaint", "query", "spam", "abuse"}
VALID_CATEGORIES = {
    "Pothole", "Flooding", "Drainage", "Street Light", "Garbage",
    "Water Supply", "Building Hazard", "Live Wire", "Noise", "Other"
}

SYSTEM_PROMPT = """You are CitySync's civic complaint classifier for Indian municipal bodies.
Classify the complaint in strict JSON with these exact fields:
{
  "intent": "<valid_complaint|query|spam|abuse>",
  "category": "<Pothole|Flooding|Drainage|Street Light|Garbage|Water Supply|Building Hazard|Live Wire|Noise|Other>",
  "severity": <integer 1-10>,
  "location_mention": "<extracted place name or null>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<1 sentence explanation>"
}

Severity guide:
1-3: Minor inconvenience (small pothole, dim streetlight)
4-6: Moderate impact (road damage, burst pipe)  
7-8: Significant hazard (flooded road, large crater)
9-10: Life-threatening emergency (live wire, building collapse, deep flood)

Respond ONLY with valid JSON. No explanations outside JSON."""

USER_PROMPT_TEMPLATE = """Complaint (language: {language}):
"{description}"

{image_context}
Classify this complaint."""


# ── Mock classifier (keyword-based, no API key) ───────────────────────────────
KEYWORD_RULES = [
    (["live wire", "live electricity", "dangling wire", "electric wire", "bijli wire"], "Live Wire", 9),
    (["flood", "waterlog", "pani bhar", "pani aa gaya", "drainage overflow", "drain overflow"], "Flooding", 7),
    (["pothole", "gadd", "road damage", "gaddha", "khaddha"], "Pothole", 5),
    (["street light", "light not working", "lamp post", "batti nahi", "andhere"], "Street Light", 4),
    (["garbage", "kachra", "waste", "dustbin", "dump", "sewage smell"], "Garbage", 4),
    (["water supply", "paani nahi", "no water", "water cut", "meter leak"], "Water Supply", 6),
    (["building collapse", "building damage", "crack in wall", "slab falling"], "Building Hazard", 9),
    (["drainage", "nala", "drain blocked", "gutter"], "Drainage", 5),
    (["noise", "sound", "loud music", "construction noise"], "Noise", 3),
]

SPAM_KEYWORDS = ["test", "testing", "hello", "hi", "abc", "asdf", "1234"]


def _mock_classify(description: str, language: str) -> ClassificationResult:
    """Deterministic keyword-based classification for demo without OpenAI key."""
    desc_lower = description.lower()

    # Check for spam
    if any(spam in desc_lower for spam in SPAM_KEYWORDS) and len(description) < 20:
        return ClassificationResult(
            intent="spam",
            category="Other",
            severity=1,
            location_mention=None,
            confidence=0.90,
            reasoning="Short text matching spam patterns",
        )

    # Match keywords
    matched_category = "Other"
    matched_severity = 4
    best_match_count = 0

    for keywords, category, severity in KEYWORD_RULES:
        match_count = sum(1 for kw in keywords if kw in desc_lower)
        if match_count > best_match_count:
            best_match_count = match_count
            matched_category = category
            matched_severity = severity

    # Extract location mention (simple regex — Indian place patterns)
    location_mention = None
    loc_patterns = [
        r'\bnear\s+([A-Z][a-zA-Z\s]+)',
        r'\b(?:road|street|nagar|colony|ward|sector|plot)\b',
        r'\bin\s+([A-Z][a-zA-Z\s]+)',
    ]
    for pattern in loc_patterns:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            location_mention = match.group(0)[:50]
            break

    confidence = 0.72 + (best_match_count * 0.05)
    confidence = min(confidence, 0.95)

    log.info(
        "mock_classification",
        category=matched_category,
        severity=matched_severity,
        confidence=confidence,
    )

    return ClassificationResult(
        intent="valid_complaint",
        category=matched_category,
        severity=matched_severity,
        location_mention=location_mention,
        confidence=confidence,
        reasoning=f"[MOCK] Keyword-matched: {matched_category} at severity {matched_severity}",
    )


# ── Groq classifier ────────────────────────────────────────────────────────────
async def _groq_classify(
    description: str,
    language: str,
    image_base64: Optional[str] = None,
) -> ClassificationResult:
    """Call the configured Groq model through Portkey with structured JSON output."""
    from shared.groq_client import create_chat_completion

    image_context = ""
    messages_content = []

    if image_base64:
        image_context = "Use the submitted image as visual evidence when classifying the complaint."
        messages_content = [
            {"type": "text", "text": USER_PROMPT_TEMPLATE.format(
                language=language, description=description, image_context=image_context
            )},
            {"type": "image_url", "image_url": {
                "url": f"data:image/jpeg;base64,{image_base64}", "detail": "low"
            }},
        ]
    else:
        messages_content = USER_PROMPT_TEMPLATE.format(
            language=language, description=description, image_context=""
        )

    t_start = time.perf_counter()
    response = await create_chat_completion(
        feature="classification",
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": messages_content},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_completion_tokens=300,
    )
    latency_ms = (time.perf_counter() - t_start) * 1000

    raw = response.choices[0].message.content
    data = json.loads(raw)

    required_fields = {"intent", "category", "severity", "confidence"}
    if not isinstance(data, dict) or not required_fields.issubset(data):
        raise ValueError("Classifier returned an incomplete structured response")

    # Validate labels — reject out-of-set values
    intent = data.get("intent", "valid_complaint")
    if intent not in VALID_INTENTS:
        intent = "valid_complaint"
    category = data.get("category", "Other")
    if category not in VALID_CATEGORIES:
        category = "Other"

    result = ClassificationResult(
        intent=intent,
        category=category,
        severity=max(1, min(10, int(data.get("severity", 5)))),
        location_mention=data.get("location_mention"),
        confidence=float(data.get("confidence", 0.7)),
        reasoning=data.get("reasoning", ""),
    )

    log.info(
        "groq_classification",
        model=settings.groq_model,
        category=category,
        severity=result.severity,
        confidence=result.confidence,
        latency_ms=round(latency_ms, 1),
        input_tokens=response.usage.prompt_tokens,
        output_tokens=response.usage.completion_tokens,
    )

    return result, {
        "latency_ms": latency_ms,
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
        "raw": data,
    }


# ── Public interface ──────────────────────────────────────────────────────────
async def classify_complaint(
    ticket_id: str,
    description: str,
    language: str = "en",
    image_base64: Optional[str] = None,
) -> ClassificationResult:
    """
    Classify a complaint. Uses mock if MOCK_AI=true (default for hackathon).
    Logs to model_calls table regardless of mode.
    """
    t_start = time.perf_counter()
    model_meta = {}

    if settings.mock_ai:
        result = _mock_classify(description, language)
        model_name = "mock-keyword-v1"
        latency_ms = (time.perf_counter() - t_start) * 1000
    else:
        try:
            result, model_meta = await _groq_classify(description, language, image_base64)
            model_name = settings.groq_model
            latency_ms = model_meta.get("latency_ms", 0)
        except Exception as e:
            log.error("groq_classification_failed", error_type=type(e).__name__)
            log.warning("falling_back_to_mock", ticket_id=ticket_id)
            result = _mock_classify(description, language)
            model_name = "mock-fallback"
            latency_ms = (time.perf_counter() - t_start) * 1000

    # Log to model_calls table
    try:
        from shared.database import get_db
        from shared.models import ModelCall
        import uuid

        async with get_db() as session:
            call_log = ModelCall(
                id=str(uuid.uuid4()),
                ticket_id=ticket_id,
                model=model_name,
                input_tokens=model_meta.get("input_tokens"),
                output_tokens=model_meta.get("output_tokens"),
                latency_ms=latency_ms,
                result_json=result.model_dump(),
            )
            session.add(call_log)
    except Exception as e:
        log.warning("model_call_log_failed", error=str(e))

    return result
