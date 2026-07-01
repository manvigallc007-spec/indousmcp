"""Category grid: richer tiles that now include the non-directory verticals (movies + H-1B)."""

from starlette.testclient import TestClient

from indo_usa_mcp.web.app import app


def test_browse_grid_includes_movies_and_employers():
    r = TestClient(app).get("/browse")
    assert r.status_code == 200
    assert "catcard" in r.text and "bhero" in r.text        # tiles + hero band
    assert "Movies" in r.text and "/movies" in r.text
    assert "H-1B Sponsors" in r.text and "/employers" in r.text
    # a couple of the core verticals still render
    assert "Restaurants" in r.text and "Temples" in r.text
