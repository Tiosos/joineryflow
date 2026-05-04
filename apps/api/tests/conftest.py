import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


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
    "project_favourites",
    "projects",
    "audit_log",
    "session",
    "app_user",
    "workspace",
)


@pytest.fixture
def truncate_all():
    """Use in autouse cleanup fixtures in route tests that need full TRUNCATE."""
    from app.db import SessionLocal

    def _do():
        s = SessionLocal()
        try:
            s.execute(text(f"TRUNCATE {', '.join(TRUNCATE_TABLES)} RESTART IDENTITY CASCADE"))
            s.commit()
        finally:
            s.close()

    return _do
