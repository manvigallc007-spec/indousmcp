"""Seed fixtures for local testing without a live scrape.

These are FICTIONAL restaurants (invented names, 555 phone numbers, example.com sites)
so nothing here asserts false facts about real businesses. They flow through the normal
pipeline (raw -> clean/score -> canonical), so confidence scores, regions, dietary tags
and embeddings are all populated realistically. Loaded via `cli seed`.
"""

from __future__ import annotations

from psycopg.types.json import Jsonb

from .. import db
from . import ingest

# Coordinates are approximate metro centers; good enough to exercise geo queries.
SEED_RESTAURANTS: list[dict] = [
    # ---- Bay Area ----
    {"name": "Saffron Tiffin House", "city": "Sunnyvale", "state": "CA",
     "lat": 37.3688, "lng": -122.0363, "phone": "+1-408-555-0101",
     "website": "https://example.com/saffron-tiffin", "cuisine_type": "South Indian",
     "address_full": "100 Murphy Ave, Sunnyvale, CA 94086", "price_range": "$$",
     "dietary_tags": ["vegetarian"], "is_featured": True},
    {"name": "Punjab Junction Dhaba", "city": "Fremont", "state": "CA",
     "lat": 37.5485, "lng": -121.9886, "phone": "+1-510-555-0102",
     "website": "https://example.com/punjab-junction", "cuisine_type": "Punjabi",
     "address_full": "200 Fremont Blvd, Fremont, CA 94536", "price_range": "$$"},
    {"name": "Madras Coffee Corner", "city": "Santa Clara", "state": "CA",
     "lat": 37.3541, "lng": -121.9552, "phone": "+1-408-555-0103",
     "website": "https://example.com/madras-coffee", "cuisine_type": "South Indian, Udupi",
     "address_full": "300 El Camino Real, Santa Clara, CA 95050",
     "dietary_tags": ["vegetarian", "vegan"]},
    # ---- NYC / NJ ----
    {"name": "Curry Hill Kitchen", "city": "New York", "state": "NY",
     "lat": 40.7440, "lng": -73.9830, "phone": "+1-212-555-0104",
     "website": "https://example.com/curry-hill", "cuisine_type": "North Indian, Mughlai",
     "address_full": "400 Lexington Ave, New York, NY 10016", "price_range": "$$$",
     "is_featured": True},
    {"name": "Edison Spice Route", "city": "Edison", "state": "NJ",
     "lat": 40.5187, "lng": -74.4121, "phone": "+1-732-555-0105",
     "website": "https://example.com/edison-spice", "cuisine_type": "Gujarati",
     "address_full": "500 Oak Tree Rd, Edison, NJ 08820",
     "dietary_tags": ["vegetarian", "jain"]},
    {"name": "Jersey Biryani Bowl", "city": "Jersey City", "state": "NJ",
     "lat": 40.7178, "lng": -74.0431, "phone": "+1-201-555-0106",
     "website": "https://example.com/jersey-biryani", "cuisine_type": "Hyderabadi",
     "address_full": "600 Newark Ave, Jersey City, NJ 07306", "price_range": "$$"},
    # ---- Dallas ----
    {"name": "Irving Dosa Factory", "city": "Irving", "state": "TX",
     "lat": 32.8140, "lng": -96.9489, "phone": "+1-972-555-0107",
     "website": "https://example.com/irving-dosa", "cuisine_type": "South Indian",
     "address_full": "700 N MacArthur Blvd, Irving, TX 75061",
     "dietary_tags": ["vegetarian"]},
    {"name": "Plano Tandoori Nights", "city": "Plano", "state": "TX",
     "lat": 33.0198, "lng": -96.6989, "phone": "+1-469-555-0108",
     "website": "https://example.com/plano-tandoori", "cuisine_type": "North Indian",
     "address_full": "800 Preston Rd, Plano, TX 75093", "price_range": "$$"},
    # ---- Houston ----
    {"name": "Hillcroft Halal Grill", "city": "Houston", "state": "TX",
     "lat": 29.7250, "lng": -95.4870, "phone": "+1-713-555-0109",
     "website": "https://example.com/hillcroft-halal", "cuisine_type": "Mughlai",
     "address_full": "900 Hillcroft Ave, Houston, TX 77036",
     "dietary_tags": ["halal"]},
    {"name": "Sugar Land Thali Co", "city": "Sugar Land", "state": "TX",
     "lat": 29.6197, "lng": -95.6349, "phone": "+1-281-555-0110",
     "website": "https://example.com/sugarland-thali", "cuisine_type": "Gujarati",
     "address_full": "1000 Hwy 6, Sugar Land, TX 77478",
     "dietary_tags": ["vegetarian", "jain"]},
    # ---- Chicago ----
    {"name": "Devon Avenue Chaat", "city": "Chicago", "state": "IL",
     "lat": 41.9973, "lng": -87.6900, "phone": "+1-773-555-0111",
     "website": "https://example.com/devon-chaat", "cuisine_type": "North Indian, Indo-Chinese",
     "address_full": "1100 W Devon Ave, Chicago, IL 60659", "price_range": "$"},
    {"name": "Naperville Kerala House", "city": "Naperville", "state": "IL",
     "lat": 41.7508, "lng": -88.1535, "phone": "+1-630-555-0112",
     "website": "https://example.com/naperville-kerala", "cuisine_type": "Kerala, Malabar",
     "address_full": "1200 Ogden Ave, Naperville, IL 60563", "price_range": "$$"},
]


def load_seed() -> dict[str, int]:
    """Insert seed fixtures into restaurant_raw, then run the normal pipeline."""
    for i, r in enumerate(SEED_RESTAURANTS):
        candidate = {
            "source_name": "seed",
            "source_url": r.get("website"),
            "source_id": f"seed-{i:03d}",
            "country": "USA",
            **r,
        }
        db.execute(
            """
            INSERT INTO restaurant_raw (source_name, source_url, source_id, payload)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (source_name, source_id)
            DO UPDATE SET payload = EXCLUDED.payload, processed = false, processed_at = NULL
            """,
            (candidate["source_name"], candidate["source_url"], candidate["source_id"],
             Jsonb(candidate)),
        )
    result = ingest.process_raw()

    # Reflect the is_featured flag from the fixtures (pipeline doesn't set it).
    featured = [f"seed-{i:03d}" for i, r in enumerate(SEED_RESTAURANTS) if r.get("is_featured")]
    if featured:
        db.execute(
            "UPDATE restaurants SET is_featured = true WHERE source_name='seed' "
            "AND source_id = ANY(%s)",
            (featured,),
        )
    result["seeded"] = len(SEED_RESTAURANTS)
    result["featured"] = len(featured)
    return result
