"""Deterministic screen-space placement of names on point-history lines."""

from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, replace
from itertools import combinations, islice, permutations, product
from math import isfinite
from typing import Literal

from doppelkopf_app.ui.chart_styles import PlayerLineStyle

_EDGE = 3.0
_GAP = 4.0
_POINT_GAP = 6.0
_MIN_FONT = 11.0
_HALO = 2.0
# Some final glyphs (for example bold "f") extend beyond their measured advance.
_GLYPH_OVERHANG = 2.0
_MIN_END_MARGIN = 12.0
# A 3 px history stroke plus half a pixel of separation from the text halo.
_CURVE_PADDING = 2.0
# Two coincident 3 px strokes do not visibly separate a name from its curve.
_LEADER_SEPARATION = 3.0
_CLEARANCE = 0.01
_MOBILE_WIDTH = 600.0
_NEARBY_SHIFT = 6.0
# Remove the existing halo/gap reserve first; the final step allows at most
# 2 px of the 3 px curve stroke inside the measured text ink.
_MOBILE_TOLERANCES = (0.0, 2.0, 3.5, 4.5)
_MOBILE_ANCHORS = 8
_Side = Literal["above", "below"]


@dataclass(frozen=True, slots=True)
class PlotMetrics:
    """Actual plot dimensions and measured name widths, all in CSS pixels."""

    width: float
    height: float
    font_size: float
    text_widths: dict[int, float]
    text_half_height: float | None = None


@dataclass(frozen=True, slots=True)
class LabelPlacement:
    """Text right edge/vertical center and its unmodified line anchor in pixels."""

    player_id: int
    game: int
    x: float
    y: float
    point_x: float
    point_y: float
    width: float
    needs_leader: bool = False


@dataclass(frozen=True, slots=True)
class LabelLayout:
    """A common game anchor, with an explicit bounded mobile curve tolerance."""

    anchor_game: int
    placements: tuple[LabelPlacement, ...]
    crowded: bool
    font_size: float
    collision_count: int = 0
    curve_tolerance: float = 0.0


@dataclass(frozen=True, slots=True)
class _Geometry:
    metrics: PlotMetrics
    font_size: float
    last_game: int
    lower: int
    upper: int
    label_left: float
    label_right: float
    curve_tolerance: float = 0.0

    @property
    def curve_padding(self) -> float:
        return _CURVE_PADDING - self.curve_tolerance

    @property
    def ink_half(self) -> float:
        # Vega's middle baseline shifts the alphabetic baseline by round(.3f).
        # This conservative band covers ascenders, accents and descenders.
        measured = self.metrics.text_half_height
        source_half = measured if measured is not None else self.metrics.font_size * 0.75
        return source_half * self.font_size / self.metrics.font_size + _HALO

    def point(self, game: int, points: int) -> tuple[float, float]:
        x = (self.metrics.width / 2 if self.last_game == 1 else
             self.metrics.width * (game - 1) / (self.last_game - 1))
        y = (self.metrics.height / 2 if self.upper == self.lower else
             self.metrics.height * (self.upper - points) / (self.upper - self.lower))
        return x, y

    def placement(
        self, row: dict[str, int], style: PlayerLineStyle, offset: float | None = None,
    ) -> LabelPlacement:
        x, point_y = self.point(row["Spiel"], row[style.name])
        measured = self.metrics.text_widths[style.player_id]
        width = measured * self.font_size / self.metrics.font_size
        y = point_y + (offset if offset is not None else -self.ink_half - _POINT_GAP)
        label_x = min(x - _GAP, self.label_right)
        return LabelPlacement(style.player_id, row["Spiel"], label_x, y, x, point_y, width)


