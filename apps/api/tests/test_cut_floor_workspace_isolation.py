"""Cross-workspace cut_floor access must 404 (no existence leak)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _seed_two_workspaces_one_plan(truncate_all):
    """Workspace A has a cut_plan + cut_schedule; workspace B has its own user."""
    truncate_all()
    from app.auth.passwords import hash_password
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        wid_a = s.execute(
            text("INSERT INTO workspace(slug,name) VALUES('cfa','A') RETURNING id")
        ).scalar()
        uid_a = s.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name,
                                     password_hash, auth_role)
                VALUES (:w, 'a@cf.test', 'A', :p, 'drafter') RETURNING id
                """
            ),
            {"w": wid_a, "p": hash_password("pw")},
        ).scalar()
        pid_a = s.execute(
            text(
                """
                INSERT INTO projects(project_code, name, pm_id, workspace_id)
                VALUES ('A-1', 'A', :u, :w) RETURNING project_id
                """
            ),
            {"u": uid_a, "w": wid_a},
        ).scalar()
        plan_a = s.execute(
            text(
                """
                INSERT INTO cut_plan(workspace_id, project_id, name, created_by)
                VALUES (:w, :p, 'Hidden plan', :u) RETURNING id
                """
            ),
            {"w": wid_a, "p": pid_a, "u": uid_a},
        ).scalar()
        sched_a = s.execute(
            text(
                """
                INSERT INTO cut_schedule(cut_plan_id, scheduled_for, status,
                                          priority, created_by)
                VALUES (:cp, CURRENT_DATE, 'planned', 100, :u) RETURNING id
                """
            ),
            {"cp": plan_a, "u": uid_a},
        ).scalar()

        wid_b = s.execute(
            text("INSERT INTO workspace(slug,name) VALUES('cfb','B') RETURNING id")
        ).scalar()
        s.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name,
                                     password_hash, auth_role)
                VALUES (:w, 'b@cf.test', 'B', :p, 'drafter')
                """
            ),
            {"w": wid_b, "p": hash_password("pw")},
        )
        s.commit()
        return {"pid_a": pid_a, "plan_a": plan_a, "sched_a": sched_a}
    finally:
        s.close()


def _login_b(client: TestClient):
    r = client.post(
        "/auth/login",
        json={"workspace_slug": "cfb", "email": "b@cf.test", "password": "pw"},
    )
    assert r.status_code == 200, r.text


def test_get_cut_plan_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces_one_plan(truncate_all)
    _login_b(client)
    assert client.get(f"/cut-plans/{ids['plan_a']}").status_code == 404


def test_list_project_cut_plans_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces_one_plan(truncate_all)
    _login_b(client)
    assert client.get(f"/projects/{ids['pid_a']}/cut-plans").status_code == 404


def test_delete_cut_plan_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces_one_plan(truncate_all)
    _login_b(client)
    assert client.delete(f"/cut-plans/{ids['plan_a']}").status_code == 404


def test_get_cut_schedule_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces_one_plan(truncate_all)
    _login_b(client)
    assert client.get(f"/cut-schedules/{ids['sched_a']}").status_code == 404


def test_list_cut_schedules_cross_workspace_excludes_foreign(client, truncate_all):
    ids = _seed_two_workspaces_one_plan(truncate_all)
    _login_b(client)
    r = client.get("/cut-schedules")
    assert r.status_code == 200
    bodies = r.json()
    assert all(row.get("project_id") != ids["pid_a"] for row in bodies)


def test_patch_cut_schedule_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces_one_plan(truncate_all)
    _login_b(client)
    r = client.patch(
        f"/cut-schedules/{ids['sched_a']}", json={"status": "running"}
    )
    assert r.status_code == 404


def test_create_cut_schedule_referencing_foreign_plan_returns_404(client, truncate_all):
    ids = _seed_two_workspaces_one_plan(truncate_all)
    _login_b(client)
    r = client.post(
        "/cut-schedules",
        json={
            "cut_plan_id": ids["plan_a"],
            "scheduled_for": "2026-05-09",
        },
    )
    assert r.status_code == 404
