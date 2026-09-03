from __future__ import annotations

from redline.map_render import BrailleMapRenderer, MapPoint, event_points


def _has_red_layer(map_text) -> bool:
    return any(
        color in str(span.style)
        for span in map_text.spans
        for color in ("#ff334f", "#c51f43", "#86172f")
    )


def _styled_cells(map_text, color: str) -> int:
    return sum(span.end - span.start for span in map_text.spans if color in str(span.style))


def test_braille_renderer_has_blue_base_and_separate_red_outbreak_layer():
    renderer = BrailleMapRenderer(width=60, height=20)

    base = renderer.render([], "world")
    outbreak = renderer.render([MapPoint("one", 1.0, 30.0)], "world")

    assert any("#24598f" in str(span.style) for span in base.spans)
    assert not _has_red_layer(base)
    assert _has_red_layer(outbreak)
    assert not any(character.isdigit() for character in outbreak.plain)


def test_nearby_outbreaks_remain_a_braille_mark_without_cluster_numbers():
    renderer = BrailleMapRenderer(width=60, height=20)
    map_text = renderer.render([MapPoint("one", 1.0, 30.0), MapPoint("two", 1.1, 30.1)], "world")

    assert _has_red_layer(map_text)
    assert not any(character.isdigit() for character in map_text.plain)


def test_braille_renderer_focus_hides_other_regions():
    renderer = BrailleMapRenderer(width=48, height=16)
    rwanda = MapPoint("rwanda", -1.9, 29.9)
    brazil = MapPoint("brazil", -14.2, -51.9)

    focused = renderer.render([rwanda, brazil], "africa")
    expected = renderer.render([rwanda], "africa")

    assert focused.plain == expected.plain
    assert focused.spans == expected.spans
    assert _has_red_layer(focused)


def test_world_map_preserves_geographic_aspect_ratio_in_terminal_cells():
    renderer = BrailleMapRenderer(width=80, height=30)
    lines = renderer.render([], "world").plain.splitlines()
    occupied_rows = [index for index, line in enumerate(lines) if line.strip()]

    assert len(lines) == 30
    assert all(len(line) == 80 for line in lines)
    # Braille has a 2x4 dot grid. A 2:1 world therefore occupies about 20 of 30 rows,
    # rather than being stretched vertically to fill the panel.
    assert 18 <= occupied_rows[-1] - occupied_rows[0] + 1 <= 22


def test_rd_context_never_becomes_an_outbreak_marker():
    rows = [
        {
            "event_id": "rd",
            "latitude": 48.4,
            "longitude": 31.2,
            "location_precision": "country",
            "source_category": "rd_blueprint",
            "disease_key": "ebola",
            "emergency": "none",
        },
        {
            "event_id": "outbreak",
            "latitude": -1.9,
            "longitude": 29.9,
            "location_precision": "country",
            "source_category": "who_don",
            "disease_key": "ebola",
            "emergency": "none",
        },
        {
            "event_id": "landing-page",
            "latitude": 48.4,
            "longitude": 31.2,
            "location_precision": "country",
            "source_category": "who_don",
            "disease_key": None,
            "emergency": "none",
        },
    ]

    assert [point.event_id for point in event_points(rows)] == ["outbreak"]


def test_global_context_never_becomes_a_map_point_even_with_coordinates():
    rows = [
        {
            "event_id": "global-context",
            "territory": "GLOBAL",
            "latitude": 20.0,
            "longitude": 10.0,
            "location_precision": "region",
            "source_category": "who_sitrep",
            "disease_key": "ebola",
            "emergency": "pheic",
            "map_status": "outbreak",
        }
    ]

    assert event_points(rows) == []


def test_same_disease_in_multiple_territories_uses_spread_intensity():
    rows = [
        {
            "event_id": f"event-{index}",
            "territory": territory,
            "latitude": latitude,
            "longitude": longitude,
            "location_precision": "country",
            "source_category": "who_don",
            "disease_key": "ebola",
            "emergency": "none",
            "map_status": "outbreak",
        }
        for index, (territory, latitude, longitude) in enumerate(
            (("Uganda", 1.3, 32.3), ("Rwanda", -1.9, 29.9))
        )
    ]

    points = event_points(rows)
    rendered = BrailleMapRenderer(width=60, height=20).render(points)

    assert all(point.intensity == 2 for point in points)
    assert any("#c51f43" in str(span.style) for span in rendered.spans)


def test_explicit_extinction_uses_a_filled_grey_braille_layer():
    renderer = BrailleMapRenderer(width=60, height=20)
    outbreak = renderer.render([MapPoint("outbreak", 1.0, 30.0)])
    extinction = renderer.render([MapPoint("extinction", 1.0, 30.0, map_status="extinction")])

    assert any("#737b8c" in str(span.style) for span in extinction.spans)
    assert sum(character != " " for character in extinction.plain) > sum(
        character != " " for character in outbreak.plain
    )


def test_spread_is_a_graduated_land_area_instead_of_an_outbreak_cross():
    renderer = BrailleMapRenderer(width=80, height=30)
    outbreak = renderer.render([MapPoint("outbreak", 10.0, 20.0)])
    regional = renderer.render(
        [MapPoint("regional", 10.0, 20.0, map_status="spread", map_scope="region")]
    )
    continental = renderer.render(
        [MapPoint("continental", 10.0, 20.0, map_status="spread", map_scope="continent")]
    )

    assert _styled_cells(outbreak, "#ff334f") < _styled_cells(regional, "#c51f43")
    assert _styled_cells(regional, "#c51f43") < _styled_cells(continental, "#86172f")


def test_global_extinction_greys_the_world_landmass_not_one_marker():
    renderer = BrailleMapRenderer(width=80, height=30)
    regional = renderer.render(
        [MapPoint("regional", 10.0, 20.0, map_status="extinction", map_scope="region")]
    )
    global_layer = renderer.render(
        [MapPoint("global", 10.0, 20.0, map_status="extinction", map_scope="global")]
    )

    assert _styled_cells(global_layer, "#737b8c") > _styled_cells(regional, "#737b8c") * 10


def test_event_points_preserve_explicit_simulation_map_scope():
    rows = [
        {
            "event_id": "synthetic-spread",
            "territory": "Eurasia",
            "latitude": 50.0,
            "longitude": 70.0,
            "location_precision": "region",
            "source_category": "test_scenario",
            "disease_key": "anthrax",
            "emergency": "regional",
            "map_status": "spread",
            "map_scope": "continent",
        }
    ]

    point = event_points(rows)[0]
    assert point.map_scope == "continent"
    assert point.intensity == 3
