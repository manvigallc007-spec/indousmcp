"""Live check: owner magic-link login + portal dashboard + edit (dev, no SMTP)."""

import re

from starlette.testclient import TestClient

from indo_usa_mcp import db
from indo_usa_mcp.web import app

c = TestClient(app)

row = db.query_one(
    "SELECT owner_email FROM claims WHERE status='claimed' AND owner_email IS NOT NULL LIMIT 1")
email = row["owner_email"]
print("owner email:", email)

# 1. Request magic link (dev mode prints it on the page since SMTP is off).
r = c.post("/portal/login", data={"email": email})
m = re.search(r"/portal/auth\?t=([A-Za-z0-9_.\-]+)", r.text)
print("magic link issued:", bool(m))

# 2. Use the link -> session, then load the dashboard.
c.get(f"/portal/auth?t={m.group(1)}")
d = c.get("/portal")
print("dashboard ok:", d.status_code == 200, "| shows listings:", "your listings" in d.text.lower())

# 3. Edit a listing from the portal (must be allowed).
ids = re.findall(r"/portal/edit/(\w+)/(\d+)", d.text)
if ids:
    vert, rid = ids[0]
    e = c.get(f"/portal/edit/{vert}/{rid}")
    print(f"edit page /portal/edit/{vert}/{rid} ->", e.status_code)
    p = c.post(f"/portal/edit/{vert}/{rid}", data={"festival_specials": "Diwali specials"})
    print("save ->", p.status_code, "| saved msg:", "saved" in p.text.lower())

# 4. Logout drops the session.
c.get("/portal/logout")
after = c.get("/portal", follow_redirects=False)
print("after logout /portal ->", after.status_code, "(303 = signed out)")
