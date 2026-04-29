import pytest
from app.auth.permissions import has_permission

CASES = [
    ("admin",            "it_management", "write",   True),
    ("admin",            "orderbook",     "approve", True),
    ("manager",          "tracking",      "write",   True),
    ("manager",          "it_management", "write",   False),
    ("editor",           "tracking",      "write",   True),
    ("editor",           "orderbook",     "approve", False),
    ("purchase_officer", "tracking",      "read",    True),
    ("purchase_officer", "tracking",      "write",   False),
    ("purchase_officer", "tracking",      "comment", True),
    ("purchase_officer", "list",          "read",    True),
    ("purchase_officer", "list",          "write",   False),
    ("purchase_officer", "orderbook",     "write",   True),
    ("purchase_officer", "orderbook",     "approve", True),
    ("purchase_officer", "it_management", "read",    False),
    ("viewer",           "tracking",      "read",    True),
    ("viewer",           "tracking",      "write",   False),
    ("viewer",           "orderbook",     "approve", False),
]


@pytest.mark.parametrize("role,module,action,expected", CASES)
def test_matrix(role, module, action, expected):
    assert has_permission(role, module, action) is expected


@pytest.mark.parametrize("module,action,allowed", [
    ("dashboard",     "read",    True),
    ("tracking",      "write",   True),
    ("tracking",      "approve", True),
    ("list",          "write",   True),
    ("shop_dwgs",     "write",   False),
    ("orderbook",     "approve", True),
    ("it_management", "read",    False),
])
def test_drafter_matrix(module, action, allowed):
    assert has_permission("drafter", module, action) is allowed


def test_drafter_orderbook_full_access():
    """Drafter is elevated to PM parity for the orderbook module in
    Procurement Workbench v1."""
    from app.auth.permissions import MATRIX
    assert MATRIX["drafter"]["orderbook"] == {"read", "write", "approve", "comment"}
