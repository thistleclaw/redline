from redline.aliases import find_disease


def test_disease_aliases_require_token_boundaries_and_choose_specific_match():
    assert find_disease("cash5 reconciliation") is None
    assert find_disease("H5 avian influenza outbreak").key == "avian_influenza"
    assert find_disease("SARS-CoV update").key == "mers_sars"
