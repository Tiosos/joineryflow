"""Tests for the workspace_counter helper (sub-project #10 T02)."""
import pytest
from sqlalchemy import text

from app.counters import next_value


def test_first_call_returns_one(db, workspace_id):
    n = next_value(db, workspace_id=workspace_id, name="po_number")
    assert n == 1


def test_sequential_calls_monotonic(db, workspace_id):
    values = [next_value(db, workspace_id=workspace_id, name="po_number") for _ in range(100)]
    assert values == list(range(1, 101))


def test_separate_names_separate_sequences(db, workspace_id):
    a1 = next_value(db, workspace_id=workspace_id, name="po_number")
    b1 = next_value(db, workspace_id=workspace_id, name="invoice_number")
    a2 = next_value(db, workspace_id=workspace_id, name="po_number")
    b2 = next_value(db, workspace_id=workspace_id, name="invoice_number")
    assert (a1, a2) == (1, 2)
    assert (b1, b2) == (1, 2)


def test_separate_workspaces_separate_sequences(db):
    w1 = db.execute(
        text("INSERT INTO workspace(slug,name) VALUES('ctr-w1','W1') RETURNING id")
    ).scalar()
    w2 = db.execute(
        text("INSERT INTO workspace(slug,name) VALUES('ctr-w2','W2') RETURNING id")
    ).scalar()
    assert next_value(db, workspace_id=w1, name="po_number") == 1
    assert next_value(db, workspace_id=w2, name="po_number") == 1
    assert next_value(db, workspace_id=w1, name="po_number") == 2
    assert next_value(db, workspace_id=w2, name="po_number") == 2


def test_rejects_empty_name(db, workspace_id):
    with pytest.raises(ValueError):
        next_value(db, workspace_id=workspace_id, name="")


def test_rejects_oversize_name(db, workspace_id):
    with pytest.raises(ValueError):
        next_value(db, workspace_id=workspace_id, name="x" * 33)