def plan_point_labels(
    rows: Sequence[dict[str, int]],
    styles: Sequence[PlayerLineStyle],
    metrics: PlotMetrics,
    y_domain: tuple[int, int],
    previous: LabelLayout | None = None,
) -> LabelLayout | None:
    """Keep readable labels near the right, leaving the latest half-game clear.

    The caller must render with X domain ``[1, max(game)]``, the supplied Y
    domain, and the returned font size, without truncating text. Scores remain untouched;
    floating-point calculations describe only display coordinates. Incomplete
    measurements or no safe placement return ``None``. The names stay in
    the right quarter when possible; short histories or narrow plots move its
    label band left enough to preserve the margin and the complete player name.
    """
    if not rows or not styles:
        return None
    ordered = sorted(styles, key=lambda style: style.player_id)
    data = sorted(rows, key=lambda row: row["Spiel"])
    if not _valid_metrics(metrics, ordered) or data[-1]["Spiel"] <= 0:
        return None
    if y_domain[0] > y_domain[1]:
        raise ValueError("The point-chart Y domain must be ascending.")
    if metrics.font_size < _MIN_FONT:
        return None
    source_half = (metrics.text_half_height if metrics.text_half_height is not None
                   else metrics.font_size * 0.75)
    height_factor = 2 * source_half / metrics.font_size
    available_font = ((metrics.height - 2 * _EDGE - (len(ordered) - 1) * _GAP
                       - len(ordered) * 2 * _HALO) / (height_factor * len(ordered)))
    initial_font = min(metrics.font_size, max(_MIN_FONT, available_font))
    last_game = data[-1]["Spiel"]
    candidates = [row for row in reversed(data)
                  if row["Spiel"] >= 1 + (last_game - 1) * 0.75]
    if previous is not None:
        candidates.sort(key=lambda row: row["Spiel"] != previous.anchor_game)
    fonts = [initial_font, *range(int(initial_font) - 1, int(_MIN_FONT) - 1, -1)]
    if previous is not None and _MIN_FONT <= previous.font_size <= initial_font:
        fonts = [previous.font_size, *(font for font in fonts if font != previous.font_size)]
    geometries = []
    for font_size in fonts:
        label_band = _label_band(metrics, font_size, last_game, ordered)
        geometry = _Geometry(metrics, font_size, last_game, *y_domain, *label_band)
        geometries.append(geometry)
    lines = {style.player_id: _line_points(data, style, geometries[0]) for style in ordered}
    mobile_alternative: LabelLayout | None = None

    def finish(layout: LabelLayout) -> LabelLayout:
        selected = _prefer_closer_layout(layout, mobile_alternative, metrics, lines)
        return _with_leaders(selected, lines)

    mobile = metrics.width < _MOBILE_WIDTH
    retained_uniform = None
    retained_mixed = None
    retained_near_mixed = None
    for geometry in geometries:
        if previous is not None:
            retained = _retain_previous(previous, candidates, ordered, geometry, lines)
            if retained is not None:
                if _uniform_side(retained.placements, lines) is not None:
                    if not mobile or _near_own_curves(retained.placements, geometry, lines):
                        return finish(retained)
                    if retained_uniform is None:
                        retained_uniform = retained
                if retained_mixed is None:
                    retained_mixed = retained
                if (retained_near_mixed is None
                        and _near_own_curves(retained.placements, geometry, lines)):
                    retained_near_mixed = retained

    # Keep a repeated line/name rhythm before considering mixed sides. Search
    # immediate neighbors at every font first, so a readable smaller font wins
    # over a large, distant stack that would need long association lines.
    sides: tuple[_Side, ...] = ("above", "below")
    for side in sides:
        for geometry in geometries:
            for row in candidates:
                placements = _free_placements(row, ordered, geometry, lines, side=side)
                if placements is not None:
                    return finish(LabelLayout(row["Spiel"], placements, False, geometry.font_size))

    if mobile:
        if retained_near_mixed is not None:
            return finish(retained_near_mixed)
        # Prefer a close, fully clear mixed arrangement to mobile curve contact.
        for geometry in geometries:
            for row in candidates:
                placements = _free_placements(row, ordered, geometry, lines)
                if placements is not None:
                    return finish(LabelLayout(row["Spiel"], placements, False, geometry.font_size))
        nearby = _mobile_near_layout(candidates, ordered, geometries, lines, previous)
        if nearby is not None:
            if not nearby.crowded:
                return finish(nearby)
            mobile_alternative = nearby
        if retained_uniform is not None:
            return finish(retained_uniform)

    for side in sides:
        for reorder in (False, True):
            for geometry in geometries:
                for row in candidates:
                    placements = _interval_placements(
                        row, ordered, geometry, lines, reorder=reorder, side=side,
                    )
                    if placements is not None:
                        return finish(
                            LabelLayout(row["Spiel"], placements, True, geometry.font_size),
                        )

    # A safe mixed placement stays still unless a uniform arrangement is now
    # possible. Score corrections still refresh its conditional leaders.
    if retained_mixed is not None:
        return finish(retained_mixed)
    for geometry in geometries:
        for row in candidates:
            placements = _free_placements(row, ordered, geometry, lines)
            if placements is not None:
                return finish(LabelLayout(row["Spiel"], placements, False, geometry.font_size))
        for row in candidates:
            placements = _interval_placements(row, ordered, geometry, lines)
            if placements is not None:
                return finish(LabelLayout(row["Spiel"], placements, True, geometry.font_size))

    # Prefer a slightly smaller font to swapping the vertical order of names,
    # which would otherwise require long, crossing association lines.
    for geometry in geometries:
        for row in candidates:
            placements = _interval_placements(row, ordered, geometry, lines, reorder=True)
            if placements is not None:
                return finish(LabelLayout(row["Spiel"], placements, True, geometry.font_size))

    # An extreme plot may have insufficient space even with bounded tolerance.
    # Only then fall back to the largest strictly clear subset.
    for size in range(len(ordered) - 1, 0, -1):
        for geometry in geometries:
            for row in candidates:
                for subset in islice(combinations(ordered, size), 256):
                    placements = _interval_placements(row, subset, geometry, lines, reorder=True)
                    if placements is not None:
                        return finish(
                            LabelLayout(row["Spiel"], placements, True, geometry.font_size),
                        )
    return finish(mobile_alternative) if mobile_alternative is not None else None


