"""Controlled Lock: a non-owner's save becomes a request

Today's item lock is advisory: `patch_item` lets a non-owner's save through and
records `item.lock_overridden` after the fact. **Q509** turns that into a
Controlled Lock — the save becomes a *request* the owner (or a manager)
approves or rejects — and the audit event this table replaces is the evidence
that people really do override in practice.

One table, `item_lock_request`, holds the proposed change until it is decided.
`requested_changes` is the `PatchItemIn` body as submitted, so approval replays
exactly what was asked for rather than a reconstruction.

**Scope.** `PATCH /items/{id}` only — the one surface that emits
`item.lock_overridden` today. **Q510** reads as a ceiling, not a mandate: no
field, tab, Area, revision or department locks, and **no project lock** either,
because `projects` carries no lock column of any kind (verified against the
schema at `0031`) — a project lock would be new functionality, not a
conversion. **Q508**'s other two lock types (Hard, Approval) and **Q511** /
**Q512** (optimistic concurrency, per-field versioning) have no task in the
plan; see `OPEN-QUESTIONS.md` Q566.

Revision ID: 0032
Revises: 0031
Create Date: 2026-09-19
"""
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE item_lock_request (
        request_id        bigserial PRIMARY KEY,
        item_id           integer     NOT NULL
                            REFERENCES items (item_id) ON DELETE CASCADE,
        requested_by      integer     NOT NULL REFERENCES app_user (id),
        requested_changes jsonb       NOT NULL
                            CHECK (jsonb_typeof(requested_changes) = 'object'),
        status            varchar(16) NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'approved', 'rejected')),
        created_at        timestamptz NOT NULL DEFAULT now(),
        updated_at        timestamptz NOT NULL DEFAULT now(),
        decided_by        integer     REFERENCES app_user (id),
        decided_at        timestamptz,
        decision_note     text,
        CONSTRAINT item_lock_request_decided_ck CHECK (
            (status = 'pending' AND decided_by IS NULL AND decided_at IS NULL)
            OR (status <> 'pending' AND decided_by IS NOT NULL AND decided_at IS NOT NULL)
        )
    );

    COMMENT ON TABLE item_lock_request IS
        'Controlled Lock (Q509): a non-owner save on a locked item, held for '
        'the lock owner or a manager to approve or reject.';
    COMMENT ON COLUMN item_lock_request.requested_changes IS
        'The PatchItemIn body as submitted, replayed verbatim on approval.';

    -- One live request per person per item: saving again revises your own
    -- pending request rather than queueing a second, older proposal behind it.
    CREATE UNIQUE INDEX uniq_pending_lock_request
        ON item_lock_request (item_id, requested_by)
     WHERE status = 'pending';

    -- The editor's "N changes waiting" read.
    CREATE INDEX idx_lock_request_pending
        ON item_lock_request (item_id)
     WHERE status = 'pending';
    """)


def downgrade():
    # Pending requests are proposals that were never applied to an item, so
    # dropping the table loses nothing that reached `items`; decided ones stay
    # recorded in audit_log as item.lock_request.{create,approve,reject}.
    op.execute("DROP TABLE IF EXISTS item_lock_request;")
