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
