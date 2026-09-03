from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from geonamescache import GeonamesCache

from redline.models import LocationPrecision


@dataclass(frozen=True, slots=True)
class Place:
    label: str
    latitude: float
    longitude: float
    region: str
    precision: LocationPrecision
    location_key: str
    country_code: str


REGION_BOUNDS: dict[str, tuple[float, float, float, float]] = {
    "world": (-180.0, -90.0, 180.0, 90.0),
    "africa": (-20.0, -38.0, 55.0, 38.0),
    "americas": (-170.0, -58.0, -30.0, 78.0),
    "asia": (20.0, -10.0, 180.0, 82.0),
    "europe": (-25.0, 34.0, 65.0, 73.0),
    "oceania": (105.0, -50.0, 180.0, 5.0),
}

CONTINENT_REGIONS = {
    "AF": "africa",
    "AS": "asia",
    "EU": "europe",
    "NA": "americas",
    "SA": "americas",
    "OC": "oceania",
    "AN": "antarctica",
}

# Country centroids are preferable to capital coordinates for the most common source locations.
COUNTRY_CENTROIDS = {
    "AF": (33.9, 67.7),
    "AO": (-11.2, 17.9),
    "BR": (-14.2, -51.9),
    "BI": (-3.4, 29.9),
    "CM": (7.4, 12.4),
    "CA": (56.1, -106.3),
    "CN": (35.9, 104.2),
    "CO": (4.6, -74.3),
    "CG": (-0.2, 15.8),
    "CD": (-4.0, 21.8),
    "ET": (9.1, 40.5),
    "FR": (46.2, 2.2),
    "DE": (51.2, 10.4),
    "IN": (20.6, 78.9),
    "IT": (41.9, 12.6),
    "JP": (36.2, 138.3),
    "KE": (0.0, 37.9),
    "MX": (23.6, -102.6),
    "NG": (9.1, 8.7),
    "PK": (30.4, 69.3),
    "RU": (61.5, 105.3),
    "RW": (-1.9, 29.9),
    "ZA": (-30.6, 22.9),
    "ES": (40.5, -3.7),
    "SD": (12.9, 30.2),
    "TH": (15.9, 100.9),
    "UG": (1.4, 32.3),
    "UA": (48.4, 31.2),
    "GB": (55.4, -3.4),
    "US": (39.8, -98.6),
    "VE": (6.4, -66.6),
}

COUNTRY_ALIASES = {
    "drc": "CD",
    "russian federation": "RU",
    "usa": "US",
    "россия": "RU",
    "российская федерация": "RU",
    "украина": "UA",
    "беларусь": "BY",
    "казахстан": "KZ",
    "китай": "CN",
    "индия": "IN",
    "сша": "US",
    "соединенные штаты": "US",
    "великобритания": "GB",
    "франция": "FR",
    "германия": "DE",
    "италия": "IT",
    "испания": "ES",
    "япония": "JP",
}

WORD = re.compile(r"[^\W_]+(?:[’'’-][^\W_]+)*", re.UNICODE)
CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)


def _normal(value: str) -> str:
    return " ".join(WORD.findall(value.casefold().replace("ё", "е")))


def _russian_inflections(value: str) -> tuple[str, ...]:
    normalized = _normal(value)
    if not normalized or re.search(r"[^а-я -]", normalized):
        return ()
    if normalized.endswith("ск"):
        return normalized + "а", normalized + "е", normalized + "ом"
    if normalized.endswith("а"):
        return normalized[:-1] + "е", normalized[:-1] + "ы", normalized[:-1] + "у"
    if normalized.endswith("я"):
        return normalized[:-1] + "е", normalized[:-1] + "и", normalized[:-1] + "ю"
    if normalized.endswith("ь"):
        return normalized[:-1] + "и", normalized[:-1] + "ью"
    return ()


@lru_cache(maxsize=1)
def _place_index() -> dict[str, tuple[Place, ...]]:
    cache = GeonamesCache(min_city_population=15_000)
    countries = cache.get_countries()
    cities = tuple(cache.get_cities().values())
    capitals = {(str(city["countrycode"]), _normal(str(city["name"]))): city for city in cities}
    index: dict[str, list[Place]] = {}
    countries_by_code = {str(code): value for code, value in countries.items()}
    country_places: dict[str, Place] = {}

    def add(name: str, place: Place) -> None:
        normalized = _normal(name)
        if len(normalized) < 3 or normalized.isdigit():
            return
        bucket = index.setdefault(normalized, [])
        if place not in bucket:
            bucket.append(place)

    def add_name(name: str, place: Place) -> None:
        add(name, place)
        for inflection in _russian_inflections(name):
            add(inflection, place)

    for code, country in countries_by_code.items():
        coordinates = COUNTRY_CENTROIDS.get(code)
        if coordinates is None:
            capital = capitals.get((code, _normal(str(country.get("capital", "")))))
            if capital is None:
                continue
            coordinates = float(capital["latitude"]), float(capital["longitude"])
        place = Place(
            str(country["name"]),
            coordinates[0],
            coordinates[1],
            CONTINENT_REGIONS.get(str(country.get("continentcode", "")), "world"),
            LocationPrecision.COUNTRY,
            f"country:{code}",
            code,
        )
        country_places[code] = place
        add_name(str(country["name"]), place)

    for alias, code in COUNTRY_ALIASES.items():
        if place := country_places.get(code):
            add_name(alias, place)

    for city in cities:
        code = str(city["countrycode"])
        country = countries_by_code.get(code, {})
        place = Place(
            f"{city['name']}, {country.get('name', code)}",
            float(city["latitude"]),
            float(city["longitude"]),
            CONTINENT_REGIONS.get(str(country.get("continentcode", "")), "world"),
            LocationPrecision.POINT,
            f"city:{city['geonameid']}",
            code,
        )
        add_name(str(city["name"]), place)
        for alias in city.get("alternatenames") or ():
            # Primary GeoNames spellings cover normal English source text. Retaining the
            # Cyrillic alternatives adds Russian input without duplicating every world script.
            if CYRILLIC.search(str(alias)):
                add_name(str(alias), place)

    return {name: tuple(places) for name, places in index.items()}


def find_place(text: str) -> Place | None:
    tokens = WORD.findall(text.replace("ё", "е"))
    if not tokens:
        return None
    index = _place_index()
    matches: list[tuple[int, int, int, Place]] = []
    for size in range(min(7, len(tokens)), 0, -1):
        for start in range(len(tokens) - size + 1):
            raw_tokens = tokens[start : start + size]
            phrase = _normal(" ".join(raw_tokens))
            for place in index.get(phrase, ()):
                # A lowercase single word such as "reading" is not enough to assert a city.
                if (
                    size == 1
                    and place.precision is LocationPrecision.POINT
                    and not raw_tokens[0][:1].isupper()
                ):
                    continue
                precision_rank = 2 if place.precision is LocationPrecision.POINT else 1
                matches.append((size, precision_rank, len(phrase), place))
        if matches:
            break
    return max(matches, key=lambda match: match[:3])[3] if matches else None


def places_overlap(left: Place | None, right: Place | None) -> bool:
    if left is None or right is None:
        return False
    if left.location_key == right.location_key:
        return True
    if left.country_code != right.country_code:
        return False
    return (
        left.precision is LocationPrecision.COUNTRY or right.precision is LocationPrecision.COUNTRY
    )


def normalize_place_name(value: str) -> str:
    return _normal(value)