def _line_points(
    rows: Sequence[dict[str, int]], style: PlayerLineStyle, geometry: _Geometry,
) -> list[tuple[float, float]]:
    # Remove only geometrically redundant vertices, using exact score/game
    # arithmetic. Long flat histories then cost no more to intersect than a
    # single segment. The source rows and actual label anchors stay unchanged.
    points: list[tuple[int, int]] = []
    for row in rows:
        current = (row["Spiel"], row[style.name])
        while len(points) >= 2:
            start, middle = points[-2:]
            first = (middle[0] - start[0], middle[1] - start[1])
            second = (current[0] - middle[0], current[1] - middle[1])
            if (first[0] * second[1] != first[1] * second[0]
                    or first[0] * second[0] + first[1] * second[1] < 0):
                break
            points.pop()
        points.append(current)
    return [geometry.point(game, score) for game, score in points]


def _mobile_near_layout(
    candidates: Sequence[dict[str, int]], styles: Sequence[PlayerLineStyle],
    geometries: Sequence[_Geometry], lines: dict[int, list[tuple[float, float]]],
    previous: LabelLayout | None,
) -> LabelLayout | None:
    smallest = min(geometries, key=lambda geometry: geometry.font_size)
    required_height = (2 * _EDGE + len(styles) * 2 * smallest.ink_half
                       + (len(styles) - 1) * _GAP)
    if required_height > smallest.metrics.height + 1e-9:
        return None
    # Bound only this additional mobile search. The ordinary strict search
    # still checks every eligible game. Keep the previous/rightmost anchor and
    # spread the remaining probes over the eligible portion of a long history.
    if len(candidates) > _MOBILE_ANCHORS:
        indices = sorted({round(index * (len(candidates) - 1) / (_MOBILE_ANCHORS - 2))
                          for index in range(_MOBILE_ANCHORS - 1)} | {1})
        candidates = [candidates[index] for index in indices]
    best = None
    if previous is not None and 0 < previous.curve_tolerance <= _MOBILE_TOLERANCES[-1]:
        for base in geometries:
            geometry = replace(base, curve_tolerance=previous.curve_tolerance)
            retained = _retain_previous(previous, candidates, styles, geometry, lines)
            if retained is not None:
                if _near_own_curves(retained.placements, geometry, lines):
                    return retained
                if best is None:
                    best = retained
    for tolerance in _MOBILE_TOLERANCES:
        for side in ("above", "below", None):
            for base in geometries:
                geometry = replace(base, curve_tolerance=tolerance)
                for row in candidates:
                    placements = _free_placements(row, styles, geometry, lines, side=side)
                    if placements is None:
                        placements = _interval_placements(
                            row, styles, geometry, lines, side=side, nearby=True,
                        )
                    if placements is not None:
                        return LabelLayout(row["Spiel"], placements, False, geometry.font_size,
                                           curve_tolerance=tolerance)
    # Some small plots cannot keep every name in a six-pixel neighborhood.
    # Choose the least displaced complete arrangement within the same hard
    # text/plot bounds and tolerance limit before resorting to missing names.
    for tolerance in _MOBILE_TOLERANCES:
        for base in geometries:
            geometry = replace(base, curve_tolerance=tolerance)
            for row in candidates:
                placements = _interval_placements(row, styles, geometry, lines, reorder=True)
                if placements is not None:
                    layout = LabelLayout(row["Spiel"], placements, True, geometry.font_size,
                                         curve_tolerance=tolerance)
                    best = (layout if best is None else
                            _prefer_closer_layout(best, layout, geometry.metrics, lines))
    return best


