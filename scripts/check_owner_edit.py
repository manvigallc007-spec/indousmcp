"""Live check: owner claims a listing, then edits it via the management page."""

from starlette.testclient import TestClient

from indo_usa_mcp import db
from indo_usa_mcp.pipeline import ingest, outreach
from indo_usa_mcp.web import app

# Fresh restaurant + claim + verify so we have a claimed token to manage.
r = db.query_one(
    "SELECT id, name FROM restaurants WHERE deleted_at IS NULL AND NOT is_claimed LIMIT 1")
claim = outreach.create_claim(r["id"], channel="email", contact_target="owner@example.com")
outreach.verify_claim(claim["token"], owner_email="owner@example.com")
token = claim["token"]
print("owner of:", r["name"], f"(id={r['id']})  token=…{token[-6:]}")

client = TestClient(app)

# Owner opens management page.
page = client.get(f"/manage?token={token}")
print("GET /manage ->", page.status_code, "| form shows name:", r["name"] in page.text)

# Owner edits hours, price, and dietary.
resp = client.post("/manage", data={
    "token": token, "phone": "+1-555-999-0000", "price_range": "$$$",
    "hours": "Mo-Su 12:00-22:00", "dietary": ["vegetarian", "jain"],
})
print("POST /manage ->", resp.status_code, "| saved:", "Saved" in resp.text or "change" in resp.text.lower())

after = db.query_one(
    "SELECT phone, price_range, hours_json, dietary_tags, version FROM restaurants WHERE id=%s",
    (r["id"],))
print("after edit:", {k: after[k] for k in ("phone", "price_range", "hours_json", "dietary_tags", "version")})

# Stale check runs cleanly (nothing recent should deactivate).
print("deactivate_stale(99999d):", ingest.deactivate_stale(days=99999))
