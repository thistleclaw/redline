from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files

from rich.text import Text

from redline.geography import REGION_BOUNDS

LAND_STYLE = "#24598f"
OUTBREAK_STYLE = "bold #ff334f"
SPREAD_STYLE = "bold #c51f43"
INTENSE_SPREAD_STYLE = "bold #86172f"
EXTINCTION_STYLE = "bold #737b8c"
OUTBREAK_STYLES = {1: OUTBREAK_STYLE, 2: SPREAD_STYLE, 3: INTENSE_SPREAD_STYLE}
SELECTED_OUTBREAK_STYLES = {
    level: f"{style} on #3b0710" for level, style in OUTBREAK_STYLES.items()
}
SELECTED_EXTINCTION_STYLE = "bold #a1a8b5 on #252a33"
NATURAL_EARTH_FILE = "data/ne_110m_land_v5.1.2.geojson"
GLOBAL_TERRITORIES = {
    "global",
    "world",
    "worldwide",
    "international",
    "весь мир",
    "общий мир",
    "глобально",
}
NON_GEOGRAPHIC_CATEGORIES = {"rd_blueprint", "health_emergency_dashboard", "risk_assessment"}

BRAILLE_BITS = (
    (0, 0, 0x01),
    (0, 1, 0x02),
    (0, 2, 0x04),
    (0, 3, 0x40),
    (1, 0, 0x08),
    (1, 1, 0x10),
    (1, 2, 0x20),
    (1, 3, 0x80),
)
BRAILLE_BIT = {(x, y): bit for x, y, bit in BRAILLE_BITS}

Coordinate = tuple[float, float]
Bounds = tuple[float, float, float, float]
Layer = Sequence[Sequence[int]]


def _row_value(row: Mapping[str, object], key: str, default: object = None) -> object:
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


@dataclass(frozen=True, slots=True)
class MapPoint:
    event_id: str
    latitude: float
    longitude: float
    selected: bool = False
    map_status: str = "outbreak"
    intensity: int = 1
    map_scope: str = "local"


@dataclass(frozen=True, slots=True)
class _Viewport:
    bounds: Bounds
    dot_width: int
    dot_height: int
    scale: float
    offset_x: float
    offset_y: float

    @classmethod
    def fitted(cls, width: int, height: int, bounds: Bounds) -> _Viewport:
        """Fit geographic degrees into square Braille dots without stretching the map."""
        dot_width = width * 2
        dot_height = height * 4
        left, bottom, right, top = bounds
        padding = 1
        usable_width = max(1, dot_width - 1 - padding * 2)
        usable_height = max(1, dot_height - 1 - padding * 2)
        scale = min(usable_width / (right - left), usable_height / (top - bottom))
        map_width = (right - left) * scale
        map_height = (top - bottom) * scale
        return cls(
            bounds=bounds,
            dot_width=dot_width,
            dot_height=dot_height,
            scale=scale,
            offset_x=(dot_width - 1 - map_width) / 2,
            offset_y=(dot_height - 1 - map_height) / 2,
        )

    def project(self, longitude: float, latitude: float) -> tuple[int, int]:
        left, _bottom, _right, top = self.bounds
        x = round(self.offset_x + (longitude - left) * self.scale)
        y = round(self.offset_y + (top - latitude) * self.scale)
        return x, y


@lru_cache(maxsize=1)
def _land_rings() -> tuple[tuple[Coordinate, ...], ...]:
    """Load the pinned Natural Earth 1:110m physical land geometry."""
    resource = files("redline").joinpath(NATURAL_EARTH_FILE)
    payload = json.loads(resource.read_text(encoding="utf-8"))
    rings: list[tuple[Coordinate, ...]] = []
    for feature in payload["features"]:
        geometry = feature.get("geometry") or {}
        if geometry.get("type") != "Polygon":
            continue
        for raw_ring in geometry.get("coordinates", []):
            ring = tuple((float(point[0]), float(point[1])) for point in raw_ring)
            if len(ring) >= 2:
                rings.append(ring)
    return tuple(rings)


def _clip_segment(
    start: Coordinate, end: Coordinate, bounds: Bounds
) -> tuple[Coordinate, Coordinate] | None:
    """Liang-Barsky clipping keeps focused-region rendering inside the viewport."""
    left, bottom, right, top = bounds
    x0, y0 = start
    x1, y1 = end
    dx = x1 - x0
    dy = y1 - y0
    lower = 0.0
    upper = 1.0
    for direction, distance in (
        (-dx, x0 - left),
        (dx, right - x0),
        (-dy, y0 - bottom),
        (dy, top - y0),
    ):
        if direction == 0:
            if distance < 0:
                return None
            continue
        ratio = distance / direction
        if direction < 0:
            lower = max(lower, ratio)
        else:
            upper = min(upper, ratio)
        if lower > upper:
            return None
    return (x0 + lower * dx, y0 + lower * dy), (x0 + upper * dx, y0 + upper * dy)


