"""Metro coverage: new diaspora hubs are present, every bbox is sane, and states map cleanly."""

from indo_usa_mcp.pipeline.scrapers import metros as M

_NEW = ["northern_virginia", "suburban_maryland", "sacramento", "minneapolis", "san_diego",
        "denver", "tampa", "orlando", "charlotte", "columbus", "portland", "las_vegas", "hartford"]

# Batch 4: Central Valley CA, university towns, and additional mid-size hubs.
_BATCH4 = ["fresno", "stockton", "bakersfield", "ann_arbor", "champaign", "west_lafayette",
           "college_station", "madison", "huntsville", "albuquerque", "greensboro", "buffalo",
           "fort_myers"]


def test_new_metros_present_and_state_mapped():
    for m in _NEW + _BATCH4:
        assert m in M.METROS, m
        assert M.state_for(m), m            # single-state, so state_for resolves without a point
    assert len(M.METROS) >= 70              # original + batches


def test_all_bboxes_well_formed():
    for name, box in M.METROS.items():
        s, w, n, e = box
        assert -90 <= s < n <= 90, f"{name} latitude"      # south below north
        assert -180 <= w < e <= 0, f"{name} longitude"     # west of east, US lng is negative


def test_every_metro_has_a_state_except_split_nyc():
    for name in M.METROS:
        if name == "nyc_nj":                # straddles NY/NJ — resolved by longitude at call time
            continue
        assert M.state_for(name), name


def test_scrape_regions_include_new_metros():
    assert "denver" in M.SCRAPE_REGIONS and "northern_virginia" in M.SCRAPE_REGIONS
    assert "usa" in M.SCRAPE_REGIONS


def test_scrape_set_rotates_and_keeps_priority():
    batch = M.scrape_set()
    assert set(batch) <= set(M.METROS)                  # only valid metros
    assert set(M._PRIORITY) <= set(batch)               # priority metros always included
    assert len(batch) < len(M.METROS)                   # it's a rotating subset, not everything
    assert batch == [m for m in M.METROS if m in batch]  # deterministic METROS order
