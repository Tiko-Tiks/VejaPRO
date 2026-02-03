from pathlib import Path
from typing import Optional, Tuple
import uuid

from fastapi import HTTPException
from supabase import create_client

from app.core.config import get_settings


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
        raise RuntimeError("Supabase credentials are not configured")
    return create_client(settings.supabase_url, key)


def build_object_url(bucket: str, path: str) -> str:
    settings = get_settings()
    return f"{settings.supabase_url}/storage/v1/object/{bucket}/{path}"


def upload_evidence_file(
    *,
    project_id: str,
    filename: Optional[str],
    content: bytes,
    content_type: Optional[str],
) -> Tuple[str, str]:
    path = build_object_path(project_id, filename)
    client = get_storage_client()
    options = {"content-type": content_type} if content_type else None
    try:
        result = client.storage.from_(BUCKET_EVIDENCES).upload(path, content, options)
    except Exception as exc:  # pragma: no cover - depends on supabase
        raise HTTPException(502, "Storage upload failed") from exc

    error = None
    if isinstance(result, dict):
        error = result.get("error")
    else:
        error = getattr(result, "error", None)

    if error:
        raise HTTPException(502, "Storage upload failed")

    return path, build_object_url(BUCKET_EVIDENCES, path)
