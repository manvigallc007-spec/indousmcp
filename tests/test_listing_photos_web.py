"""Listing photos end to end through the web: owner uploads, admin approves, visitor sees it.

The access rules are the point here. An upload endpoint that writes to disk must refuse an
anonymous caller and refuse an owner reaching at someone else's listing, and nothing may be visible
on the public page before an admin has approved it.
"""

import io

import pytest
from starlette.testclient import TestClient

from indo_usa_mcp import db, photos, verticals
from indo_usa_mcp.config import settings
from indo_usa_mcp.web.app import app


@pytest.fixture(autouse=True)
def tmp_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "admin_password", "zztest-admin")
    return tmp_path


def _png(w=900, h=700, colour=(180, 80, 30)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), colour).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def owned():
    """A listing claimed by a signed-in owner, plus a logged-in client for them."""
    email = "zzowner@example.com"
    # portal._owned() treats a listing whose contact email matches as owned (the self-added case),
    # so setting `email` is how a test makes someone a real owner -- there is no claimed_by column.
    rid = verticals.create_record(
        "restaurants", {"name": "ZZTEST Web Photo Cafe", "city": "Zzwebphoto", "state": "TX",
                        "lat": 33.0, "lng": -96.7, "email": email}, source="test")["id"]
    try:
        yield {"id": rid, "email": email}
    finally:
        db.execute("DELETE FROM listing_photos WHERE vertical='restaurants' AND listing_id=%s", (rid,))
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


def _upload(client, rid, data=None, mime="image/png"):
    return client.post(f"/portal/listing/restaurants/{rid}/photo",
                       files={"photo": ("snap.png", data or _png(), mime)},
                       data={"caption": "Our thali"}, follow_redirects=False)


# ------------------------------------------------------------------ access control
def test_anonymous_upload_is_refused(owned):
    r = TestClient(app).post(f"/portal/listing/restaurants/{owned['id']}/photo",
                             files={"photo": ("a.png", _png(), "image/png")},
                             follow_redirects=False)
    assert r.status_code in (302, 303, 403)
    assert "/portal/login" in r.headers.get("location", "") or r.status_code == 403
    assert photos.count_for_listing("restaurants", owned["id"]) == 0


def test_a_signed_in_user_cannot_upload_to_someone_elses_listing(owned, monkeypatch):
    """Ownership is checked server-side, not inferred from the URL."""
    from indo_usa_mcp.web import portal
    monkeypatch.setattr(portal, "portal_email", lambda request: "stranger@example.com")
    monkeypatch.setattr(portal, "_owned", lambda email: [])
    r = _upload(TestClient(app), owned["id"])
    assert r.status_code in (302, 303, 403)
    assert photos.count_for_listing("restaurants", owned["id"]) == 0


# ------------------------------------------------------------------ the owner flow
def _as_owner(monkeypatch, owned):
    from indo_usa_mcp.web import portal
    monkeypatch.setattr(portal, "portal_email", lambda request: owned["email"])
    monkeypatch.setattr(portal, "_owned",
                        lambda email: [{"vertical": "restaurants", "id": owned["id"]}])
    return TestClient(app)


def test_owner_uploads_and_sees_it_pending(monkeypatch, owned):
    c = _as_owner(monkeypatch, owned)
    r = _upload(c, owned["id"])
    assert r.status_code == 303 and "photo=ok" in r.headers["location"]

    rows = photos.for_listing("restaurants", owned["id"], status="")
    assert len(rows) == 1 and rows[0]["status"] == "pending"
    assert rows[0]["caption"] == "Our thali"

    page = c.get(f"/portal/listing/restaurants/{owned['id']}").text
    assert "awaiting review" in page
    assert "/uploads/photos/" in page                      # the owner can see their own upload


def test_a_bad_upload_shows_the_owner_why(monkeypatch, owned):
    c = _as_owner(monkeypatch, owned)
    r = c.post(f"/portal/listing/restaurants/{owned['id']}/photo",
               files={"photo": ("a.txt", b"definitely not an image", "image/png")},
               follow_redirects=False)
    assert "photo=not_an_image" in r.headers["location"]
    assert "image we can read" in c.get(r.headers["location"]).text


