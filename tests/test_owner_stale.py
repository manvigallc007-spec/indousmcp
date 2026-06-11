"""Tests for owner-edit whitelist and management routes (no DB)."""

from indo_usa_mcp.pipeline import ingest
from indo_usa_mcp.web import app


def test_owner_editable_excludes_identity_and_internal_fields():
    for forbidden in ("name", "lat", "lng", "natural_key", "confidence_score",
                      "is_featured", "is_claimed", "version", "source_name"):
        assert forbidden not in ingest.OWNER_EDITABLE
    for allowed in ("phone", "email", "website", "hours_json", "dietary_tags", "price_range"):
        assert allowed in ingest.OWNER_EDITABLE


def test_manage_routes_registered():
    paths = {(r.path, tuple(sorted(r.methods - {"HEAD"}))) for r in app.routes}
    assert ("/manage", ("GET",)) in paths
    assert ("/manage", ("POST",)) in paths
