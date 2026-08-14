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
    ("shop_dwgs",     "write",   True),
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


def test_drafter_shop_dwgs_full_access():
    """Drafter is elevated to PM-parity on shop_dwgs in sub-project #5a so
    they can create drawings, upload revisions, submit, and (when not the
    uploader) approve/reject."""
    from app.auth.permissions import MATRIX
    assert MATRIX["drafter"]["shop_dwgs"] == {"read", "write", "approve", "comment"}


def test_editor_shop_dwgs_can_read_and_write_but_not_approve():
    """Foreman/Machine team (auth_role=editor) can read+write+comment but cannot
    approve drawings — review is a manager/admin/drafter responsibility."""
    from app.auth.permissions import MATRIX
    assert "approve" not in MATRIX["editor"]["shop_dwgs"]


def test_viewer_shop_dwgs_read_only():
    from app.auth.permissions import MATRIX
    assert MATRIX["viewer"]["shop_dwgs"] == {"read"}


def test_drafter_isample_full_access():
    """Drafter is elevated to PM-parity on isample (sub-project #5c)."""
    from app.auth.permissions import MATRIX
    assert MATRIX["drafter"]["isample"] == {"read", "write", "approve", "comment"}


def test_editor_isample_can_read_and_write_but_not_approve():
    """Editor can create/edit samples but cannot approve them."""
    from app.auth.permissions import MATRIX
    assert "write" in MATRIX["editor"]["isample"]
    assert "approve" not in MATRIX["editor"]["isample"]


def test_manager_isample_full_access():
    from app.auth.permissions import MATRIX
    assert MATRIX["manager"]["isample"] == {"read", "write", "approve", "comment"}


def test_viewer_isample_read_only():
    from app.auth.permissions import MATRIX
    assert MATRIX["viewer"]["isample"] == {"read"}


def test_purchase_officer_isample_read_only():
    from app.auth.permissions import MATRIX
    assert MATRIX["purchase_officer"]["isample"] == {"read"}


# --- Catalog module (sub-project #7a) ----------------------------------------

def test_drafter_catalog_full_access():
    """Drafter is elevated to admin/manager parity on catalog (#7a)."""
    from app.auth.permissions import MATRIX
    assert MATRIX["drafter"]["catalog"] == {"read", "write", "approve", "comment"}


def test_editor_catalog_can_read_write_comment_no_approve():
    """Foreman/Machine team (editor) can propose catalog edits but cannot
    approve — final curation belongs to drafter+/manager+."""
    from app.auth.permissions import MATRIX
    assert MATRIX["editor"]["catalog"] == {"read", "write", "comment"}


def test_purchase_officer_catalog_read_and_comment():
    """Procurement reads + comments on catalog (e.g. flagging wrong supplier)
    but does not curate."""
    from app.auth.permissions import MATRIX
    assert MATRIX["purchase_officer"]["catalog"] == {"read", "comment"}


def test_viewer_catalog_read_only():
    from app.auth.permissions import MATRIX
    assert MATRIX["viewer"]["catalog"] == {"read"}


def test_manager_admin_catalog_full_access():
    from app.auth.permissions import MATRIX
    assert MATRIX["manager"]["catalog"] == {"read", "write", "approve", "comment"}
    assert MATRIX["admin"]["catalog"] == {"read", "write", "approve", "comment"}


# --- Cut Floor module (sub-project #7b) --------------------------------------

def test_drafter_cut_floor_full_access():
    """Drafter is elevated to admin/manager parity on cut_floor (#7b).

    Module landed in #7b so the CV import routes can gate on it; #7c will
    extend its consumers (CutPlan + CutSchedule + /cut-floor page).
    """
    from app.auth.permissions import MATRIX
    assert MATRIX["drafter"]["cut_floor"] == {"read", "write", "approve", "comment"}


def test_editor_cut_floor_can_read_write_comment_no_approve():
    """Foreman/Machine team (editor) can drive cut imports + edit schedule
    but cannot approve."""
    from app.auth.permissions import MATRIX
    assert MATRIX["editor"]["cut_floor"] == {"read", "write", "comment"}


def test_purchase_officer_cut_floor_read_only():
    from app.auth.permissions import MATRIX
    assert MATRIX["purchase_officer"]["cut_floor"] == {"read"}


def test_viewer_cut_floor_read_only():
    from app.auth.permissions import MATRIX
    assert MATRIX["viewer"]["cut_floor"] == {"read"}


def test_manager_admin_cut_floor_full_access():
    from app.auth.permissions import MATRIX
    assert MATRIX["manager"]["cut_floor"] == {"read", "write", "approve", "comment"}
    assert MATRIX["admin"]["cut_floor"] == {"read", "write", "approve", "comment"}


# ── permissions_for: the matrix row served on /auth/me ────────────────────────

def test_permissions_for_covers_every_module():
    from app.auth.permissions import _ALL_MODULES, MATRIX, permissions_for
    for role in MATRIX:
        row = permissions_for(role)
        assert set(row) == set(_ALL_MODULES), role


def test_permissions_for_agrees_with_has_permission():
    from app.auth.permissions import _ALL_MODULES, MATRIX, permissions_for
    for role in MATRIX:
        row = permissions_for(role)
        for module in _ALL_MODULES:
            for action in ("read", "write", "approve", "comment"):
                assert (action in row[module]) is has_permission(role, module, action)


def test_permissions_for_unknown_role_denies_everything():
    from app.auth.permissions import permissions_for
    assert all(v == [] for v in permissions_for("nope").values())


def test_permissions_for_actions_are_sorted():
    """Stable ordering keeps the /auth/me payload diffable."""
    from app.auth.permissions import MATRIX, permissions_for
    for role in MATRIX:
        for actions in permissions_for(role).values():
            assert actions == sorted(actions)
