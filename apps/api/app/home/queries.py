"""SQL query functions for the home dashboard endpoint.

Schema drift notes verified against live DB:
  - procurement_batches has NO workspace_id column. Workspace scoping goes via
    project_id -> projects.pm_id -> app_user.workspace_id (same EXISTS pattern
    as items/queries.py _WORKSPACE_FILTER).
  - items has NO 'value' column. value_in_progress metric always returns 0.0.
    TODO: add items.value column in a future migration when cost tracking lands.
  - purchase_orders.status valid values: Draft, Pending, Approved, Rejected,
    Delivered, Cancelled, Hold, Quote, Next. 'open' = NOT IN (Delivered, Cancelled, Rejected).
  - approval_workflows.status valid values: Pending, Approved, Rejected, Skipped.
  - stages table may be empty in fresh DB (seeded per-test in tests).
  - app_user.auth_role includes 'drafter' as a distinct role (not just 'editor').

Strategy: 6-8 small SQL statements, clarity over one mega-CTE.
"""
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.sessions import AuthUser
from .schemas import (
    DeliveryToday,
    FavouriteProject,
    HomeDashboardOut,
    MetricCard,
    MyDayItem,
    TeamActivityRow,
)

# Workspace filter for items (no workspace_id on items table).
# items -> projects -> pm_id -> app_user.workspace_id
_ITEM_WORKSPACE_EXISTS = """
    EXISTS (
        SELECT 1 FROM projects p2
        JOIN app_user au ON au.id = p2.pm_id
        WHERE p2.project_id = i.project_id
          AND au.workspace_id = :wid
    )
"""

# Workspace filter for procurement_batches (no workspace_id on batches table).
# batches -> projects -> pm_id -> app_user.workspace_id
_BATCH_WORKSPACE_EXISTS = """
    EXISTS (
        SELECT 1 FROM projects p2
        JOIN app_user au ON au.id = p2.pm_id
        WHERE p2.project_id = b.project_id
          AND au.workspace_id = :wid
    )
"""


def _role_view(user: AuthUser) -> str:
    if user.auth_role == "admin":
        return "ceo"
    if user.auth_role == "manager":
        return "pm"
    if user.auth_role == "drafter":
        return "drafter"
    if user.auth_role == "purchase_officer":
        return "purchase_officer"
    return "viewer"


# ── Metrics ────────────────────────────────────────────────────────────────────

def _metrics_general(db: Session, *, user: AuthUser, today: date) -> list[MetricCard]:
    """4 metric cards for ceo / pm / drafter / viewer roles.

    Scoping:
      - ceo (admin): workspace-wide
      - pm (manager): items in projects where pm_id = caller
      - drafter: items where cutlist_owner_id = caller
      - viewer/editor: workspace-wide (read-only)
    """
    wid = user.workspace_id
    uid = user.id
    role = _role_view(user)

    if role == "pm":
        scope_clause = "AND i.project_id IN (SELECT project_id FROM projects WHERE pm_id = :uid)"
    elif role == "drafter":
        scope_clause = "AND i.cutlist_owner_id = :uid"
    else:
        scope_clause = ""

    # metric 1: overdue items with at least one item_stages row where
    # due_date < today AND done_date IS NULL
    overdue_row = db.execute(
        text(
            f"""
            SELECT COUNT(DISTINCT i.item_id) AS cnt
            FROM items i
            WHERE {_ITEM_WORKSPACE_EXISTS}
              {scope_clause}
              AND EXISTS (
                  SELECT 1 FROM item_stages s
                  WHERE s.item_id = i.item_id
                    AND s.due_date < :today
                    AND s.done_date IS NULL
              )
            """
        ),
        {"wid": wid, "uid": uid, "today": today},
    ).mappings().first()
    overdue_count = int(overdue_row["cnt"]) if overdue_row else 0

    # metric 2: in_optimisation — DOWN done_date IS NOT NULL AND CNC done_date IS NULL
    in_opt_row = db.execute(
        text(
            f"""
            SELECT COUNT(DISTINCT i.item_id) AS cnt
            FROM items i
            WHERE {_ITEM_WORKSPACE_EXISTS}
              {scope_clause}
              AND EXISTS (
                  SELECT 1 FROM item_stages s
                  WHERE s.item_id = i.item_id AND s.stage_key = 'DOWN' AND s.done_date IS NOT NULL
              )
              AND NOT EXISTS (
                  SELECT 1 FROM item_stages s
                  WHERE s.item_id = i.item_id AND s.stage_key = 'CNC' AND s.done_date IS NOT NULL
              )
            """
        ),
        {"wid": wid, "uid": uid},
    ).mappings().first()
    in_opt_count = int(in_opt_row["cnt"]) if in_opt_row else 0

    # metric 3: awaiting_install — DEL done_date IS NOT NULL AND INST done_date IS NULL
    await_install_row = db.execute(
        text(
            f"""
            SELECT COUNT(DISTINCT i.item_id) AS cnt
            FROM items i
            WHERE {_ITEM_WORKSPACE_EXISTS}
              {scope_clause}
              AND EXISTS (
                  SELECT 1 FROM item_stages s
                  WHERE s.item_id = i.item_id AND s.stage_key = 'DEL' AND s.done_date IS NOT NULL
              )
              AND NOT EXISTS (
                  SELECT 1 FROM item_stages s
                  WHERE s.item_id = i.item_id AND s.stage_key = 'INST' AND s.done_date IS NOT NULL
              )
            """
        ),
        {"wid": wid, "uid": uid},
    ).mappings().first()
    await_install_count = int(await_install_row["cnt"]) if await_install_row else 0

    # metric 4: value_in_progress
    # TODO: items table has no 'value' column. Returns 0.0 until a future migration
    # adds items.value (numeric) as a cost-tracking field.
    value_in_progress = 0.0

    return [
        MetricCard(
            key="overdue",
            label="Overdue Items",
            value=overdue_count,
            href="/tracking?status=overdue",
        ),
        MetricCard(
            key="in_optimisation",
            label="In Optimisation",
            value=in_opt_count,
            href="/tracking?stage=in_optimisation",
        ),
        MetricCard(
            key="awaiting_install",
            label="Awaiting Install",
            value=await_install_count,
            href="/tracking?stage=awaiting_install",
        ),
        MetricCard(
            key="value_in_progress",
            label="Value in Progress",
            value=value_in_progress,
            href="/tracking?status=LIVE",
        ),
    ]


