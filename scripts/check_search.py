"""Validate tag filter, open_now computation, and merge on live data."""

import datetime as dt

from indo_usa_mcp import db, hours, queries, verticals

# 1. Tag filter.
res = queries.get_indian_restaurants(tag="dosa", limit=5)
print("tag=dosa ->", res["count"], "results:", [r["name"] for r in res["results"]][:5])

# 2. open_now on a record that has parsed hours.
row = db.query_one(
    "SELECT id, name, hours_json FROM restaurants WHERE hours_json ? 'structured' "
    "AND hours_json->'structured' <> 'null' LIMIT 1")
if row:
    s = hours.structured_of(row["hours_json"])
    for label, when in [("Mon 13:00", dt.datetime(2026, 6, 8, 13, 0)),
                        ("Mon 04:00", dt.datetime(2026, 6, 8, 4, 0))]:
        print(f"open_now {row['name']} @ {label}:", hours.is_open(s, when))

# 3. Tag coverage.
n_tagged = db.query_one("SELECT count(*) AS n FROM restaurants WHERE array_length(tags,1) > 0")["n"]
print("restaurants with >=1 tag:", n_tagged, "/ 315")

# 4. Merge a duplicate group (if any), then confirm soft-delete.
dupes = verticals.duplicates = None
groups = db.query(
    "SELECT array_agg(id ORDER BY id) AS ids, count(*) AS n FROM restaurants "
    "WHERE deleted_at IS NULL GROUP BY lower(name), lower(city) HAVING count(*) > 1 LIMIT 1")
if groups:
    ids = groups[0]["ids"]
    before = db.query_one("SELECT count(*) AS n FROM restaurants WHERE deleted_at IS NULL")["n"]
    verticals.merge_duplicates("restaurants", ids[0], ids[1:])
    after = db.query_one("SELECT count(*) AS n FROM restaurants WHERE deleted_at IS NULL")["n"]
    print(f"merge {ids}: active {before} -> {after} (dropped {len(ids)-1})")
else:
    print("no duplicate groups to merge")
