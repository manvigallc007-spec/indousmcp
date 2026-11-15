"""Owner-uploaded listing photos: ingest, moderate, serve.

Why this exists
---------------
`photo_url` is only ever filled opportunistically by web-enrichment from a business's own website,
so most listings render as text. A directory whose entries have no picture reads as abandoned no
matter how good the data is — and photos are the one thing an owner can contribute that visibly
improves their own listing, which is what brings them back to the portal.

Zero budget, so storage is the VPS disk (same convention as ./backups and flyer uploads) and
resizing is Pillow, already a dependency. No CDN, no image service.

Safety decisions, all deliberate
  * **Derivatives only.** The upload is re-encoded to WebP at up to three widths and ONLY those are
    written. There is never a user-supplied file on disk to serve, which removes the whole class of
    "upload a .svg / polyglot and have the browser execute it".
  * **EXIF is dropped** by that same re-encode. Phone photos carry GPS: publishing a shop owner's
    home coordinates because they photographed a menu indoors would be a real harm.
  * **Pillow verifies the bytes are an image** before anything else, and a pixel ceiling guards
    against decompression bombs.
  * **Filenames are generated**, never taken from the upload, so path traversal is impossible.
  * **Nothing is public until an admin approves it** (`status='pending'`), and uploading requires a
    signed-in owner of that listing (enforced by web/portal.py).
"""

from __future__ import annotations

import hashlib
import io
import pathlib
import uuid
from typing import Any

from . import db
from .config import settings

# Only raster formats a browser renders as an image. Deliberately no SVG: it is a script carrier.
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}

# Widths we generate, smallest first. A source narrower than a width simply doesn't get it, so we
# never upscale and never claim a resolution we don't have.
WIDTHS = (400, 800, 1600)

# Decompression-bomb ceiling: a 64MP "image" can be a few KB on disk and gigabytes decoded.
MAX_PIXELS = 50_000_000

MAX_PER_LISTING = 8          # a gallery, not a photo host
_QUALITY = 82                # WebP quality: visually clean at roughly a third of the JPEG bytes
_SUBDIR = "photos"


def enabled() -> bool:
    """Uploads need somewhere to write and Pillow present. Both are normally true."""
    try:
        import PIL  # noqa: F401
    except Exception:
        return False
    return bool(settings.upload_dir)


def _dir() -> pathlib.Path:
    d = pathlib.Path(settings.upload_dir) / _SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


# ------------------------------------------------------------------------------- earned trust
# The queue exists to catch a bad first photo from someone unknown. Once an owner has had one
# approved, holding their later uploads is admin work for no safety gain -- so they skip it.
#
# Trust is per owner (they may run several listings), and it is REVOKED by a single rejection: an
# owner who has posted something we refused goes back to being reviewed, permanently. That is
# deliberately blunt, because the cost of re-reviewing is small and the cost of an unreviewed bad
# photo on a public page is not.
def owner_trust(owner_email: str) -> dict[str, Any]:
    """Whether this owner's uploads skip review, and the counts behind that decision."""
    row = db.query_one(
        # 'ever approved', not 'still live': removing your own photo is normal housekeeping and
        # must not cost you trust. reviewed_at is only set when a human or the trust rule
        # approved it, so a pending photo the owner deleted does not count.
        "SELECT count(*) FILTER (WHERE reviewed_at IS NOT NULL AND status <> 'rejected')"
        "         AS published,"
        "       count(*) FILTER (WHERE status='rejected') AS rejected "
        "FROM listing_photos WHERE lower(owner_email)=lower(%s)",
        ((owner_email or "").strip(),))
    published = int((row or {}).get("published") or 0)
    rejected = int((row or {}).get("rejected") or 0)
    trusted = bool(settings.photo_auto_publish and published >= 1 and rejected == 0)
    return {"trusted": trusted, "published": published, "rejected": rejected,
            "reason": ("auto_publish_off" if not settings.photo_auto_publish
                       else "rejected_before" if rejected
                       else "no_approval_yet" if not published
                       else "earned")}


