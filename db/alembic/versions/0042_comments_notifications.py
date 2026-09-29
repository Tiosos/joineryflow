"""comments + mentions + in-app notifications (Plan V1 §29, Q473 / Q521 / Q523)

`comment` is one thread entity over four object types — Project, Area, Room,
Joinery Item. §29 names eight (adding Component, Task, Change, Revision), but
Task and Change are not entities in this tree and Component / Revision are
ambiguous, so the user scoped v1 to the four that exist.

The object is held as **four nullable real FKs** with a CHECK that exactly one
is set, rather than a polymorphic `(object_type, object_id)` pair: a deleted
item / area / room / project takes its thread with it via ON DELETE CASCADE
instead of leaving dangling comments, and `object_type` is a generated column,
not a second source of truth.

Replies are **one level deep** and DB-enforced, the way 0028 enforces Q449:
`parent_is_reply` is always false when a parent is set, so the composite FK
`(parent_comment_id, parent_is_reply) -> comment (comment_id, is_reply)` can
only be satisfied by a top-level comment. Which object a reply belongs to is
inherited from its parent by the application — a reply never names an object
of its own.

`comment_mention` records who was explicitly mentioned (the client sends user
ids; the body's `@Name` text is presentation only, never parsed for identity).
`notification` is the minimal in-app inbox Q521 asks for — one row per
recipient per comment per kind ('mention' | 'reply'); no channels, preferences
or escalation (§30's rules engine is not part of this).

Not searchable: no 0033 trigger is added.

Revision ID: 0042
Revises: 0041
Create Date: 2026-09-29
"""
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE comment (
        comment_id        BIGSERIAL PRIMARY KEY,
        workspace_id      bigint NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,

        project_id        bigint REFERENCES projects(project_id) ON DELETE CASCADE,
        area_id           bigint REFERENCES area(area_id)        ON DELETE CASCADE,
        room_id           bigint REFERENCES room(room_id)        ON DELETE CASCADE,
        item_id           bigint REFERENCES items(item_id)       ON DELETE CASCADE,
        CONSTRAINT ck_comment_one_object
            CHECK (num_nonnulls(project_id, area_id, room_id, item_id) = 1),
        object_type       varchar(8) GENERATED ALWAYS AS (
            CASE WHEN project_id IS NOT NULL THEN 'project'
                 WHEN area_id    IS NOT NULL THEN 'area'
                 WHEN room_id    IS NOT NULL THEN 'room'
                 ELSE 'item' END
        ) STORED,

        parent_comment_id bigint,
        is_reply          boolean GENERATED ALWAYS AS (parent_comment_id IS NOT NULL) STORED,
        parent_is_reply   boolean GENERATED ALWAYS AS (
            CASE WHEN parent_comment_id IS NULL THEN NULL ELSE false END
        ) STORED,
        CONSTRAINT uq_comment_id_is_reply UNIQUE (comment_id, is_reply),
        CONSTRAINT fk_comment_parent_is_top_level
            FOREIGN KEY (parent_comment_id, parent_is_reply)
            REFERENCES comment (comment_id, is_reply)
            ON DELETE CASCADE,

        author_id         bigint REFERENCES app_user(id) ON DELETE SET NULL,
        body              text   NOT NULL,
        CONSTRAINT ck_comment_body_len CHECK (length(btrim(body)) BETWEEN 1 AND 5000),
        created_at        timestamptz NOT NULL DEFAULT now(),
        edited_at         timestamptz,
        deleted_at        timestamptz,
        deleted_by        bigint REFERENCES app_user(id) ON DELETE SET NULL
    );
    CREATE INDEX idx_comment_project ON comment (project_id, created_at) WHERE project_id IS NOT NULL;
    CREATE INDEX idx_comment_area    ON comment (area_id,    created_at) WHERE area_id    IS NOT NULL;
    CREATE INDEX idx_comment_room    ON comment (room_id,    created_at) WHERE room_id    IS NOT NULL;
    CREATE INDEX idx_comment_item    ON comment (item_id,    created_at) WHERE item_id    IS NOT NULL;
    CREATE INDEX idx_comment_parent  ON comment (parent_comment_id) WHERE parent_comment_id IS NOT NULL;

    CREATE TABLE comment_mention (
        comment_id bigint NOT NULL REFERENCES comment(comment_id) ON DELETE CASCADE,
        user_id    bigint NOT NULL REFERENCES app_user(id)        ON DELETE CASCADE,
        PRIMARY KEY (comment_id, user_id)
    );

    CREATE TABLE notification (
        notification_id BIGSERIAL PRIMARY KEY,
        workspace_id    bigint NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
        recipient_id    bigint NOT NULL REFERENCES app_user(id)  ON DELETE CASCADE,
        actor_id        bigint REFERENCES app_user(id) ON DELETE SET NULL,
        kind            varchar(8) NOT NULL CHECK (kind IN ('mention', 'reply')),
        comment_id      bigint NOT NULL REFERENCES comment(comment_id) ON DELETE CASCADE,
        created_at      timestamptz NOT NULL DEFAULT now(),
        read_at         timestamptz,
        -- one notification per recipient per comment per kind: an edit that
        -- re-mentions someone already notified must not ping them twice.
        CONSTRAINT uq_notification_once UNIQUE (recipient_id, comment_id, kind)
    );
    CREATE INDEX idx_notification_recipient ON notification (recipient_id, created_at DESC);
    CREATE INDEX idx_notification_unread ON notification (recipient_id) WHERE read_at IS NULL;
    """)


def downgrade():
    op.execute("""
    DROP TABLE IF EXISTS notification;
    DROP TABLE IF EXISTS comment_mention;
    DROP TABLE IF EXISTS comment;
    """)
