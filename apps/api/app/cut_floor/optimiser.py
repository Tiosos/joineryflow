"""CutPlan optimiser — sub-project #9 / #9-engine.

Two single-sheet packers behind one shape:

  * `pack_naive`   — the original shelf next-fit-decreasing stub (kept as a
    fallback + A/B baseline).
  * `pack_maxrects` — MaxRects Best-Area-Fit, a real 2D nester with much
    better yield.

`pack_sheets` wraps either one to pack across **multiple** sheets: parts that
overflow one sheet nest onto the next instead of being dropped.

Pure Python, stdlib only — no DB, no Pydantic — so every packing invariant is
unit tested against deterministic inputs. The route layer adapts DB rows into
`PackPart`s and adapts the results into Pydantic schemas.

Geometry convention (matches part_slot / BoardTab): the sheet spans
`sheet_len` on the X axis and `sheet_wid` on the Y axis. A placed slot's
`(x, y)` is its top-left corner; `(w, h)` its width (X) and height (Y).
`kerf` is the saw gap reserved between neighbouring parts.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_EPS = 1e-6


@dataclass
class PackPart:
    """One rectangle to place. `qty` is expanded by the caller — each
    `PackPart` is a single instance. `uid` uniquely identifies the instance so
    the multi-sheet wrapper can carry overflow to the next sheet."""
    w: float
    h: float
    label: str
    part_id: int | None = None
    allow_rotation: bool = True
    uid: int | None = None


@dataclass
class PlacedSlot:
    x: float
    y: float
    w: float
    h: float
    label: str
    part_id: int | None = None
    uid: int | None = None


@dataclass
class Skip:
    label: str
    reason: str  # 'too_large' | 'no_room'
    part_id: int | None = None
    uid: int | None = None


@dataclass
class PackResult:
    """One sheet's worth of placement."""
    placed: list[PlacedSlot] = field(default_factory=list)
    skipped: list[Skip] = field(default_factory=list)
    utilization_pct: float = 0.0


@dataclass
class MultiPackResult:
    """A whole optimisation run across one or more sheets."""
    sheets: list[PackResult] = field(default_factory=list)
    skipped: list[Skip] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Naive shelf packer (original stub — kept as fallback / baseline)
# ---------------------------------------------------------------------------

def _best_orientation(
    part: PackPart, sheet_len: float, sheet_wid: float
) -> tuple[float, float] | None:
    """Pick the orientation that fits within the full sheet, preferring the
    one with the smaller height. Returns `(w, h)` or `None` when the part is
    larger than the sheet in every legal orientation."""
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
    """Single-sheet shelf packing (next-fit decreasing). Deliberately simple —
    the acceptance criterion is wire-shape correctness, not yield."""
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
                Skip(part.label, "too_large", part.part_id, part.uid)
            )
            continue
        pw, ph = oriented

        if cursor_x > 0 and cursor_x + pw > sheet_len:
            cursor_y += shelf_height + kerf
            cursor_x = 0.0
            shelf_height = 0.0

        if cursor_y + ph > sheet_wid:
            result.skipped.append(
                Skip(part.label, "no_room", part.part_id, part.uid)
            )
            continue

        result.placed.append(
            PlacedSlot(cursor_x, cursor_y, pw, ph, part.label, part.part_id, part.uid)
        )
        used_area += pw * ph
        cursor_x += pw + kerf
        shelf_height = max(shelf_height, ph)

    area = sheet_len * sheet_wid
    result.utilization_pct = round(used_area / area, 4) if area > 0 else 0.0
    return result


# ---------------------------------------------------------------------------
# MaxRects Best-Area-Fit packer (the real engine)
# ---------------------------------------------------------------------------

@dataclass
class _Rect:
    x: float
    y: float
    w: float
    h: float


def _contains(a: _Rect, b: _Rect) -> bool:
    """True when `a` fully contains `b`."""
    return (
        a.x <= b.x + _EPS and a.y <= b.y + _EPS
        and a.x + a.w >= b.x + b.w - _EPS
        and a.y + a.h >= b.y + b.h - _EPS
    )


def _split_free(free: list[_Rect], region: _Rect) -> list[_Rect]:
    """Split every free rectangle that overlaps `region` into the (up to four)
    maximal slabs around it. `region` is the placed part inflated by kerf, so
    the surviving free space keeps a saw gap from every placement."""
    out: list[_Rect] = []
    rx2, ry2 = region.x + region.w, region.y + region.h
    for f in free:
        fx2, fy2 = f.x + f.w, f.y + f.h
        # No overlap → keep the free rect untouched.
        if (region.x >= fx2 - _EPS or rx2 <= f.x + _EPS
                or region.y >= fy2 - _EPS or ry2 <= f.y + _EPS):
            out.append(f)
            continue
        if region.x - f.x > _EPS:               # left slab
            out.append(_Rect(f.x, f.y, region.x - f.x, f.h))
        if fx2 - rx2 > _EPS:                     # right slab
            out.append(_Rect(rx2, f.y, fx2 - rx2, f.h))
        if region.y - f.y > _EPS:               # top slab
            out.append(_Rect(f.x, f.y, f.w, region.y - f.y))
        if fy2 - ry2 > _EPS:                     # bottom slab
            out.append(_Rect(f.x, ry2, f.w, fy2 - ry2))
    return out


def _prune_free(free: list[_Rect]) -> list[_Rect]:
    """Drop free rectangles fully contained in another (MaxRects keeps only
    maximal rectangles). Equal rectangles: keep the lower index."""
    keep = [True] * len(free)
    for i in range(len(free)):
        if not keep[i]:
            continue
        for j in range(len(free)):
            if i == j or not keep[j]:
                continue
            if _contains(free[j], free[i]):
                if _contains(free[i], free[j]) and i < j:
                    continue  # equal → keep the earlier one (i)
                keep[i] = False
                break
    return [free[i] for i in range(len(free)) if keep[i]]