# --------------------------------------------------------------------------------------- ingest
def _decode(data: bytes):
    """Return an upright RGB image, or raise ValueError if these bytes aren't a usable image.

    Pillow's verify() consumes the file object, so the image has to be opened twice — that is the
    documented way to check an image without trusting it.
    """
    from PIL import Image, ImageOps

    # Open is lazy — it reads the header, so .size is known without decoding the pixels. Pillow's
    # own bomb guard can fire here too; it means the same thing as our ceiling, so it maps to the
    # same error rather than being reported as a corrupt file.
    try:
        img = Image.open(io.BytesIO(data))
    except Image.DecompressionBombError as exc:
        raise ValueError("image_too_large") from exc
    except Exception as exc:
        raise ValueError("not_an_image") from exc

    if (img.width * img.height) > MAX_PIXELS:
        raise ValueError("image_too_large")
    if img.width < 200 or img.height < 200:
        raise ValueError("image_too_small")

    # Structural check on a throwaway handle: verify() leaves the object it was called on unusable,
    # which is why Pillow's docs say to reopen afterwards. Doing it second means a bomb is reported
    # as a bomb instead of as a decode failure.
    try:
        Image.open(io.BytesIO(data)).verify()
    except Image.DecompressionBombError as exc:
        raise ValueError("image_too_large") from exc
    except Exception as exc:
        raise ValueError("not_an_image") from exc

    try:
        img = ImageOps.exif_transpose(img)       # honour the orientation tag before dropping EXIF
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.load()                               # force the decode now, so a truncated file fails here
    except Image.DecompressionBombError as exc:
        raise ValueError("image_too_large") from exc
    except Exception as exc:
        raise ValueError("not_an_image") from exc
    return img


def ingest(vertical: str, listing_id: int, owner_email: str, data: bytes, mime_type: str,
           *, caption: str = "") -> dict[str, Any]:
    """Validate, re-encode and store an upload as a pending photo.

    Returns {"ok": True, "id": ...} or {"ok": False, "error": <code>}. Never raises: the callers are
    web handlers, and a malformed upload is an expected input, not an exception.
    """
    if not enabled():
        return {"ok": False, "error": "unavailable"}
    if (mime_type or "").split(";")[0].strip().lower() not in ALLOWED_MIME:
        return {"ok": False, "error": "unsupported_type"}
    if not data:
        return {"ok": False, "error": "empty"}
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        return {"ok": False, "error": "file_too_large"}

    owner = (owner_email or "").strip().lower()
    if count_for_listing(vertical, listing_id) >= MAX_PER_LISTING:
        return {"ok": False, "error": "too_many"}

    digest = hashlib.sha256(data).hexdigest()
    if db.query_one("SELECT id FROM listing_photos WHERE vertical=%s AND listing_id=%s AND sha256=%s",
                    (vertical, listing_id, digest)):
        return {"ok": False, "error": "duplicate"}

    try:
        img = _decode(data)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:
        return {"ok": False, "error": "not_an_image"}

    stem = uuid.uuid4().hex                      # generated, so the upload's own name never matters
    out: dict[str, str] = {}
    stored = 0
    try:
        for w in WIDTHS:
            if w > img.width and w != WIDTHS[0]:
                continue                         # never upscale
            scale = min(w, img.width) / img.width
            size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
            resized = img.resize(size, _resample())
            buf = io.BytesIO()
            # No exif/icc passed through: this re-encode is what strips the GPS tags.
            resized.save(buf, format="WEBP", quality=_QUALITY, method=4)
            name = f"{stem}_{w}.webp"
            (_dir() / name).write_bytes(buf.getvalue())
            out[w] = f"{_SUBDIR}/{name}"
            stored += buf.getbuffer().nbytes
    except Exception:
        _unlink([f"{_SUBDIR}/{stem}_{w}.webp" for w in WIDTHS])
        return {"ok": False, "error": "encode_failed"}

    widest = max(out)
    trust = owner_trust(owner)
    status = "published" if trust["trusted"] else "pending"
    row = db.query_one(
        "INSERT INTO listing_photos (vertical, listing_id, owner_email, path_sm, path_md, path_lg,"
        " width, height, caption, sha256, bytes_stored, status, reviewed_at, reviewed_by,"
        " sort_order) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
        " CASE WHEN %s = 'published' THEN now() END, %s,"
        " COALESCE((SELECT max(sort_order)+1 FROM listing_photos"
        "           WHERE vertical=%s AND listing_id=%s), 0)) RETURNING id",
        (vertical, listing_id, owner,
         out.get(400) or out[widest], out.get(800) or out[widest], out.get(1600),
         min(widest, img.width), round(img.height * min(widest, img.width) / img.width),
         (caption or "").strip()[:200] or None, digest, stored, status, status,
         "auto:trusted-owner" if status == "published" else None,
         vertical, listing_id))
    if status == "published":
        sync_primary(vertical, listing_id)
    return {"ok": True, "id": row["id"], "widths": sorted(out), "status": status,
            "auto_published": status == "published"}


def _resample():
    from PIL import Image
    return Image.Resampling.LANCZOS


