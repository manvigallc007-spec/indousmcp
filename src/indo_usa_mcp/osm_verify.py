"""Verify non-OSM listings against OpenStreetMap (confirm + enrich + raise trust).

The directory's primary scraper IS OpenStreetMap, but many listings arrive from OTHER sources —
IRS nonprofits, NPPES professionals, owner submissions, Socrata, the consulates seed. This module
cross-checks each of those against OSM near its coordinates: when a same-named POI sits within a
short radius, it's a second independent confirmation, so we

  * fill missing phone / website / hours / attribute-tags from OSM (never overwriting existing values),
  * bump `confidence_score` (feeds ranking via ranking.trust_score),
  * refresh `last_seen_at` (so the LifecycleAgent doesn't archive a good, real listing),
  * stamp `osm_verified_at`.

REWARD-ONLY: OSM *not* finding a place proves nothing (OSM coverage is partial), so a miss only
advances `osm_checked_at` and never penalizes. Structured like linkcheck.py: batch-select stale rows
by a cursor column, act, write the cursor, be polite. Free + zero-budget (public Overpass).
"""

from __future__ import annotations

import json
import time
from typing import Any

from . import db, embeddings, osm, verticals
from .osm import OverpassError
from .pipeline.clean import normalize_name

# Events are time-bound and agent-managed — not stable POIs to verify against OSM.
_VERTICALS = [v for v in verticals.VERTICALS if v != "events"]
_CONF_BUMP = 0.15   # an independent OSM confirmation is a real trust signal (capped at 1.0)


def _name_match(a: str, b: str) -> bool:
    """True when two place names are the same business: normalized equality, containment, or a
    strong token overlap (Jaccard >= 0.6). Deliberately strict so we never attach the WRONG nearby
    POI to a listing."""
    na, nb = normalize_name(a or ""), normalize_name(b or "")
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.6


def _match_element(name: str, elements: list[dict]) -> dict | None:
    """First OSM element whose name matches and isn't a non-India-diaspora homonym."""
    for el in elements:
        cand = (el.get("tags") or {}).get("name")
        if cand and not osm.is_excluded_name(cand) and _name_match(name, cand):
            return el
    return None


def verify_listings(limit_per_vertical: int = 30, max_age_days: int = 45) -> dict[str, Any]:
    """Verify a batch of non-OSM listings per vertical against OSM. Returns per-vertical counts."""
    out: dict[str, Any] = {}
    for v in _VERTICALS:
        t = verticals._table(v)
        cols = verticals._table_columns(t)
        if "osm_checked_at" not in cols:            # migration not applied yet -> skip safely
            continue
        rows = db.query(
            f"SELECT id, name, lat, lng, phone, website, tags, hours_json, confidence_score FROM {t} "
            f"WHERE deleted_at IS NULL AND is_active AND lat IS NOT NULL "
            f"AND coalesce(source_name,'') NOT LIKE 'osm%%' "
            f"AND (osm_checked_at IS NULL OR osm_checked_at < now() - (%s || ' days')::interval) "
            f"ORDER BY osm_checked_at NULLS FIRST, id LIMIT %s", (max_age_days, limit_per_vertical))
        checked = verified = enriched = 0
        for r in rows:
            try:
                elements = osm.nearby_named(r["lat"], r["lng"])
            except OverpassError:
                out[v] = {"checked": checked, "verified": verified, "enriched": enriched,
                          "stopped": "overpass_unavailable"}
                return _finish(out)                 # Overpass is down -> stop politely, retry later
            except Exception:
                continue                            # transient row-level issue -> leave cursor, retry

            el = _match_element(r["name"], elements)
            if el is None:                          # reward-only: a miss just advances the cursor
                db.execute(f"UPDATE {t} SET osm_checked_at = now() WHERE id = %s", (r["id"],))
                checked += 1
                time.sleep(1.0)
                continue

            info = osm.contact_from_tags(el.get("tags") or {})
            changed = _apply_match(t, cols, r, info)
            verified += 1
            enriched += 1 if changed else 0
            checked += 1
            time.sleep(1.0)                         # Overpass is heavy — space calls out
        out[v] = {"checked": checked, "verified": verified, "enriched": enriched}
    return _finish(out)


def _apply_match(table: str, cols: set[str], row: dict, info: dict) -> bool:
    """Fill-missing phone/website/hours + merge tags from OSM, bump confidence + freshness, stamp
    verified. Returns True if any listing content (phone/website/hours/tags) actually changed."""
    sets: list[str] = []
    params: list[Any] = []
    content_changed = False

    if "phone" in cols and not (row.get("phone") or "").strip() and info.get("phone"):
        sets.append("phone = %s"); params.append(info["phone"]); content_changed = True
    if "website" in cols and not (row.get("website") or "").strip() and info.get("website"):
        sets.append("website = %s"); params.append(info["website"]); content_changed = True
    if "hours_json" in cols and info.get("hours") and not row.get("hours_json"):
        # hours_json is JSONB everywhere; scrapers store the raw OSM opening_hours as {"raw": ...}
        sets.append("hours_json = %s::jsonb")
        params.append(json.dumps({"raw": info["hours"]})); content_changed = True
    if "tags" in cols and info.get("tags"):
        new = [tag for tag in info["tags"] if tag not in set(row.get("tags") or [])]
        if new:
            # union-merge + dedup in SQL (tags is text[] across every vertical)
            sets.append("tags = (SELECT ARRAY(SELECT DISTINCT unnest("
                        "COALESCE(tags, '{}'::text[]) || %s::text[])))")
            params.append(list(info["tags"])); content_changed = True

    sets.append("confidence_score = LEAST(1.0, COALESCE(confidence_score, 0.5) + %s)")
    params.append(_CONF_BUMP)
    sets.append("last_seen_at = now()")
    if "osm_verified_at" in cols:
        sets.append("osm_verified_at = now()")
    sets.append("osm_checked_at = now()")
    if "updated_at" in cols:
        sets.append("updated_at = now()")
    db.execute(f"UPDATE {table} SET {', '.join(sets)} WHERE id = %s", params + [row["id"]])

    # Re-embed from the FULL updated record (slim SELECT lacks description/facets -> would degrade).
    if content_changed and embeddings.enabled():
        full = db.query_one(f"SELECT * FROM {table} WHERE id = %s", (row["id"],))
        if full:
            db.execute(f"UPDATE {table} SET embedding = %s::vector WHERE id = %s",
                       (embeddings.to_vector_literal(embeddings.embed(embeddings.text_for(full))),
                        row["id"]))
    return content_changed


def _finish(out: dict[str, Any]) -> dict[str, Any]:
    tot = {"checked": 0, "verified": 0, "enriched": 0}
    for v in out.values():
        for k in tot:
            tot[k] += v.get(k, 0)
    out["_total"] = tot
    return out
