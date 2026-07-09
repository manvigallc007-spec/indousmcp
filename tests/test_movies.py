"""Movies vertical: TMDB parsing, ticket links, agent registration, and the /movies page.

Parsing is pure (no network); the page + list are DB-mocked."""

from starlette.testclient import TestClient

import indo_usa_mcp.movies as movies
from indo_usa_mcp import db
from indo_usa_mcp.web import landing
from indo_usa_mcp.web.app import app


def test_parse_movie_maps_fields():
    m = {"id": 12345, "title": "RRR 2", "original_title": "RRR 2", "original_language": "te",
         "poster_path": "/abc.jpg", "overview": "An epic.", "release_date": "2026-06-12",
         "genre_ids": [28, 18, 99999], "popularity": 87.4}
    row = movies.parse_movie(m)
    assert row["tmdb_id"] == 12345 and row["title"] == "RRR 2"
    assert row["language"] == "Telugu"                               # te -> Telugu
    assert row["poster_url"] == "https://image.tmdb.org/t/p/w500/abc.jpg"
    assert row["genres"] == ["Action", "Drama"]                      # unknown id dropped
    assert row["release_date"] == "2026-06-12"
    assert "showtimes" in row["ticket_url"] and "RRR" in row["ticket_url"]


def test_parse_movie_requires_id_and_title():
    assert movies.parse_movie({"title": "No id"}) is None
    assert movies.parse_movie({"id": 1}) is None


def test_refresh_noop_without_key(monkeypatch):
    monkeypatch.setattr(movies.settings, "tmdb_api_key", "")
    assert movies.refresh() == {"skipped": "no_tmdb_key"}
    assert movies.enabled() is False


def test_movies_agent_registered():
    from indo_usa_mcp.agents import AGENTS
    assert "movies" in AGENTS


def test_movies_page_renders(monkeypatch):
    fake = [{"tmdb_id": 1, "title": "Jawan 2", "original_title": "Jawan 2", "language": "Hindi",
             "poster_url": "https://img/p.jpg", "overview": "Action.", "release_date": "2026-06-10",
             "genres": ["Action"], "ticket_url": "https://www.google.com/search?q=Jawan+2+showtimes"}]
    monkeypatch.setattr(movies, "list_in_theaters", lambda language=None, limit=60: fake)
    monkeypatch.setattr(movies, "languages_in_theaters", lambda: ["Hindi", "Telugu"])
    r = TestClient(app).get("/movies")
    assert r.status_code == 200
    assert "Jawan 2" in r.text
    assert "Find showtimes" in r.text
    assert "https://img/p.jpg" in r.text          # poster
    assert "TMDB" in r.text                        # attribution


def test_movies_page_empty(monkeypatch):
    monkeypatch.setattr(movies, "list_in_theaters", lambda language=None, limit=60: [])
    monkeypatch.setattr(movies, "languages_in_theaters", lambda: [])
    r = TestClient(app).get("/movies")
    assert r.status_code == 200
    assert "No Indian movies listed" in r.text


# --- chat integration: movie intent routes to the movies table (not the place directory) ---
import indo_usa_mcp.assistant as a


def test_is_movie_query():
    assert a._is_movie_query("what telugu movies are playing")
    assert a._is_movie_query("any new films in theaters?")
    assert a._is_movie_query("cinema showtimes")
    assert not a._is_movie_query("biryani near me")
    assert not a._is_movie_query("indian grocery in plano")


def test_movie_language_detection():
    assert a._movie_language("new telugu movies") == "Telugu"
    assert a._movie_language("bollywood films") == "Hindi"
    assert a._movie_language("kollywood") == "Tamil"
    assert a._movie_language("movies playing") is None


def test_movies_reply_builds_cards(monkeypatch):
    fake = [{"title": "RRR 2", "overview": "Epic.", "poster_url": "http://img/p.jpg",
             "ticket_url": "http://tix", "language": "Telugu", "release_date": "2026-06-01",
             "genres": ["Action"]}]
    monkeypatch.setattr(movies, "list_in_theaters", lambda language=None, limit=12: fake)
    out = a._movies_reply("telugu movies", {})
    assert out["provider"] == "movies" and len(out["cards"]) == 1
    c = out["cards"][0]
    assert c["name"] == "RRR 2" and c["vertical"] == "movies"
    assert c["photo_url"] == "http://img/p.jpg" and c["website"] == "http://tix"
    assert "Telugu" in c["features"] and "2026" in c["features"]


