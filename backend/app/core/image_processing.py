"""Image processing utilities for evidence uploads.

Generates optimized variants (thumbnail, medium) in WebP format
using Pillow.  Falls back gracefully when Pillow is unavailable
(e.g. in CI/test environments) — callers receive ``None`` variants.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageOps  # type: ignore[import-untyped]

    PILLOW_AVAILABLE = True
except ImportError:  # pragma: no cover
    PILLOW_AVAILABLE = False

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

THUMBNAIL_MAX_SIZE = (400, 300)
MEDIUM_MAX_WIDTH = 1200

THUMBNAIL_QUALITY = 80
MEDIUM_QUALITY = 85
ORIGINAL_QUALITY = 90

# Files larger than this are re-compressed to ORIGINAL_QUALITY JPEG.
ORIGINAL_COMPRESS_THRESHOLD = 2 * 1024 * 1024  # 2 MB


@dataclass
class ImageVariants:
    """Container for processed image variants."""

    original_bytes: bytes
    original_content_type: str
    thumbnail_bytes: Optional[bytes] = None
    medium_bytes: Optional[bytes] = None


def _is_image(content_type: Optional[str], filename: Optional[str]) -> bool:
    """Return True if the file looks like an image we can process."""
    image_types = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp", "image/tiff"}
    if content_type and content_type.lower() in image_types:
        return True
    if filename:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return ext in {"jpg", "jpeg", "png", "webp", "gif", "bmp", "tiff"}
    return False


def _to_webp(img: Image.Image, max_size: tuple[int, int], quality: int) -> bytes:
    """Resize *img* to fit within *max_size* and encode as WebP."""
    resized = img.copy()
    resized.thumbnail(max_size, Image.LANCZOS)
    buf = io.BytesIO()
    resized.save(buf, format="WEBP", quality=quality, method=4)
    return buf.getvalue()


def process_image(
    content: bytes,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
) -> ImageVariants:
    """Process an uploaded image into optimized variants.

    Returns an ``ImageVariants`` with:
    * ``original_bytes`` — potentially re-compressed original
    * ``thumbnail_bytes`` — 400x300 WebP (or ``None``)
    * ``medium_bytes`` — max-1200px-wide WebP (or ``None``)

    If Pillow is unavailable or the file is not an image, only
    ``original_bytes`` is populated (pass-through).
    """
    if not PILLOW_AVAILABLE or not _is_image(content_type, filename):
        return ImageVariants(
            original_bytes=content,
            original_content_type=content_type or "application/octet-stream",
        )

    try:
        img = Image.open(io.BytesIO(content))
        img = ImageOps.exif_transpose(img)  # auto-orient

        # Convert palette / RGBA for JPEG/WebP compatibility
        if img.mode in ("P", "PA"):
            img = img.convert("RGBA")
        if img.mode == "RGBA":
            # WebP supports alpha; for JPEG fallback we'd flatten
            pass

        # --- Thumbnail (400x300, WebP) --------------------------------
        thumbnail_bytes = _to_webp(img, THUMBNAIL_MAX_SIZE, THUMBNAIL_QUALITY)

        # --- Medium (max 1200px wide, WebP) ----------------------------
        medium_max = (MEDIUM_MAX_WIDTH, int(MEDIUM_MAX_WIDTH * img.height / max(img.width, 1)))
        medium_bytes = _to_webp(img, medium_max, MEDIUM_QUALITY)

        # --- Original: re-compress large files -------------------------
        original_bytes = content
        original_ct = content_type or "application/octet-stream"

        if len(content) > ORIGINAL_COMPRESS_THRESHOLD:
            buf = io.BytesIO()
            save_img = img.convert("RGB") if img.mode == "RGBA" else img
            save_img.save(buf, format="JPEG", quality=ORIGINAL_QUALITY, optimize=True)
            compressed = buf.getvalue()
            if len(compressed) < len(content):
                original_bytes = compressed
                original_ct = "image/jpeg"
                logger.info(
                    "Compressed original %s: %d -> %d bytes",
                    filename,
                    len(content),
                    len(compressed),
                )

        return ImageVariants(
            original_bytes=original_bytes,
            original_content_type=original_ct,
            thumbnail_bytes=thumbnail_bytes,
            medium_bytes=medium_bytes,
        )

    except Exception:
        logger.warning("Failed to process image %s, using original", filename, exc_info=True)
        return ImageVariants(
            original_bytes=content,
            original_content_type=content_type or "application/octet-stream",
        )
