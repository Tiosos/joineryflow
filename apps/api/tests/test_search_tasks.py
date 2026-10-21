"""Tasks in Global Search (migration 0081; spec docs/archive/2026-10-21-tasks.md).

A task is the one indexed type whose rows are not all equally visible: its document carries
`visibility` and `private_to`, and `index.TaskScope` / `build_filter` keep a private task from anyone
but its people and managers. These tests cover the document, the triggers that keep it current, the
filter, and the route end to end on the FakeIndex.
"""
import pytest
from sqlalchemy import text

from app.auth import rbac_engine
from app.db import SessionLocal
from app.main import app
from app.search import documents as D
from app.search.index import FakeIndex, SearchQuery, TaskScope, build_filter
from app.search.routes import search_index

from .conftest import truncate_fixture
from .helpers import login, login_same_workspace
from .search_helpers import make_tree

BASE_KEYS = {"id", "type", "entity_id", "workspace_id", "project_id", "project_code",
             "codes", "title", "subtitle", "body", "status", "archived", "updated_at", "url"}

_cleanup = truncate_fixture()


def _user(db, w, name="Sam", role="editor"):
    return db.execute(text(
        "INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)"
        " VALUES (:w, :e, :n, 'x', :r) RETURNING id"),
        {"w": w, "e": f"{name.lower()}-{role}@tasks.test", "n": name, "r": role}).scalar()


def _task(db, w, creator, *, title="Chase the hinge supplier", assignee=None, status="open",
          project=None, item=None, cutlist=None, due=None, description=None):
    return db.execute(text("""
        INSERT INTO task(workspace_id, title, description, status, assignee_id, created_by, due_date,
                         project_id, item_id, cutlist_id)
        VALUES (:w, :t, :d, :s, :a, :c, :due, :p, :i, :cl) RETURNING task_id"""),
        {"w": w, "t": title, "d": description, "s": status, "a": assignee, "c": creator,
         "due": due, "p": project, "i": item, "cl": cutlist}).scalar()


# --- the document ----------------------------------------------------------------------------

def test_a_private_task_document(db, workspace_id):
    me, sam = _user(db, workspace_id, "Mia"), _user(db, workspace_id, "Sam")
    tid = _task(db, workspace_id, me, assignee=sam, due="2030-01-31", description="before Friday")
    d = D.load(db, "task", [tid])[tid]
    assert set(d) == BASE_KEYS | {"visibility", "private_to"}
    assert (d["id"], d["type"], d["visibility"]) == (f"task-{tid}", "task", "private")
    assert d["private_to"] == sorted([me, sam])
    assert d["subtitle"] == "Open · Due 2030-01-31"
    assert "before Friday" in d["body"] and "Sam" in d["body"] and "Mia" in d["body"]
    assert d["url"] == f"/tasks?task={tid}" and d["archived"] is False and d["project_id"] is None


def test_an_item_task_carries_its_label_codes_and_project(db, workspace_id):
    t = make_tree(db, workspace_id)
    me = _user(db, workspace_id)
    tid = _task(db, workspace_id, me, item=t["item"])
    num = db.execute(text("SELECT num FROM items WHERE item_id = :i"), {"i": t["item"]}).scalar()
    d = D.load(db, "task", [tid])[tid]
    assert d["visibility"] == "tracking" and d["private_to"] == [me]
    assert d["subtitle"].startswith(f"Item {num} · Open") and str(num) in d["codes"]
    assert (d["project_id"], d["project_code"]) == (t["project"], "SRCH-1")


def test_project_and_cutlist_tasks_take_their_modules_visibility(db, workspace_id):
    t = make_tree(db, workspace_id)
    me = _user(db, workspace_id)
    on_project = _task(db, workspace_id, me, project=t["project"])
    on_cutlist = _task(db, workspace_id, me, cutlist=t["cutlist"])
    docs = D.load(db, "task", [on_project, on_cutlist])
    assert docs[on_project]["visibility"] == "tracking" and "SRCH-1" in docs[on_project]["codes"]
    assert docs[on_project]["subtitle"].startswith("Project SRCH-1")
    assert docs[on_cutlist]["visibility"] == "list" and docs[on_cutlist]["subtitle"].startswith("Cutlist ")


@pytest.mark.parametrize("status,archived", [("open", False), ("in_progress", False),
                                             ("done", True), ("cancelled", True)])
def test_done_and_cancelled_tasks_are_archived(db, workspace_id, status, archived):
    tid = _task(db, workspace_id, _user(db, workspace_id), status=status)
    d = D.load(db, "task", [tid])[tid]
    assert d["archived"] is archived and d["status"] == status


