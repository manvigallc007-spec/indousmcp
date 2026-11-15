"""Owner-uploaded listing photos: the ingest pipeline, its refusals, moderation and rendering.

The refusals are the point of most of these. An upload endpoint is the most hostile input the site
takes, and this one writes to disk, so the tests pin: only real raster images get in, nothing
user-supplied is ever written, EXIF (which carries GPS) is dropped, a decompression bomb is refused,
and nothing is visible before an admin approves it.

Real dev DB + a temp upload dir; rows and files are cleaned up in finally blocks.
"""

import io
import pathlib

import pytest

from indo_usa_mcp import db, photos, verticals
from indo_usa_mcp.config import settings


# ------------------------------------------------------------------ fixtures
@pytest.fixture(autouse=True)
def tmp_uploads(tmp_path, monkeypatch):
    """Never write into the real ./uploads during tests."""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    return tmp_path


@pytest.fixture
def listing():
    rid = verticals.create_record(
        "restaurants", {"name": "ZZTEST Photo Cafe", "city": "Zzphoto", "state": "TX"},
        source="test")["id"]
    try:
        yield rid
    finally:
        db.execute("DELETE FROM listing_photos WHERE vertical='restaurants' AND listing_id=%s", (rid,))
        db.execute("DELETE FROM restaurants WHERE id=%s", (rid,))


def _png(w=1200, h=900, colour=(200, 90, 30)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), colour).save(buf, format="PNG")
    return buf.getvalue()


# ------------------------------------------------------------------ happy path
def test_ingest_stores_webp_derivatives_and_a_pending_row(listing, tmp_uploads):
    res = photos.ingest("restaurants", listing, "Owner@Example.com ", _png(1200, 900), "image/png")
    assert res["ok"], res
    assert res["widths"] == [400, 800]              # no 1600 from a 1200px source: never upscale

    row = photos.get(res["id"])
    assert row["status"] == "pending"               # nothing is public until an admin approves
    assert row["owner_email"] == "owner@example.com"   # normalised
    assert row["path_sm"].startswith("photos/") and row["path_sm"].endswith(".webp")

    for rel in (row["path_sm"], row["path_md"]):
        f = tmp_uploads / rel
        assert f.is_file() and f.stat().st_size > 0
        assert f.read_bytes()[:4] == b"RIFF"        # really WebP, not the bytes we were handed


def test_a_large_source_gets_all_three_widths(listing):
    res = photos.ingest("restaurants", listing, "o@e.com", _png(2000, 1200), "image/png")
    assert res["ok"] and res["widths"] == [400, 800, 1600]


def test_nothing_user_supplied_is_written_to_disk(listing, tmp_uploads):
    """Only our own re-encoded derivatives land on disk, so there is no uploaded file to serve."""
    photos.ingest("restaurants", listing, "o@e.com", _png(), "image/png")
    written = list((tmp_uploads / "photos").iterdir())
    assert written and all(f.suffix == ".webp" for f in written)


def test_filenames_are_generated_not_taken_from_the_upload(listing, tmp_uploads):
    photos.ingest("restaurants", listing, "o@e.com", _png(), "image/png")
    for f in (tmp_uploads / "photos").iterdir():
        stem = f.stem.rsplit("_", 1)[0]
        assert len(stem) == 32 and all(c in "0123456789abcdef" for c in stem)


def test_exif_is_stripped(listing, tmp_uploads):
    """Phone photos carry GPS. Publishing an owner's home coordinates because they shot a menu
    indoors would be a real harm, so the re-encode must not carry EXIF through."""
    from PIL import Image
    src = Image.new("RGB", (1000, 800), (5, 5, 5))
    buf = io.BytesIO()
    exif = src.getexif()
    exif[271] = "ZZTestCamera"                       # Make
    src.save(buf, format="JPEG", exif=exif.tobytes())
    assert b"ZZTestCamera" in buf.getvalue()         # it really is in the source

    res = photos.ingest("restaurants", listing, "o@e.com", buf.getvalue(), "image/jpeg")
    assert res["ok"]
    row = photos.get(res["id"])
    for rel in (row["path_sm"], row["path_md"]):
        data = (tmp_uploads / rel).read_bytes()
        assert b"ZZTestCamera" not in data
        assert not Image.open(io.BytesIO(data)).getexif()


