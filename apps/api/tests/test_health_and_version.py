"""Health-check split and /version (Phase 0 §2 and §9.2).

Covers: /health stays as the live alias; /health/ready is 200 only when the
database answers AND its schema is at the head the image was built with (Q2
gate 3 — a new image on an old schema must read unhealthy); /version always
answers, even when the database is down.
"""
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import meta
from app.db import SessionLocal
from app.main import app

client = TestClient(app)


def test_health_is_kept_as_the_live_alias():
    # README.md:40 and e2e smoke specs depend on this route — it must not change.
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_live_is_alive():
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_ready_when_db_and_schema_match():
    r = client.get("/health/ready")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["checks"]["db"] is True
    assert body["checks"]["schema_match"] is True
    assert body["checks"]["db_schema"] == [body["checks"]["expected_schema_head"]]


def test_ready_fails_when_schema_is_behind():
    """Move alembic_version off head, prove the gate trips, restore it.

    This is the half-upgrade the check exists for: new image, old schema.
    """
    db = SessionLocal()
    try:
        real = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        db.execute(text("UPDATE alembic_version SET version_num = 'behind-test'"))
        db.commit()
        try:
            r = client.get("/health/ready")
            assert r.status_code == 503
            body = r.json()
            assert body["ok"] is False
            assert body["checks"]["db"] is True
            assert body["checks"]["schema_match"] is False
            assert body["checks"]["db_schema"] == ["behind-test"]
        finally:
            db.execute(
                text("UPDATE alembic_version SET version_num = :v"), {"v": real}
            )
            db.commit()
    finally:
        db.close()

    # Paranoia: the next readiness call is healthy again.
    assert client.get("/health/ready").status_code == 200


def test_ready_fails_when_db_is_down(monkeypatch):
    def _boom():
        raise RuntimeError("no db")

    monkeypatch.setattr("app.main.SessionLocal", _boom)
    r = client.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["ok"] is False
    assert body["checks"]["db"] is False


def test_version_reports_image_and_schema():
    r = client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert body["version"]  # "dev" in a source checkout, the image tag in prod
    assert body["schema_head"] == meta.expected_schema_head()
    assert body["db_schema"] == [meta.expected_schema_head()]


def test_version_answers_even_with_db_down(monkeypatch):
    def _boom():
        raise RuntimeError("no db")

    monkeypatch.setattr("app.main.SessionLocal", _boom)
    r = client.get("/version")
    assert r.status_code == 200
    assert r.json()["db_schema"] is None
