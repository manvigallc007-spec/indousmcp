"""NPPES provider scraper: maps the CMS registry JSON to a professionals candidate. No network."""

import indo_usa_mcp.professionals.nppes as nppes
from indo_usa_mcp.professionals import pipeline as pp

_SAMPLE = {"results": [{
    "number": 1234567890, "enumeration_type": "NPI-1",
    "basic": {"first_name": "ANIL", "last_name": "PATEL", "credential": "M.D."},
    "taxonomies": [{"desc": "Internal Medicine", "primary": True}],
    "addresses": [{"address_purpose": "LOCATION", "address_1": "123 Oak St", "city": "EDISON",
                   "state": "NJ", "postal_code": "088201234", "telephone_number": "732-555-0100"}],
}]}


class _Resp:
    status_code = 200

    def json(self):
        return _SAMPLE


def test_profession_type_mapping():
    assert nppes._profession_type("General Dentist") == "dentist"
    assert nppes._profession_type("Pharmacy") == "pharmacy"
    assert nppes._profession_type("Internal Medicine") == "doctor"


def test_nppes_maps_a_provider(monkeypatch):
    monkeypatch.setattr(nppes.httpx, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(nppes.time, "sleep", lambda *_: None)
    cands = list(nppes.NppesScraper().scrape("NJ", surnames=["Patel"]))
    assert len(cands) == 1
    c = cands[0]
    assert c["source_name"] == "nppes" and c["source_id"] == "1234567890"
    assert "Patel" in c["name"] and "M.D" in c["name"]
    assert c["city"] == "Edison" and c["state"] == "NJ"
    assert c["profession_type"] == "doctor" and c["speciality"] == "Internal Medicine"
    assert c["lat"] is None and "Edison" in c["address_full"]


def test_coordless_records_get_city_disambiguated_keys():
    a = pp.clean_professional({"name": "Anil Patel", "city": "Edison", "state": "NJ",
                               "source_name": "nppes"})
    b = pp.clean_professional({"name": "Anil Patel", "city": "Dallas", "state": "TX",
                               "source_name": "nppes"})
    assert a["natural_key"] != b["natural_key"]   # same name, different city -> not merged
