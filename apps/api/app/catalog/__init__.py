"""Catalog enrichment + CV mapping CRUD (sub-project #7a).

Workspace-scoped CRUD across the 6 material catalog tables, plus the
cv_material_mapping register that translates freeform CV codes to
(target_table, target_id). All routes gated by ("catalog", action)."""
