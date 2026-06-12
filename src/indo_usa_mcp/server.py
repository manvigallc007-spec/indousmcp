"""FastMCP server exposing the Phase-1 restaurant capabilities.

Run with: python -m indo_usa_mcp.server   (stdio transport)
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from . import queries
from .config import settings
from .pipeline import feedback, outreach
from .temples import queries as temple_queries

mcp = FastMCP("indo-usa-diaspora", host=settings.mcp_host, port=settings.mcp_port)


@mcp.tool()
def get_indian_restaurants(
    lat: float | None = None,
    lng: float | None = None,
    radius_miles: float = 10.0,
    city: str | None = None,
    state: str | None = None,
    region_tag: str | None = None,
    dietary_tags: list[str] | None = None,
    featured_only: bool = False,
    limit: int = 25,
) -> dict[str, Any]:
    """Find Indian restaurants by location and/or filters.

    Provide either a point (`lat`+`lng`, optionally `radius_miles`) or `city`/`state`.
    Optional filters: `region_tag` (e.g. "Gujarati", "South Indian"), `dietary_tags`
    (any of "vegetarian", "vegan", "halal", "jain"), and `featured_only`.

    Returns a list of records each with metadata, a `confidence_score` (0-1), an
    `is_featured` flag, and `distance_miles` when a point was supplied.
    """
    return queries.get_indian_restaurants(
        lat=lat,
        lng=lng,
        radius_miles=radius_miles,
        city=city,
        state=state,
        region_tag=region_tag,
        dietary_tags=dietary_tags,
        featured_only=featured_only,
        limit=limit,
    )


@mcp.tool()
def get_restaurant_details(restaurant_id: int) -> dict[str, Any]:
    """Fetch the full canonical record for one restaurant, plus its version history."""
    record = queries.get_restaurant_details(restaurant_id)
    if record is None:
        return {"error": "not_found", "restaurant_id": restaurant_id}
    return record


@mcp.tool()
def search_restaurants_by_text(
    query: str,
    city: str | None = None,
    state: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Free-text search over restaurant name/cuisine/region, ranked by relevance.

    Optionally constrain to a `city`/`state`. Featured listings are surfaced first.
    """
    return queries.search_restaurants_by_text(query, city=city, state=state, limit=limit)


@mcp.tool()
def find_unclaimed_restaurants(limit: int = 20, min_confidence: float = 0.5) -> dict[str, Any]:
    """List active, unclaimed restaurants that are eligible for claim outreach.

    Excludes restaurants with an open claim or contacted within the cooldown window.
    Each result is annotated with the chosen outreach `_channel` and a `_requires_human`
    flag (true for chains / featured / high-value targets that a person should handle).
    """
    rows = outreach.find_unclaimed(limit=limit, min_confidence=min_confidence)
    return {"count": len(rows), "results": rows}


@mcp.tool()
def draft_claim_outreach(limit: int = 20, min_confidence: float = 0.5) -> dict[str, Any]:
    """Generate claim links and personalized outreach drafts for unclaimed restaurants.

    Creates a single-use claim per restaurant and logs a draft message per the platform's
    anti-spam and no-impersonation guardrails. Messages are NOT auto-sent; high-value
    targets are flagged `requires_human`. Returns the drafted items for review/delivery.
    """
    return outreach.run_outreach(limit=limit, min_confidence=min_confidence)


@mcp.tool()
def submit_correction(restaurant_id: int, field: str, value: str, reason: str = "") -> dict[str, Any]:
    """Propose a correction to a restaurant field (agents/users reporting bad data).

    Correctable fields: phone, email, website, menu_url, address_full, city, state,
    region_tag, price_range, cuisine_type, festival_specials. The correction is stored and
    applied by the Feedback agent — automatically for unclaimed listings, or routed to a
    human for claimed/featured ones. Identity fields (name, coordinates) are not correctable.
    """
    return feedback.submit_correction(restaurant_id, field, value, reason=reason, source="agent")


# --------------------------------------------------------------- temples (Phase 2)
@mcp.tool()
def get_indian_temples(
    lat: float | None = None,
    lng: float | None = None,
    radius_miles: float = 15.0,
    city: str | None = None,
    state: str | None = None,
    religion: str | None = None,
    denomination: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Find Indian-American temples (Hindu/Sikh/Jain places of worship).

    Provide a point (`lat`+`lng`, optional `radius_miles`) or `city`/`state`. Filter by
    `religion` ("hindu", "sikh", "jain") or `denomination` (e.g. "swaminarayan"). Returns
    records with deity, region, hours, confidence and `distance_miles` when a point is given.
    """
    return temple_queries.get_indian_temples(
        lat=lat, lng=lng, radius_miles=radius_miles, city=city, state=state,
        religion=religion, denomination=denomination, limit=limit)


@mcp.tool()
def get_temple_details(temple_id: int) -> dict[str, Any]:
    """Full canonical record for one temple, plus its version history."""
    record = temple_queries.get_temple_details(temple_id)
    if record is None:
        return {"error": "not_found", "temple_id": temple_id}
    return record


@mcp.tool()
def search_temples_by_text(
    query: str, city: str | None = None, state: str | None = None, limit: int = 25,
) -> dict[str, Any]:
    """Free-text/semantic search over temples (name/deity/denomination/region)."""
    return temple_queries.search_temples_by_text(query, city=city, state=state, limit=limit)


def main() -> None:
    # stdio for local clients; streamable-http for a hosted service (see deploy/).
    if settings.mcp_transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport=settings.mcp_transport)


if __name__ == "__main__":
    main()
