from datetime import datetime, timezone
from typing import Any


def analyze_site_photo(file_url: str) -> dict[str, Any]:
    """
    Minimal AI analysis placeholder.
    Returns required keys when ENABLE_VISION_AI is true.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "generated_by_ai": True,
        "confidence": "low",
        "model": "mock-vision-v0",
        "timestamp": timestamp,
    }
