"""Agent runner audit-serialization + Discovery coverage logic. No live DB needed.

Regression: the `discovery` agent was recorded as status='error' because its result embeds
analytics.top_misses(), whose rows carry a datetime (`last_seen`). The runner wrote the audit row
with Jsonb(result) using the stdlib JSON encoder, which raises on datetime. The runner now passes a
default=str dumps so any agent result/params serialize. Separately, DiscoveryAgent never populated
its per-metro coverage (always 0 -> every metro 'suggested')."""

import datetime
import json

from indo_usa_mcp.agents import definitions as d
from indo_usa_mcp.agents import runner


def test_runner_jsonb_dumps_handles_datetime_and_decimal():
    from decimal import Decimal
    dumps = runner._jsonb.keywords["dumps"]          # the configured serializer
    payload = {"last_seen": datetime.datetime(2026, 6, 19, 12, 0), "n": 3, "amt": Decimal("1.5")}
    s = dumps(payload)                               # must NOT raise on datetime/Decimal
    back = json.loads(s)
    assert back["n"] == 3
    assert isinstance(back["last_seen"], str)        # datetime -> stringified, audit row persists


def test_metro_of_buckets_coordinates():
    assert d._metro_of(32.9, -96.8) == "dallas"      # inside the DFW bbox
    assert d._metro_of(40.7, -73.9) == "nyc_nj"      # inside the NYC/NJ bbox
    assert d._metro_of(17.4, 78.5) is None           # Hyderabad -> no metro
    assert d._metro_of(None, None) is None
    assert d._metro_of("x", "y") is None             # unparseable -> None, not a crash


def test_discovery_populates_per_metro_coverage(monkeypatch):
    # 2 listings in Dallas, 1 in NYC, 1 abroad (unplaced). With min_per_metro=2, Dallas is covered
    # (not suggested), NYC is thin (suggested).
    fake = [{"lat": 32.9, "lng": -96.8}, {"lat": 33.0, "lng": -96.7},
            {"lat": 40.7, "lng": -73.9}, {"lat": 17.4, "lng": 78.5}]
    monkeypatch.setattr(d.db, "query", lambda *a, **k: fake)
    res = d.DiscoveryAgent().run(min_per_metro=2)

    assert res["total_restaurants"] == 4
    assert res["placed_in_metros"] == 3
    suggested = {t["metro"]: t["known"] for t in res["suggested_targets"]}
    assert "dallas" not in suggested                 # 2 >= min -> covered
    assert suggested.get("nyc_nj") == 1              # 1 < min -> suggested with real count
    assert res["covered_metros"] == 1                # only Dallas cleared the bar
