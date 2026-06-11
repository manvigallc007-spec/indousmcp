"""Ad-hoc end-to-end verification against the live (seeded) database."""

import json

from indo_usa_mcp import queries
from indo_usa_mcp.pipeline import outreach


def show(title, obj):
    print(f"\n=== {title} ===")
    print(json.dumps(obj, indent=2, default=str))


# 1. Geo-radius near Sunnyvale (Bay Area), featured surfaced first.
geo = queries.get_indian_restaurants(lat=37.3688, lng=-122.0363, radius_miles=25, limit=5)
show(
    "get_indian_restaurants near Bay Area",
    {
        "count": geo["count"],
        "results": [
            {"name": r["name"], "city": r["city"],
             "miles": r.get("distance_miles"), "featured": r["is_featured"]}
            for r in geo["results"]
        ],
    },
)

# 2. Dietary filter.
jain = queries.get_indian_restaurants(dietary_tags=["jain"], limit=10)
show("filter dietary_tags=jain", [r["name"] for r in jain["results"]])

# 3. Semantic text search.
s = queries.search_restaurants_by_text("vegetarian south indian dosa", limit=3)
show(
    "search 'vegetarian south indian dosa'",
    {"ranking": s["ranking"],
     "hits": [{"name": r["name"], "score": round(r["match_score"], 3)} for r in s["results"]]},
)

# 4. Details + version history.
rid = geo["results"][0]["id"]
d = queries.get_restaurant_details(rid)
show(
    "get_restaurant_details",
    {"name": d["name"], "region_tag": d["region_tag"],
     "confidence": d["confidence_score"], "versions": len(d["version_history"])},
)

# 5. Outreach drafting (claim links + messages).
o = outreach.run_outreach(limit=3)
show(
    "draft_claim_outreach",
    {"drafted": o["drafted"], "requires_human": o["requires_human"],
     "sample": {k: o["items"][0][k] for k in ("name", "channel", "claim_link")} if o["items"] else None},
)

print("\n=== overall stats ===")
print(json.dumps(queries.stats(), indent=2, default=str))
