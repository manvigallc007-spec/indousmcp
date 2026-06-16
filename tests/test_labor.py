"""DOL H-1B disclosure importer: wage normalization, filtering, aggregation, KB. No network/DB."""

import indo_usa_mcp.knowledge as K
import indo_usa_mcp.labor as L


def test_annual_wage_normalizes_units():
    assert L._annual_wage("150000", "Year") == 150000.0
    assert L._annual_wage("72.12", "Hour") == 72.12 * 2080
    assert L._annual_wage("3,000", "Week") == 3000 * 52        # commas tolerated
    assert L._annual_wage("0", "Year") is None                # non-positive dropped
    assert L._annual_wage("abc", "Year") is None
    assert L._annual_wage("999999999", "Year") is None        # above the sane cap


def test_is_certified():
    assert L._is_certified("Certified") and L._is_certified("Certified - Withdrawn")
    assert not L._is_certified("Denied") and not L._is_certified("Withdrawn")


def _write_csv(path):
    rows = [
        "VISA_CLASS,CASE_STATUS,EMPLOYER_NAME,SOC_TITLE,WAGE_RATE_OF_PAY_FROM,WAGE_UNIT_OF_PAY,WORKSITE_STATE",
        "H-1B,Certified,Infosys Limited,Software Developers,150000,Year,CA",
        "H-1B,Certified - Withdrawn,Infosys Limited,Software Developers,72.12,Hour,CA",
        "H-1B,Certified,Tata Consultancy,Computer Systems Analysts,110000,Year,TX",
        "E-3 Australian,Certified,Some Firm,Software Developers,160000,Year,NY",   # excluded: not H-1B
        "H-1B,Denied,Reject Corp,Software Developers,90000,Year,WA",               # excluded: not certified
    ]
    path.write_text("\n".join(rows), encoding="utf-8")
    return str(path)


def test_import_disclosure_aggregates_and_feeds_kb(tmp_path, monkeypatch):
    csv_path = _write_csv(tmp_path / "h1b.csv")
    saved = []
    monkeypatch.setattr(K, "upsert_document", lambda **kw: (saved.append(kw) or {"ok": True}))
    out = L.import_disclosure(source=csv_path, fiscal_year="2024")
    assert out["ok"] and out["certified_h1b"] == 3        # 2 Infosys (incl. withdrawn) + 1 TCS
    assert out["employers"] == 2 and out["occupations"] == 2
    assert out["kb_documents"] == 3                         # employers, wages, states
    assert {kw["source_ref"] for kw in saved} == {"h1b:employers", "h1b:wages", "h1b:states"}
    emp = next(kw for kw in saved if kw["source_ref"] == "h1b:employers")
    assert "Infosys Limited (2)" in emp["content"]          # top sponsor by certified count
    wage = next(kw for kw in saved if kw["source_ref"] == "h1b:wages")
    assert "Software Developers" in wage["content"] and "$150,0" in wage["content"]


def test_import_disclosure_skips_without_source(monkeypatch):
    monkeypatch.setattr(L.settings, "dol_h1b_disclosure_url", "")
    assert L.import_disclosure()["skipped"] == "no_source"
