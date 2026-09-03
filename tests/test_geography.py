from redline.geography import find_place, places_overlap


def test_offline_gazetteer_resolves_starobilsk_aliases_and_inflections():
    english = find_place("Starobilsk")
    russian = find_place("Старобельск")
    inflected = find_place("Новых случаев в Старобельске не зарегистрировано")

    assert english is not None
    assert english.location_key == "city:692832"
    assert russian == english
    assert inflected == english
    assert round(english.latitude, 5) == 49.27881
    assert round(english.longitude, 4) == 38.9075


def test_country_watch_region_contains_a_city_but_not_another_country():
    assert places_overlap(find_place("Старобельск"), find_place("Украина"))
    assert not places_overlap(
        find_place("Democratic Republic of the Congo"), find_place("Republic of the Congo")
    )


def test_lowercase_common_word_is_not_treated_as_a_city():
    assert find_place("reading the weekly report") is None


def test_common_lowercase_word_is_not_interpreted_as_an_iso_country_code():
    assert find_place("This intervention can reduce exposure") is None
