import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


# Reference/lookup rows that many tables FK against (items.status ->
# status_options, item_stages.stage_key -> stages). Several test files seed
# these per-test AND truncate them in teardown, which leaves them empty for any
# later file that assumes they are still present (e.g. test_shop_floor_routes,
# test_optimiser). This autouse fixture re-asserts them before every test —
# idempotent (ON CONFLICT DO NOTHING) — so the suite is order-independent for
# reference data and never depends on `make seed` having run.
_REF_STATUS_OPTIONS = [
    ("CLEAR", 1), ("VOID", 2), ("NOTE!", 3),
    ("LIVE", 4), ("APPROVED", 5), ("HOLD", 6),
]
_REF_STAGES = [
    ("REQ", "Required", 1), ("SM", "Shop Material", 2), ("LISTED", "Listed", 3),
    ("DOWN", "Down", 4), ("CNC", "CNC", 5), ("EDGED", "Edged", 6),
    ("PAINTED", "Painted", 7), ("MADE", "Made", 8), ("DEL", "Delivered", 9),
    ("INST", "Installed", 10),
]


@pytest.fixture(autouse=True)
def _ensure_reference_data():
    from app.db import SessionLocal

    s = SessionLocal()
    try:
        for key, order in _REF_STATUS_OPTIONS:
            s.execute(
                text("INSERT INTO status_options(status_key, sort_order)"
                     " VALUES(:k, :o) ON CONFLICT DO NOTHING"),
                {"k": key, "o": order},
            )
        for key, label, order in _REF_STAGES:
            s.execute(
                text("INSERT INTO stages(stage_key, label, sort_order)"
                     " VALUES(:k, :l, :o) ON CONFLICT DO NOTHING"),
                {"k": key, "l": label, "o": order},
            )
        s.commit()
    finally:
        s.close()
    yield


@pytest.fixture(autouse=True)
def _fresh_pool_per_test():
    """Dispose the API's SQLAlchemy connection pool around every test.

    Symptom this prevents: cross-file pytest deadlocks. Test A's
    TestClient calls leave pooled connections that hold row locks
    from rolled-back partial transactions. Test B then TRUNCATEs the
    shared `app_user` / `audit_log` tables in teardown and deadlocks
    against those stale locks.

    Disposing the engine before AND after each test forces the pool
    to close every existing connection (releasing held locks) so each
    test starts and ends with a clean pool. Cost is ~ms per test for
    fresh connection setup.
    """
    from app.db import engine
    engine.dispose()
    yield


@pytest.fixture
def db():
    """Transaction-rollback fixture: every test runs inside a transaction that
    is rolled back on teardown, so the shared DATABASE_URL schema stays clean."""
    url = os.environ["DATABASE_URL"]
    eng = create_engine(url, future=True)
    conn = eng.connect()
    trans = conn.begin()
    Session = sessionmaker(bind=conn, autoflush=False, future=True)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        trans.rollback()
        conn.close()


@pytest.fixture
def workspace_id(db):
    wid = db.execute(
        text("INSERT INTO workspace(slug,name) VALUES('test','Test') RETURNING id")
    ).scalar()
    return wid


TRUNCATE_TABLES = (
    "estimate_line_labour",
    "estimate_line_hardware",
    "estimate_line_part",
    "estimate_line",
    "estimate_revision",
    "estimate",
    "customer",
    "workspace_labour_rate",
    "stage_completion_log",
    "worker_assignment",
    "shop_drawing_revision",
    "shop_drawing",
    "sample",
    "item_attachment",
    "file_blob",
    "batch_allocations",
    "procurement_batches",
    "project_hardware_catalog_log",
    "project_hardware_catalog",
    "item_hardware_lines",
    "parts",
    "modules",
    "item_status_log",
    "item_edit_log",
    "item_stages",
    "items",
    "cv_import_run",
    "project_favourites",
    "projects",
    "cv_material_mapping",
    "audit_log",
    "session",
    "app_user",
    "workspace",
)


@pytest.fixture
def truncate_all():
    """Use in autouse cleanup fixtures in route tests that need full TRUNCATE.

    Sets a per-statement lock_timeout so any residual cross-test
    deadlock (which `_fresh_pool_per_test` may not have fully prevented)
    fails fast at 5 seconds instead of cascading into the next file.
    """
    from app.db import SessionLocal, engine

    def _do():
        # Dispose the pool right before TRUNCATE so any FastAPI route
        # connections from prior tests (which may hold idle row locks)
        # are forcibly closed, freeing the AccessExclusiveLock TRUNCATE
        # needs.
        engine.dispose()
        s = SessionLocal()
        try:
            s.execute(text("SET LOCAL lock_timeout = '5s'"))
            s.execute(text(f"TRUNCATE {', '.join(TRUNCATE_TABLES)} RESTART IDENTITY CASCADE"))
            s.commit()
        finally:
            s.close()

    return _do
