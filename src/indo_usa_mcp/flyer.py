"""Flyer upload: an image (event poster, business promo) -> LLM-vision extraction -> a pre-filled
review form -> the existing submissions/events approval queues.

Vision is Gemini-only (see config.flyer_uploads_enabled) -- the only one of the app's free LLM
presets that reads images out of the box. Extraction never raises and never auto-publishes; a human
always reviews via /portal/flyer/<id>/review before anything reaches submissions.submit() or
events.submit_flyer_event(). Storage is local disk (zero-budget, same convention as ./backups).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from . import db, verticals
from .config import settings
from .onboard import _strip_json

_ALLOWED_MIME = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}

_TARGETS = ", ".join(sorted({v["label"] for v in verticals.VERTICALS.values()}))
_SYSTEM = (
    "You read a flyer/poster image (a business promo or an event announcement) for a US directory of "
    "Indian-American businesses and events. Use ONLY what is visibly printed on the image -- never "
    "invent, guess, or assume a fact that isn't shown. Classify it into exactly one category: "
    f"{_TARGETS}, or \"Events\" if it is announcing a specific dated event/gathering. "
    "Output STRICT JSON ONLY, one object with exactly these keys and no others -- no markdown fences, "
    "no explanation: vertical (the category label above, exactly as written, or \"Events\"), name "
    "(business name or event title), description (one honest sentence from what's shown), start_date "
    "(YYYY-MM-DD, events only, else empty string), start_time (HH:MM 24h, events only, else empty "
    "string), end_date (YYYY-MM-DD, events only, else empty string), venue_name, address_full, city, "
    "state (2-letter USPS code if shown), phone, website, email, organizer (events only), category "
    "(a short event category word, events only, else empty string), confidence (0.0-1.0, your own "
    "estimate of extraction reliability). Use an empty string for anything not visible on the image.")

_LABEL_TO_VERTICAL = {v["label"]: k for k, v in verticals.VERTICALS.items()}


def _resolve_vertical(label: str) -> str | None:
    label = (label or "").strip()
    if label.lower() == "events":
        return "events"
    return _LABEL_TO_VERTICAL.get(label)


def extract_from_image(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    """Vision-extract structured fields from a flyer image. Never raises; returns an {'error': ...}
    shape when vision is unavailable or the call/parse fails."""
    from . import assistant

    if not settings.flyer_uploads_enabled:
        return {"error": "vision_unavailable"}
    raw = assistant.complete_vision(_SYSTEM, "Extract the flyer details as JSON.", image_bytes, mime_type)
    if not raw:
        return {"error": "extraction_failed"}
    try:
        parsed = json.loads(_strip_json(raw))
    except Exception:
        return {"error": "extraction_failed"}
    if not isinstance(parsed, dict):
        return {"error": "extraction_failed"}
    parsed["vertical"] = _resolve_vertical(parsed.get("vertical", ""))
    return parsed


def save_image(data: bytes, mime_type: str) -> str:
    """Save an uploaded flyer image to local disk under settings.upload_dir. Returns the relative
    path (e.g. 'flyers/<uuid>.jpg'). Raises ValueError on a disallowed mime type or oversized file --
    callers should catch and surface a friendly error."""
    ext = _ALLOWED_MIME.get((mime_type or "").lower())
    if not ext:
        raise ValueError("unsupported_image_type")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise ValueError("image_too_large")
    rel = f"flyers/{uuid.uuid4().hex}.{ext}"
    dest = Path(settings.upload_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return rel


def create_upload(uploader_email: str, image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    """Save the image + run extraction + record a flyer_uploads row. Never raises -- an extraction
    failure still keeps the image/row (status stays 'extracted' with an error note) so the review
    form can fall back to manual entry rather than losing the upload."""
    try:
        rel_path = save_image(image_bytes, mime_type)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    extracted = extract_from_image(image_bytes, mime_type)
    error = extracted.get("error")
    row = db.query_one(
        "INSERT INTO flyer_uploads (uploader_email, image_path, mime_type, vertical_guess, "
        "extracted, error) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
        (uploader_email, rel_path, mime_type, extracted.get("vertical"),
         Jsonb(extracted) if extracted else None, error))
    return {"ok": True, "id": row["id"], "vertical_guess": extracted.get("vertical"),
            "extracted": extracted, "image_path": rel_path}


def get_upload(upload_id: int, uploader_email: str) -> dict[str, Any] | None:
    """Fetch a flyer_uploads row, scoped to its uploader (ownership check)."""
    return db.query_one(
        "SELECT * FROM flyer_uploads WHERE id = %s AND lower(uploader_email) = lower(%s)",
        (upload_id, uploader_email))


def list_for_uploader(uploader_email: str, limit: int = 20) -> list[dict[str, Any]]:
    return db.query(
        "SELECT id, image_path, vertical_guess, status, created_at, created_submission_id, "
        "created_event_id FROM flyer_uploads WHERE lower(uploader_email) = lower(%s) "
        "ORDER BY created_at DESC LIMIT %s", (uploader_email, limit))


def mark_submitted(upload_id: int, *, submission_id: int | None = None,
                   event_id: int | None = None) -> None:
    db.execute(
        "UPDATE flyer_uploads SET status = 'submitted', created_submission_id = %s, "
        "created_event_id = %s WHERE id = %s", (submission_id, event_id, upload_id))
