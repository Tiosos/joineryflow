"""Pure helpers for shop-floor lifecycle (sub-project #8).

These functions are deliberately database-free so unit tests can call
them directly. Stage ordering varies per item via the
`paint_after_assembly` flag (user decision recorded in the #8 plan).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

SHOP_FLOOR_ORDER_DEFAULT: tuple[str, ...] = (
    "DOWN", "CNC", "EDGED", "PAINTED", "MADE",
)
SHOP_FLOOR_ORDER_PAINT_LAST: tuple[str, ...] = (
    "DOWN", "CNC", "EDGED", "MADE", "PAINTED",
)

UNDO_WINDOW = timedelta(minutes=5)


def shop_floor_order(paint_after_assembly: bool) -> tuple[str, ...]:
    """Return the lifecycle ordering for a single item.

    `paint_after_assembly = False` (default): paint goes before assembly.
    `paint_after_assembly = True`: paint is the last finish step after
    the cabinet is assembled.
    """
    return (
        SHOP_FLOOR_ORDER_PAINT_LAST
        if paint_after_assembly
        else SHOP_FLOOR_ORDER_DEFAULT
    )


def prior_stages(
    stage_key: str,
    *,
    painting_req: bool,
    paint_after_assembly: bool,
) -> tuple[str, ...]:
    """Return the shop-floor stages that must be done before `stage_key`.

    PAINTED is omitted from the priors when an item doesn't require
    painting. Raises ValueError if `stage_key` is not a shop-floor stage.
    """
    order = shop_floor_order(paint_after_assembly)
    if stage_key not in order:
        raise ValueError(f"unknown shop-floor stage: {stage_key}")
    idx = order.index(stage_key)
    priors = order[:idx]
    if not painting_req:
        priors = tuple(s for s in priors if s != "PAINTED")
    return priors


def later_stages(
    stage_key: str,
    *,
    painting_req: bool,
    paint_after_assembly: bool,
) -> tuple[str, ...]:
    """Return the shop-floor stages that come after `stage_key`.

    The inverse of `prior_stages`. PAINTED is omitted when an item doesn't
    require painting. Raises ValueError if `stage_key` is not a shop-floor
    stage. Used to block undoing a stage whose successor is already done.
    """
    order = shop_floor_order(paint_after_assembly)
    if stage_key not in order:
        raise ValueError(f"unknown shop-floor stage: {stage_key}")
    idx = order.index(stage_key)
    after = order[idx + 1:]
    if not painting_req:
        after = tuple(s for s in after if s != "PAINTED")
    return after


def is_within_undo_window(completed_at: datetime, *, now: datetime | None = None) -> bool:
    """True iff `completed_at` is within the worker undo window (5 min)."""
    current = now if now is not None else datetime.now(timezone.utc)
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return (current - completed_at) <= UNDO_WINDOW