def _unlink(rel_paths) -> None:
    base = pathlib.Path(settings.upload_dir)
    for rel in rel_paths:
        try:
            (base / rel).unlink(missing_ok=True)
        except Exception:
            pass


# --------------------------------------------------------------------------------------- reads
_COLS = ("id, vertical, listing_id, owner_email, status, path_sm, path_md, path_lg, width, height,"
         " caption, sort_order, created_at, reject_reason")


def for_listing(vertical: str, listing_id: int, *, status: str = "published") -> list[dict]:
    """Photos for one listing. `status=''` returns every state (the owner's own view)."""
    sql = f"SELECT {_COLS} FROM listing_photos WHERE vertical=%s AND listing_id=%s"
    args: list[Any] = [vertical, listing_id]
    if status:
        sql += " AND status=%s"
        args.append(status)
    else:
        sql += " AND status <> 'removed'"
    return db.query(sql + " ORDER BY sort_order, id", tuple(args))


def primary(vertical: str, listing_id: int) -> dict | None:
    """The photo to use as the listing's main image, if any owner photo is published."""
    rows = for_listing(vertical, listing_id)
    return rows[0] if rows else None


def count_for_listing(vertical: str, listing_id: int) -> int:
    row = db.query_one("SELECT count(*) AS n FROM listing_photos "
                       "WHERE vertical=%s AND listing_id=%s AND status <> 'removed'",
                       (vertical, listing_id))
    return int(row["n"]) if row else 0


def pending(limit: int = 60) -> list[dict]:
    return db.query(
        f"SELECT {_COLS} FROM listing_photos WHERE status='pending' "
        "ORDER BY created_at LIMIT %s", (limit,))


def pending_count() -> int:
    row = db.query_one("SELECT count(*) AS n FROM listing_photos WHERE status='pending'")
    return int(row["n"]) if row else 0


def get(photo_id: int) -> dict | None:
    return db.query_one(f"SELECT {_COLS}, sha256 FROM listing_photos WHERE id=%s", (photo_id,))


def recent_published(limit: int = 24, *, auto_only: bool = False) -> list[dict]:
    """Recently live photos, newest first — the audit trail for anything that skipped the queue.

    Auto-publishing without somewhere to see the result would mean trusting owners with no way to
    notice when that trust was misplaced.
    """
    sql = (f"SELECT {_COLS}, reviewed_by FROM listing_photos WHERE status='published'")
    if auto_only:
        # '%%' because psycopg parses a bare % in the SQL as one of its own placeholders.
        sql += " AND reviewed_by LIKE 'auto:%%'"
    return db.query(sql + " ORDER BY COALESCE(reviewed_at, created_at) DESC LIMIT %s", (limit,))


# --------------------------------------------------------------------------------- moderation
def publish(photo_id: int, reviewer: str = "admin") -> dict[str, Any]:
    db.execute("UPDATE listing_photos SET status='published', reviewed_at=now(), reviewed_by=%s,"
               " reject_reason=NULL WHERE id=%s AND status <> 'removed'", (reviewer, photo_id))
    row = get(photo_id)
    if row:
        sync_primary(row["vertical"], row["listing_id"])
    return {"ok": True}


def sync_primary(vertical: str, listing_id: int) -> str | None:
    """Promote the listing's first published owner photo into its `photo_url` column.

    Cards, OG/share images and LocalBusiness.image all read `photo_url`, so this is what makes an
    owner photo show up on every existing surface without adding a query per card. An owner's own
    picture also outranks whatever web-enrichment scraped off their website.

    Returns the URL now in place, or None when the listing has no published photo (in which case
    any previously promoted URL is cleared so a removed photo stops being referenced).
    """
    from . import verticals

    try:
        table = verticals._table(vertical)
    except Exception:
        return None
    top = primary(vertical, listing_id)
    url = _url(top["path_lg"] or top["path_md"]) if top else None
    try:
        if url:
            db.execute(f"UPDATE {table} SET photo_url=%s WHERE id=%s", (url, listing_id))
        else:
            # only clear what WE promoted; never discard an enrichment photo
            db.execute(f"UPDATE {table} SET photo_url=NULL "
                       f"WHERE id=%s AND photo_url LIKE %s", (listing_id, f"/uploads/{_SUBDIR}/%"))
    except Exception:
        return None
    return url


def is_owner_photo(url: str | None) -> bool:
    """True when a listing's photo_url points at an owner upload rather than a scraped image."""
    return bool(url) and str(url).startswith(f"/uploads/{_SUBDIR}/")