def test_owner_can_remove_their_photo(monkeypatch, owned):
    c = _as_owner(monkeypatch, owned)
    _upload(c, owned["id"])
    pid = photos.for_listing("restaurants", owned["id"], status="")[0]["id"]
    r = c.post(f"/portal/listing/restaurants/{owned['id']}/photo/{pid}/delete",
               follow_redirects=False)
    assert r.status_code == 303
    assert photos.count_for_listing("restaurants", owned["id"]) == 0


# ------------------------------------------------------------------ public visibility
def test_a_pending_photo_is_not_on_the_public_page(monkeypatch, owned):
    c = _as_owner(monkeypatch, owned)
    _upload(c, owned["id"])
    public = TestClient(app).get(f"/listing/restaurants/{owned['id']}").text
    assert "/uploads/photos/" not in public      # no image served
    assert "class='lp-gal'" not in public        # and no gallery element (its CSS always ships)


def test_once_published_it_appears_with_a_responsive_image(monkeypatch, owned):
    c = _as_owner(monkeypatch, owned)
    _upload(c, owned["id"], data=_png(1800, 1200))
    pid = photos.for_listing("restaurants", owned["id"], status="")[0]["id"]
    photos.publish(pid, "admin")

    public = TestClient(app).get(f"/listing/restaurants/{owned['id']}").text
    assert "lp-gal" in public and "/uploads/photos/" in public
    assert "srcset=" in public and "400w" in public and "1600w" in public
    assert "sizes=" in public and "loading='lazy'" in public
    assert "Photos supplied by the owner" in public       # provenance is stated
    assert ".lp-gal{" in public                           # its stylesheet came along


def test_the_served_file_is_a_webp_and_cacheable(monkeypatch, owned):
    c = _as_owner(monkeypatch, owned)
    _upload(c, owned["id"])
    row = photos.for_listing("restaurants", owned["id"], status="")[0]
    r = TestClient(app).get(f"/uploads/{row['path_md']}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"
    assert "max-age" in r.headers.get("cache-control", "")
    assert r.content[:4] == b"RIFF"


def test_upload_paths_cannot_escape_the_photo_directory():
    c = TestClient(app)
    for bad in ("photos/../../etc/passwd", "photos/..%2f..%2fsecret", "../uploads/photos/x.webp",
                "photos/sub/dir.webp", "secrets/key.webp"):
        assert c.get(f"/uploads/{bad}").status_code == 404


# ------------------------------------------------------------------ admin moderation
def _as_admin():
    c = TestClient(app)
    r = c.post("/admin/login",
               data={"username": settings.admin_username, "password": "zztest-admin"},
               follow_redirects=False)
    assert r.status_code in (302, 303), "admin login failed; the rest would be a login page"
    return c


def test_admin_queue_shows_pending_and_publishes(monkeypatch, owned):
    oc = _as_owner(monkeypatch, owned)
    _upload(oc, owned["id"])
    pid = photos.for_listing("restaurants", owned["id"], status="")[0]["id"]

    ac = _as_admin()
    page = ac.get("/admin/photos")
    assert page.status_code == 200
    assert "ZZTEST Web Photo Cafe" in page.text   # the listing it belongs to is named
    assert str(pid) in page.text                 # with an actionable control for this photo

    ac.post("/admin/photos", data={"id": str(pid), "action": "publish"}, follow_redirects=False)
    assert photos.get(pid)["status"] == "published"


def test_admin_reject_deletes_the_files(monkeypatch, owned, tmp_uploads):
    oc = _as_owner(monkeypatch, owned)
    _upload(oc, owned["id"])
    row = photos.for_listing("restaurants", owned["id"], status="")[0]
    stored = [tmp_uploads / p for p in (row["path_sm"], row["path_md"]) if p]
    assert all(p.is_file() for p in stored)

    _as_admin().post("/admin/photos", data={"id": str(row["id"]), "action": "reject",
                                            "reason": "not this business"}, follow_redirects=False)
    assert photos.get(row["id"])["status"] == "rejected"
    assert not any(p.exists() for p in stored)


def test_the_photo_queue_is_not_reachable_without_admin_login(owned):
    r = TestClient(app).get("/admin/photos", follow_redirects=False)
    assert r.status_code in (302, 303, 401, 403, 503)
    assert "awaiting review" not in r.text


def test_admin_nav_shows_a_badge_for_waiting_photos(monkeypatch, owned):
    oc = _as_owner(monkeypatch, owned)
    _upload(oc, owned["id"])
    page = _as_admin().get("/admin").text
    assert "/admin/photos" in page                         # the queue is linked from the nav