def test_a_soft_deleted_item_or_cutlist_takes_its_tasks_out_of_the_index(db, workspace_id):
    t = make_tree(db, workspace_id)
    me = _user(db, workspace_id)
    on_item = _task(db, workspace_id, me, item=t["item"])
    on_cutlist = _task(db, workspace_id, me, cutlist=t["cutlist"])
    assert set(D.load(db, "task", [on_item, on_cutlist])) == {on_item, on_cutlist}
    db.execute(text("UPDATE items SET deleted = true WHERE item_id = :i"), {"i": t["item"]})
    db.execute(text("UPDATE cutlist SET deleted = true WHERE cutlist_id = :c"), {"c": t["cutlist"]})
    assert D.load(db, "task", [on_item, on_cutlist]) == {}


# --- the triggers (0081) ---------------------------------------------------------------------

def _outbox_since(db, base):
    return [tuple(r) for r in db.execute(text(
        "SELECT entity_type, entity_id FROM search_outbox WHERE outbox_id > :b ORDER BY outbox_id"),
        {"b": base})]


def _mark(db):
    return db.execute(text("SELECT COALESCE(MAX(outbox_id), 0) FROM search_outbox")).scalar()


def test_task_writes_enqueue_the_task(db, workspace_id):
    me = _user(db, workspace_id)
    base = _mark(db)
    tid = _task(db, workspace_id, me)
    db.execute(text("UPDATE task SET title = 'New' WHERE task_id = :t"), {"t": tid})
    db.execute(text("DELETE FROM task WHERE task_id = :t"), {"t": tid})
    assert _outbox_since(db, base) == [("task", tid)] * 3


def test_values_a_task_document_embeds_fan_out_to_it(db, workspace_id):
    t = make_tree(db, workspace_id)
    sam = _user(db, workspace_id, "Sam")
    on_project = _task(db, workspace_id, sam, project=t["project"])
    on_item = _task(db, workspace_id, sam, item=t["item"])
    on_cutlist = _task(db, workspace_id, sam, cutlist=t["cutlist"])
    assigned = _task(db, workspace_id, _user(db, workspace_id, "Mia"), assignee=sam)

    def fired(sql, **p):
        base = _mark(db)
        db.execute(text(sql), p)
        return {e for e in _outbox_since(db, base) if e[0] == "task"}

    assert fired("UPDATE projects SET project_code = 'SRCH-9' WHERE project_id = :p",
                 p=t["project"]) == {("task", on_project)}
    assert fired("UPDATE items SET code = 'K-1' WHERE item_id = :i", i=t["item"]) == {("task", on_item)}
    assert fired("UPDATE items SET deleted = true WHERE item_id = :i", i=t["item"]) == {("task", on_item)}
    assert fired("UPDATE cutlist SET name = 'Renamed' WHERE cutlist_id = :c",
                 c=t["cutlist"]) == {("task", on_cutlist)}
    assert fired("UPDATE app_user SET full_name = 'Samuel' WHERE id = :u", u=sam) == {("task", assigned)}


def test_unrelated_saves_do_not_fan_out_to_tasks(db, workspace_id):
    t = make_tree(db, workspace_id)
    _task(db, workspace_id, _user(db, workspace_id), item=t["item"], project=None)
    base = _mark(db)
    db.execute(text("UPDATE items SET description = 'Island bench v2' WHERE item_id = :i"), {"i": t["item"]})
    db.execute(text("UPDATE projects SET builder = 'B' WHERE project_id = :p"), {"p": t["project"]})
    assert [e for e in _outbox_since(db, base) if e[0] == "task"] == []


# --- the filter -------------------------------------------------------------------------------

def _q(scope, types=("task",), **kw):
    return SearchQuery(q="x", workspace_id=5, types=list(types), task_scope=scope, **kw)


def test_build_filter_for_a_manager_a_plain_user_and_a_user_with_no_module_reads():
    manager = build_filter(_q(TaskScope(9, True, True, True)))
    assert manager == ('workspace_id = 5 AND (type = task AND (visibility = "tracking" OR '
                       'visibility = "list" OR visibility = "private")) AND archived = false')
    editor = build_filter(_q(TaskScope(9, True, False, False)))
    assert 'visibility = "list"' not in editor
    assert '(visibility = "private" AND private_to = 9)' in editor and 'visibility = "private")' not in editor
    nothing = build_filter(_q(TaskScope(9, False, False, False)))
    assert nothing == ('workspace_id = 5 AND (type = task AND ((visibility = "private" AND private_to = 9)))'
                       ' AND archived = false')       # only the user's own private tasks


