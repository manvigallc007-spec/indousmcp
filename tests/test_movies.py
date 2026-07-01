"""Movies vertical: TMDB parsing, ticket links, agent registration, and the /movies page.

Parsing is pure (no network); the page + list are DB-mocked."""

from starlette.testclient import TestClient

import indo_usa_mcp.movies as movies
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