def _line(start: tuple[int, int], end: tuple[int, int]) -> Iterator[tuple[int, int]]:
    """Yield a continuous one-dot coastline in the Braille pixel grid."""
    x0, y0 = start
    x1, y1 = end
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    error = dx + dy
    while True:
        yield x0, y0
        if x0 == x1 and y0 == y1:
            return
        doubled = error * 2
        if doubled >= dy:
            error += dy
            x0 += sx
        if doubled <= dx:
            error += dx
            y0 += sy


def _set_dot(layer: list[list[int]], x: int, y: int, width: int, height: int) -> None:
    if not (0 <= x < width * 2 and 0 <= y < height * 4):
        return
    layer[y // 4][x // 2] |= BRAILLE_BIT[(x % 2, y % 4)]


@lru_cache(maxsize=32)
def _cached_land_layer(width: int, height: int, bounds: Bounds) -> tuple[tuple[int, ...], ...]:
    """Rasterize each base-map size once; event-layer refreshes remain effectively instant."""
    viewport = _Viewport.fitted(width, height, bounds)
    layer = [[0 for _ in range(width)] for _ in range(height)]
    for ring in _land_rings():
        for start, end in zip(ring, ring[1:], strict=False):
            # Natural Earth splits land at the date line. This avoids an accidental
            # horizontal line through the whole map if a ring ever wraps around.
            if abs(end[0] - start[0]) > 180:
                continue
            clipped = _clip_segment(start, end, viewport.bounds)
            if clipped is None:
                continue
            projected_start = viewport.project(*clipped[0])
            projected_end = viewport.project(*clipped[1])
            for x, y in _line(projected_start, projected_end):
                _set_dot(layer, x, y, width, height)
    return tuple(tuple(row) for row in layer)


@lru_cache(maxsize=32)
def _cached_land_fill_layer(width: int, height: int, bounds: Bounds) -> tuple[tuple[int, ...], ...]:
    """Rasterize polygon interiors so area effects color land instead of arbitrary discs."""
    viewport = _Viewport.fitted(width, height, bounds)
    layer = [[0 for _ in range(width)] for _ in range(height)]
    for ring in _land_rings():
        projected = tuple(viewport.project(*point) for point in ring)
        if len(projected) < 3:
            continue
        for y in range(viewport.dot_height):
            intersections: list[float] = []
            for (x0, y0), (x1, y1) in zip(projected, projected[1:], strict=False):
                if y0 == y1 or not (min(y0, y1) <= y < max(y0, y1)):
                    continue
                intersections.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
            intersections.sort()
            for start, end in zip(intersections[0::2], intersections[1::2], strict=False):
                for x in range(max(0, round(start)), min(viewport.dot_width, round(end) + 1)):
                    _set_dot(layer, x, y, width, height)
    return tuple(tuple(row) for row in layer)


def _has_dot(layer: Layer, x: int, y: int, width: int, height: int) -> bool:
    if not (0 <= x < width * 2 and 0 <= y < height * 4):
        return False
    return bool(layer[y // 4][x // 2] & BRAILLE_BIT[(x % 2, y % 4)])


class BrailleMapRenderer:
    """Render coastline, graduated red outbreak signals, and grey extinction areas."""

    def __init__(self, width: int = 66, height: int = 25) -> None:
        # The widget owns the available geometry. Never render a larger canvas than it has,
        # otherwise Textual crops the coastline after a terminal resize.
        self.width = max(1, width)
        self.height = max(1, height)

    def render(self, points: Iterable[MapPoint], focus: str = "world") -> Text:
        bounds = REGION_BOUNDS.get(focus.casefold(), REGION_BOUNDS["world"])
        viewport = _Viewport.fitted(self.width, self.height, bounds)
        land_layer = _cached_land_layer(self.width, self.height, bounds)
        land_fill_layer = _cached_land_fill_layer(self.width, self.height, bounds)
        outbreak_layer = [[0 for _ in range(self.width)] for _ in range(self.height)]
        outbreak_levels = [[0 for _ in range(self.width)] for _ in range(self.height)]
        extinction_layer = [[0 for _ in range(self.width)] for _ in range(self.height)]
        selected_cells: set[tuple[int, int]] = set()

        self._draw_signals(
            outbreak_layer,
            outbreak_levels,
            extinction_layer,
            selected_cells,
            viewport,
            land_fill_layer,
            points,
        )
        return self._compose(
            land_layer,
            outbreak_layer,
            outbreak_levels,
            extinction_layer,
            selected_cells,
        )

    def _draw_signals(
        self,
        outbreak_layer: list[list[int]],
        outbreak_levels: list[list[int]],
        extinction_layer: list[list[int]],
        selected_cells: set[tuple[int, int]],
        viewport: _Viewport,
        land_fill_layer: Layer,
        points: Iterable[MapPoint],
    ) -> None:
        left, bottom, right, top = viewport.bounds
        for point in points:
            if not (left <= point.longitude <= right and bottom <= point.latitude <= top):
                continue
            center_x, center_y = viewport.project(point.longitude, point.latitude)
            is_area = point.map_status in {"spread", "extinction"}
            if is_area:
                target_layer = (
                    extinction_layer if point.map_status == "extinction" else outbreak_layer
                )
                if point.map_scope == "global":
                    offsets = (
                        (x - center_x, y - center_y)
                        for y in range(viewport.dot_height)
                        for x in range(viewport.dot_width)
                    )
                else:
                    radius_degrees = {
                        "local": 2.0,
                        "country": 6.0,
                        "region": 16.0,
                        "continent": 42.0,
                    }.get(point.map_scope, 16.0)
                    radius = max(3, round(radius_degrees * viewport.scale))
                    offsets = (
                        (delta_x, delta_y)
                        for delta_y in range(-radius, radius + 1)
                        for delta_x in range(-radius, radius + 1)
                        if delta_x * delta_x + delta_y * delta_y <= radius * radius
                    )
            else:
                # A five-dot Braille cross is legible without becoming a text glyph or label.
                offsets = iter(((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)))
                target_layer = outbreak_layer
            touched_cells: set[tuple[int, int]] = set()
            for delta_x, delta_y in offsets:
                x = center_x + delta_x
                y = center_y + delta_y
                if is_area and not _has_dot(land_fill_layer, x, y, self.width, self.height):
                    continue
                _set_dot(target_layer, x, y, self.width, self.height)
                if 0 <= x < self.width * 2 and 0 <= y < self.height * 4:
                    cell = (y // 4, x // 2)
                    touched_cells.add(cell)
                    if point.selected and (x, y) == (center_x, center_y):
                        selected_cells.add(cell)
            if point.map_status != "extinction":
                signal_intensity = max(
                    point.intensity,
                    {
                        "local": 1,
                        "country": 1,
                        "region": 2,
                        "continent": 3,
                        "global": 3,
                    }.get(point.map_scope, 1),
                    2 if point.map_status == "spread" else 1,
                )
                for row, column in touched_cells:
                    prior = outbreak_levels[row][column]
                    outbreak_levels[row][column] = min(
                        3, max(signal_intensity, prior + 1 if prior else 1)
                    )

    def _compose(
        self,
        land_layer: Layer,
        outbreak_layer: list[list[int]],
        outbreak_levels: list[list[int]],
        extinction_layer: list[list[int]],
        selected_cells: set[tuple[int, int]],
    ) -> Text:
        result = Text()
        for row in range(self.height):
            for column in range(self.width):
                land_mask = land_layer[row][column]
                outbreak_mask = outbreak_layer[row][column]
                extinction_mask = extinction_layer[row][column]
                mask = land_mask | outbreak_mask | extinction_mask
                if not mask:
                    result.append(" ")
                elif extinction_mask:
                    style = (
                        SELECTED_EXTINCTION_STYLE
                        if (row, column) in selected_cells
                        else EXTINCTION_STYLE
                    )
                    result.append(chr(0x2800 + mask), style=style)
                elif outbreak_mask:
                    level = max(1, outbreak_levels[row][column])
                    styles = (
                        SELECTED_OUTBREAK_STYLES
                        if (row, column) in selected_cells
                        else OUTBREAK_STYLES
                    )
                    style = styles[level]
                    result.append(chr(0x2800 + mask), style=style)
                else:
                    result.append(chr(0x2800 + land_mask), style=LAND_STYLE)
            if row < self.height - 1:
                result.append("\n")
        return result


def event_points(
    rows: Iterable[Mapping[str, object]], selected_id: str | None = None
) -> list[MapPoint]:
    candidates: list[Mapping[str, object]] = []
    disease_territories: dict[str, set[str]] = {}
    for row in rows:
        latitude, longitude = row["latitude"], row["longitude"]
        territory = str(_row_value(row, "territory", "") or "").strip()
        precision = str(_row_value(row, "location_precision", "unknown") or "unknown")
        # Context documents and generic landing pages are not outbreaks, even if their
        # navigation text happens to mention a country. A map signal needs a recognized
        # disease or an explicitly declared emergency.
        if (
            latitude is None
            or longitude is None
            or territory.casefold() in GLOBAL_TERRITORIES
            or precision == "unknown"
            or row["source_category"] in NON_GEOGRAPHIC_CATEGORIES
            or (not row["disease_key"] and row["emergency"] == "none")
        ):
            continue
        candidates.append(row)
        if row["disease_key"] and territory:
            disease_territories.setdefault(str(row["disease_key"]), set()).add(territory.casefold())

    points: list[MapPoint] = []
    for row in candidates:
        disease_key = str(row["disease_key"] or "")
        territory_count = len(disease_territories.get(disease_key, ()))
        map_status = str(_row_value(row, "map_status", "outbreak") or "outbreak")
        map_scope = str(_row_value(row, "map_scope", "local") or "local")
        scope_intensity = {"local": 1, "country": 1, "region": 2, "continent": 3, "global": 3}
        intensity = max(
            scope_intensity.get(map_scope, 1),
            2 if map_status == "spread" or territory_count >= 2 else 1,
        )
        if territory_count >= 4:
            intensity = 3
        points.append(
            MapPoint(
                event_id=str(row["event_id"]),
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                selected=str(row["event_id"]) == selected_id,
                map_status=map_status,
                intensity=intensity,
                map_scope=map_scope,
            )
        )
    return points