def _metrics_purchase_officer(db: Session, *, user: AuthUser, today: date) -> list[MetricCard]:
    """4 metric cards for the purchase_officer role."""
    wid = user.workspace_id
    week_end = today + timedelta(days=7)

    # metric 1: overdue deliveries — batches with eta_date < today and not yet received
    overdue_row = db.execute(
        text(
            f"""
            SELECT COUNT(*) AS cnt
            FROM procurement_batches b
            WHERE {_BATCH_WORKSPACE_EXISTS}
              AND b.eta_date < :today
              AND b.received_date IS NULL
            """
        ),
        {"wid": wid, "today": today},
    ).mappings().first()
    overdue_count = int(overdue_row["cnt"]) if overdue_row else 0

    # metric 2: open_pos — purchase_orders NOT in terminal states
    open_pos_row = db.execute(
        text(
            """
            SELECT COUNT(*) AS cnt
            FROM purchase_orders
            WHERE status NOT IN ('Delivered', 'Cancelled', 'Rejected')
            """
        ),
        {},
    ).mappings().first()
    open_pos_count = int(open_pos_row["cnt"]) if open_pos_row else 0

    # metric 3: deliveries_this_week — batches with eta_date in [today, today+7], not received
    deliveries_week_row = db.execute(
        text(
            f"""
            SELECT COUNT(*) AS cnt
            FROM procurement_batches b
            WHERE {_BATCH_WORKSPACE_EXISTS}
              AND b.eta_date BETWEEN :today AND :week_end
              AND b.received_date IS NULL
            """
        ),
        {"wid": wid, "today": today, "week_end": week_end},
    ).mappings().first()
    deliveries_week_count = int(deliveries_week_row["cnt"]) if deliveries_week_row else 0

    # metric 4: pending_approvals — approval_workflows with status='Pending'
    pending_approvals_row = db.execute(
        text(
            """
            SELECT COUNT(*) AS cnt
            FROM approval_workflows
            WHERE status = 'Pending'
            """
        ),
        {},
    ).mappings().first()
    pending_approvals_count = int(pending_approvals_row["cnt"]) if pending_approvals_row else 0

    return [
        MetricCard(
            key="overdue",
            label="Overdue Deliveries",
            value=overdue_count,
            href="/orderbook?filter=overdue",
        ),
        MetricCard(
            key="open_pos",
            label="Open POs",
            value=open_pos_count,
            href="/orderbook?status=open",
        ),
        MetricCard(
            key="deliveries_this_week",
            label="Deliveries This Week",
            value=deliveries_week_count,
            href="/orderbook?filter=this_week",
        ),
        MetricCard(
            key="pending_approvals",
            label="Pending Approvals",
            value=pending_approvals_count,
            href="/orderbook?filter=pending_approvals",
        ),
    ]


# ── My Day ─────────────────────────────────────────────────────────────────────

