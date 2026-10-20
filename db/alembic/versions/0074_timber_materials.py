"""Solid Timber gets a catalog table of its own

Step 2 of the catalog plan, after Glass (`0070`). Solid Timber items lived in `benchtop_materials` with
`product_type = 'Solid Timber'`. `timber_materials` has the common catalog columns plus the old Orders
screen's timber fields: colour, finish, grain and rating (free text), thickness, width and length (mm),
unit of measure, product website and one picture. Quotes treat Timber as a *part* kind (like Board,
Custom, Benchtop and Glass): the Solid Timber rows were already referenced from `estimate_line_part` as
BENCHTOP, so `estimate_line_part` accepts TIMBER and `estimate_line_hardware` is untouched.

Data-preserving, as `0070`: every Benchtop row typed Solid Timber moves over **keeping its material_id**
(`slab_id` equalled the SKU for imported rows and is dropped; `cost_per_slab` becomes `cost_per_unit`;
`thickness_mm`, `bench_length_mm` / `bench_width_mm` (as `length_mm` / `width_mm`), `colour`, `finish`,
`um`, `product_website` and the picture carry over) and every (type, id) reference is pointed at
TIMBER / `timber_materials`. Downgrade moves the rows back to Benchtop (new ids, matched by SKU;
`slab_id` = SKU) and drops the table; the timber-only fields (grain, rating) are lost.

Revision ID: 0074
Revises: 0073
Create Date: 2026-10-16
"""
from alembic import op

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None

_KINDS = ("BOARD", "HARDWARE", "CUSTOM", "BENCHTOP", "APPLIANCE", "HIRE", "EDGING", "GLASS")
_TABLES = ("board_materials", "hardware_materials", "custom_made", "benchtop_materials", "appliances",
           "equipment_hire", "edging_materials", "glass_materials")
_ENTITIES = ("project", "item", "cutlist", "order", "supplier", "drawing", "sample", "customer", "estimate")

# (table, column) naming a material kind as 'BENCHTOP'-style text
_TYPE_COLS = (
    ("project_hardware_catalog", "material_type"),
    ("project_hardware_catalog_log", "material_type"),
    ("procurement_batches", "material_type"),
    ("material_take_line", "material_type"),
    ("material_summary_line", "material_type"),
    ("estimate_line_part", "material_type"),
    ("estimate_line_material_order", "material_type"),
)


def _in(values):
    return ", ".join(f"'{v}'" for v in values)


def _recheck(table, name, column, values):
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name};")
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({column} IN ({_in(values)}));")


def _widen(add: bool):
    kinds = _KINDS + (("TIMBER",) if add else ())
    tables = _TABLES + (("timber_materials",) if add else ())
    for t in ("procurement_batches", "project_hardware_catalog", "project_hardware_catalog_log"):
        _recheck(t, f"{t}_material_type_check", "material_type", kinds)
    for t in ("material_take_line", "material_summary_line"):
        _recheck(t, f"{t}_material_type_check", "material_type", kinds + ("OTHER",))
    _recheck("estimate_line_part", "estimate_line_part_material_type_check", "material_type",
             ("BOARD", "CUSTOM", "BENCHTOP", "GLASS") + (("TIMBER",) if add else ()))
    _recheck("cv_material_mapping", "cv_material_mapping_target_material_table_check",
             "target_material_table", tables)
    _recheck("po_line_items", "po_line_items_material_table_check", "material_table", tables)
    _recheck("search_outbox", "search_outbox_entity_type_check", "entity_type", _ENTITIES + tables)


