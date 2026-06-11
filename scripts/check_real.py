"""Quick look at semantic search + approval queue over the real scraped dataset."""

from indo_usa_mcp import db, queries

s = queries.search_restaurants_by_text("punjabi tandoori", state="CA", limit=4)
print("SEARCH 'punjabi tandoori' (CA) ranking:", s["ranking"])
for r in s["results"]:
    print(f"  {round(r['match_score'], 3):<6} {r['name']} - {r['city']}")

print("\nSAMPLE PENDING APPROVALS (lowest confidence first):")
rows = db.query(
    "SELECT proposed->>'name' AS name, confidence, risk "
    "FROM approval_queue WHERE status='pending' ORDER BY confidence LIMIT 5"
)
for row in rows:
    print(f"  conf={row['confidence']:<5} {row['risk']:<4} {row['name']}")
