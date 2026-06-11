"""End-to-end claim flow against the live dev DB, via the web app's TestClient."""

from starlette.testclient import TestClient

from indo_usa_mcp import db
from indo_usa_mcp.pipeline import outreach
from indo_usa_mcp.web import app

# Pick any active restaurant to claim.
r = db.query_one("SELECT id, name FROM restaurants WHERE deleted_at IS NULL LIMIT 1")
print("restaurant:", r["name"], f"(id={r['id']})")

claim = outreach.create_claim(r["id"], channel="email", contact_target="owner@example.com")
token = claim["token"]
print("claim link:", claim["claim_link"])

client = TestClient(app)

# 1. Owner opens the claim link -> form shows the restaurant name.
page = client.get(f"/claim?token={token}")
print("GET /claim ->", page.status_code, "| shows name:", r["name"] in page.text)

# 2. Owner submits email -> claimed.
resp = client.post("/claim", data={"token": token, "email": "owner@example.com"})
print("POST /claim ->", resp.status_code, "| 'claimed' in page:", "claimed" in resp.text.lower())

# 3. Verify ownership flipped in the DB.
after = db.query_one("SELECT is_claimed FROM restaurants WHERE id=%s", (r["id"],))
cl = db.query_one("SELECT status FROM claims WHERE token=%s", (token,))
print("DB is_claimed:", after["is_claimed"], "| claim status:", cl["status"])

# 4. Re-opening the link now shows 'already claimed'.
again = client.get(f"/claim?token={token}")
print("GET /claim again ->", again.status_code, "| already claimed:", "already claimed" in again.text.lower())