def reject(photo_id: int, reason: str = "", reviewer: str = "admin") -> dict[str, Any]:
    """Reject and delete the files: a rejected photo is usually wrong or unwanted, and keeping
    someone's image on disk after refusing to show it serves no purpose."""
    row = get(photo_id)
    if row:
        _unlink([p for p in (row["path_sm"], row["path_md"], row["path_lg"]) if p])
    db.execute("UPDATE listing_photos SET status='rejected', reviewed_at=now(), reviewed_by=%s,"
               " reject_reason=%s WHERE id=%s", (reviewer, (reason or "").strip()[:200] or None,
                                                 photo_id))
    if row:
        sync_primary(row["vertical"], row["listing_id"])
    return {"ok": True}


def remove(photo_id: int, owner_email: str) -> dict[str, Any]:
    """Owner takes their own photo down. Scoped by owner_email so one owner cannot touch another's."""
    row = db.query_one("SELECT path_sm, path_md, path_lg, vertical, listing_id FROM listing_photos "
                       "WHERE id=%s AND lower(owner_email)=lower(%s)",
                       (photo_id, (owner_email or "").strip()))
    if not row:
        return {"ok": False, "error": "not_found"}
    _unlink([p for p in (row["path_sm"], row["path_md"], row["path_lg"]) if p])
    db.execute("UPDATE listing_photos SET status='removed' WHERE id=%s", (photo_id,))
    full = get(photo_id)
    if full:
        sync_primary(full["vertical"], full["listing_id"])
    return {"ok": True}


# ------------------------------------------------------------------------------------ rendering
def _url(rel: str | None) -> str:
    return f"/uploads/{rel}" if rel else ""


def img_html(photo: dict, *, alt: str, sizes: str = "(max-width:700px) 100vw, 700px",
             cls: str = "", style: str = "", lazy: bool = True) -> str:
    """A responsive <img> for a photo row: the browser picks the width it actually needs.

    Without srcset a phone downloads the 1600px file to paint a 360px card, which is the whole
    reason for generating derivatives.
    """
    import html as _h

    srcset = ", ".join(
        f"{_url(p)} {w}w" for p, w in ((photo.get("path_sm"), 400), (photo.get("path_md"), 800),
                                       (photo.get("path_lg"), 1600)) if p)
    cap = photo.get("caption") or alt
    return (f"<img src='{_url(photo.get('path_md') or photo.get('path_sm'))}'"
            + (f" srcset='{srcset}'" if srcset else "")
            + f" sizes='{_h.escape(sizes, quote=True)}'"
            + f" alt='{_h.escape(cap or '', quote=True)}'"
            + (f" class='{cls}'" if cls else "")
            + (f" style='{style}'" if style else "")
            + (" loading='lazy' decoding='async'" if lazy else "")
            + (f" width='{photo['width']}' height='{photo['height']}'"
               if photo.get("width") and photo.get("height") else "")
            + " onerror='this.remove()'>")


def gallery_html(vertical: str, listing_id: int, name: str) -> str:
    """The published photos for a listing, as a horizontally scrollable strip. '' when there are
    none, so the listing page is unchanged for listings without owner photos."""
    rows = for_listing(vertical, listing_id)
    if not rows:
        return ""
    import html as _h

    shots = "".join(
        f"<figure class='lp-shot'>{img_html(r, alt=name, sizes='(max-width:700px) 86vw, 420px')}"
        + (f"<figcaption>{_h.escape(r['caption'])}</figcaption>" if r.get("caption") else "")
        + "</figure>" for r in rows)
    label = "photo" if len(rows) == 1 else "photos"
    return (f"<section class='lp-gal' aria-label='{len(rows)} {label} of {_h.escape(name)}'>"
            f"{shots}</section>"
            "<p class='lp-credit'>Photos supplied by the owner · "
            "<a href='/contact'>report a problem</a></p>")


CSS = """
 .lp-gal{display:flex;gap:10px;overflow-x:auto;scroll-snap-type:x mandatory;margin:10px 0 2px;
   -webkit-overflow-scrolling:touch;scrollbar-width:none;padding-bottom:2px}
 .lp-gal::-webkit-scrollbar{display:none}
 .lp-shot{flex:0 0 auto;margin:0;max-width:86vw;scroll-snap-align:start}
 .lp-shot img{display:block;height:230px;width:auto;max-width:none;border-radius:var(--r-lg);
   background:var(--panel-2);object-fit:cover}
 .lp-shot figcaption{color:var(--muted);font-size:12.5px;margin-top:5px;max-width:420px}
 .lp-credit{color:var(--faint);font-size:12px;margin:6px 0 14px}
 @media(max-width:700px){.lp-shot img{height:190px}}
"""
