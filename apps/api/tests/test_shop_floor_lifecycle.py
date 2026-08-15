"""Unit tests for shop_floor.lifecycle pure helpers (sub-project #8)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.shop_floor.lifecycle import (
    SHOP_FLOOR_ORDER_DEFAULT,
    SHOP_FLOOR_ORDER_PAINT_LAST,
    is_within_undo_window,
    later_stages,
    prior_stages,
    shop_floor_order,
)


def test_shop_floor_order_default_is_paint_before_made():
    assert shop_floor_order(False) == SHOP_FLOOR_ORDER_DEFAULT
    assert shop_floor_order(False).index("PAINTED") < shop_floor_order(False).index("MADE")


def test_shop_floor_order_paint_last_flips_made_and_painted():
    assert shop_floor_order(True) == SHOP_FLOOR_ORDER_PAINT_LAST
    assert shop_floor_order(True).index("MADE") < shop_floor_order(True).index("PAINTED")


def test_prior_stages_for_first_stage_is_empty():
    assert prior_stages("DOWN", painting_req=True, paint_after_assembly=False) == ()


def test_prior_stages_includes_painted_when_painting_req():
    assert prior_stages(
        "MADE", painting_req=True, paint_after_assembly=False
    ) == ("DOWN", "CNC", "EDGED", "PAINTED")


def test_prior_stages_skips_painted_when_no_painting():
    assert prior_stages(
        "MADE", painting_req=False, paint_after_assembly=False
    ) == ("DOWN", "CNC", "EDGED")


def test_prior_stages_paint_last_for_painted_includes_made():
    assert prior_stages(
        "PAINTED", painting_req=True, paint_after_assembly=True
    ) == ("DOWN", "CNC", "EDGED", "MADE")


def test_prior_stages_paint_last_for_made_excludes_painted():
    assert prior_stages(
        "MADE", painting_req=True, paint_after_assembly=True
    ) == ("DOWN", "CNC", "EDGED")


def test_later_stages_is_inverse_of_prior_stages():
    assert later_stages("DOWN", painting_req=True, paint_after_assembly=False) == (
        "CNC", "EDGED", "PAINTED", "MADE",
    )


def test_later_stages_for_last_stage_is_empty():
    assert later_stages("MADE", painting_req=True, paint_after_assembly=False) == ()


def test_later_stages_skips_painted_when_no_painting():
    assert later_stages(
        "CNC", painting_req=False, paint_after_assembly=False
    ) == ("EDGED", "MADE")


def test_later_stages_paint_last_for_edged_puts_made_before_painted():
    assert later_stages(
        "EDGED", painting_req=True, paint_after_assembly=True
    ) == ("MADE", "PAINTED")


def test_later_stages_unknown_stage_raises():
    with pytest.raises(ValueError):
        later_stages("REQ", painting_req=False, paint_after_assembly=False)


def test_prior_stages_unknown_stage_raises():
    with pytest.raises(ValueError):
        prior_stages("REQ", painting_req=False, paint_after_assembly=False)


def test_undo_window_within_5_minutes_true():
    now = datetime.now(timezone.utc)
    assert is_within_undo_window(now - timedelta(minutes=2), now=now) is True


def test_undo_window_at_5_minute_boundary_inclusive():
    now = datetime.now(timezone.utc)
    assert is_within_undo_window(now - timedelta(minutes=5), now=now) is True


def test_undo_window_after_5_minutes_false():
    now = datetime.now(timezone.utc)
    assert is_within_undo_window(now - timedelta(minutes=6), now=now) is False


def test_undo_window_naive_datetime_treated_as_utc():
    now = datetime.now(timezone.utc)
    naive = (now - timedelta(minutes=1)).replace(tzinfo=None)
    assert is_within_undo_window(naive, now=now) is True