def test_orientation_is_applied_before_exif_is_dropped(listing):
    """A phone photo marked "rotate 90" must come out upright, since the tag is about to be lost."""
    from PIL import Image
    src = Image.new("RGB", (1000, 500), (9, 9, 9))   # landscape
    buf = io.BytesIO()
    exif = src.getexif()
    exif[274] = 6                                    # Orientation: rotate 90 CW
    src.save(buf, format="JPEG", exif=exif.tobytes())
    res = photos.ingest("restaurants", listing, "o@e.com", buf.getvalue(), "image/jpeg")
    assert res["ok"]
    row = photos.get(res["id"])
    assert row["height"] > row["width"]              # transposed to portrait


# ------------------------------------------------------------------ refusals
def test_non_image_bytes_are_refused(listing):
    assert photos.ingest("restaurants", listing, "o@e.com", b"not an image at all",
                         "image/png")["error"] == "not_an_image"


def test_svg_is_refused_even_with_an_image_mime(listing):
    """SVG is a script carrier; it is not in ALLOWED_MIME and its bytes are not a raster image."""
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    assert not photos.ingest("restaurants", listing, "o@e.com", svg, "image/svg+xml")["ok"]
    assert not photos.ingest("restaurants", listing, "o@e.com", svg, "image/png")["ok"]


def test_a_png_renamed_as_an_html_payload_is_still_judged_on_its_bytes(listing):
    html = b"<!doctype html><script>alert(1)</script>"
    assert photos.ingest("restaurants", listing, "o@e.com", html, "image/jpeg")["error"] \
        == "not_an_image"


def test_unsupported_mime_is_refused(listing):
    assert photos.ingest("restaurants", listing, "o@e.com", _png(), "image/gif")["error"] \
        == "unsupported_type"
    assert photos.ingest("restaurants", listing, "o@e.com", _png(), "application/pdf")["error"] \
        == "unsupported_type"


def test_mime_with_parameters_is_still_accepted(listing):
    assert photos.ingest("restaurants", listing, "o@e.com", _png(), "image/png; charset=binary")["ok"]


def test_oversized_file_is_refused(listing, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 0)
    assert photos.ingest("restaurants", listing, "o@e.com", _png(), "image/png")["error"] \
        == "file_too_large"


def test_a_decompression_bomb_is_refused(listing, monkeypatch):
    """A tiny file can decode to gigabytes; the pixel ceiling is what stops it."""
    monkeypatch.setattr(photos, "MAX_PIXELS", 10_000)        # 100x100
    assert photos.ingest("restaurants", listing, "o@e.com", _png(1200, 900), "image/png")["error"] \
        == "image_too_large"


def test_a_tiny_image_is_refused(listing):
    assert photos.ingest("restaurants", listing, "o@e.com", _png(60, 40), "image/png")["error"] \
        == "image_too_small"


def test_empty_upload_is_refused(listing):
    assert photos.ingest("restaurants", listing, "o@e.com", b"", "image/png")["error"] == "empty"


def test_the_same_image_twice_is_a_duplicate_not_a_second_card(listing):
    data = _png(900, 700)
    assert photos.ingest("restaurants", listing, "o@e.com", data, "image/png")["ok"]
    assert photos.ingest("restaurants", listing, "o@e.com", data, "image/png")["error"] == "duplicate"
    assert photos.count_for_listing("restaurants", listing) == 1


def test_a_gallery_is_capped(listing, monkeypatch):
    monkeypatch.setattr(photos, "MAX_PER_LISTING", 2)
    for i in range(2):
        assert photos.ingest("restaurants", listing, "o@e.com", _png(500, 400, (i, i, i)),
                             "image/png")["ok"]
    assert photos.ingest("restaurants", listing, "o@e.com", _png(500, 400, (9, 9, 9)),
                         "image/png")["error"] == "too_many"


# ------------------------------------------------------------------ moderation
def test_pending_photos_are_not_public(listing):
    photos.ingest("restaurants", listing, "o@e.com", _png(), "image/png")
    assert photos.for_listing("restaurants", listing) == []       # published only
    assert photos.primary("restaurants", listing) is None
    assert len(photos.for_listing("restaurants", listing, status="")) == 1   # owner sees it


