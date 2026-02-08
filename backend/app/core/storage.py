import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from supabase import create_client

from app.core.config import get_settings

logger = logging.getLogger(__name__)

BUCKET_EVIDENCES = "evidences"


def _file_extension(filename: Optional[str]) -> str:
    if not filename:
        return ""
    return Path(filename).suffix.lower()


def build_object_path(project_id: str, filename: Optional[str]) -> str:
    token = uuid.uuid4().hex
    ext = _file_extension(filename)
    return f"{project_id}/{token}{ext}"


def get_storage_client():
    settings = get_settings()
    key = settings.supabase_service_role_key or settings.supabase_key
    if not settings.supabase_url or not key:
        raise RuntimeError("Nesukonfigūruoti Supabase prisijungimo duomenys")
    return create_client(settings.supabase_url, key)


def build_object_url(bucket: str, path: str) -> str:
    settings = get_settings()
    return f"{settings.supabase_url}/storage/v1/object/{bucket}/{path}"


def _upload_single(client, bucket: str, path: str, content: bytes, content_type: Optional[str]) -> str:
    """Upload a single file and return its public URL."""
    options = {"content-type": content_type} if content_type else None
    try:
        result = client.storage.from_(bucket).upload(path, content, options)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(502, "Nepavyko įkelti į saugyklą") from exc

    error = None
    if isinstance(result, dict):
        error = result.get("error")
    else:
        error = getattr(result, "error", None)

    if error:
        raise HTTPException(502, "Nepavyko įkelti į saugyklą")

    return build_object_url(bucket, path)


def upload_evidence_file(
    *,
    project_id: str,
    filename: Optional[str],
    content: bytes,
    content_type: Optional[str],
) -> tuple[str, str]:
    path = build_object_path(project_id, filename)
    url = _upload_single(get_storage_client(), BUCKET_EVIDENCES, path, content, content_type)
    return path, url


@dataclass
class UploadedVariants:
    """URLs for all uploaded image variants."""

    original_url: str
    thumbnail_url: Optional[str] = None
    medium_url: Optional[str] = None


def upload_image_variants(
    *,
    project_id: str,
    filename: Optional[str],
    original_bytes: bytes,
    original_content_type: Optional[str],
    thumbnail_bytes: Optional[bytes] = None,
    medium_bytes: Optional[bytes] = None,
) -> UploadedVariants:
    """Upload original + optional thumbnail and medium WebP variants.

    Path schema:
    - Original:  ``{project_id}/{uuid}{ext}``
    - Thumbnail: ``{project_id}/{uuid}_thumb.webp``
    - Medium:    ``{project_id}/{uuid}_md.webp``
    """
    token = uuid.uuid4().hex
    ext = _file_extension(filename)
    client = get_storage_client()

    # --- Original ---
    original_path = f"{project_id}/{token}{ext}"
    original_url = _upload_single(
        client,
        BUCKET_EVIDENCES,
        original_path,
        original_bytes,
        original_content_type,
    )

    # --- Thumbnail ---
    thumbnail_url = None
    if thumbnail_bytes:
        thumb_path = f"{project_id}/{token}_thumb.webp"
        try:
            thumbnail_url = _upload_single(
                client,
                BUCKET_EVIDENCES,
                thumb_path,
                thumbnail_bytes,
                "image/webp",
            )
        except Exception:
            logger.warning("Failed to upload thumbnail for %s", project_id, exc_info=True)

    # --- Medium ---
    medium_url = None
    if medium_bytes:
        medium_path = f"{project_id}/{token}_md.webp"
        try:
            medium_url = _upload_single(
                client,
                BUCKET_EVIDENCES,
                medium_path,
                medium_bytes,
                "image/webp",
            )
        except Exception:
            logger.warning("Failed to upload medium variant for %s", project_id, exc_info=True)

    return UploadedVariants(
        original_url=original_url,
        thumbnail_url=thumbnail_url,
        medium_url=medium_url,
    )

