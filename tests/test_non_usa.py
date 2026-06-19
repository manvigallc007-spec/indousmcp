"""Geographic guardrail: flag listings physically OUTSIDE the USA (foreign scrape bleed).

Pure-function tests for verticals._non_usa_reason / _in_us_bbox — no DB, no network. Coordinates
are authoritative; the scraper-defaulted country='USA' is weak, so a non-US state only counts as a
'review' hint when there are no coordinates to confirm."""

import indo_usa_mcp.verticals as v


def test_us_locations_pass():
    # Real US points across the lower 48, Alaska, Hawaii, Puerto Rico.
    for country, st, la, lo in [
        ("USA", "TX", 32.7767, -96.7970),   # Dallas
        ("USA", "CA", 37.3382, -121.8863),  # San Jose
        ("USA", "NY", 40.7128, -74.0060),   # New York
        ("USA", "HI", 21.3069, -157.8583),  # Honolulu
        ("USA", "AK", 61.2181, -149.9003),  # Anchorage
        ("USA", "PR", 18.4655, -66.1057),   # San Juan
        ("USA", "ME", 44.8012, -68.7778),   # Bangor (east edge)
    ]:
        assert v._non_usa_reason(country, st, la, lo) is None, (country, la, lo)


def test_foreign_coords_are_high_confidence():
    # Country defaulted to 'USA' by the scraper, but the coordinates are clearly abroad.
    for la, lo in [
        (17.3850, 78.4867),   # Hyderabad, India
        (19.0760, 72.8777),   # Mumbai, India
        (51.5074, -0.1278),   # London, UK
        (19.4326, -99.1332),  # Mexico City
        (28.6139, 77.2090),   # New Delhi
        (1.3521, 103.8198),   # Singapore
    ]:
        r = v._non_usa_reason("USA", "TX", la, lo)
        assert r is not None and r[1] == "high", (la, lo, r)


def test_explicit_foreign_country_beats_in_box_coords():
    # An explicit non-US country wins even when the rectangular box happens to contain the coords
    # (southern-Ontario Toronto sits inside the US lat/lng rectangle).
    assert v._non_usa_reason("Canada", "ON", 43.6532, -79.3832)[1] == "high"


def test_border_city_with_us_labels_is_a_known_gap():
    # KNOWN LIMITATION: a Canadian border city tagged country='USA' + a US state + real (US-range)
    # coords is NOT flagged — a rectangular box can't separate southern Ontario from the US. Such
    # rows are rare (OSM scrapes are US-bbox-bound; Wikidata is country-scoped). The same row with a
    # non-US country, or a non-US state and no coords, IS caught (see the tests above/below).
    assert v._non_usa_reason("USA", "TX", 43.6532, -79.3832) is None


def test_explicit_foreign_country_is_high_confidence():
    for country in ["India", "Canada", "United Kingdom", "Mexico"]:
        r = v._non_usa_reason(country, None, None, None)
        assert r is not None and r[1] == "high", country


def test_non_us_state_without_coords_is_review():
    for state in ["Maharashtra", "Telangana", "Ontario", "England"]:
        r = v._non_usa_reason("USA", state, None, None)
        assert r is not None and r[1] == "review", state


def test_null_island_coords_not_treated_as_foreign():
    # 0,0 is junk/missing coords, not "abroad" — fall through to country/state (both US here).
    assert v._non_usa_reason("USA", "TX", 0, 0) is None


def test_clean_us_records_without_coords_pass():
    assert v._non_usa_reason("USA", "TX", None, None) is None
    assert v._non_usa_reason("USA", "California", None, None) is None   # full name normalizes to CA
    assert v._non_usa_reason(None, None, None, None) is None            # nothing to go on -> keep


def test_us_country_aliases_pass():
    for c in ["USA", "us", "United States", "United States of America", "America"]:
        assert v._non_usa_reason(c, "TX", None, None) is None


def test_in_us_bbox_basic():
    assert v._in_us_bbox(40.0, -100.0) is True     # Kansas-ish
    assert v._in_us_bbox(17.385, 78.486) is False  # Hyderabad
    assert v._in_us_bbox(0.0, 0.0) is False        # Null Island


def test_indian_city_without_coords_is_review():
    # The gap city-matching closes: country defaulted 'USA', a (wrong) US state, NO coords, but the
    # city is literally an Indian city. Telugu-belt towns included for this audience.
    for city in ["Hyderabad", "Mumbai", "Bengaluru", "Vijayawada", "Visakhapatnam", "Guntur",
                 "Warangal", "Tirupati", "New Delhi", "kolkata", "  Pune  "]:
        r = v._non_usa_reason("USA", "TX", None, None, city)
        assert r is not None and r[1] == "review", city


def test_us_cities_and_ambiguous_names_not_flagged():
    # Real US cities pass; Indian names with notable US namesakes are deliberately excluded.
    for city in ["Dallas", "Plano", "Irving", "Fremont", "Edison", "Jersey City",
                 "Delhi", "Salem", "Madras", None, ""]:
        assert v._non_usa_reason("USA", "TX", None, None, city) is None, city


def test_coords_outrank_city_field():
    # Usable US coords are authoritative even if the city text looks Indian (bad city data, real US).
    assert v._non_usa_reason("USA", "TX", 32.7767, -96.7970, "Hyderabad") is None
    # ...and an Indian city WITH Indian coords is high (coords), not just review.
    assert v._non_usa_reason("USA", "TX", 17.385, 78.486, "Hyderabad")[1] == "high"


def test_junk_coords_fall_through_to_city():
    # 0,0 placeholder coords must not mask an Indian city -> still surfaced for review.
    assert v._non_usa_reason("USA", "TX", 0, 0, "Mumbai")[1] == "review"


def test_is_indian_city_helper():
    assert v._is_indian_city("Hyderabad") is True
    assert v._is_indian_city("HYDERABAD") is True
    assert v._is_indian_city("Dallas") is False
    assert v._is_indian_city(None) is False
    assert v._is_indian_city("") is False