def upgrade():
    op.execute("""
        CREATE TABLE timber_materials (
            material_id            bigserial PRIMARY KEY,
            sku                    varchar(255) NOT NULL,
            description            varchar(255),
            supplier               varchar(128),
            cost_per_unit          numeric(12,2),
            lead_time_days         integer DEFAULT 0,
            notes                  text,
            is_active              boolean DEFAULT true,
            created_at             timestamptz DEFAULT now(),
            updated_at             timestamptz DEFAULT now(),
            workspace_id           bigint REFERENCES workspace(id) ON DELETE CASCADE,
            unit_cost              numeric(12,2),
            synonyms               text[] NOT NULL DEFAULT '{}',
            default_supplier       varchar(128),
            default_lead_time_days integer,
            archived_at            timestamptz,
            archived_by            bigint REFERENCES app_user(id),
            supplier_id            bigint REFERENCES vendors(vendor_id) ON DELETE SET NULL,
            default_supplier_id    bigint REFERENCES vendors(vendor_id) ON DELETE SET NULL,
            product_type           varchar(64),
            colour                 varchar(128),
            finish                 varchar(128),
            grain                  varchar(64),
            rating                 varchar(64),
            thickness_mm           numeric(8,2),
            width_mm               numeric(8,2),
            length_mm              numeric(8,2),
            um                     varchar(32),
            product_website        varchar(255),
            image_blob             bigint REFERENCES file_blob(file_blob_id),
            CONSTRAINT timber_materials_workspace_sku_key UNIQUE (workspace_id, sku)
        );
        CREATE INDEX idx_timber_materials_active ON timber_materials (workspace_id) WHERE archived_at IS NULL;
        CREATE INDEX idx_timber_materials_supplier_id ON timber_materials (supplier_id);
        CREATE INDEX idx_timber_materials_synonyms ON timber_materials USING gin (synonyms);
        CREATE INDEX idx_timber_materials_workspace ON timber_materials (workspace_id);
    """)
    _widen(True)
    op.execute("""
        CREATE TRIGGER search_enqueue_timber_materials
        AFTER INSERT OR DELETE OR UPDATE ON timber_materials
        FOR EACH ROW EXECUTE FUNCTION search_enqueue('timber_materials', 'material_id');

        INSERT INTO timber_materials (material_id, sku, description, supplier, cost_per_unit, lead_time_days,
               notes, created_at, updated_at, workspace_id, unit_cost, synonyms, default_supplier,
               default_lead_time_days, archived_at, archived_by, supplier_id, default_supplier_id, product_type,
               colour, finish, thickness_mm, width_mm, length_mm, um, product_website, image_blob)
        SELECT material_id, COALESCE(sku, slab_id), description, supplier, cost_per_slab, lead_time_days, notes,
               created_at, updated_at, workspace_id, unit_cost, synonyms, default_supplier,
               default_lead_time_days, archived_at, archived_by, supplier_id, default_supplier_id, product_type,
               colour, finish, thickness_mm, bench_width_mm, bench_length_mm, um, product_website, image_blob
          FROM benchtop_materials
         WHERE lower(btrim(product_type)) = 'solid timber';
        SELECT setval(pg_get_serial_sequence('timber_materials', 'material_id'),
                      GREATEST((SELECT COALESCE(MAX(material_id), 0) FROM timber_materials), 1),
                      (SELECT COUNT(*) > 0 FROM timber_materials));
    """)
    for table, col in _TYPE_COLS:
        op.execute(f"""
            UPDATE {table} SET {col} = 'TIMBER'
             WHERE {col} = 'BENCHTOP' AND material_id IN (SELECT material_id FROM timber_materials);
        """)
    op.execute("""
        UPDATE cv_material_mapping SET target_material_table = 'timber_materials'
         WHERE target_material_table = 'benchtop_materials'
           AND target_material_id IN (SELECT material_id FROM timber_materials);
        UPDATE po_line_items SET material_table = 'timber_materials'
         WHERE material_table = 'benchtop_materials'
           AND material_id IN (SELECT material_id FROM timber_materials);
        DELETE FROM benchtop_materials WHERE lower(btrim(product_type)) = 'solid timber';
    """)


def _refuse_too_long_skus():
    """The legacy `benchtop_materials.slab_id` is varchar(64) but `timber_materials.sku` is varchar(255): refuse the
    downgrade, naming the rows, rather than cut a SKU short (code-review fix, 2026-10-20). Alembic runs
    the whole downgrade in one transaction, so nothing is changed when this raises."""
    op.execute("""
        DO $$
        DECLARE bad text; n integer;
        BEGIN
            SELECT count(*) INTO n FROM timber_materials WHERE char_length(sku) > 64;
            IF n > 0 THEN
                SELECT string_agg(format('id %s sku %L (%s characters, limit 64)', material_id, sku, char_length(sku)),
                                  '; ' ORDER BY material_id)
                  INTO bad
                  FROM (SELECT material_id, sku FROM timber_materials WHERE char_length(sku) > 64
                         ORDER BY material_id LIMIT 50) x;
                RAISE EXCEPTION '0074 downgrade refused, % SKU(s) in timber_materials are longer than benchtop_materials.slab_id allows and would be cut short; shorten or remove them first. Rows %', n, bad;
            END IF;
        END $$;
    """)


def downgrade():
    _refuse_too_long_skus()
    op.execute("""
        CREATE TEMP TABLE _timber_back (old_id bigint, new_id bigint) ON COMMIT DROP;
        WITH moved AS (
            INSERT INTO benchtop_materials (slab_id, sku, description, supplier, cost_per_slab, lead_time_days,
                   notes, created_at, updated_at, workspace_id, unit_cost, synonyms, default_supplier,
                   default_lead_time_days, archived_at, archived_by, supplier_id, default_supplier_id,
                   product_type, colour, finish, thickness_mm, bench_width_mm, bench_length_mm, um,
                   product_website, image_blob)
            SELECT left(sku, 64), sku, description, supplier, cost_per_unit, lead_time_days, notes,
                   created_at, updated_at, workspace_id, unit_cost, synonyms, default_supplier,
                   default_lead_time_days, archived_at, archived_by, supplier_id, default_supplier_id,
                   product_type, colour, finish, thickness_mm, width_mm, length_mm, um,
                   product_website, image_blob
              FROM timber_materials
            RETURNING material_id, sku, workspace_id
        )
        INSERT INTO _timber_back
        SELECT t.material_id, m.material_id
          FROM moved m JOIN timber_materials t
            ON t.sku = m.sku AND t.workspace_id IS NOT DISTINCT FROM m.workspace_id;
    """)
    for table, col in _TYPE_COLS:
        op.execute(f"""
            UPDATE {table} t SET {col} = 'BENCHTOP', material_id = b.new_id
              FROM _timber_back b WHERE t.{col} = 'TIMBER' AND t.material_id = b.old_id;
        """)
    op.execute("""
        UPDATE cv_material_mapping t SET target_material_table = 'benchtop_materials', target_material_id = b.new_id
          FROM _timber_back b WHERE t.target_material_table = 'timber_materials' AND t.target_material_id = b.old_id;
        UPDATE po_line_items t SET material_table = 'benchtop_materials', material_id = b.new_id
          FROM _timber_back b WHERE t.material_table = 'timber_materials' AND t.material_id = b.old_id;
    """)
    op.execute("DELETE FROM search_outbox WHERE entity_type = 'timber_materials';")
    _widen(False)
    op.execute("DROP TABLE timber_materials;")