def test_publishing_makes_it_public(listing):
    pid = photos.ingest("restaurants", listing, "o@e.com", _png(), "image/png")["id"]
    photos.publish(pid, "admin")
    rows = photos.for_listing("restaurants", listing)
    assert len(rows) == 1 and rows[0]["id"] == pid
    assert photos.primary("restaurants", listing)["id"] == pid


def test_rejecting_deletes_the_files(listing, tmp_uploads):
    res = photos.ingest("restaurants", listing, "o@e.com", _png(), "image/png")
    row = photos.get(res["id"])
    paths = [tmp_uploads / p for p in (row["path_sm"], row["path_md"]) if p]
    assert all(p.is_file() for p in paths)
    photos.reject(res["id"], "wrong business", "admin")
    assert not any(p.exists() for p in paths)
    assert photos.get(res["id"])["status"] == "rejected"
    assert photos.for_listing("restaurants", listing) == []


def test_an_owner_can_remove_only_their_own_photo(listing):
    pid = photos.ingest("restaurants", listing, "mine@e.com", _png(), "image/png")["id"]
    assert photos.remove(pid, "someone-else@e.com")["error"] == "not_found"
    assert photos.get(pid)["status"] == "pending"
    assert photos.remove(pid, "Mine@E.com")["ok"]                 # case-insensitive match
    assert photos.get(pid)["status"] == "removed"


def test_removed_photos_leave_the_owner_view_too(listing):
    pid = photos.ingest("restaurants", listing, "o@e.com", _png(), "image/png")["id"]
    photos.remove(pid, "o@e.com")
    assert photos.for_listing("restaurants", listing, status="") == []
    assert photos.count_for_listing("restaurants", listing) == 0  # frees a gallery slot


def test_admin_queue_lists_pending_oldest_first(listing):
    before = photos.pending_count()
    photos.ingest("restaurants", listing, "o@e.com", _png(500, 400), "image/png")
    photos.ingest("restaurants", listing, "o@e.com", _png(500, 400, (1, 2, 3)), "image/png")
    assert photos.pending_count() == before + 2
    ids = [r["id"] for r in photos.pending()]
    assert ids == sorted(ids)


# ------------------------------------------------------------------ rendering
def test_img_html_is_responsive_so_a_phone_does_not_fetch_the_1600px_file(listing):
    res = photos.ingest("restaurants", listing, "o@e.com", _png(2000, 1200), "image/png")
    row = photos.get(res["id"])
    h = photos.img_html(row, alt="Dosa Hut")
    assert "srcset=" in h and "400w" in h and "800w" in h and "1600w" in h
    assert "sizes=" in h and "loading='lazy'" in h
    assert "width=" in h and "height=" in h          # intrinsic size: no layout shift
    assert h.startswith("<img src='/uploads/photos/")


def test_rendering_escapes_captions_and_names(listing):
    res = photos.ingest("restaurants", listing, "o@e.com", _png(), "image/png",
                        caption="A <script>alert(1)</script> \"caption\"")
    row = photos.get(res["id"])
    h = photos.img_html(row, alt="x")
    assert "<script>" not in h and "&lt;script&gt;" in h


def test_gallery_is_empty_for_a_listing_without_photos(listing):
    assert photos.gallery_html("restaurants", listing, "ZZTEST Photo Cafe") == ""


def test_gallery_renders_published_photos_only(listing):
    a = photos.ingest("restaurants", listing, "o@e.com", _png(900, 700), "image/png")["id"]
    photos.ingest("restaurants", listing, "o@e.com", _png(900, 700, (1, 1, 1)), "image/png")
    photos.publish(a)
    g = photos.gallery_html("restaurants", listing, "ZZTEST Photo Cafe")
    assert g.count("<figure") == 1
    assert "1 photo of" in g and "owner" in g.lower()


def test_captions_are_length_capped(listing):
    res = photos.ingest("restaurants", listing, "o@e.com", _png(), "image/png", caption="x" * 500)
    assert len(photos.get(res["id"])["caption"]) <= 200


