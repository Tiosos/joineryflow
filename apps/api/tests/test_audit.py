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
    # Filter to this test's workspace + target so committed live audit rows
    # in the shared dev DB don't shadow the assertion. The fixture's
    # transaction sees its own writes (READ COMMITTED) and rolls back on
    # teardown, so the row must be addressed by something unique to it.
    row = db.execute(
        text(
            "SELECT event, payload FROM audit_log "
            "WHERE workspace_id = :w AND target = :t"
        ),
        {"w": workspace_id, "t": "a@b"},
    ).mappings().first()
    assert row is not None
    assert row["event"] == "auth.login"
    assert row["payload"]["ip"] == "127.0.0.1"