def _prefer_closer_layout(
    layout: LabelLayout, alternative: LabelLayout | None, metrics: PlotMetrics,
    lines: dict[int, list[tuple[float, float]]],
) -> LabelLayout:
    if alternative is None:
        return layout
    if len(alternative.placements) > len(layout.placements):
        return alternative
    if (len(alternative.placements) == len(layout.placements)
            and _layout_distance(alternative, metrics, lines)
            < _layout_distance(layout, metrics, lines)):
        return alternative
    return layout


def _layout_distance(
    layout: LabelLayout, metrics: PlotMetrics, lines: dict[int, list[tuple[float, float]]],
) -> tuple[float, float, float, float]:
    source_half = metrics.text_half_height or metrics.font_size * 0.75
    distance = source_half * layout.font_size / metrics.font_size + _HALO + _CURVE_PADDING + 0.25
    offsets = []
    for label in layout.placements:
        top, bottom = _own_curve_bounds(label, lines[label.player_id])
        offsets.append(min(abs(label.y - (top - distance)), abs(label.y - (bottom + distance))))
    return (max(offsets), sum(offset * offset for offset in offsets),
            layout.curve_tolerance, -layout.font_size)


def _near_own_curves(
    placements: tuple[LabelPlacement, ...], geometry: _Geometry,
    lines: dict[int, list[tuple[float, float]]],
) -> bool:
    return all(min(abs(label.y - target.y) for target in
                   _above_and_below(label, geometry, lines[label.player_id]))
               <= _NEARBY_SHIFT + 1e-9 for label in placements)


def _with_leaders(
    layout: LabelLayout, lines: dict[int, list[tuple[float, float]]],
) -> LabelLayout:
    # Recheck even retained positions: score corrections can move another curve
    # into the gap without invalidating the bounded name placement.
    return replace(layout, placements=tuple(
        replace(label, needs_leader=_needs_leader(label, lines)) for label in layout.placements
    ))


def _needs_leader(
    label: LabelPlacement, lines: dict[int, list[tuple[float, float]]],
) -> bool:
    """Whether a foreign curve separates a safe name from its own local curve."""
    own = lines[label.player_id]
    if len(own) < 2:
        return False
    for player_id, other in lines.items():
        if player_id == label.player_id or len(other) < 2:
            continue
        left = max(label.x - label.width, own[0][0], other[0][0])
        right = min(label.x, own[-1][0], other[-1][0])
        if left >= right:
            continue
        # Even bounded mobile contact cannot reach a name's center. Neither
        # curve crosses that height here, and their distance difference is
        # linear between shared knots, so its extrema occur at these endpoints.
        knots = {left, right, *(x for x, _ in own if left < x < right),
                 *(x for x, _ in other if left < x < right)}
        for x in knots:
            own_distance = _curve_height(own, x) - label.y
            other_distance = _curve_height(other, x) - label.y
            if (own_distance * other_distance > 0
                    and abs(own_distance) - abs(other_distance) > _LEADER_SEPARATION):
                return True
    return False


