"""The order pop-up's tabs, part 2: Glass C (price calculator), Timber (order form), TGSolid (production rows)

- `glass_rate`: the calculator's price list per workspace, two kinds: `glass` (priced per m2) and `process`
  (per metre of perimeter, or per each), kept by the purchase officer. `um` says how a rate multiplies.
- `order_glass_calc`: one row per order: the size being costed (length, width, thickness in mm) and the
  ticked rates (`selection`: rate id -> qty). The cost is worked out on read, never stored.
- `order_timber_form`: one row per order, the Timberwood Panels custom pressing order form (face, back,
  substrate, each with a "supplied by TG" tick, finished product, deliver to, special instructions) and the
  PDF Create makes from it.
- `order_tg_run`: TG Solid production rows of an order (production start, date made, made by, date ex
  factory, location, notes).

Revision ID: 0065
Revises: 0064
Create Date: 2026-10-15
"""
from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE glass_rate (
            glass_rate_id bigserial PRIMARY KEY,
            workspace_id  bigint NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
            kind          text NOT NULL CHECK (kind IN ('glass', 'process')),
            name          varchar(150) NOT NULL,
            rate          numeric(15,4) NOT NULL CHECK (rate >= 0),
            um            varchar(10) NOT NULL,
            supplier_no   varchar(50),
            sort_order    integer NOT NULL DEFAULT 0,
            is_active     boolean NOT NULL DEFAULT true,
            created_at    timestamptz NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX uq_glass_rate_name ON glass_rate (workspace_id, kind, lower(name));

        CREATE TABLE order_glass_calc (
            po_id      bigint PRIMARY KEY REFERENCES purchase_orders(po_id) ON DELETE CASCADE,
            length_mm  integer CHECK (length_mm IS NULL OR length_mm > 0),
            width_mm   integer CHECK (width_mm IS NULL OR width_mm > 0),
            thick_mm   integer CHECK (thick_mm IS NULL OR thick_mm > 0),
            selection  jsonb NOT NULL DEFAULT '{}'::jsonb,
            updated_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE order_timber_form (
            po_id                bigint PRIMARY KEY REFERENCES purchase_orders(po_id) ON DELETE CASCADE,
            face                 varchar(200),
            back                 varchar(200),
            substrate            varchar(200),
            face_by_tg           boolean NOT NULL DEFAULT false,
            back_by_tg           boolean NOT NULL DEFAULT false,
            substrate_by_tg      boolean NOT NULL DEFAULT false,
            finished_description text,
            deliver_to           text,
            special_instructions text,
            form_blob            bigint REFERENCES file_blob(file_blob_id),
            form_created_at      timestamptz,
            updated_at           timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE order_tg_run (
            run_id           bigserial PRIMARY KEY,
            po_id            bigint NOT NULL REFERENCES purchase_orders(po_id) ON DELETE CASCADE,
            production_start date,
            date_made        date,
            made_by          varchar(100),
            date_ex_factory  date,
            location         varchar(50),
            notes            text,
            created_by       bigint REFERENCES app_user(id) ON DELETE SET NULL,
            created_at       timestamptz NOT NULL DEFAULT now(),
            updated_at       timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_order_tg_run_po ON order_tg_run (po_id, run_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE order_tg_run; DROP TABLE order_timber_form; DROP TABLE order_glass_calc; DROP TABLE glass_rate;")
