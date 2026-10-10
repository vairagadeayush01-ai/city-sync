"""OpenAI-compatible Groq client, with optional Portkey gateway routing."""
import json
import uuid

from openai import AsyncOpenAI

from shared.config import settings
from shared.logging_config import get_trace_id


async def create_chat_completion(*, feature: str = "inference", **request):
    """Use Portkey when configured; otherwise use Groq keys with direct fallback."""
    api_key = settings.portkey_api_key.strip()
    config_id = settings.portkey_config_id.strip()
    if bool(api_key) != bool(config_id):
        raise RuntimeError("Set both PORTKEY_API_KEY and PORTKEY_CONFIG_ID, or leave both empty")

    if api_key and config_id:
        # Metadata intentionally excludes prompts, outputs, IDs, and image data.
        trace_id = get_trace_id() or str(uuid.uuid4())
        client = AsyncOpenAI(
            api_key="portkey",
            base_url=settings.portkey_base_url,
            default_headers={
                "x-portkey-api-key": api_key,
                "x-portkey-config": config_id,
                "x-portkey-debug": "false",
                "x-portkey-trace-id": trace_id,
                "x-portkey-metadata": json.dumps(
                    {"service": "citysync", "feature": feature}, separators=(",", ":")
                ),
            },
        )
        return await client.chat.completions.create(**request)

    keys = []
    for key in (settings.groq_api_key, settings.groq_fallback_api_key):
        key = key.strip()
        if key and key not in keys:
            keys.append(key)
    if not keys:
        raise RuntimeError("Set GROQ_API_KEY to use Groq directly, or configure Portkey")

    last_error = None
    for key in keys:
        client = AsyncOpenAI(api_key=key, base_url=settings.groq_base_url)
        try:
            return await client.chat.completions.create(**request)
        except Exception as exc:
            last_error = exc
    raise last_error
