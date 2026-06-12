"""Live check: events approval routing + upcoming/past lifecycle (synthetic, no feeds)."""

from psycopg.types.json import Jsonb

from indo_usa_mcp import db
from indo_usa_mcp.events import pipeline as events
from indo_usa_mcp.events import queries as q

db.init_db()
db.execute("DELETE FROM events WHERE source_name='ical-test'")
db.execute("DELETE FROM event_raw WHERE source_name='ical-test'")

future = {"name": "Diwali Mela", "start_at": "2099-11-08T18:00:00", "city": "Edison",
          "state": "NJ", "venue_name": "Community Center", "website": "https://x/d",
          "festival_specials": "garba", "source_name": "ical-test", "source_id": "f1"}
past = {"name": "Holi Bash", "start_at": "2020-03-10T12:00:00", "city": "Fremont",
        "state": "CA", "venue_name": "Park", "website": "https://x/h",
        "source_name": "ical-test", "source_id": "p1"}
for c in (future, past):
    db.execute("INSERT INTO event_raw (source_name, source_url, source_id, payload) "
               "VALUES (%s,%s,%s,%s) ON CONFLICT (source_name, source_id) DO UPDATE "
               "SET payload=EXCLUDED.payload, processed=false",
               (c["source_name"], c.get("website"), c["source_id"], Jsonb(c)))

print("process:", events.process_raw())
s = q.stats()
print("stats: approved=%s pending=%s upcoming=%s past=%s" % (
    s["approved"], s["pending"], s["upcoming"], s["past"]))

up = q.get_indian_events(state="NJ", limit=10)
print("upcoming (NJ):", [e["name"] for e in up["results"]])
allp = q.get_indian_events(include_past=True, limit=10)
print("include_past names:", sorted({e["name"] for e in allp["results"] if e["name"] in ('Diwali Mela', 'Holi Bash')}))
print("=> past event kept but excluded from upcoming:",
      "Holi Bash" not in [e["name"] for e in up["results"]]
      and "Holi Bash" in [e["name"] for e in allp["results"]])
