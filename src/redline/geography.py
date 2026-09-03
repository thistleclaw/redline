from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Place:
    label: str
    latitude: float
    longitude: float
    region: str


# Curated centroids used only when a source names a country but supplies no point.
PLACES: dict[str, Place] = {
    "afghanistan": Place("Afghanistan", 33.9, 67.7, "asia"),
    "angola": Place("Angola", -11.2, 17.9, "africa"),
    "brazil": Place("Brazil", -14.2, -51.9, "americas"),
    "burundi": Place("Burundi", -3.4, 29.9, "africa"),
    "cameroon": Place("Cameroon", 7.4, 12.4, "africa"),
    "canada": Place("Canada", 56.1, -106.3, "americas"),
    "china": Place("China", 35.9, 104.2, "asia"),
    "colombia": Place("Colombia", 4.6, -74.3, "americas"),
    "congo": Place("Republic of the Congo", -0.2, 15.8, "africa"),
    "democratic republic of the congo": Place(
        "Democratic Republic of the Congo", -4.0, 21.8, "africa"
    ),
    "drc": Place("Democratic Republic of the Congo", -4.0, 21.8, "africa"),
    "ethiopia": Place("Ethiopia", 9.1, 40.5, "africa"),
    "france": Place("France", 46.2, 2.2, "europe"),
    "germany": Place("Germany", 51.2, 10.4, "europe"),
    "india": Place("India", 20.6, 78.9, "asia"),
    "italy": Place("Italy", 41.9, 12.6, "europe"),
    "japan": Place("Japan", 36.2, 138.3, "asia"),
    "kenya": Place("Kenya", -0.0, 37.9, "africa"),
    "mexico": Place("Mexico", 23.6, -102.6, "americas"),
    "nigeria": Place("Nigeria", 9.1, 8.7, "africa"),
    "pakistan": Place("Pakistan", 30.4, 69.3, "asia"),
    "russia": Place("Russia", 61.5, 105.3, "europe"),
    "russian federation": Place("Russia", 61.5, 105.3, "europe"),
    "rwanda": Place("Rwanda", -1.9, 29.9, "africa"),
    "south africa": Place("South Africa", -30.6, 22.9, "africa"),
    "spain": Place("Spain", 40.5, -3.7, "europe"),
    "sudan": Place("Sudan", 12.9, 30.2, "africa"),
    "thailand": Place("Thailand", 15.9, 100.9, "asia"),
    "uganda": Place("Uganda", 1.4, 32.3, "africa"),
    "ukraine": Place("Ukraine", 48.4, 31.2, "europe"),
    "united kingdom": Place("United Kingdom", 55.4, -3.4, "europe"),
    "united states": Place("United States", 39.8, -98.6, "americas"),
    "usa": Place("United States", 39.8, -98.6, "americas"),
    "venezuela": Place("Venezuela", 6.4, -66.6, "americas"),
}


REGION_BOUNDS: dict[str, tuple[float, float, float, float]] = {
    "world": (-180.0, -90.0, 180.0, 90.0),
    "africa": (-20.0, -38.0, 55.0, 38.0),
    "americas": (-170.0, -58.0, -30.0, 78.0),
    "asia": (20.0, -10.0, 180.0, 82.0),
    "europe": (-25.0, 34.0, 65.0, 73.0),
    "oceania": (105.0, -50.0, 180.0, 5.0),
}


def find_place(text: str) -> Place | None:
    lowered = text.casefold()
    matches = [(key, place) for key, place in PLACES.items() if key in lowered]
    return max(matches, key=lambda item: len(item[0]))[1] if matches else None