def test_movies_reply_empty(monkeypatch):
    monkeypatch.setattr(movies, "list_in_theaters", lambda language=None, limit=12: [])
    out = a._movies_reply("tamil movies", {})
    assert out["cards"] == [] and "Tamil" in out["reply"]


# --- admin moderation: pause/suspend + soft-delete + scoped edit ---
_ZZ_TMDB = 999900001


def _seed_movie(**over):
    db.execute("DELETE FROM movies WHERE tmdb_id = %s", (_ZZ_TMDB,))
    data = {"tmdb_id": _ZZ_TMDB, "title": "ZZTEST Movie", "language": "Telugu", "now_playing": True}
    data.update(over)
    row = db.query_one(
        "INSERT INTO movies (tmdb_id, title, language, now_playing) VALUES (%(tmdb_id)s,%(title)s,"
        "%(language)s,%(now_playing)s) RETURNING id", data)
    return row["id"]


def test_movies_set_active_and_deleted_roundtrip():
    mid = _seed_movie()
    try:
        m = movies.get_movie(mid)
        assert m["is_active"] is True and m["deleted_at"] is None
        movies.set_active(mid, False)
        assert movies.get_movie(mid)["is_active"] is False
        movies.set_active(mid, True)
        assert movies.get_movie(mid)["is_active"] is True
        movies.set_deleted(mid, True)
        assert movies.get_movie(mid)["deleted_at"] is not None
        movies.set_deleted(mid, False)
        assert movies.get_movie(mid)["deleted_at"] is None
    finally:
        db.execute("DELETE FROM movies WHERE id = %s", (mid,))


def test_movies_apply_edits_ignores_disallowed_fields():
    mid = _seed_movie()
    try:
        out = movies.apply_edits(mid, {"title": "New Title", "tmdb_id": 1, "now_playing": False})
        assert out["fields"] == ["title"]
        m = movies.get_movie(mid)
        assert m["title"] == "New Title" and m["tmdb_id"] == _ZZ_TMDB and m["now_playing"] is True
    finally:
        db.execute("DELETE FROM movies WHERE id = %s", (mid,))


def test_list_in_theaters_excludes_paused():
    mid = _seed_movie(title="ZZTEST Paused Movie")
    try:
        assert any(r["tmdb_id"] == _ZZ_TMDB for r in movies.list_in_theaters(limit=500))
        movies.set_active(mid, False)
        assert not any(r["tmdb_id"] == _ZZ_TMDB for r in movies.list_in_theaters(limit=500))
        movies.set_active(mid, True)
        assert any(r["tmdb_id"] == _ZZ_TMDB for r in movies.list_in_theaters(limit=500))
    finally:
        db.execute("DELETE FROM movies WHERE id = %s", (mid,))


def test_refresh_does_not_reset_pause(monkeypatch):
    # Regression: refresh()'s ON CONFLICT upsert must not clobber the admin pause flag -- only
    # now_playing/data-driven columns are in its SET list.
    mid = _seed_movie()
    movies.set_active(mid, False)
    try:
        monkeypatch.setattr(movies.settings, "tmdb_api_key", "fake-key")
        monkeypatch.setattr(movies, "_discover", lambda lang, since, until: (
            [{"id": _ZZ_TMDB, "title": "ZZTEST Movie", "original_language": "te"}]
            if lang == "te" else []))
        movies.refresh()
        assert movies.get_movie(mid)["is_active"] is False
    finally:
        db.execute("DELETE FROM movies WHERE id = %s", (mid,))


def test_reply_routes_movie_query(monkeypatch):
    fake = [{"title": "Jawan 2", "overview": "", "poster_url": None, "ticket_url": "http://t",
             "language": "Hindi", "release_date": None, "genres": []}]
    monkeypatch.setattr(a, "_english", lambda text, filters: text)   # no translate/network
    monkeypatch.setattr(movies, "list_in_theaters", lambda language=None, limit=12: fake)
    out = a.reply([{"role": "user", "content": "what hindi movies are in theaters"}],
                  filters={"lang": "en"})
    assert out["provider"] == "movies"
    assert out["cards"][0]["name"] == "Jawan 2"