# ------------------------------------------------------------------ promotion to photo_url
def test_publishing_promotes_the_photo_to_the_listing(listing):
    """Cards, share images and LocalBusiness.image all read photo_url, so promoting the owner photo
    into that column is what makes it appear everywhere without a per-card query."""
    pid = photos.ingest("restaurants", listing, "o@e.com", _png(1800, 1200), "image/png")["id"]
    assert not (verticals.get_record("restaurants", listing) or {}).get("photo_url")
    photos.publish(pid)
    url = (verticals.get_record("restaurants", listing) or {}).get("photo_url")
    assert url and url.startswith("/uploads/photos/") and photos.is_owner_photo(url)


def test_removing_the_last_photo_clears_the_promotion(listing):
    pid = photos.ingest("restaurants", listing, "o@e.com", _png(), "image/png")["id"]
    photos.publish(pid)
    photos.remove(pid, "o@e.com")
    assert not (verticals.get_record("restaurants", listing) or {}).get("photo_url")


def test_clearing_never_discards_a_scraped_photo(listing):
    """Only a URL we promoted is cleared; an enrichment photo must survive."""
    scraped = "https://cdn.example.com/from-their-website.jpg"
    db.execute("UPDATE restaurants SET photo_url=%s WHERE id=%s", (scraped, listing))
    pid = photos.ingest("restaurants", listing, "o@e.com", _png(), "image/png")["id"]
    photos.reject(pid, "no", "admin")            # never published, so nothing to promote
    assert (verticals.get_record("restaurants", listing) or {}).get("photo_url") == scraped


def test_the_next_photo_takes_over_when_the_first_goes(listing):
    a = photos.ingest("restaurants", listing, "o@e.com", _png(900, 700, (1, 1, 1)), "image/png")["id"]
    b = photos.ingest("restaurants", listing, "o@e.com", _png(900, 700, (2, 2, 2)), "image/png")["id"]
    photos.publish(a)
    photos.publish(b)
    first = (verticals.get_record("restaurants", listing) or {}).get("photo_url")
    photos.remove(a, "o@e.com")
    second = (verticals.get_record("restaurants", listing) or {}).get("photo_url")
    assert second and second != first            # the gallery's new first photo is promoted


def test_enrichment_will_not_overwrite_an_owner_photo():
    """The guard that stops the agent silently undoing an approval."""
    import inspect
    from indo_usa_mcp import web_enrich
    src = inspect.getsource(web_enrich)
    assert "photos.is_owner_photo(r.get(\"photo_url\"))" in src
    assert photos.is_owner_photo("/uploads/photos/abc_800.webp")
    assert not photos.is_owner_photo("https://cdn.example.com/x.jpg")
    assert not photos.is_owner_photo(None)


# ------------------------------------------------------------------ earned trust
def test_the_first_photo_from_an_unknown_owner_is_always_reviewed(listing):
    res = photos.ingest("restaurants", listing, "newcomer@e.com", _png(), "image/png")
    assert res["status"] == "pending" and not res["auto_published"]
    assert photos.owner_trust("newcomer@e.com")["reason"] == "no_approval_yet"


def test_once_approved_an_owner_skips_the_queue(listing):
    first = photos.ingest("restaurants", listing, "regular@e.com", _png(900, 700), "image/png")
    photos.publish(first["id"])
    assert photos.owner_trust("regular@e.com") == {
        "trusted": True, "published": 1, "rejected": 0, "reason": "earned"}

    second = photos.ingest("restaurants", listing, "regular@e.com", _png(900, 700, (2, 2, 2)),
                           "image/png")
    assert second["auto_published"] and second["status"] == "published"
    row = photos.get(second["id"])
    assert row["status"] == "published"
    assert photos.for_listing("restaurants", listing)[0]["id"] in (first["id"], second["id"])


def test_an_auto_published_photo_is_promoted_immediately(listing):
    first = photos.ingest("restaurants", listing, "regular2@e.com", _png(900, 700), "image/png")
    photos.publish(first["id"])
    photos.remove(first["id"], "regular2@e.com")          # clears the promotion
    second = photos.ingest("restaurants", listing, "regular2@e.com", _png(1800, 1200), "image/png")
    assert second["auto_published"]
    url = (verticals.get_record("restaurants", listing) or {}).get("photo_url")
    assert url and photos.is_owner_photo(url)


