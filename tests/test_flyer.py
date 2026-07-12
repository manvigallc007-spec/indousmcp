"""Flyer upload: image -> LLM-vision extraction -> review form -> submissions/events approval queues.
Real dev DB, ZZTEST rows, try/finally; vision LLM calls are mocked via monkeypatch (no network).
Local disk storage is redirected to tmp_path for save_image/create_upload tests."""

from psycopg.types.json import Jsonb
from starlette.testclient import TestClient

import indo_usa_mcp.embeddings as emb
from indo_usa_mcp import db, flyer
from indo_usa_mcp.config import settings
from indo_usa_mcp.events import pipeline as events
from indo_usa_mcp.web import chat, portal
from indo_usa_mcp.web.app import app

_client = TestClient(app)


def _enable_gemini(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "llm_api_key", "fake-gemini-key")


def _disable(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "search")


# --------------------------------------------------------------- config gate
def test_flyer_uploads_enabled_requires_gemini_and_key(monkeypatch):
    _disable(monkeypatch)
    assert settings.flyer_uploads_enabled is False
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "llm_api_key", "")
    assert settings.flyer_uploads_enabled is False
    _enable_gemini(monkeypatch)
    assert settings.flyer_uploads_enabled is True


def test_extract_from_image_short_circuits_when_disabled(monkeypatch):
    _disable(monkeypatch)
    out = flyer.extract_from_image(b"fake", "image/jpeg")
    assert out == {"error": "vision_unavailable"}


