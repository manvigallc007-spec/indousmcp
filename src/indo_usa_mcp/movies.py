"""Indian movies currently in US theaters — free, via The Movie Database (TMDB) API.

Time-sensitive content (not a geographic business listing), refreshed by the `movies` agent. We list
what's playing for Indian-language films and link out to buy tickets — per-theater showtimes aren't
available free/legally. Enable by setting TMDB_API_KEY (free, non-commercial). Attribution required:
"This product uses the TMDB API but is not endorsed or certified by TMDB."

The parsing functions are pure + unit-tested without network; refresh() does the HTTP + DB writes.
"""

from __future__ import annotations

import datetime
from typing import Any
from urllib.parse import quote

import httpx

from . import db
from .config import settings

_API = "https://api.themoviedb.org/3"
_IMG = "https://image.tmdb.org/t/p/w500"

# Indian languages we surface (TMDB original_language code -> display name).
_LANGS: dict[str, str] = {
    "hi": "Hindi", "te": "Telugu", "ta": "Tamil", "ml": "Malayalam", "kn": "Kannada",
    "pa": "Punjabi", "bn": "Bengali", "mr": "Marathi", "gu": "Gujarati",
}
# TMDB movie genre ids -> names (stable list).
_GENRES: dict[int, str] = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy", 80: "Crime",
    99: "Documentary", 18: "Drama", 10751: "Family", 14: "Fantasy", 36: "History",
    27: "Horror", 10402: "Music", 9648: "Mystery", 10749: "Romance", 878: "Sci-Fi",
    10770: "TV Movie", 53: "Thriller", 10752: "War", 37: "Western",
}


def enabled() -> bool:
    return bool((settings.tmdb_api_key or "").strip())


def ticket_url(title: str) -> str:
    """A 'find showtimes / buy tickets' search link (we can't fetch per-theater showtimes free)."""
    return "https://www.google.com/search?q=" + quote(f"{title} movie showtimes near me")


def parse_movie(m: dict) -> dict | None:
    """Pure: a TMDB discover/movie result -> our movie row. None if it lacks an id/title."""
    title = m.get("title") or m.get("original_title")
    if not m.get("id") or not title:
        return None
    return {
        "tmdb_id": int(m["id"]),
        "title": title,
        "original_title": m.get("original_title") or None,
        "language": _LANGS.get(m.get("original_language"), m.get("original_language")),
        "poster_url": (_IMG + m["poster_path"]) if m.get("poster_path") else None,
        "overview": (m.get("overview") or "")[:1000] or None,
        "release_date": (m.get("release_date") or "").strip() or None,
        "genres": [_GENRES[g] for g in (m.get("genre_ids") or []) if g in _GENRES],
        "popularity": float(m.get("popularity") or 0),
        "ticket_url": ticket_url(title),
    }


def _discover(lang: str, since: str, until: str) -> list[dict]:
    try:
        r = httpx.get(f"{_API}/discover/movie", timeout=12.0, params={
            "api_key": settings.tmdb_api_key.strip(), "with_original_language": lang,
            "region": "US", "sort_by": "popularity.desc", "include_adult": "false",
            "release_date.gte": since, "release_date.lte": until, "with_release_type": "2|3"})
        if r.status_code == 200:
            return r.json().get("results") or []
    except Exception:
        pass
    return []


def refresh(days_back: int = 45) -> dict[str, Any]:
    """Fetch Indian-language films released into US theaters in the last `days_back` days and upsert
    them as now_playing. Idempotent; no-op without a TMDB key."""
    if not enabled():
        return {"skipped": "no_tmdb_key"}
    today = datetime.date.today()
    since = (today - datetime.timedelta(days=days_back)).isoformat()
    until = (today + datetime.timedelta(days=7)).isoformat()
    seen: dict[int, dict] = {}
    for lang in _LANGS:
        for m in _discover(lang, since, until):
            row = parse_movie(m)
            if row:
                seen[row["tmdb_id"]] = row
    db.execute("UPDATE movies SET now_playing = false WHERE now_playing")   # clear the old set
    for row in seen.values():
        db.execute(
            "INSERT INTO movies (tmdb_id, title, original_title, language, poster_url, overview, "
            "release_date, genres, popularity, ticket_url, now_playing, fetched_at, updated_at) "
            "VALUES (%(tmdb_id)s,%(title)s,%(original_title)s,%(language)s,%(poster_url)s,"
            "%(overview)s,%(release_date)s,%(genres)s,%(popularity)s,%(ticket_url)s,true,now(),now()) "
            "ON CONFLICT (tmdb_id) DO UPDATE SET title=EXCLUDED.title, language=EXCLUDED.language, "
            "poster_url=EXCLUDED.poster_url, overview=EXCLUDED.overview, "
            "release_date=EXCLUDED.release_date, genres=EXCLUDED.genres, "
            "popularity=EXCLUDED.popularity, ticket_url=EXCLUDED.ticket_url, now_playing=true, "
            "fetched_at=now(), updated_at=now()", row)
    return {"fetched": len(seen)}


def list_in_theaters(language: str | None = None, limit: int = 60) -> list[dict]:
    where, params = ["now_playing"], []
    if language:
        where.append("LOWER(language) = LOWER(%s)")
        params.append(language)
    try:
        return db.query(
            f"SELECT tmdb_id, title, original_title, language, poster_url, overview, release_date, "
            f"genres, ticket_url FROM movies WHERE {' AND '.join(where)} "
            f"ORDER BY popularity DESC, release_date DESC NULLS LAST LIMIT %s", params + [limit])
    except Exception:
        return []


def languages_in_theaters() -> list[str]:
    try:
        return [r["language"] for r in db.query(
            "SELECT DISTINCT language FROM movies WHERE now_playing AND language IS NOT NULL "
            "ORDER BY 1")]
    except Exception:
        return []