def test_trust_is_recorded_as_auto_in_the_audit_trail(listing):
    first = photos.ingest("restaurants", listing, "audit@e.com", _png(900, 700), "image/png")
    photos.publish(first["id"], "admin")
    second = photos.ingest("restaurants", listing, "audit@e.com", _png(900, 700, (3, 3, 3)),
                           "image/png")
    live = {r["id"]: r for r in photos.recent_published(50)}
    assert live[second["id"]]["reviewed_by"].startswith("auto:")
    assert live[first["id"]]["reviewed_by"] == "admin"
    assert second["id"] in {r["id"] for r in photos.recent_published(50, auto_only=True)}
    assert first["id"] not in {r["id"] for r in photos.recent_published(50, auto_only=True)}


def test_one_rejection_revokes_trust(listing):
    ok = photos.ingest("restaurants", listing, "slip@e.com", _png(900, 700), "image/png")
    photos.publish(ok["id"])
    bad = photos.ingest("restaurants", listing, "slip@e.com", _png(900, 700, (4, 4, 4)),
                        "image/png")
    assert bad["auto_published"]                           # trusted at this point
    photos.reject(bad["id"], "not this business", "admin")  # a takedown revokes it

    t = photos.owner_trust("slip@e.com")
    assert t["trusted"] is False and t["reason"] == "rejected_before"
    again = photos.ingest("restaurants", listing, "slip@e.com", _png(900, 700, (5, 5, 5)),
                          "image/png")
    assert again["status"] == "pending"


def test_trust_is_per_owner_not_per_listing(listing):
    """An owner may run several listings; being vetted once is enough."""
    other = verticals.create_record(
        "restaurants", {"name": "ZZTEST Photo Cafe Two", "city": "Zzphoto", "state": "TX"},
        source="test")["id"]
    try:
        first = photos.ingest("restaurants", listing, "multi@e.com", _png(900, 700), "image/png")
        photos.publish(first["id"])
        res = photos.ingest("restaurants", other, "multi@e.com", _png(900, 700), "image/png")
        assert res["auto_published"]
    finally:
        db.execute("DELETE FROM listing_photos WHERE listing_id=%s", (other,))
        db.execute("DELETE FROM restaurants WHERE id=%s", (other,))


def test_trust_matching_ignores_email_case(listing):
    first = photos.ingest("restaurants", listing, "Case@E.com", _png(900, 700), "image/png")
    photos.publish(first["id"])
    assert photos.owner_trust("case@e.com")["trusted"]
    assert photos.ingest("restaurants", listing, "CASE@e.COM", _png(900, 700, (6, 6, 6)),
                         "image/png")["auto_published"]


def test_the_kill_switch_holds_everything(listing, monkeypatch):
    first = photos.ingest("restaurants", listing, "killsw@e.com", _png(900, 700), "image/png")
    photos.publish(first["id"])
    assert photos.owner_trust("killsw@e.com")["trusted"]

    monkeypatch.setattr(settings, "photo_auto_publish", False)
    t = photos.owner_trust("killsw@e.com")
    assert t["trusted"] is False and t["reason"] == "auto_publish_off"
    assert photos.ingest("restaurants", listing, "killsw@e.com", _png(900, 700, (7, 7, 7)),
                         "image/png")["status"] == "pending"


def test_tidying_your_own_gallery_does_not_cost_you_trust(listing):
    """Removing a photo is housekeeping, not misbehaviour — only a rejection revokes trust."""
    first = photos.ingest("restaurants", listing, "tidy@e.com", _png(900, 700), "image/png")
    photos.publish(first["id"])
    photos.remove(first["id"], "tidy@e.com")
    t = photos.owner_trust("tidy@e.com")
    assert t["trusted"] and t["reason"] == "earned"


def test_deleting_a_pending_photo_does_not_grant_trust(listing):
    """A photo nobody ever approved must not count as an approval."""
    res = photos.ingest("restaurants", listing, "sneaky@e.com", _png(900, 700), "image/png")
    photos.remove(res["id"], "sneaky@e.com")
    assert photos.owner_trust("sneaky@e.com") == {
        "trusted": False, "published": 0, "rejected": 0, "reason": "no_approval_yet"}