# --------------------------------------------------------------- save_image
def test_save_image_rejects_bad_mime_and_oversize(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    try:
        flyer.save_image(b"data", "application/pdf")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "unsupported_image_type"

    monkeypatch.setattr(settings, "max_upload_mb", 1)
    try:
        flyer.save_image(b"x" * (2 * 1024 * 1024), "image/jpeg")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "image_too_large"


def test_save_image_writes_file(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    rel = flyer.save_image(b"fakejpegbytes", "image/jpeg")
    assert rel.startswith("flyers/") and rel.endswith(".jpg")
    assert (tmp_path / rel).read_bytes() == b"fakejpegbytes"


# --------------------------------------------------------------- create_upload
def test_create_upload_inserts_row(monkeypatch, tmp_path):
    _enable_gemini(monkeypatch)
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(flyer, "extract_from_image",
                        lambda data, mime: {"vertical": "restaurants", "name": "ZZTEST Flyer Biz",
                                            "confidence": 0.9})
    db.execute("DELETE FROM flyer_uploads WHERE uploader_email = 'zztest@example.com'")
    try:
        res = flyer.create_upload("zztest@example.com", b"fakejpeg", "image/jpeg")
        assert res["ok"] and res["vertical_guess"] == "restaurants"
        row = db.query_one("SELECT * FROM flyer_uploads WHERE id = %s", (res["id"],))
        assert row["status"] == "extracted" and row["extracted"]["name"] == "ZZTEST Flyer Biz"
    finally:
        db.execute("DELETE FROM flyer_uploads WHERE uploader_email = 'zztest@example.com'")


# --------------------------------------------------------------- events.submit_flyer_event
def test_submit_flyer_event_always_pending(monkeypatch):
    monkeypatch.setattr(emb, "enabled", lambda: False)
    rec = {"name": "ZZTEST Flyer Garba Night", "city": "Plano", "state": "TX",
           "venue_name": "Community Hall", "start_at": "2099-01-01T18:00"}
    db.execute("DELETE FROM events WHERE name = %s", (rec["name"],))
    try:
        out = events.submit_flyer_event(rec)
        assert out["ok"]
        row = db.query_one("SELECT status, confidence_score FROM events WHERE id = %s", (out["id"],))
        # High-confidence complete record would normally auto-approve via _reconcile; flyer-sourced
        # events must NEVER take that path regardless of confidence.
        assert row["status"] == "pending"
    finally:
        db.execute("DELETE FROM events WHERE name = %s", (rec["name"],))


def test_submit_flyer_event_rejects_missing_fields():
    assert events.submit_flyer_event({"name": ""})["error"] == "missing_required_fields"
    assert events.submit_flyer_event({"name": "X"})["error"] == "missing_required_fields"


def test_submit_flyer_event_rejects_duplicate(monkeypatch):
    monkeypatch.setattr(emb, "enabled", lambda: False)
    rec = {"name": "ZZTEST Flyer Dup Event", "city": "Plano", "state": "TX",
          "start_at": "2099-02-02T18:00"}
    db.execute("DELETE FROM events WHERE name = %s", (rec["name"],))
    try:
        first = events.submit_flyer_event(rec)
        assert first["ok"]
        second = events.submit_flyer_event(rec)
        assert second["ok"] is False and second["error"] == "duplicate_event"
    finally:
        db.execute("DELETE FROM events WHERE name = %s", (rec["name"],))


# --------------------------------------------------------------- portal routes
def test_portal_flyer_requires_login():
    r = _client.get("/portal/flyer", follow_redirects=False)
    assert r.status_code == 303 and "/portal/login" in r.headers["location"]


def test_portal_flyer_shows_unavailable_when_disabled(monkeypatch):
    monkeypatch.setattr(portal, "portal_email", lambda req: "owner@example.com")
    _disable(monkeypatch)
    r = _client.get("/portal/flyer")
    assert r.status_code == 200 and "isn't available" in r.text


def test_portal_flyer_post_redirects_to_review(monkeypatch, tmp_path):
    monkeypatch.setattr(portal, "portal_email", lambda req: "owner@example.com")
    _enable_gemini(monkeypatch)
    monkeypatch.setattr(portal.flyer, "create_upload",
                        lambda email, data, mime: {"ok": True, "id": 999, "vertical_guess": "restaurants"})
    r = _client.post("/portal/flyer", files={"image": ("f.jpg", b"data", "image/jpeg")},
                     follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/portal/flyer/999/review"


def test_portal_flyer_review_shows_extracted_fields_and_is_owner_scoped(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    db.execute("DELETE FROM flyer_uploads WHERE uploader_email = 'owner@example.com'")
    row = db.query_one(
        "INSERT INTO flyer_uploads (uploader_email, image_path, mime_type, vertical_guess, extracted) "
        "VALUES ('owner@example.com', 'flyers/x.jpg', 'image/jpeg', 'restaurants', %s) RETURNING id",
        (Jsonb({"name": "ZZTEST Review Biz", "city": "Plano"}),))
    fid = row["id"]
    try:
        monkeypatch.setattr(portal, "portal_email", lambda req: "owner@example.com")
        r = _client.get(f"/portal/flyer/{fid}/review")
        assert r.status_code == 200 and "ZZTEST Review Biz" in r.text

        # a different signed-in user cannot see it
        monkeypatch.setattr(portal, "portal_email", lambda req: "someone-else@example.com")
        r2 = _client.get(f"/portal/flyer/{fid}/review")
        assert r2.status_code == 404
    finally:
        db.execute("DELETE FROM flyer_uploads WHERE id = %s", (fid,))


def test_portal_flyer_confirm_business_calls_submissions(monkeypatch):
    db.execute("DELETE FROM flyer_uploads WHERE uploader_email = 'owner@example.com'")
    row = db.query_one(
        "INSERT INTO flyer_uploads (uploader_email, image_path, mime_type) "
        "VALUES ('owner@example.com', 'flyers/x.jpg', 'image/jpeg') RETURNING id")
    fid = row["id"]
    try:
        monkeypatch.setattr(portal, "portal_email", lambda req: "owner@example.com")
        captured = {}
        monkeypatch.setattr(portal.submissions, "submit",
                            lambda v, payload, contact_email=None, note=None:
                            captured.update(v=v, payload=payload) or {"ok": True, "id": 42})
        r = _client.post(f"/portal/flyer/{fid}/confirm",
                         data={"vertical": "restaurants", "name": "ZZTEST Confirm Biz"},
                         follow_redirects=False)
        assert r.status_code == 303 and "added=1" in r.headers["location"]
        assert captured["v"] == "restaurants" and captured["payload"]["name"] == "ZZTEST Confirm Biz"
        assert db.query_one("SELECT status, created_submission_id FROM flyer_uploads WHERE id=%s",
                            (fid,)) == {"status": "submitted", "created_submission_id": 42}
    finally:
        db.execute("DELETE FROM flyer_uploads WHERE id = %s", (fid,))


def test_portal_flyer_confirm_event_calls_submit_flyer_event(monkeypatch):
    db.execute("DELETE FROM flyer_uploads WHERE uploader_email = 'owner@example.com'")
    row = db.query_one(
        "INSERT INTO flyer_uploads (uploader_email, image_path, mime_type) "
        "VALUES ('owner@example.com', 'flyers/x.jpg', 'image/jpeg') RETURNING id")
    fid = row["id"]
    try:
        monkeypatch.setattr(portal, "portal_email", lambda req: "owner@example.com")
        captured = {}
        monkeypatch.setattr(portal.events, "submit_flyer_event",
                            lambda rec: captured.update(rec=rec) or {"ok": True, "id": 77})
        r = _client.post(f"/portal/flyer/{fid}/confirm",
                         data={"vertical": "events", "name": "ZZTEST Confirm Event",
                               "start_date": "2099-03-03", "start_time": "18:00"},
                         follow_redirects=False)
        assert r.status_code == 303 and "added=1" in r.headers["location"]
        assert captured["rec"]["name"] == "ZZTEST Confirm Event"
        assert db.query_one("SELECT created_event_id FROM flyer_uploads WHERE id=%s", (fid,)
                            )["created_event_id"] == 77
    finally:
        db.execute("DELETE FROM flyer_uploads WHERE id = %s", (fid,))


def test_portal_flyer_confirm_event_requires_start_date(monkeypatch):
    db.execute("DELETE FROM flyer_uploads WHERE uploader_email = 'owner@example.com'")
    row = db.query_one(
        "INSERT INTO flyer_uploads (uploader_email, image_path, mime_type) "
        "VALUES ('owner@example.com', 'flyers/x.jpg', 'image/jpeg') RETURNING id")
    fid = row["id"]
    try:
        monkeypatch.setattr(portal, "portal_email", lambda req: "owner@example.com")
        r = _client.post(f"/portal/flyer/{fid}/confirm",
                         data={"vertical": "events", "name": "ZZTEST No Date"})
        assert r.status_code == 400
    finally:
        db.execute("DELETE FROM flyer_uploads WHERE id = %s", (fid,))


# --------------------------------------------------------------- chat entry point
def test_chat_flyer_requires_login(monkeypatch):
    monkeypatch.setattr(chat, "portal_email", lambda req: None)
    called = []
    monkeypatch.setattr(chat.flyer, "create_upload", lambda *a, **k: called.append(1))
    r = _client.post("/chat/flyer", files={"image": ("f.jpg", b"data", "image/jpeg")})
    assert r.status_code == 401 and r.json()["needs_login"] is True
    assert not called


def test_chat_flyer_returns_review_link_when_signed_in(monkeypatch):
    monkeypatch.setattr(chat, "portal_email", lambda req: "owner@example.com")
    _enable_gemini(monkeypatch)
    monkeypatch.setattr(chat.flyer, "create_upload",
                        lambda email, data, mime: {"ok": True, "id": 55, "vertical_guess": "events"})
    r = _client.post("/chat/flyer", files={"image": ("f.jpg", b"data", "image/jpeg")})
    assert r.status_code == 200
    body = r.json()
    assert body["link"] == "/portal/flyer/55/review" and "/portal/flyer/55/review" in body["reply"]