# Free-rect choice heuristics. Each scores a candidate placement of a part
# (w × h) into free rect `f`; the lowest score wins. No single heuristic is
# best on every input — Best-Short-Side-Fit tiles uniform grids tightly,
# Best-Area-Fit suits mixed sizes, Bottom-Left keeps a low skyline — so
# `pack_maxrects` runs all three and keeps whichever sheet packs the most.

def _score_bssf(f: _Rect, w: float, h: float) -> tuple:
    dw, dh = f.w - w, f.h - h
    return (min(dw, dh), max(dw, dh))


def _score_baf(f: _Rect, w: float, h: float) -> tuple:
    dw, dh = f.w - w, f.h - h
    return (f.w * f.h - w * h, min(dw, dh))


def _score_blsf(f: _Rect, w: float, h: float) -> tuple:
    return (f.y + h, f.x)  # lowest top edge, then leftmost


_HEURISTICS = (_score_bssf, _score_baf, _score_blsf)


def _pack_once(order, sheet_len, sheet_wid, kerf, score_fn) -> PackResult:
    """One MaxRects pass over pre-sorted parts using a single choice heuristic."""
    result = PackResult()
    free: list[_Rect] = [_Rect(0.0, 0.0, float(sheet_len), float(sheet_wid))]
    used_area = 0.0

    for part in order:
        oris = [(part.w, part.h)]
        if part.allow_rotation and part.w != part.h:
            oris.append((part.h, part.w))

        if not any(
            w <= sheet_len + _EPS and h <= sheet_wid + _EPS for w, h in oris
        ):
            result.skipped.append(
                Skip(part.label, "too_large", part.part_id, part.uid)
            )
            continue

        best = None  # (score, free_rect, w, h)
        for f in free:
            for (w, h) in oris:
                if w <= f.w + _EPS and h <= f.h + _EPS:
                    score = score_fn(f, w, h)
                    if best is None or score < best[0]:
                        best = (score, f, w, h)

        if best is None:
            result.skipped.append(
                Skip(part.label, "no_room", part.part_id, part.uid)
            )
            continue

        _, f, w, h = best
        result.placed.append(
            PlacedSlot(f.x, f.y, w, h, part.label, part.part_id, part.uid)
        )
        used_area += w * h
        # Reserve kerf on the right/bottom; slabs beyond the sheet clip away.
        region = _Rect(f.x, f.y, w + kerf, h + kerf)
        free = _prune_free(_split_free(free, region))

    area = sheet_len * sheet_wid
    result.utilization_pct = round(used_area / area, 4) if area > 0 else 0.0
    return result


def pack_maxrects(
    parts: list[PackPart],
    sheet_len: float,
    sheet_wid: float,
    kerf: float = 3.0,
) -> PackResult:
    """Single-sheet MaxRects nester. Parts are placed largest-first; the sheet
    is packed under each free-rect heuristic and the best-yielding result is
    returned. Non grain-locked parts may be rotated 90°; a `kerf` gap is kept
    between every neighbour."""
    order = sorted(parts, key=lambda p: (p.w * p.h, max(p.w, p.h)), reverse=True)
    best: PackResult | None = None
    for score_fn in _HEURISTICS:
        res = _pack_once(order, sheet_len, sheet_wid, kerf, score_fn)
        key = (len(res.placed), res.utilization_pct)
        if best is None or key > (len(best.placed), best.utilization_pct):
            best = res
    return best if best is not None else PackResult()


# ---------------------------------------------------------------------------
# Multi-sheet wrapper
# ---------------------------------------------------------------------------

_PACKERS = {"maxrects": pack_maxrects, "naive": pack_naive}


def pack_sheets(
    parts: list[PackPart],
    sheet_len: float,
    sheet_wid: float,
    kerf: float = 3.0,
    strategy: str = "maxrects",
    max_sheets: int = 20,
) -> MultiPackResult:
    """Pack `parts` across up to `max_sheets` identical sheets using the chosen
    single-sheet `strategy`. Overflow (parts that fit a sheet but not the
    remaining space) rolls onto a fresh sheet; parts bigger than the sheet are
    reported `too_large`; parts still unplaced when `max_sheets` is exhausted
    are reported `no_room`."""
    packer = _PACKERS.get(strategy, pack_maxrects)

    remaining = list(parts)
    for idx, p in enumerate(remaining):
        if p.uid is None:
            p.uid = idx

    sheets: list[PackResult] = []
    skipped: list[Skip] = []

    while remaining and len(sheets) < max_sheets:
        res = packer(remaining, sheet_len, sheet_wid, kerf)
        if not res.placed:
            # Nothing fits even on a fresh, empty sheet → the rest never will.
            skipped.extend(res.skipped)
            remaining = []
            break
        sheets.append(res)
        placed_uids = {s.uid for s in res.placed}
        too_large_uids = {s.uid for s in res.skipped if s.reason == "too_large"}
        skipped.extend(s for s in res.skipped if s.reason == "too_large")
        # The `no_room` parts (didn't fit the leftover space) retry next sheet.
        remaining = [
            p for p in remaining
            if p.uid not in placed_uids and p.uid not in too_large_uids
        ]

    for p in remaining:  # exhausted max_sheets
        skipped.append(Skip(p.label, "no_room", p.part_id, p.uid))

    return MultiPackResult(sheets=sheets, skipped=skipped)
