"""SQL query functions for the items module.

Column name mapping (legacy FileMaker schema vs spec):
  items.item_id   -> aliased as id
  items.num       -> aliased as item_number
  items.rm_no     -> aliased as room_no
  items.rm_desc   -> aliased as room_desc
  items.zone      -> str (varchar 16 in DB, not int)
  items.painting_req -> painting_required (aliased)
  items.solid_surface_req -> solid_surface_required (aliased)
  item_hardware_lines.line_id -> used in JOINs (not .id)
  batch_allocations.item_hardware_line_id -> FK to item_hardware_lines.line_id
  project_hardware_catalog.material_type -> catalog_source_table (aliased)
  project_hardware_catalog.material_id -> source_id used in CTE join

Workspace scoping: items have no workspace_id column. Isolation goes via
  items.project_id -> projects.pm_id -> app_user.workspace_id
mirroring the _WORKSPACE_FILTER pattern in projects/queries.py.

Strategy: Two queries rather than one giant GROUP BY + window function:
  Query 1: items with cutlist_owner_name + ready/blocked counts (correlated subqueries).
  Query 2: all item_stages rows for this project, merged in Python into stages dicts.
This avoids GROUP BY fan-out complications with the jsonb_object_agg approach
when combined with the availability correlated subqueries.

Split by concern into `_q_*` modules; every name is re-exported here so
`queries.<name>` and `from .queries import <name>` keep working.
"""
from ._q_base import (  # noqa: F401
    _JOINERY_I,
    _PATCH_FIELD_MAP,
    _VALID_STATUS_KEYS,
    _VERSION_KEY_BY_LABEL,
    _WORKSPACE_FILTER,
    _apply_item_changes,
    _changed_fields,
    _item_row,
    _project_in_workspace,
    _resolve_area_room,
    _room_label,
    _user_in_workspace,
)
from ._q_read import (  # noqa: F401
    _ITEM_COLS,
    get_item_availability,
    get_item_detail,
    list_items_for_project,
)
from ._q_locks import (  # noqa: F401
    ItemContentLocked,
    _LOCK_REQUEST_COLS,
    _lock_request_row,
    _upsert_lock_request,
    assert_item_content_unlocked,
    claim_or_release_lock,
    clear_hard_lock,
    decide_lock_request,
    list_lock_requests,
    set_hard_lock,
)
from ._q_write import (  # noqa: F401
    create_item,
    delete_item,
    patch_item,
    restore_item,
)
from ._q_status import (  # noqa: F401
    VALID_STAGE_KEYS,
    _write_approval_lock_audit,
    bulk_patch_item_status,
    patch_item_status,
    patch_lifecycle,
)
