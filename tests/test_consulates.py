"""Indian consulates seed: curated dataset shape + payload + deduped upsert. No network/DB."""

import indo_usa_mcp.consulates as consulates
from indo_usa_mcp import verticals


def test_dataset_is_well_formed():
    assert len(consulates.CONSULATES) == 7
    for c in consulates.CONSULATES:
        assert c["name"] and c["city"] and c["state"] and c.get("website", "").startswith("http")
    cities = {c["city"] for c in consulates.CONSULATES}
    assert {"New York", "San Francisco", "Chicago", "Houston", "Atlanta", "Seattle"} <= cities


def test_payload_targets_services_vertical():
    p = consulates._payload(consulates.CONSULATES[1])   # New York
    assert p["service_type"] == "consulate" and p["state"] == "NY"
    assert p["country"] == "USA" and p["website"].startswith("http")
    assert "passport" in p["description"] and "VFS Global" in p["description"]


def test_seed_upserts_into_services(monkeypatch):
    created = []
    monkeypatch.setattr(verticals, "create_record",
                        lambda v, p: created.append((v, p["name"])) or {"ok": True, "id": len(created)})
    out = consulates.seed()
    assert out["consulates"] == 7 and out["added"] == 7
    assert all(v == "services" for v, _ in created)
    assert ("services", "Embassy of India, Washington DC") in created
