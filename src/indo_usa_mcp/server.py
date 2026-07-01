"""FastMCP server exposing the Phase-1 restaurant capabilities.

Run with: python -m indo_usa_mcp.server   (stdio transport)
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from . import queries, reviews, verticals
from .apparel import queries as apparel_queries
from .community import queries as community_queries
from .config import settings
from .events import queries as event_queries
from .groceries import queries as grocery_queries
from .pipeline import feedback, outreach
from .professionals import queries as professional_queries
from .salons import queries as salon_queries
from .services import queries as service_queries
from .studios import queries as studio_queries
from .sweets import queries as sweets_queries
from .temples import queries as temple_queries
from .legal import queries as legal_queries
from .education import queries as education_queries
from .realestate import queries as realestate_queries
from .finance import queries as finance_queries

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
    tag: str | None = None,
    open_now: bool = False,
    featured_only: bool = False,
    limit: int = 25,
) -> dict[str, Any]:
    """Find Indian restaurants by location and/or filters.

    Provide either a point (`lat`+`lng`, optionally `radius_miles`) or `city`/`state`.
    Optional filters: `region_tag` (e.g. "Gujarati", "South Indian"), `dietary_tags`
    (any of "vegetarian", "vegan", "halal", "jain"), `tag` (a keyword/dish like "biryani",
    "dosa", "catering"), `open_now` (only places open at the current time), `featured_only`.

    Each record includes a `description`, `tags`, a `confidence_score` (0-1), an `is_featured`
    flag, an `open_now` flag (true/false/null), and `distance_miles` when a point was supplied.
    """
    return queries.get_indian_restaurants(
        lat=lat, lng=lng, radius_miles=radius_miles, city=city, state=state,
        region_tag=region_tag, dietary_tags=dietary_tags, tag=tag, open_now=open_now,
        featured_only=featured_only, limit=limit)


@mcp.tool()
def get_indian_movies_in_theaters(language: str | None = None, limit: int = 40) -> dict[str, Any]:
    """List Indian-language movies currently playing in US theaters (Hindi, Telugu, Tamil,
    Malayalam, Kannada, Punjabi, Bengali, Marathi, Gujarati).

    Optional `language` filters to one (e.g. "Telugu"). Each movie includes `title`, `language`,
    `poster_url`, `overview`, `release_date`, `genres`, and a `ticket_url` — a "find showtimes / buy
    tickets" search link (per-theater showtimes are not available via a free source). Data from TMDB.
    """
    from . import movies
    rows = movies.list_in_theaters(language=language, limit=limit)
    return {"results": rows, "count": len(rows), "languages": movies.languages_in_theaters(),
            "attribution": "Movie data from TMDB (themoviedb.org); not endorsed or certified by TMDB."}


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


@mcp.tool()
def submit_review(vertical: str, listing_id: int, rating: int, text: str = "",
                  name: str = "") -> dict[str, Any]:
    """Submit a community review (1-5 star rating + optional text) for a listing.

    `vertical` is the category key (restaurants, temples, groceries, professionals, salons, apparel,
    sweets, studios, services, community, legal, education, realestate, finance) and `listing_id` is
    the id returned by that category's get_/search_ tools. Reviews are moderated: clean ones publish
    immediately and spam/abusive ones are held for human review. Returns {'ok', 'id', 'status'}.
    """
    return reviews.submit(vertical, listing_id, rating, body=text, name=name, source="agent")


@mcp.tool()
def get_reviews(vertical: str, listing_id: int, limit: int = 20) -> dict[str, Any]:
    """Published community reviews for a listing (newest first) + its rolled-up community rating.

    The community rating is first-party (visitor-submitted) and is separate from any web-harvested
    `rating` returned by the get_/search_ tools. Returns {'community_rating', 'community_rating_count',
    'reviews': [{rating, title, body, author, created_at}]}.
    """
    summary = reviews.rating_summary(vertical, listing_id)
    items = [{"rating": int(r["rating"]), "title": r.get("title"), "body": r.get("body"),
              "author": r.get("author_name") or "Anonymous", "created_at": str(r.get("created_at"))}
             for r in reviews.list_for_listing(vertical, listing_id, limit=limit)]
    return {**summary, "reviews": items}


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
    tag: str | None = None,
    open_now: bool = False,
    limit: int = 25,
) -> dict[str, Any]:
    """Find Indian-American temples (Hindu/Sikh/Jain places of worship).

    Provide a point (`lat`+`lng`, optional `radius_miles`) or `city`/`state`. Filter by
    `religion` ("hindu", "sikh", "jain"), `denomination` (e.g. "swaminarayan"), `tag`, or
    `open_now`. Records include description, deity, region, tags, hours and `open_now`.
    """
    return temple_queries.get_indian_temples(
        lat=lat, lng=lng, radius_miles=radius_miles, city=city, state=state,
        religion=religion, denomination=denomination, tag=tag, open_now=open_now, limit=limit)


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


# ------------------------------------------------------------- groceries (Phase 2)
@mcp.tool()
def get_indian_groceries(
    lat: float | None = None,
    lng: float | None = None,
    radius_miles: float = 15.0,
    city: str | None = None,
    state: str | None = None,
    region_tag: str | None = None,
    tag: str | None = None,
    open_now: bool = False,
    limit: int = 25,
) -> dict[str, Any]:
    """Find Indian grocery stores (desi groceries / supermarkets).

    Provide a point (`lat`+`lng`, optional `radius_miles`) or `city`/`state`. Optional
    `region_tag` (e.g. "Gujarati"), `tag` (e.g. "spices", "halal"), `open_now`. Records
    include description, store type, tags, hours, region and `open_now`.
    """
    return grocery_queries.get_indian_groceries(
        lat=lat, lng=lng, radius_miles=radius_miles, city=city, state=state,
        region_tag=region_tag, tag=tag, open_now=open_now, limit=limit)


@mcp.tool()
def get_grocery_details(grocery_id: int) -> dict[str, Any]:
    """Full canonical record for one grocery store, plus its version history."""
    record = grocery_queries.get_grocery_details(grocery_id)
    if record is None:
        return {"error": "not_found", "grocery_id": grocery_id}
    return record


@mcp.tool()
def search_groceries_by_text(
    query: str, city: str | None = None, state: str | None = None, limit: int = 25,
) -> dict[str, Any]:
    """Free-text/semantic search over Indian grocery stores (name/region/store type)."""
    return grocery_queries.search_groceries_by_text(query, city=city, state=state, limit=limit)


# -------------------------------------------------------- professionals (Phase 2)
@mcp.tool()
def get_indian_professionals(
    lat: float | None = None,
    lng: float | None = None,
    radius_miles: float = 15.0,
    city: str | None = None,
    state: str | None = None,
    profession_type: str | None = None,
    speciality: str | None = None,
    tag: str | None = None,
    open_now: bool = False,
    limit: int = 25,
) -> dict[str, Any]:
    """Find Indian-American healthcare professionals (doctors, dentists, clinics, pharmacies).

    Provide a point (`lat`+`lng`, optional `radius_miles`) or `city`/`state`. Filter by
    `profession_type` ("doctors", "dentist", "clinic", "pharmacy"), `speciality` (e.g.
    "pediatrics", "cardiology", "ayurveda"), `tag`, or `open_now`. Note: these are matched
    from public data via an Indian-name signal, so a `confidence_score` is included.
    """
    return professional_queries.get_indian_professionals(
        lat=lat, lng=lng, radius_miles=radius_miles, city=city, state=state,
        profession_type=profession_type, speciality=speciality, tag=tag, open_now=open_now,
        limit=limit)


@mcp.tool()
def get_professional_details(professional_id: int) -> dict[str, Any]:
    """Full canonical record for one professional/practice, plus its version history."""
    record = professional_queries.get_professional_details(professional_id)
    if record is None:
        return {"error": "not_found", "professional_id": professional_id}
    return record


@mcp.tool()
def search_professionals_by_text(
    query: str, city: str | None = None, state: str | None = None, limit: int = 25,
) -> dict[str, Any]:
    """Free-text/semantic search over Indian-American healthcare professionals."""
    return professional_queries.search_professionals_by_text(query, city=city, state=state, limit=limit)


# --------------------------------------------------------------- salons (Phase 2)
@mcp.tool()
def get_indian_salons(
    lat: float | None = None,
    lng: float | None = None,
    radius_miles: float = 15.0,
    city: str | None = None,
    state: str | None = None,
    tag: str | None = None,
    open_now: bool = False,
    limit: int = 25,
) -> dict[str, Any]:
    """Find Indian beauty salons (threading, henna/mehndi, hair, bridal).

    Provide a point (`lat`+`lng`, optional `radius_miles`) or `city`/`state`. Filter by
    `tag` (e.g. "threading", "henna", "bridal") or `open_now`. Records include description,
    services (tags), hours and an `open_now` flag.
    """
    return salon_queries.get_indian_salons(
        lat=lat, lng=lng, radius_miles=radius_miles, city=city, state=state,
        tag=tag, open_now=open_now, limit=limit)


@mcp.tool()
def get_salon_details(salon_id: int) -> dict[str, Any]:
    """Full canonical record for one salon, plus its version history."""
    record = salon_queries.get_salon_details(salon_id)
    if record is None:
        return {"error": "not_found", "salon_id": salon_id}
    return record


@mcp.tool()
def search_salons_by_text(
    query: str, city: str | None = None, state: str | None = None, limit: int = 25,
) -> dict[str, Any]:
    """Free-text/semantic search over Indian beauty salons."""
    return salon_queries.search_salons_by_text(query, city=city, state=state, limit=limit)


# --------------------------------------------------------------- events (Phase 2)
@mcp.tool()
def get_indian_events(
    lat: float | None = None,
    lng: float | None = None,
    radius_miles: float = 25.0,
    city: str | None = None,
    state: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    include_past: bool = False,
    limit: int = 25,
) -> dict[str, Any]:
    """Find upcoming Indian-American community events (festivals, garba, concerts, puja).

    Provide a point (`lat`+`lng`, optional `radius_miles`) or `city`/`state`. Filter by
    `category` ("festival", "garba", "concert", "puja", …) or `tag` ("diwali", "holi", …).
    Returns UPCOMING events by default (soonest first); set `include_past=true` for history.
    Each event has `start_at`/`end_at`, venue, category and a description.
    """
    return event_queries.get_indian_events(
        lat=lat, lng=lng, radius_miles=radius_miles, city=city, state=state,
        category=category, tag=tag, include_past=include_past, limit=limit)


@mcp.tool()
def get_event_details(event_id: int) -> dict[str, Any]:
    """Full canonical record for one event, plus its version history."""
    record = event_queries.get_event_details(event_id)
    if record is None:
        return {"error": "not_found", "event_id": event_id}
    return record


@mcp.tool()
def search_events_by_text(
    query: str, city: str | None = None, state: str | None = None, limit: int = 25,
) -> dict[str, Any]:
    """Free-text/semantic search over Indian-American events (incl. past, for history)."""
    return event_queries.search_events_by_text(query, city=city, state=state, limit=limit)


# --------------------------------------------------------------- apparel & jewelry
@mcp.tool()
def get_indian_apparel(
    lat: float | None = None, lng: float | None = None, radius_miles: float = 15.0,
    city: str | None = None, state: str | None = None, tag: str | None = None,
    open_now: bool = False, limit: int = 25,
) -> dict[str, Any]:
    """Find Indian apparel & jewelry stores (sarees, lehengas, ethnic wear, gold jewelers).

    Provide a point (`lat`+`lng`, optional `radius_miles`) or `city`/`state`. Filter by `tag`
    (e.g. "saree", "bridal", "gold", "jewelry", "tailoring") or `open_now`.
    """
    return apparel_queries.get_indian_apparel(
        lat=lat, lng=lng, radius_miles=radius_miles, city=city, state=state,
        tag=tag, open_now=open_now, limit=limit)


@mcp.tool()
def get_apparel_details(apparel_id: int) -> dict[str, Any]:
    """Full canonical record for one apparel/jewelry store, plus its version history."""
    record = apparel_queries.get_apparel_details(apparel_id)
    if record is None:
        return {"error": "not_found", "apparel_id": apparel_id}
    return record


@mcp.tool()
def search_apparel_by_text(
    query: str, city: str | None = None, state: str | None = None, limit: int = 25,
) -> dict[str, Any]:
    """Free-text/semantic search over Indian apparel & jewelry stores."""
    return apparel_queries.search_apparel_by_text(query, city=city, state=state, limit=limit)


# --------------------------------------------------------------- sweets & bakeries
@mcp.tool()
def get_indian_sweets(
    lat: float | None = None, lng: float | None = None, radius_miles: float = 15.0,
    city: str | None = None, state: str | None = None, tag: str | None = None,
    open_now: bool = False, limit: int = 25,
) -> dict[str, Any]:
    """Find Indian sweets shops (mithai) & bakeries.

    Provide a point (`lat`+`lng`, optional `radius_miles`) or `city`/`state`. Filter by `tag`
    (e.g. "mithai", "jalebi", "bakery", "eggless") or `open_now`.
    """
    return sweets_queries.get_indian_sweets(
        lat=lat, lng=lng, radius_miles=radius_miles, city=city, state=state,
        tag=tag, open_now=open_now, limit=limit)


@mcp.tool()
def get_sweets_details(sweets_id: int) -> dict[str, Any]:
    """Full canonical record for one sweets shop / bakery, plus its version history."""
    record = sweets_queries.get_sweets_details(sweets_id)
    if record is None:
        return {"error": "not_found", "sweets_id": sweets_id}
    return record


@mcp.tool()
def search_sweets_by_text(
    query: str, city: str | None = None, state: str | None = None, limit: int = 25,
) -> dict[str, Any]:
    """Free-text/semantic search over Indian sweets shops & bakeries."""
    return sweets_queries.search_sweets_by_text(query, city=city, state=state, limit=limit)


# --------------------------------------------------------------- yoga & dance studios
@mcp.tool()
def get_indian_studios(
    lat: float | None = None, lng: float | None = None, radius_miles: float = 15.0,
    city: str | None = None, state: str | None = None, tag: str | None = None,
    open_now: bool = False, limit: int = 25,
) -> dict[str, Any]:
    """Find Indian yoga & cultural studios (yoga, classical dance, music, language classes).

    Provide a point (`lat`+`lng`, optional `radius_miles`) or `city`/`state`. Filter by `tag`
    (e.g. "yoga", "bharatanatyam", "kathak", "tabla", "carnatic") or `open_now`.
    """
    return studio_queries.get_indian_studios(
        lat=lat, lng=lng, radius_miles=radius_miles, city=city, state=state,
        tag=tag, open_now=open_now, limit=limit)


@mcp.tool()
def get_studio_details(studio_id: int) -> dict[str, Any]:
    """Full canonical record for one studio, plus its version history."""
    record = studio_queries.get_studio_details(studio_id)
    if record is None:
        return {"error": "not_found", "studio_id": studio_id}
    return record


@mcp.tool()
def search_studios_by_text(
    query: str, city: str | None = None, state: str | None = None, limit: int = 25,
) -> dict[str, Any]:
    """Free-text/semantic search over Indian yoga/dance/music studios."""
    return studio_queries.search_studios_by_text(query, city=city, state=state, limit=limit)


# --------------------------------------------------------------- community services
@mcp.tool()
def get_indian_services(
    lat: float | None = None, lng: float | None = None, radius_miles: float = 15.0,
    city: str | None = None, state: str | None = None, tag: str | None = None,
    open_now: bool = False, limit: int = 25,
) -> dict[str, Any]:
    """Find Indian community services (money transfer/remittance, banks, immigration/visa,
    travel agents, tax/insurance).

    Provide a point (`lat`+`lng`, optional `radius_miles`) or `city`/`state`. Filter by `tag`
    (e.g. "money-transfer", "immigration", "travel", "tax") or `open_now`.
    """
    return service_queries.get_indian_services(
        lat=lat, lng=lng, radius_miles=radius_miles, city=city, state=state,
        tag=tag, open_now=open_now, limit=limit)


@mcp.tool()
def get_service_details(service_id: int) -> dict[str, Any]:
    """Full canonical record for one service business, plus its version history."""
    record = service_queries.get_service_details(service_id)
    if record is None:
        return {"error": "not_found", "service_id": service_id}
    return record


@mcp.tool()
def search_services_by_text(
    query: str, city: str | None = None, state: str | None = None, limit: int = 25,
) -> dict[str, Any]:
    """Free-text/semantic search over Indian community services."""
    return service_queries.search_services_by_text(query, city=city, state=state, limit=limit)


# --------------------------------------------------------------- community orgs
@mcp.tool()
def get_indian_community(
    lat: float | None = None, lng: float | None = None, radius_miles: float = 25.0,
    city: str | None = None, state: str | None = None, tag: str | None = None,
    open_now: bool = False, limit: int = 25,
) -> dict[str, Any]:
    """Find Indian community organizations & cultural associations (regional samaj/sangam,
    cultural centers, Indo-American associations).

    Provide a point (`lat`+`lng`) or `city`/`state`. Filter by `tag` (e.g. a region like
    "telugu", "gujarati", or "association"/"cultural_center").
    """
    return community_queries.get_indian_community(
        lat=lat, lng=lng, radius_miles=radius_miles, city=city, state=state,
        tag=tag, open_now=open_now, limit=limit)


@mcp.tool()
def get_community_details(community_id: int) -> dict[str, Any]:
    """Full canonical record for one community organization, plus its version history."""
    record = community_queries.get_community_details(community_id)
    if record is None:
        return {"error": "not_found", "community_id": community_id}
    return record


@mcp.tool()
def search_community_by_text(
    query: str, city: str | None = None, state: str | None = None, limit: int = 25,
) -> dict[str, Any]:
    """Free-text/semantic search over Indian community organizations & associations."""
    return community_queries.search_community_by_text(query, city=city, state=state, limit=limit)


# --------------------------------------------------------------- immigration & legal
@mcp.tool()
def get_indian_legal(
    lat: float | None = None, lng: float | None = None, radius_miles: float = 25.0,
    city: str | None = None, state: str | None = None, tag: str | None = None,
    open_now: bool = False, limit: int = 25,
) -> dict[str, Any]:
    """Find Indian-American immigration attorneys & law firms.

    Provide a point (`lat`+`lng`, optional `radius_miles`) or `city`/`state`. Filter by `tag`
    (e.g. "immigration").
    """
    return legal_queries.get_indian_legal(
        lat=lat, lng=lng, radius_miles=radius_miles, city=city, state=state,
        tag=tag, open_now=open_now, limit=limit)


@mcp.tool()
def get_legal_details(legal_id: int) -> dict[str, Any]:
    """Full canonical record for one immigration/legal listing, plus its version history."""
    record = legal_queries.get_legal_details(legal_id)
    if record is None:
        return {"error": "not_found", "legal_id": legal_id}
    return record


@mcp.tool()
def search_legal_by_text(
    query: str, city: str | None = None, state: str | None = None, limit: int = 25,
) -> dict[str, Any]:
    """Free-text/semantic search over Indian-American immigration attorneys & law firms."""
    return legal_queries.search_legal_by_text(query, city=city, state=state, limit=limit)


# --------------------------------------------------------------- education & tutoring
@mcp.tool()
def get_indian_education(
    lat: float | None = None, lng: float | None = None, radius_miles: float = 25.0,
    city: str | None = None, state: str | None = None, tag: str | None = None,
    open_now: bool = False, limit: int = 25,
) -> dict[str, Any]:
    """Find Indian-American education & tutoring (heritage/language schools, Bal Vihar, coaching).

    Provide a point (`lat`+`lng`, optional `radius_miles`) or `city`/`state`. Filter by `tag`
    (e.g. "language_school", "heritage", "tutoring").
    """
    return education_queries.get_indian_education(
        lat=lat, lng=lng, radius_miles=radius_miles, city=city, state=state,
        tag=tag, open_now=open_now, limit=limit)


@mcp.tool()
def get_education_details(education_id: int) -> dict[str, Any]:
    """Full canonical record for one education/tutoring listing, plus its version history."""
    record = education_queries.get_education_details(education_id)
    if record is None:
        return {"error": "not_found", "education_id": education_id}
    return record


@mcp.tool()
def search_education_by_text(
    query: str, city: str | None = None, state: str | None = None, limit: int = 25,
) -> dict[str, Any]:
    """Free-text/semantic search over Indian-American education & tutoring."""
    return education_queries.search_education_by_text(query, city=city, state=state, limit=limit)


# --------------------------------------------------------------- real estate
@mcp.tool()
def get_indian_realestate(
    lat: float | None = None, lng: float | None = None, radius_miles: float = 25.0,
    city: str | None = None, state: str | None = None, tag: str | None = None,
    open_now: bool = False, limit: int = 25,
) -> dict[str, Any]:
    """Find Indian-American realtors & real-estate agencies.

    Provide a point (`lat`+`lng`, optional `radius_miles`) or `city`/`state`. Filter by `tag`
    (e.g. "agency", "mortgage").
    """
    return realestate_queries.get_indian_realestate(
        lat=lat, lng=lng, radius_miles=radius_miles, city=city, state=state,
        tag=tag, open_now=open_now, limit=limit)


@mcp.tool()
def get_realestate_details(realestate_id: int) -> dict[str, Any]:
    """Full canonical record for one real-estate listing, plus its version history."""
    record = realestate_queries.get_realestate_details(realestate_id)
    if record is None:
        return {"error": "not_found", "realestate_id": realestate_id}
    return record


@mcp.tool()
def search_realestate_by_text(
    query: str, city: str | None = None, state: str | None = None, limit: int = 25,
) -> dict[str, Any]:
    """Free-text/semantic search over Indian-American realtors & real-estate agencies."""
    return realestate_queries.search_realestate_by_text(query, city=city, state=state, limit=limit)


# --------------------------------------------------------------- finance & tax
@mcp.tool()
def get_indian_finance(
    lat: float | None = None, lng: float | None = None, radius_miles: float = 25.0,
    city: str | None = None, state: str | None = None, tag: str | None = None,
    open_now: bool = False, limit: int = 25,
) -> dict[str, Any]:
    """Find Indian-American CPAs, tax preparers & financial advisors.

    Provide a point (`lat`+`lng`, optional `radius_miles`) or `city`/`state`. Filter by `tag`
    (e.g. "cpa", "tax", "financial_advisor").
    """
    return finance_queries.get_indian_finance(
        lat=lat, lng=lng, radius_miles=radius_miles, city=city, state=state,
        tag=tag, open_now=open_now, limit=limit)


@mcp.tool()
def get_finance_details(finance_id: int) -> dict[str, Any]:
    """Full canonical record for one finance/tax listing, plus its version history."""
    record = finance_queries.get_finance_details(finance_id)
    if record is None:
        return {"error": "not_found", "finance_id": finance_id}
    return record


@mcp.tool()
def search_finance_by_text(
    query: str, city: str | None = None, state: str | None = None, limit: int = 25,
) -> dict[str, Any]:
    """Free-text/semantic search over Indian-American CPAs, tax preparers & financial advisors."""
    return finance_queries.search_finance_by_text(query, city=city, state=state, limit=limit)


@mcp.tool()
def search_all(
    query: str, city: str | None = None, state: str | None = None,
    lat: float | None = None, lng: float | None = None, limit: int = 20,
) -> dict[str, Any]:
    """Search across ALL Indian-American verticals at once — restaurants, temples, groceries,
    healthcare professionals, beauty salons, events, apparel & jewelry, sweets & bakeries,
    yoga/dance studios, and community services.

    Use for broad queries like "Indian things near me in Edison NJ" or "vegetarian South
    Indian". Results are ranked by relevance: an exact name match ranks first, then by
    keyword/semantic similarity, proximity (pass `lat`+`lng`) and freshness. Each result is
    tagged with its `vertical`. Optionally constrain by `city`/`state`.
    """
    return verticals.search_all(query, city=city, state=state, lat=lat, lng=lng, limit=limit)


# ---------------------------------------------------- agent traffic analytics
def _client_name() -> str | None:
    """Best-effort MCP client/agent identity (name/version) for the current call."""
    try:
        from mcp.server.lowlevel.server import request_ctx
        ci = request_ctx.get().session.client_params.clientInfo
        return f"{ci.name}/{ci.version}" if ci and ci.name else None
    except Exception:
        return None


def _record(tool: str, kwargs: dict, result) -> None:
    try:
        from . import analytics
        count = result.get("count") if isinstance(result, dict) else None
        analytics.log_call(tool, kwargs, count, _client_name())
        analytics.log_impressions(tool, result)
    except Exception:
        pass  # analytics must never break a tool response


def _install_tracking() -> None:
    """Wrap every registered tool's fn to log the call (tool, args, count, client)."""
    import functools

    for name, tool in mcp._tool_manager._tools.items():
        orig = tool.fn
        if getattr(tool, "is_async", False):
            @functools.wraps(orig)
            async def w(*a, _orig=orig, _name=name, **k):
                res = await _orig(*a, **k)
                _record(_name, k, res)
                return res
        else:
            @functools.wraps(orig)
            def w(*a, _orig=orig, _name=name, **k):
                res = _orig(*a, **k)
                _record(_name, k, res)
                return res
        tool.fn = w


_install_tracking()


def main() -> None:
    # stdio for local clients; streamable-http for a hosted service (see deploy/).
    if settings.mcp_transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport=settings.mcp_transport)


if __name__ == "__main__":
    main()
