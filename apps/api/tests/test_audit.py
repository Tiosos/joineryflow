from sqlalchemy import text
from app.auth.audit import write_audit


def test_write_audit(db, workspace_id):
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=None,
        event="auth.login",
        target="a@b",
        payload={"ip": "127.0.0.1"},
    )
    row = db.execute(text("SELECT event, payload FROM audit_log")).mappings().first()
    assert row["event"] == "auth.login"
    assert row["payload"]["ip"] == "127.0.0.1"