def _curve_height(line: list[tuple[float, float]], x: float) -> float:
    index = min(max(1, bisect_right(line, x, key=lambda point: point[0])), len(line) - 1)
    x0, y0 = line[index - 1]
    x1, y1 = line[index]
    return y1 if x0 == x1 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def _valid_metrics(metrics: PlotMetrics, styles: Sequence[PlayerLineStyle]) -> bool:
    dimensions = (metrics.width, metrics.height, metrics.font_size)
    return (all(isfinite(value) and value > 0 for value in dimensions)
            and metrics.width / 4 > 2 * _EDGE + _GAP
            and (metrics.text_half_height is None or
                 (isfinite(metrics.text_half_height)
                  and 0 < metrics.text_half_height <= 3 * metrics.font_size))
            and all(style.player_id in metrics.text_widths
                    and isfinite(metrics.text_widths[style.player_id])
                    and metrics.text_widths[style.player_id] > 0 for style in styles))


def _label_band(
    metrics: PlotMetrics, font_size: float, last_game: int,
    styles: Sequence[PlayerLineStyle],
) -> tuple[float, float]:
    # Keep the text stroke and possible glyph overhang outside the reserved
    # half-game (at least 12 CSS pixels).
    right = (metrics.width - max(metrics.width / (2 * max(last_game - 1, 1)), _MIN_END_MARGIN)
             - _HALO - _GLYPH_OVERHANG)
    widest = (max(metrics.text_widths[style.player_id] for style in styles)
              * font_size / metrics.font_size)
    # Full names take priority over the preferred final quarter. Never pretend
    # a shortened box covers the complete glyphs. Allow them to extend left of
    # any eligible game anchor, including the beginning of the final quarter.
    left = max(_EDGE, min(metrics.width * 0.75 - _GAP, right) - widest)
    return left, right


def _retain_previous(
    previous: LabelLayout, candidates: Sequence[dict[str, int]],
    styles: Sequence[PlayerLineStyle], geometry: _Geometry,
    lines: dict[int, list[tuple[float, float]]],
) -> LabelLayout | None:
    row = next((item for item in candidates if item["Spiel"] == previous.anchor_game), None)
    old = {item.player_id: item for item in previous.placements}
    if row is None or set(old) != {style.player_id for style in styles}:
        return None
    adjusted = []
    for style in styles:
        prior = old[style.player_id]
        label = geometry.placement(row, style, (prior.y - prior.point_y)
                                   * geometry.font_size / previous.font_size)
        if geometry.font_size == previous.font_size and label.point_y == prior.point_y:
            label = replace(label, y=prior.y)
        adjusted.append(label)
    placements = tuple(adjusted)
    if _clear(placements, geometry, lines):
        return LabelLayout(previous.anchor_game, placements, previous.crowded, geometry.font_size,
                           curve_tolerance=geometry.curve_tolerance)
    return None


def _horizontal_fit(placements: tuple[LabelPlacement, ...], geometry: _Geometry) -> bool:
    return all(item.x - item.width >= geometry.label_left - 1e-9
               and item.x <= geometry.label_right + 1e-9 for item in placements)


def _boxes_fit(placements: tuple[LabelPlacement, ...], geometry: _Geometry) -> bool:
    if not _horizontal_fit(placements, geometry):
        return False
    half = geometry.ink_half
    if any(item.y - half < _EDGE or item.y + half > geometry.metrics.height - _EDGE
           for item in placements):
        return False
    ordered = sorted(placements, key=lambda item: item.y)
    return all(right.y - left.y >= 2 * half + _GAP - 1e-9
               for left, right in zip(ordered, ordered[1:], strict=False))


def _clear(
    placements: tuple[LabelPlacement, ...], geometry: _Geometry,
    lines: dict[int, list[tuple[float, float]]],
) -> bool:
    return _boxes_fit(placements, geometry) and _collision_count(placements, geometry, lines) == 0