def _my_day(db: Session, *, user: AuthUser, today: date) -> list[MyDayItem]:
    """Top-5 upcoming items for drafter or PM; empty list for other roles."""
    wid = user.workspace_id
    uid = user.id
    role = _role_view(user)
    horizon = today + timedelta(days=3)

    if role == "drafter":
        scope_clause = "AND i.cutlist_owner_id = :uid"
    elif role == "pm":
        scope_clause = "AND i.project_id IN (SELECT project_id FROM projects WHERE pm_id = :uid)"
    else:
        return []

    rows = db.execute(
        text(
            f"""
            SELECT
                i.item_id,
                pr.project_code,
                i.description,
                s.stage_key        AS next_due_stage_key,
                s.due_date         AS next_due_date
            FROM items i
            JOIN projects pr ON pr.project_id = i.project_id
            JOIN item_stages s ON s.item_id = i.item_id
            WHERE {_ITEM_WORKSPACE_EXISTS}
              {scope_clause}
              AND s.due_date <= :horizon
              AND s.due_date IS NOT NULL
              AND s.done_date IS NULL
            ORDER BY s.due_date ASC
            LIMIT 5
            """
        ),
        {"wid": wid, "uid": uid, "horizon": horizon},
    ).mappings().all()

    return [
        MyDayItem(
            item_id=r["item_id"],
            project_code=r["project_code"],
            description=r["description"],
            next_due_stage_key=r["next_due_stage_key"],
            next_due_date=r["next_due_date"],
        )
        for r in rows
    ]


# ── Deliveries Today ───────────────────────────────────────────────────────────

def _deliveries_today(db: Session, *, user: AuthUser, today: date) -> list[DeliveryToday]:
    """Procurement batches with eta_date = today, scoped to caller's workspace."""
    wid = user.workspace_id

    rows = db.execute(
        text(
            f"""
            SELECT
                b.batch_id,
                pr.project_code,
                COALESCE(b.supplier, 'Unknown') AS supplier,
                b.eta_date AS eta
            FROM procurement_batches b
            JOIN projects pr ON pr.project_id = b.project_id
            WHERE {_BATCH_WORKSPACE_EXISTS}
              AND b.eta_date = :today
              AND b.received_date IS NULL
            ORDER BY b.batch_id
            """
        ),
        {"wid": wid, "today": today},
    ).mappings().all()

    return [
        DeliveryToday(
            batch_id=r["batch_id"],
            project_code=r["project_code"],
            supplier=r["supplier"],
            eta=r["eta"],
        )
        for r in rows
    ]


# ── Team Activity ──────────────────────────────────────────────────────────────

def _team_activity(db: Session, *, user: AuthUser) -> list[TeamActivityRow]:
    """Last 8 audit_log rows for the caller's workspace, newest first."""
    rows = db.execute(
        text(
            """
            SELECT
                COALESCE(u.full_name, 'System') AS actor_name,
                a.event,
                a.target,
                a.created_at                    AS ts
            FROM audit_log a
            LEFT JOIN app_user u ON u.id = a.actor_id
            WHERE a.workspace_id = :wid
            ORDER BY a.created_at DESC
            LIMIT 8
            """
        ),
        {"wid": user.workspace_id},
    ).mappings().all()

    return [
        TeamActivityRow(
            actor_name=r["actor_name"],
            event=r["event"],
            target=r["target"],
            ts=r["ts"],
        )
        for r in rows
    ]


# ── Favourite Projects ─────────────────────────────────────────────────────────

def _favourite_projects(db: Session, *, user: AuthUser) -> list[FavouriteProject]:
    """Projects the caller has favourited, newest first."""
    rows = db.execute(
        text(
            """
            SELECT
                p.project_id AS id,
                p.project_code,
                p.name
            FROM project_favourites f
            JOIN projects p ON p.project_id = f.project_id
            WHERE f.user_id = :uid
            ORDER BY f.created_at DESC
            """
        ),
        {"uid": user.id},
    ).mappings().all()

    return [
        FavouriteProject(
            id=r["id"],
            project_code=r["project_code"],
            name=r["name"],
        )
        for r in rows
    ]


# ── All Projects Count ─────────────────────────────────────────────────────────

def _all_projects_count(db: Session, *, user: AuthUser) -> int:
    """Workspace-scoped project count using the same scoping as /projects GET."""
    row = db.execute(
        text(
            """
            SELECT COUNT(*) AS cnt
            FROM projects p
            WHERE (p.pm_id IS NULL OR p.pm_id IN (
                SELECT id FROM app_user WHERE workspace_id = :wid
            ))
            """
        ),
        {"wid": user.workspace_id},
    ).mappings().first()
    return int(row["cnt"]) if row else 0


# ── Composite entry point ──────────────────────────────────────────────────────

def dashboard(db: Session, *, user: AuthUser) -> HomeDashboardOut:
    """Build the composite home dashboard payload for the authenticated user.

    Never returns None — the caller is always authenticated.
    Uses 6-8 small SQL statements for clarity over one mega-CTE.
    """
    today = date.today()
    role = _role_view(user)

    if role == "purchase_officer":
        metrics = _metrics_purchase_officer(db, user=user, today=today)
    else:
        metrics = _metrics_general(db, user=user, today=today)

    return HomeDashboardOut(
        role_view=role,
        metrics=metrics,
        my_day=_my_day(db, user=user, today=today),
        deliveries_today=_deliveries_today(db, user=user, today=today),
        team_activity=_team_activity(db, user=user),
        favourite_projects=_favourite_projects(db, user=user),
        all_projects_count=_all_projects_count(db, user=user),
    )
