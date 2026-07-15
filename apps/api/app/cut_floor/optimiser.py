"""Naive single-sheet CutPlan optimiser — sub-project #9 (stub).

Deliberately mediocre shelf packing. The acceptance criterion is
**wire-shape correctness**, not packing quality: this emits a proposal in
the exact `CutPlanIn` shape so the existing create-plan flow can persist it
after the user confirms. A future ticket replaces `pack_naive` with a real
bin-packing engine (FFD / MaxRects / …) behind the same signature.

Pure Python, stdlib only — no DB, no Pydantic — so the packing logic is unit
tested against deterministic inputs. The route layer adapts DB rows into
`PackPart`s and adapts the `PackResult` into Pydantic schemas.

Geometry convention (matches part_slot / BoardTab): the sheet spans
`sheet_len` on the X axis and `sheet_wid` on the Y axis. A placed slot's
`(x, y)` is its top-left corner; `(w, h)` its width (X) and height (Y).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PackPart:
    """One rectangle to place. `qty` is expanded by the caller — each
    `PackPart` is a single instance."""
    w: float
    h: float
    label: str
    part_id: int | None = None
    allow_rotation: bool = True


@dataclass
class PlacedSlot:
    x: float
    y: float
    w: float
    h: float
    label: str
    part_id: int | None = None


@dataclass
class Skip:
    label: str
    reason: str  # 'too_large' | 'no_room'
    part_id: int | None = None


@dataclass
class PackResult:
    placed: list[PlacedSlot] = field(default_factory=list)
    skipped: list[Skip] = field(default_factory=list)
    utilization_pct: float = 0.0


def _best_orientation(
    part: PackPart, sheet_len: float, sheet_wid: float
) -> tuple[float, float] | None:
    """Pick the orientation that fits within the full sheet, preferring the
    one with the smaller height (lies flattest → packs more shelves). Returns
    `(w, h)` or `None` when the part is larger than the sheet in every legal
    orientation."""
    candidates = [(part.w, part.h)]
    if part.allow_rotation:
        candidates.append((part.h, part.w))
    fitting = [
        (w, h) for (w, h) in candidates if w <= sheet_len and h <= sheet_wid
    ]
    if not fitting:
        return None
    return min(fitting, key=lambda wh: wh[1])


def pack_naive(
    parts: list[PackPart],
    sheet_len: float,
    sheet_wid: float,
    kerf: float = 3.0,
) -> PackResult:
    """Single-sheet shelf packing (next-fit decreasing).

    1. Sort parts by longest edge, descending.
    2. Walk left-to-right filling a shelf; when the next part won't fit the
       row width, open a new shelf above the tallest part of the current one.
    3. Parts larger than the sheet are skipped `too_large`; parts that would
       fit an empty sheet but have no room left are skipped `no_room`.

    Single sheet only — no bin overflow. Overflowing parts skip with
    `no_room`; the caller re-runs with bigger stock or more sheets.
    """
    result = PackResult()
    order = sorted(parts, key=lambda p: max(p.w, p.h), reverse=True)

    cursor_x = 0.0
    cursor_y = 0.0
    shelf_height = 0.0
    used_area = 0.0

    for part in order:
        oriented = _best_orientation(part, sheet_len, sheet_wid)
        if oriented is None:
            result.skipped.append(
                Skip(label=part.label, reason="too_large", part_id=part.part_id)
            )
            continue
        pw, ph = oriented

        # Won't fit remaining width of the current (non-empty) shelf → wrap to
        # a new shelf above the current one.
        if cursor_x > 0 and cursor_x + pw > sheet_len:
            cursor_y += shelf_height + kerf
            cursor_x = 0.0
            shelf_height = 0.0

        # No vertical room left on the sheet.
        if cursor_y + ph > sheet_wid:
            result.skipped.append(
                Skip(label=part.label, reason="no_room", part_id=part.part_id)
            )
            continue

        result.placed.append(
            PlacedSlot(
                x=cursor_x, y=cursor_y, w=pw, h=ph,
                label=part.label, part_id=part.part_id,
            )
        )
        used_area += pw * ph
        cursor_x += pw + kerf
        shelf_height = max(shelf_height, ph)

    sheet_area = sheet_len * sheet_wid
    result.utilization_pct = (
        round(used_area / sheet_area, 4) if sheet_area > 0 else 0.0
    )
    return result