def _free_placements(
    row: dict[str, int], styles: Sequence[PlayerLineStyle], geometry: _Geometry,
    lines: dict[int, list[tuple[float, float]]],
    *, side: _Side | None = None,
) -> tuple[LabelPlacement, ...] | None:
    options: list[tuple[LabelPlacement, ...]] = []
    for style in styles:
        label = geometry.placement(row, style)
        if not _horizontal_fit((label,), geometry):
            return None
        pair = _above_and_below(label, geometry, lines[style.player_id])
        alternatives = pair[:1] if side == "above" else pair[1:] if side == "below" else pair
        options.append(tuple(label for label in alternatives if _clear((label,), geometry, lines)))
        if not options[-1]:
            return None
    # Dashboard has four players (at most 16 arrangements). Bound work if this
    # helper is later reused for a much larger chart.
    for placements in islice(product(*options), 256):
        if _boxes_fit(placements, geometry):
            return placements
    return None


def _above_and_below(
    label: LabelPlacement, geometry: _Geometry, line: list[tuple[float, float]],
) -> tuple[LabelPlacement, LabelPlacement]:
    top, bottom = _own_curve_bounds(label, line)
    distance = geometry.ink_half + geometry.curve_padding + 0.25
    return replace(label, y=top - distance), replace(label, y=bottom + distance)


def _own_curve_bounds(
    label: LabelPlacement, line: list[tuple[float, float]],
) -> tuple[float, float]:
    ranges = _line_ranges(label, line)
    return (min((low for low, _ in ranges), default=label.point_y),
            max((high for _, high in ranges), default=label.point_y))


def _uniform_side(
    placements: tuple[LabelPlacement, ...], lines: dict[int, list[tuple[float, float]]],
) -> _Side | None:
    bounds = [_own_curve_bounds(label, lines[label.player_id]) for label in placements]
    if all(label.y < top for label, (top, _) in zip(placements, bounds, strict=True)):
        return "above"
    if all(label.y > bottom for label, (_, bottom) in zip(placements, bounds, strict=True)):
        return "below"
    return None