def test_build_filter_combines_tasks_with_other_types_and_leaves_old_queries_unchanged():
    f = build_filter(_q(TaskScope(9, True, True, False), types=("item", "task")))
    assert f.startswith("workspace_id = 5 AND (type IN [item] OR (type = task AND (")
    assert build_filter(SearchQuery(q="x", workspace_id=5, types=["item", "order"])) == \
        "workspace_id = 5 AND type IN [item, order] AND archived = false"


def test_a_task_query_without_a_scope_searches_nothing():
    with pytest.raises(ValueError):
        build_filter(_q(None))
    # and the fake agrees: an unscoped query sees no task
    fake = FakeIndex()
    fake.upsert([{"id": "task-1", "type": "task", "entity_id": 1, "workspace_id": 5, "project_id": None,
                  "codes": [], "title": "hinge", "subtitle": "", "body": "", "status": "open",
                  "archived": False, "updated_at": 0, "url": "/tasks?task=1",
                  "visibility": "tracking", "private_to": [1]}])
    # (the fake raises the same ValueError build_filter does, so it never silently returns tasks)
    with pytest.raises(ValueError):
        fake.search(SearchQuery(q="hinge", workspace_id=5, types=["task"]))


def test_the_user_id_in_the_filter_is_an_integer():
    with pytest.raises(ValueError):
        build_filter(_q(TaskScope("9 OR workspace_id > 0", True, True, False)))  # type: ignore[arg-type]


# --- the route, end to end on the FakeIndex ---------------------------------------------------

@pytest.fixture
def index():
    fake = FakeIndex()
    app.dependency_overrides[search_index] = lambda: fake
    yield fake
    app.dependency_overrides.pop(search_index, None)


def _index_all_tasks(fake):
    with SessionLocal() as s:
        ids = list(s.execute(text("SELECT task_id FROM task")).scalars())
        fake.upsert(list(D.load(s, "task", ids).values()))


def _hits(client, q="hinge", **params):
    body = client.get("/search", params={"q": q, **params}).json()
    return [h["title"] for h in body["hits"] if h["type"] == "task"], body


def test_a_private_task_reaches_its_people_and_managers_only(index):
    editor, w, _ = login("editor")
    mate, mate_id = login_same_workspace(w, "editor")
    other, _ = login_same_workspace(w, "estimator")
    manager, _ = login_same_workspace(w, "manager")
    assert editor.post("/tasks", json={"title": "Chase the hinge supplier",
                                       "assignee_id": mate_id}).status_code == 201
    _index_all_tasks(index)
    assert _hits(editor)[0] == ["Chase the hinge supplier"]       # creator
    assert _hits(mate)[0] == ["Chase the hinge supplier"]         # assignee
    assert _hits(manager)[0] == ["Chase the hinge supplier"]      # manager
    names, body = _hits(other)                                    # a colleague with tracking:read
    assert names == [] and "task" not in body["type_counts"]


def test_a_task_on_an_item_follows_tracking_and_on_a_cutlist_follows_list(index, monkeypatch):
    manager, w, _ = login("manager")
    viewer, _ = login_same_workspace(w, "viewer")
    with SessionLocal() as s:
        t = make_tree(s, w)
        s.commit()
    assert manager.post("/tasks", json={"title": "Fit the hinge on the item", "item_id": t["item"]}).status_code == 201
    assert manager.post("/tasks", json={"title": "Cut the hinge sheet", "cutlist_id": t["cutlist"]}).status_code == 201
    _index_all_tasks(index)
    assert set(_hits(viewer)[0]) == {"Fit the hinge on the item", "Cut the hinge sheet"}
    for module, gone in (("tracking", "Fit the hinge on the item"), ("list", "Cut the hinge sheet")):
        matrix = {**rbac_engine.MATRIX, "viewer": {**rbac_engine.MATRIX["viewer"], module: set()}}
        monkeypatch.setattr(rbac_engine, "MATRIX", matrix)
        names, body = _hits(viewer)
        assert gone not in names and len(names) == 1 and body["type_counts"]["task"] == 1
        monkeypatch.undo()


def test_done_tasks_need_include_archived_and_another_workspace_never_sees_them(index):
    manager, _, _ = login("manager")
    stranger, _, _ = login("admin")
    tid = manager.post("/tasks", json={"title": "Order the hinge plates"}).json()["task_id"]
    manager.post(f"/tasks/{tid}/status", json={"status": "done"})
    _index_all_tasks(index)
    assert _hits(manager)[0] == []
    assert _hits(manager, include_archived="true")[0] == ["Order the hinge plates"]
    assert _hits(stranger, include_archived="true")[0] == []
