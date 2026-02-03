from datetime import datetime, timezone
from typing import Dict, Any


def analyze_site_photo(file_url: str) -> Dict[str, Any]:
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
