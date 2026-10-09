"""SQL queries for the estimating module — sub-project #9a.

Routes own the transaction boundary; queries flush only (audit/edit-log
writes use db.flush() inline). Convert-to-Project flushes at the end so the
route's commit lands the whole transaction atomically.

Workspace isolation: every query joins through `customer.workspace_id` or
`estimate.workspace_id`. Cross-workspace reads return None (route → 404).

Split by concern into `_q_*` modules; every name is re-exported here so
`queries.<name>` keeps working for routes, PDF code and tests.
"""
from ..catalog import queries as catalog_q  # noqa: F401
from ..orders import queries as orders_q  # noqa: F401
from ._q_catalog import (  # noqa: F401
    STAGE_KEYS,
    _CATALOG_BY_TYPE,
    _HW_CATALOG_BY_TYPE,
    _ORDER_UNIT_BY_TYPE,
    _PART_CATALOG_BY_TYPE,
    _resolve_hardware_snapshot,
    _resolve_order_sources_batch,
    _resolve_part_snapshot,
)
from ._q_core import (  # noqa: F401
    TENDER_STAGE_ORDER,
    TERMINAL_STATUSES,
    _LEGAL_TRANSITIONS,
    _clone_lines,
    _insert_blank_revision,
    _next_estimate_no,
    _recompute_line_totals,
    _recompute_revision_totals,
    advance_revision,
    archive_customer,
    create_customer,
    create_estimate,
    get_customer,
    get_estimate_summary,
    get_revision,
    list_customers,
    list_estimates,
    lock_revision_for_update,
    next_tender_stage,
    patch_customer,
    patch_estimate,
    patch_revision,
    revise_estimate,
    transition_revision,
)
from ._q_lines import (  # noqa: F401
    _assert_unlocked,
    _line_in_workspace,
    _maybe_clear_has_breakdown,
    add_hardware,
    add_part,
    create_line,
    delete_line,
    patch_hardware,
    patch_line,
    patch_part,
    remove_hardware,
    remove_part,
    reorder_lines,
    upsert_labour,
)
from ._q_labour import (  # noqa: F401
    list_labour_rates,
    patch_labour_rates,
)
from ._q_loaders import (  # noqa: F401
    estimate_detail,
    revision_detail,
)
from ._q_convert import (  # noqa: F401
    _PHC_TYPE_MAP,
    convert_to_project,
    handover_preview,
)
from ._q_orders import (  # noqa: F401
    _CATALOG_EVENT_TYPE,
    _build_order_groups,
    _collect_order_materials,
    _line_keys_db,
    _line_material_keys,
    _line_pending,
    _load_order_sources,
    _locked_handover_line,
    _material_rows,
    _material_state,
    _order_selection,
    _pending_keys,
    _refresh_line_state,
    _supplier_of,
    dismiss_order_line,
    dismiss_order_material,
    generate_orders,
    link_material_supplier,
    order_preview,
    restore_order_line,
    restore_order_material,
)
