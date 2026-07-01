"""Chat query routing: consulate/visa/OCI -> services (where consulates live), priests -> temples,
without short-token collisions hijacking association/society queries."""

import indo_usa_mcp.assistant as a


def test_consulate_visa_routing():
    assert a._guess_vertical("indian consulate near me") == "services"
    assert a._guess_vertical("renew my passport") == "services"
    assert a._guess_vertical("oci card application") == "services"
    assert a._guess_vertical("document attestation") == "services"
    assert a._guess_vertical("visa appointment") == "services"


def test_priest_pandit_routing():
    assert a._guess_vertical("find a pandit for griha pravesh") == "temples"
    assert a._guess_vertical("priest for wedding puja") == "temples"
    assert a._guess_vertical("purohit for satyanarayan") == "temples"


def test_no_short_token_collisions():
    # 'oci card' has a space so it can't match 'assOCIation'; community/society still route right.
    assert a._guess_vertical("telugu association") == "community"
    assert a._guess_vertical("indian cultural society") != "services"
    # existing routing unaffected
    assert a._guess_vertical("immigration lawyer") == "legal"
    assert a._guess_vertical("biryani near plano") == "restaurants"
