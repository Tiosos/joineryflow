"""Cross-workspace shop_floor access must 404 (no existence leak)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _seed_two_workspaces_one_assignment(truncate_all):
    """Workspace A has a project + item + worker + assignment;
    workspace B has its own user."""
    truncate_all()
    from app.auth.passwords import hash_password
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        # Stages lookup table is wiped by the full-suite run — re-seed
        # the 5 shop-floor stages so the FK to stages(stage_key) holds.
        for stage in ("DOWN", "CNC", "EDGED", "PAINTED", "MADE"):
            s.execute(
                text(
                    """
                    INSERT INTO stages(stage_key, label, sort_order)
                    VALUES (:k, :k, 0)
                    ON CONFLICT (stage_key) DO NOTHING
                    """
                ),
                {"k": stage},
            )
        wid_a = s.execute(
            text("INSERT INTO workspace(slug,name) VALUES('sfa','A') RETURNING id")
        ).scalar()
        uid_a = s.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name,
                                     password_hash, auth_role)
                VALUES (:w, 'a@sf.test', 'A', :p, 'editor') RETURNING id
                """
            ),
            {"w": wid_a, "p": hash_password("pw")},
        ).scalar()
        worker_a = s.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name,
                                     password_hash, auth_role,
                                     is_shop_worker)
                VALUES (:w, 'wa@sf.test', 'Worker A', :p, 'editor', true)
                RETURNING id
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
        iid_a = s.execute(
            text(
                """
                INSERT INTO items(num, project_id, code, description,
                                  painting_req, paint_after_assembly, deleted)
                VALUES (:n, :p, 'A-ITEM-1', 'A item', true, false, false)
                RETURNING item_id
                """
            ),
            {"n": wid_a * 1000 + 1, "p": pid_a},
        ).scalar()
        # 0030: Shop Floor keys on the cutlist, so the item needs one.
        cl_a = s.execute(
            text("INSERT INTO cutlist(project_id, cutlist_no)"
                 " VALUES (:p, nextval('joinery_number_seq')) RETURNING cutlist_id"),
            {"p": pid_a},
        ).scalar()
        s.execute(text("UPDATE items SET cutlist_id = :c WHERE item_id = :i"),
                  {"c": cl_a, "i": iid_a})
        aid_a = s.execute(
            text(
                """
                INSERT INTO worker_assignment(cutlist_id, stage_key, worker_id,
                                              status, assigned_by)
                VALUES ((SELECT cutlist_id FROM items WHERE item_id = :i),
                        'DOWN', :w, 'assigned', :ab)
                RETURNING assignment_id
                """
            ),
            {"i": iid_a, "w": worker_a, "ab": uid_a},
        ).scalar()

        wid_b = s.execute(
            text("INSERT INTO workspace(slug,name) VALUES('sfb','B') RETURNING id")
        ).scalar()
        s.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name,
                                     password_hash, auth_role)
                VALUES (:w, 'b@sf.test', 'B', :p, 'editor')
                """
            ),
            {"w": wid_b, "p": hash_password("pw")},
        )
        s.commit()
        return {
            "pid_a": pid_a, "iid_a": iid_a,
            "worker_a": worker_a, "aid_a": aid_a,
        }
    finally:
        s.close()


def _login_b(client: TestClient):
    r = client.post(
        "/auth/login",
        json={"workspace_slug": "sfb", "email": "b@sf.test", "password": "pw"},
    )
    assert r.status_code == 200, r.text


def test_get_board_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces_one_assignment(truncate_all)
    _login_b(client)
    assert client.get(
        f"/projects/{ids['pid_a']}/shop-floor/board"
    ).status_code == 404


def test_list_workers_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces_one_assignment(truncate_all)
    _login_b(client)
    assert client.get(
        f"/projects/{ids['pid_a']}/shop-floor/workers"
    ).status_code == 404


def test_worker_queue_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces_one_assignment(truncate_all)
    _login_b(client)
    assert client.get(f"/workers/{ids['worker_a']}/queue").status_code == 404


def test_recent_completions_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces_one_assignment(truncate_all)
    _login_b(client)
    assert client.get(
        f"/workers/{ids['worker_a']}/recent-completions"
    ).status_code == 404


def test_patch_assignment_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces_one_assignment(truncate_all)
    _login_b(client)
    r = client.patch(
        f"/assignments/{ids['aid_a']}", json={"note": "leaked"}
    )
    assert r.status_code == 404


def test_cancel_assignment_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces_one_assignment(truncate_all)
    _login_b(client)
    assert client.delete(f"/assignments/{ids['aid_a']}").status_code == 404


def test_start_assignment_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces_one_assignment(truncate_all)
    _login_b(client)
    assert client.post(
        f"/assignments/{ids['aid_a']}/start"
    ).status_code == 404


def test_create_assignment_into_foreign_project_returns_404(client, truncate_all):
    ids = _seed_two_workspaces_one_assignment(truncate_all)
    _login_b(client)
    r = client.post(
        f"/projects/{ids['pid_a']}/items/{ids['iid_a']}/assignments",
        json={"stage_key": "DOWN", "worker_id": ids["worker_a"]},
    )
    assert r.status_code == 404
