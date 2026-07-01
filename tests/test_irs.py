"""IRS nonprofit -> Indian temples/community import: tight classifier, no false positives. No net/DB."""

import indo_usa_mcp.pipeline.scrapers.irs as irs
from indo_usa_mcp import verticals


def test_classifier_tight_no_false_positives():
    assert irs._classify("Hindu Temple Society of North America") == "temples"
    assert irs._classify("Sri Venkateswara Temple") == "temples"
    assert irs._classify("Gurdwara Sahib of Fremont") == "temples"
    assert irs._classify("Telugu Association of Greater Chicago") == "community"
    assert irs._classify("India Cultural Center") == "community"
    # must NOT match:
    assert irs._classify("Indiana Farmers Cooperative") is None       # 'indiana', not India
    assert irs._classify("Jain Family Foundation") is None            # surname, not a temple/center
    assert irs._classify("Smith Charitable Trust") is None


def test_broadened_filters_catch_more_orgs():
    for name in ("BAPS Swaminarayan Sanstha", "Chinmaya Mission West", "Jain Society of Houston",
                 "Arya Samaj of Houston", "ISKCON of Dallas"):
        assert irs._classify(name) == "temples", name
    for name in ("Indian Students Association", "Asian Indian Chamber of Commerce",
                 "American Association of Physicians of Indian Origin",
                 "Maharashtra Mandal of Chicago", "Kerala Association of Dallas"):
        assert irs._classify(name) == "community", name


def test_broadened_filters_avoid_native_american_and_surnames():
    for name in ("American Indian Heritage Center", "Indian Motorcycle Riders Club",
                 "Jain Family Foundation"):
        assert irs._classify(name) is None, name


def test_payload_titlecases_and_builds_address():
    p = irs._payload({"NAME": "hindu temple", "STREET": "1 main st", "CITY": "edison",
                      "STATE": "NJ", "ZIP": "08820"})
    assert p["name"] == "Hindu Temple" and p["city"] == "Edison" and p["state"] == "NJ"
    assert "Edison" in p["address_full"] and "08820" in p["address_full"]


def test_import_filters_then_creates(monkeypatch):
    rows = [
        {"NAME": "Sri Venkateswara Temple", "STREET": "1 A St", "CITY": "Aurora", "STATE": "IL", "ZIP": "60504"},
        {"NAME": "Indiana Farmers Co-op", "STREET": "2 B St", "CITY": "Gary", "STATE": "IN", "ZIP": "46402"},
        {"NAME": "Tamil Sangam of New Jersey", "STREET": "3 C St", "CITY": "Edison", "STATE": "NJ", "ZIP": "08820"},
    ]
    created = []
    monkeypatch.setattr(irs, "_iter_rows", lambda url: iter(rows))
    monkeypatch.setattr(verticals, "create_record",
                        lambda v, p: created.append((v, p["name"])) or {"ok": True, "id": len(created)})
    out = irs.import_eo(urls=["http://x"])
    assert out["added"] == 2 and out["by_vertical"] == {"temples": 1, "community": 1}
    assert ("temples", "Sri Venkateswara Temple") in created