def _line_ranges(
    label: LabelPlacement, line: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    left = label.x - label.width - _HALO - _CURVE_PADDING
    right = label.x + _HALO + _GLYPH_OVERHANG + _CURVE_PADDING
    result = []
    # Curves are ordered by game/X. Keep both adjacent points as well, so a
    # segment crossing the entire box remains included even across game gaps.
    first = max(0, bisect_left(line, left, key=lambda point: point[0]) - 1)
    stop = min(len(line), bisect_right(line, right, key=lambda point: point[0]) + 1)
    relevant = line[first:stop]
    segments = (zip(relevant, relevant[1:], strict=False) if len(line) > 1
                else [(line[0], line[0])])
    for (x0, y0), (x1, y1) in segments:
        if x1 < left or x0 > right:
            continue
        if x0 == x1:
            result.append((min(y0, y1), max(y0, y1)))
            continue
        lo, hi = max(x0, left), min(x1, right)
        y_lo = y0 + (y1 - y0) * (lo - x0) / (x1 - x0)
        y_hi = y0 + (y1 - y0) * (hi - x0) / (x1 - x0)
        result.append((min(y_lo, y_hi), max(y_lo, y_hi)))
    return result


def _collision_count(
    placements: tuple[LabelPlacement, ...], geometry: _Geometry,
    lines: dict[int, list[tuple[float, float]]],
) -> int:
    """Count label/curve pairs, independent of how many segments touch a box."""
    half = geometry.ink_half + geometry.curve_padding
    count = 0
    for label in placements:
        for line in lines.values():
            if any(low - half <= label.y <= high + half
                   for low, high in _line_ranges(label, line)):
                count += 1
    return count


def _free_intervals(
    label: LabelPlacement, geometry: _Geometry, lines: dict[int, list[tuple[float, float]]],
) -> list[tuple[float, float]]:
    low = _EDGE + geometry.ink_half
    high = geometry.metrics.height - low
    if low > high or not _horizontal_fit((label,), geometry):
        return []
    half = geometry.ink_half + geometry.curve_padding
    blocked = sorted((start - half, end + half)
                     for line in lines.values() for start, end in _line_ranges(label, line))
    free = []
    cursor = low
    for start, end in blocked:
        if start > cursor:
            free.append((cursor, min(high, start - _CLEARANCE)))
        cursor = max(cursor, end + _CLEARANCE)
        if cursor > high:
            break
    if cursor <= high:
        free.append((cursor, high))
    return [(start, end) for start, end in free if start <= end]


def _interval_placements(
    row: dict[str, int], styles: Sequence[PlayerLineStyle], geometry: _Geometry,
    lines: dict[int, list[tuple[float, float]]],
    *, reorder: bool = False, side: _Side | None = None, nearby: bool = False,
) -> tuple[LabelPlacement, ...] | None:
    base = tuple(geometry.placement(row, style) for style in styles)
    if not _horizontal_fit(base, geometry):
        return None
    preferred = tuple(_above_and_below(label, geometry, lines[label.player_id])[side == "below"]
                      for label in base)
    free = {label.player_id: _free_intervals(label, geometry, lines) for label in preferred}
    if nearby:
        for label in preferred:
            pair = _above_and_below(label, geometry, lines[label.player_id])
            targets = pair[:1] if side == "above" else pair[1:] if side == "below" else pair
            free[label.player_id] = [
                (max(low, target.y - _NEARBY_SHIFT), min(high, target.y + _NEARBY_SHIFT))
                for low, high in free[label.player_id] for target in targets
                if max(low, target.y - _NEARBY_SHIFT) <= min(high, target.y + _NEARBY_SHIFT)
            ]
    if side is not None:
        for label in preferred:
            top, bottom = _own_curve_bounds(label, lines[label.player_id])
            padding = geometry.ink_half + geometry.curve_padding + _CLEARANCE
            free[label.player_id] = [
                (low, min(high, top - padding)) if side == "above" else
                (max(low, bottom + padding), high)
                for low, high in free[label.player_id]
                if (low <= top - padding if side == "above" else high >= bottom + padding)
            ]
    if any(not intervals for intervals in free.values()):
        return None
    point_order = tuple(sorted(preferred, key=lambda item: (item.point_y, item.player_id)))
    # Keep the point order when possible. Only try another order if different
    # name widths make every placement in that order impossible.
    orders = (point_order, *islice(permutations(preferred), 24)) if reorder else (point_order,)
    for order in orders:
        placed = _place_in_intervals(order, free, geometry)
        if placed is not None and _clear(placed, geometry, lines):
            return tuple(sorted(placed, key=lambda item: item.player_id))
    return None


def _place_in_intervals(
    preferred: tuple[LabelPlacement, ...], free: dict[int, list[tuple[float, float]]],
    geometry: _Geometry,
) -> tuple[LabelPlacement, ...] | None:
    """Fit an ordered set near its preferred heights using a bounded dynamic program."""
    spacing = 2 * geometry.ink_half + _GAP
    seeds = [position for intervals in free.values() for pair in intervals for position in pair]
    seeds.extend(label.y for label in preferred)
    # Boundary shifts include the earliest feasible packing, even for narrow
    # fractional intervals; target shifts keep the result close to its lines.
    pool = sorted({seed + step * spacing for seed in seeds
                   for step in range(-len(preferred), len(preferred) + 1)})
    states: list[tuple[float, float, tuple[LabelPlacement, ...]]] = []
    for index, label in enumerate(preferred):
        candidates = [y for y in pool
                      if any(low <= y <= high for low, high in free[label.player_id])]
        updated: list[tuple[float, float, tuple[LabelPlacement, ...]]] = []
        pointer = 0
        best: tuple[float, float, tuple[LabelPlacement, ...]] | None = None
        for y in candidates:
            while pointer < len(states) and states[pointer][0] <= y - spacing + 1e-9:
                if best is None or states[pointer][1] < best[1]:
                    best = states[pointer]
                pointer += 1
            cost = (y - label.y) ** 2
            if index == 0:
                updated.append((y, cost, (replace(label, y=y),)))
            elif best is not None:
                updated.append((y, cost + best[1], (*best[2], replace(label, y=y))))
        if not updated:
            return None
        states = updated
    return min(states, key=lambda item: item[1])[2]
