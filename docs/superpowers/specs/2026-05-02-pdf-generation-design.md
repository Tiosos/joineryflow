# JoineryFlow PDF Generation + Item Attachments — Design Spec

**Date:** 2026-05-02
**Sub-project:** #5b (sibling slice of sub-project #5; #5a Shop Drawings + file uploads is done; #5c iSample follows)
**Branch base:** `feat/foundation` (post Shop Drawings merge)
**Prior context:** `docs/superpowers/specs/2026-04-22-foundation-design.md`, `docs/superpowers/specs/2026-04-25-pm-workbench-design.md`, `docs/superpowers/specs/2026-04-28-procurement-workbench-design.md`, `docs/superpowers/specs/2026-05-01-shop-drawings-design.md`, `legacy/trackingv2.md` §5.5 + §11

---

## 0. Goal

A Drafter clicks **Print Cutlist**, **Print Hardware**, or **Print Combined PDF** in the item editor footer and gets a PDF download. The Combined PDF merges the rendered cutlist + hardware list with three uploaded reference files (CV production drawing, floor plan, site-measure PDF) plus an auto-generated painting parts list when any part has `paint_instruction != 'NONE'`. Drafters manage the three attachment slots from a new **Attachments** tab on the item editor, reusing the file-upload subsystem from #5a.

This sub-project also retires the three "PDF generation ships in sub-project #5" disabled buttons currently in `apps/web/app/(app)/items/[id]/_components/EditorFooter.tsx`.

---

## 1. Scope

### In scope

1. **Item attachments subsystem** — `item_attachment` table with `UNIQUE (item_id, kind)` slot constraint. Three kinds: `cv_drawing`, `floor_plan`, `site_measure`. Replace-on-upload semantics; audit row per swap.
2. **Attachments tab** in the item editor — three slot cards (one per kind), each showing the current file (viewer link), Replace button, Delete button.
3. **PDF engine** — WeasyPrint for HTML-to-PDF rendering of dynamic templates + pypdf for merging generated and uploaded PDFs into the Combined output.
4. **Print Cutlist endpoint** — renders `parts[]` for the item via the `cutlist.html` template (joined to `board_materials` for material name).
5. **Print Hardware endpoint** — renders `item_hardware_lines[]` for the item via the `hardware.html` template (resolved through `project_hardware_catalog` to the 6 catalog tables).
6. **Print Combined PDF endpoint** — assembles cover + cutlist + hardware + attachments + (optional) painting parts list into a single PDF. Painting page is included when any part has `paint_instruction != 'NONE'`.
7. **Print templates** — `cutlist.html`, `hardware.html`, `cover_combined.html`, `painting.html`, `missing_attachment.html`, plus `print.css` for paged-media controls.
8. **Embedded fonts** — Inter (Regular + Bold) and JetBrains Mono (Regular + Bold) committed as `.woff2` under `seed/fonts/` (~250 KB total). Referenced by `print.css` `@font-face`.
9. **Footer wiring** — the three disabled `<button>` elements in `EditorFooter.tsx` become `<a>` download links pointing at the new endpoints.
10. **Audit hooks** — every print request and every attachment mutation writes to `audit_log`.
11. **Seed update** — wire two ALF-001 items with the existing `seed/hartwood_joinery/sample_drawings/*.pdf` fixtures so the demo paths work end-to-end (one item with 3/3 slots, one with 1/3 to exercise placeholder rendering).

### Out of scope (deferred to #5c, v2, or later)

- **iSample tab** — entirely sub-project #5c.
- **Async/queued PDF generation** — sync only. A long-running render would need a job queue, status polling, and a "fetch when ready" UX. None of those exist; not justified at this scale.
- **PDF caching / persistence** — every click re-renders. The data is the source of truth; the PDF is a derivative.
- **Real PDF thumbnails of attachments in the slot cards** — placeholder file icons (`📄`) suffice for v1.
- **Email/share-link of generated PDFs** — download only.
- **Per-user print history surfaced in the UI** — only the audit log records it.
- **Custom print templates / per-workspace branding** — fixed templates.
- **Item-attachment versioning** — replace-on-upload with audit; no revision history (Shop Drawings has its own approval-cycle reasons for revisions; item attachments are reference material).
- **Auto-conversion of non-PDF attachments** — the upload subsystem already restricts to PDF/PNG/JPEG (per #5a). Combined PDF only successfully merges PDF attachments; PNG/JPEG attachments would render as unsupported. **Constraint**: attachment uploads for `cv_drawing`/`floor_plan`/`site_measure` must be PDF only — enforced in the route handler with a 415 if the bound file_blob's mime is not `application/pdf`.
- **Headless Chrome PDF rendering** — WeasyPrint chosen over the legacy spec's "Headless Chrome" decision (see §13 resolved decisions for rationale).
- **Page-numbered cross-references between sections** ("see CV drawing on page 7") — paged-media counter logic is too brittle across mixed sources; covers indicate which sections are present, no cross-refs.

---

## 2. Architecture

### 2.1 Backend layout

Two new modules. Both follow repo convention (SQLAlchemy Core `text()` queries, Pydantic v2 schemas, `require_permission` deps).

```
apps/api/app/item_attachments/
  __init__.py
  routes.py                  # GET bundle + POST/DELETE per slot
  queries.py                 # text() SQL with audit
  schemas.py                 # AttachmentSlotOut, AttachmentsBundleOut, BindAttachmentIn

apps/api/app/printing/
  __init__.py
  engine.py                  # WeasyPrint render + pypdf merge primitives
  context.py                 # context-builder: pulls item + parts + hw lines + attachments from DB
  routes.py                  # GET /items/{iid}/{cutlist,hardware,combined}.pdf
  templates/
    cutlist.html             # Jinja2 — parts table
    hardware.html            # Jinja2 — hardware lines grouped by supplier
    cover_combined.html      # Jinja2 — item header + slot manifest
    painting.html            # Jinja2 — paint_required parts subset
    missing_attachment.html  # Jinja2 — placeholder page when slot empty
    print.css                # paged-media controls + table styles + @font-face

seed/fonts/
  Inter-Regular.woff2
  Inter-Bold.woff2
  JetBrainsMono-Regular.woff2
  JetBrainsMono-Bold.woff2
```

Both routers mounted from `apps/api/app/main.py`. Auth via `require_permission("list", "read")` for print routes and `require_permission("list", "write")` for attachment mutations. Drafter is already at PM-parity on `list` (Foundation matrix), so no permissions migration is needed.

### 2.2 Web layout

```
apps/web/app/(app)/items/[id]/
  page.tsx                              # add 'attachments' to allowed tab list
  _components/
    AttachmentsTab.tsx                  # NEW — 3 slot cards + bundle fetch
    AttachmentSlotCard.tsx              # NEW — current file + Replace + Delete
    EditorFooter.tsx                    # MODIFY — wire 3 print buttons
apps/web/lib/
  attachments-types.ts                  # NEW — slot bundle types
  attachments-fetch.ts                  # NEW — get bundle / bind / clear
  print.ts                              # NEW — PDF download trigger
```

State management: same approach as PM Workbench, Procurement Workbench, Shop Drawings — raw `fetch()` + URL search params + controlled inputs. **No TanStack Query / RHF / Zustand.**

### 2.3 PDF engine setup

The api Dockerfile gains the WeasyPrint runtime deps:

```dockerfile
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
 && rm -rf /var/lib/apt/lists/*
```

Image growth: ~25 MB. No new container.

`apps/api/pyproject.toml` adds:

```toml
"weasyprint>=63",
"pypdf>=5",
"jinja2>=3.1",
```

(`jinja2` is technically already pulled in transitively by FastAPI's `Jinja2Templates`, but it's pinned explicitly for clarity.)

### 2.4 Print engine primitives

```python
# apps/api/app/printing/engine.py
from io import BytesIO
from pathlib import Path
from typing import Mapping
import jinja2
import pypdf
import weasyprint

TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=jinja2.select_autoescape(["html"]),
)


def render_html_to_pdf(template_name: str, ctx: Mapping) -> bytes:
    """Render a Jinja2 template to PDF bytes via WeasyPrint."""
    html = _env.get_template(template_name).render(**ctx)
    base_url = str(TEMPLATES_DIR)  # so print.css and font @url() resolve
    return weasyprint.HTML(string=html, base_url=base_url).write_pdf()


def merge_pdfs(parts: list[bytes]) -> bytes:
    """Concatenate PDF byte sources in order."""
    writer = pypdf.PdfWriter()
    for part in parts:
        writer.append(BytesIO(part))
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
```

Two functions, ~30 lines. The route handlers compose them.

### 2.5 Print templates

All four dynamic templates extend a shared `_base.html` skeleton that loads `print.css`. Per-template structure:

- **`cutlist.html`** — Item header block (Item description / Project code + name / Room as `rm_no · rm_desc` / Stage / Lister free-text / Date), then a parts table: Qty · Part name · Len mm · Wid mm · Material (resolved from `board_material_id` join) · Edge · Colour · Edging spec · Paint instruction. Mono numeric columns. Page break after the table; `@page { size: A4; margin: 12mm 10mm }`.
- **`hardware.html`** — Same item header block, then groups of hardware lines by supplier. Per group: supplier letter tile + name + line count + subtotal. Per row: Qty · Type · Description · Brand · Notes. Mono qty + brand columns.
- **`cover_combined.html`** — Item metadata + a "Slot manifest" table listing the three attachment kinds and which are populated/missing. Page break before the next section.
- **`painting.html`** — Subset of `parts[]` where `paint_instruction != 'NONE'`, rendered as a single column-grouped checklist with the paint instruction (`DOUBLE_SIDE / SINGLE_SIDE / EDGE_ONLY`) as a column. Only included in Combined when at least one such part exists.
- **`missing_attachment.html`** — One-page placeholder reading `[Floor Plan: not uploaded]` (parameterized per kind), in muted color. Used only by the Combined assembly when a slot is empty.

### 2.6 Combined PDF assembly

Pseudocode (full code in §5.3):

```python
def render_combined(item_id, db, store) -> bytes:
    ctx = build_context(item_id, db, store)  # item + parts + hardware + attachments

    parts: list[bytes] = []
    parts.append(render_html_to_pdf("cover_combined.html", ctx))
    parts.append(render_html_to_pdf("cutlist.html", ctx))
    parts.append(render_html_to_pdf("hardware.html", ctx))

    for kind in ("cv_drawing", "floor_plan", "site_measure"):
        slot = ctx["attachments"].get(kind)
        if slot:
            parts.append(read_attachment_bytes(store, slot))
        else:
            parts.append(render_html_to_pdf("missing_attachment.html", {"kind": kind, "item": ctx["item"]}))

    if ctx["has_painting"]:
        parts.append(render_html_to_pdf("painting.html", ctx))

    return merge_pdfs(parts)
```

Read order matches the shop floor's expected flow: data first, drawings second, painting last.

---

## 3. Data model

### 3.1 Migration 0014 — `item_attachment`

```sql
CREATE TABLE item_attachment (
  item_attachment_id  bigserial   PRIMARY KEY,
  item_id             bigint      NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
  kind                text        NOT NULL CHECK (kind IN ('cv_drawing','floor_plan','site_measure')),
  file_blob_id        bigint      NOT NULL REFERENCES file_blob(file_blob_id),
  uploaded_by         bigint      NOT NULL REFERENCES app_user(id),
  uploaded_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (item_id, kind)
);

CREATE INDEX idx_item_attachment_item ON item_attachment (item_id);
```

The `UNIQUE (item_id, kind)` enforces "three named slots per item". Replace-on-upload uses Postgres `INSERT ... ON CONFLICT (item_id, kind) DO UPDATE SET ...` inside one transaction so the swap is atomic.

`ON DELETE CASCADE` on `item_id` cleans up attachments when the parent item is deleted (item deletion is rare but supported).

No FK from `item_attachment` to a workspace — workspace scoping flows through `items → projects → app_user → workspace_id` (same chain as Shop Drawings).

### 3.2 Invariants enforced by the schema

- **One slot per kind per item.** `UNIQUE (item_id, kind)` makes it impossible to bind two file_blobs to the same slot on the same item.
- **CHECK on `kind`.** Only the three legal kinds; future kinds require a migration + matrix update.
- **FK to file_blob.** A slot cannot point to a non-existent blob; deleting a blob the slot points at is blocked by the FK.
- **Item-scoped.** `ON DELETE CASCADE` from `items(item_id)` ensures attachments don't dangle.

### 3.3 PDF-only mime constraint at the route layer

The `file_blob` table from #5a allows PDF/PNG/JPEG. For Combined PDF assembly to work, the three slot kinds must be PDF only. Enforced in the route handler:

```python
blob_mime = db.execute(text("SELECT mime FROM file_blob WHERE file_blob_id = :b AND workspace_id = :w"),
                       {"b": payload.file_blob_id, "w": user.workspace_id}).scalar()
if blob_mime != "application/pdf":
    raise HTTPException(status_code=415, detail="item attachments must be application/pdf")
```

This is application-layer rather than DDL because the `file_blob` table is generic (Shop Drawings allows images for sketches). A second slot model that wanted to allow images can be added later without schema change.

---

## 4. PDF engine

### 4.1 Why WeasyPrint over Headless Chrome

The legacy `trackingv2.md` §11 chose Headless Chrome on the rationale "merge flexibility — combined-PDF case pulls cutlist + CV drawing + floor plan + site-measure PDF + painting list in one pass." That rationale conflates two operations:

1. **Render** dynamic HTML (cutlist parts, hardware lines, painting subset) → PDF.
2. **Merge** generated PDFs with uploaded PDFs into one file.

WeasyPrint does (1). pypdf does (2). Chromium is overkill for either step in isolation, and inflates the api image by ~300 MB plus adds a second runtime dependency that fails differently from Python (subprocess crash modes vs. Python exceptions).

WeasyPrint supports modern CSS sufficiently for tabular print templates: `@page` rules, `@font-face` with `.woff2`, flexbox in row layouts, custom counters for page numbers, page break controls. The print template is its own stylesheet — Tailwind v4 (the web UI) is not loaded at print time. So "Tailwind compatibility" isn't a constraint.

### 4.2 Font loading

`print.css` declares `@font-face` rules pointing at the four `.woff2` files in `seed/fonts/`. WeasyPrint resolves these against the template's `base_url` (set to `templates/` in `engine.py`):

```css
@font-face {
  font-family: 'Inter';
  font-weight: 400;
  src: url('../../../seed/fonts/Inter-Regular.woff2') format('woff2');
}
/* + Bold + JetBrains Mono Regular + Bold */
```

Path is relative to `apps/api/app/printing/templates/`. The `seed/` directory is mounted into the api container at `/code/seed` per `docker-compose.yml`, and templates live at `/code/app/printing/templates/`, so the relative path resolves correctly inside Docker. Tests use the same path.

### 4.3 Page layout

```css
@page {
  size: A4;
  margin: 14mm 12mm 18mm 12mm;
  @bottom-center {
    content: counter(page) " / " counter(pages);
    font-family: 'JetBrains Mono', monospace;
    font-size: 9pt;
    color: #5a574f;
  }
}
```

Page numbers in mono on every page. Header/cover pages can suppress with `@page :first { @bottom-center { content: '' } }` if needed.

### 4.4 Performance expectations

- **Cutlist** (typical 30-row parts table): ~800 ms WeasyPrint render → ~80 KB PDF.
- **Hardware** (typical 20-row supplier-grouped table): ~600 ms render → ~60 KB.
- **Combined** with all 3 PDF attachments at ~100 KB each: ~3 s end-to-end (3 renders + merge).
- Memory peak: ~100 MB per request (WeasyPrint allocates the layout tree).
- Concurrency: the api uvicorn worker handles one render at a time per process; the combined render is the slowest path. Acceptable for v1.

### 4.5 Engine errors

- **Template syntax error** → `jinja2.TemplateSyntaxError` → 500 with detail. Surfaced in audit so we can catch a regression.
- **Font load failure** → WeasyPrint logs a warning and falls back to system sans/mono. Not a 500 — the PDF still renders.
- **pypdf merge of corrupt attachment** → `pypdf.errors.PdfReadError` → 500 with detail. Should not happen because uploads pass magic-byte check, but defense-in-depth.

---

## 5. Print routes

### 5.1 `GET /items/{iid}/cutlist.pdf`

```python
@router.get("/items/{iid}/cutlist.pdf")
def print_cutlist(
    iid: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
    store: FileStore = Depends(_get_store),
):
    ctx = build_context(iid, db, store, workspace_id=user.workspace_id)
    if not ctx:
        raise HTTPException(404, "item not found")
    pdf = render_html_to_pdf("cutlist.html", ctx)
    write_audit(db, workspace_id=user.workspace_id, actor_id=user.id,
                event="item.print.cutlist", target=str(iid),
                payload={"byte_size": len(pdf), "part_count": len(ctx["parts"])})
    db.commit()
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="cutlist-{iid}.pdf"',
                             "Cache-Control": "no-store"})
```

### 5.2 `GET /items/{iid}/hardware.pdf`

Same shape; `render_html_to_pdf("hardware.html", ctx)`, audit event `item.print.hardware`, filename `hardware-{iid}.pdf`. `payload` includes `hardware_line_count` and `supplier_count`.

### 5.3 `GET /items/{iid}/combined.pdf`

```python
@router.get("/items/{iid}/combined.pdf")
def print_combined(
    iid: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
    store: FileStore = Depends(_get_store),
):
    ctx = build_context(iid, db, store, workspace_id=user.workspace_id)
    if not ctx:
        raise HTTPException(404, "item not found")
    pdf = render_combined_bytes(ctx, store)
    attachments_present = {k: bool(ctx["attachments"].get(k))
                           for k in ("cv_drawing", "floor_plan", "site_measure")}
    write_audit(db, workspace_id=user.workspace_id, actor_id=user.id,
                event="item.print.combined", target=str(iid),
                payload={"byte_size": len(pdf), "attachments_present": attachments_present,
                         "has_painting": ctx["has_painting"]})
    db.commit()
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="combined-{iid}.pdf"',
                             "Cache-Control": "no-store"})
```

`render_combined_bytes` does the orchestration described in §2.6.

### 5.4 Why `inline` not `attachment` Content-Disposition

The browser shows the PDF in a tab when the user clicks the print link, not a forced download. The Drafter usually wants to preview before sending to the shop floor. Browsers still allow Save-As from the inline view, so no functionality is lost.

The web frontend uses `<a href="..." target="_blank">` for the print buttons (no `download` attribute) — opens the PDF in a new tab.

### 5.5 Context builder

`apps/api/app/printing/context.py` is a single function:

```python
def build_context(item_id: int, db: Session, store: FileStore, *, workspace_id: int) -> dict | None:
    item = db.execute(text("""
        SELECT i.item_id, i.num, i.description, i.code, i.item_code,
               i.rm_no, i.rm_desc, i.stage, i.zone, i.level,
               i.lister, i.assembler,
               i.project_id, p.project_code, p.name AS project_name
          FROM items i
          JOIN projects p ON p.project_id = i.project_id
          LEFT JOIN app_user pm ON pm.id = p.pm_id
         WHERE i.item_id = :i
           AND (p.pm_id IS NULL OR pm.workspace_id = :w)
    """), {"i": item_id, "w": workspace_id}).mappings().first()
    if not item:
        return None

    parts = db.execute(text("""
        SELECT p.qty, p.part_name, p.len_mm, p.wid_mm,
               p.board_material_id, bm.description AS material_description, bm.code AS material_code,
               p.edge, p.colour, p.edging_spec,
               p.paint_instruction
          FROM parts p
          JOIN modules m ON m.module_id = p.module_id
          LEFT JOIN board_materials bm ON bm.material_id = p.board_material_id
         WHERE m.item_id = :i
         ORDER BY m.module_id, p.seq, p.part_id
    """), {"i": item_id}).mappings().all()

    hardware = db.execute(text("""
        SELECT ihl.qty, ihl.note,
               phc.material_type, phc.material_id, phc.catalog_id
          FROM item_hardware_lines ihl
          JOIN project_hardware_catalog phc ON phc.catalog_id = ihl.catalog_id
         WHERE ihl.item_id = :i
         ORDER BY ihl.id
    """), {"i": item_id}).mappings().all()
    enriched_hw = enrich_hardware_with_catalog(db, hardware)  # one extra SELECT per material_type → name + supplier

    attachments = db.execute(text("""
        SELECT ia.kind, ia.file_blob_id, fb.original_filename, fb.byte_size, fb.storage_key
          FROM item_attachment ia
          JOIN file_blob fb ON fb.file_blob_id = ia.file_blob_id
         WHERE ia.item_id = :i
    """), {"i": item_id}).mappings().all()
    attachments_by_kind = {a["kind"]: dict(a) for a in attachments}

    return {
        "item": dict(item),
        "parts": [dict(p) for p in parts],
        "hardware": enriched_hw,                                    # grouped by supplier in the template
        "attachments": attachments_by_kind,
        "has_painting": any(p["paint_instruction"] != "NONE" for p in parts),
        "rendered_at": datetime.now(timezone.utc),
    }
```

**Schema notes:**
- `items.lister` is `varchar(128)` free-text (legacy field), not an FK to `app_user`. Templates display the string directly.
- `items.description` is the item's display name; there's no `items.title`.
- `items.rm_no` + `items.rm_desc` together represent the room (`1.01 · Kitchen`); render combined.
- `parts.paint_instruction` is an enum (`NONE / DOUBLE_SIDE / SINGLE_SIDE / EDGE_ONLY`) introduced in migration 0001 with a CHECK constraint. The painting trigger = "any part has `paint_instruction != 'NONE'`".
- `parts.board_material_id` is an FK to `board_materials(material_id)`. The context builder LEFT JOINs to fetch `description` and `code` for the parts table column. Hardware items go through the existing `enrich_hardware_with_catalog` helper (already used by the procurement workbench) to map `(material_type, material_id)` to a supplier-grouped name.

### 5.6 Caching headers

`Cache-Control: no-store` on all three print routes. Browsers should not cache generated PDFs because the underlying data may have changed since the last click.

---

## 6. Item attachments subsystem

### 6.1 Endpoints

| Verb | Path | Purpose | Permission |
|---|---|---|---|
| GET | `/items/{iid}/attachments` | Bundle of 3 slots (each null or populated with FileBlobOut) | `list:read` |
| POST | `/items/{iid}/attachments/{kind}` | Bind/replace one slot — body: `{file_blob_id}` | `list:write` |
| DELETE | `/items/{iid}/attachments/{kind}` | Clear one slot | `list:write` |

Path param `kind` is validated server-side as one of the three legal values; 422 otherwise.

### 6.2 Schemas

```python
# apps/api/app/item_attachments/schemas.py
from typing import Literal
from datetime import datetime
from pydantic import BaseModel

AttachmentKind = Literal["cv_drawing", "floor_plan", "site_measure"]


class AttachmentSlotOut(BaseModel):
    kind: AttachmentKind
    file_blob_id: int | None
    original_filename: str | None
    byte_size: int | None
    uploaded_by: int | None
    uploaded_by_name: str | None
    uploaded_at: datetime | None


class AttachmentsBundleOut(BaseModel):
    item_id: int
    slots: list[AttachmentSlotOut]   # always exactly 3 entries; populated or null


class BindAttachmentIn(BaseModel):
    file_blob_id: int
```

### 6.3 Bind (POST) semantics

```python
# Atomically: validate blob is PDF + workspace match, then UPSERT the slot.
blob = db.execute(text("""
    SELECT mime FROM file_blob WHERE file_blob_id = :b AND workspace_id = :w
"""), {"b": payload.file_blob_id, "w": user.workspace_id}).first()
if not blob:
    raise HTTPException(404, "file_blob not found in this workspace")
if blob[0] != "application/pdf":
    raise HTTPException(415, "item attachments must be application/pdf")

db.execute(text("""
    INSERT INTO item_attachment(item_id, kind, file_blob_id, uploaded_by)
    VALUES (:i, :k, :b, :u)
    ON CONFLICT (item_id, kind) DO UPDATE
      SET file_blob_id = EXCLUDED.file_blob_id,
          uploaded_by  = EXCLUDED.uploaded_by,
          uploaded_at  = now()
"""), {"i": iid, "k": kind, "b": payload.file_blob_id, "u": user.id})

write_audit(db, workspace_id=user.workspace_id, actor_id=user.id,
            event="item_attachment.bind", target=f"{iid}:{kind}",
            payload={"file_blob_id": payload.file_blob_id})
db.commit()
```

### 6.4 Clear (DELETE) semantics

```python
result = db.execute(text("""
    DELETE FROM item_attachment WHERE item_id = :i AND kind = :k
    RETURNING file_blob_id
"""), {"i": iid, "k": kind})
row = result.first()
if not row:
    raise HTTPException(404, "no attachment in this slot")
write_audit(db, workspace_id=user.workspace_id, actor_id=user.id,
            event="item_attachment.clear", target=f"{iid}:{kind}",
            payload={"file_blob_id": row[0]})
db.commit()
```

The `file_blob` row is NOT deleted — orphan GC is deferred per #5a's resolved decisions. The blob may still be referenced by a Shop Drawing revision or another item's attachment.

---

## 7. Web — Attachments tab + footer wiring

### 7.1 Tab routing

`apps/web/app/(app)/items/[id]/page.tsx` already maintains a `tab` URL param with allowed values `cutlist | hardware | board | log`. Add `attachments`:

```ts
const ALLOWED_TABS = ["cutlist", "hardware", "board", "attachments", "log"] as const;
```

Tab strip rendered above the tab body inserts an "Attachments" tab next to "Board".

### 7.2 AttachmentsTab

```
apps/web/app/(app)/items/[id]/_components/AttachmentsTab.tsx
```

On mount: `GET /api/items/{iid}/attachments`. Renders header `{populated} of 3 slots populated · used by Print Combined PDF` and three `AttachmentSlotCard` instances in a vertical stack (full-width cards, ~120 px tall each).

### 7.3 AttachmentSlotCard

Each card has three states:

- **Empty**: dashed border, "📄 No file uploaded" placeholder, single "Upload" button (file picker → `uploadFile` from #5a's `file-upload.ts` → `bindAttachment(iid, kind, file_blob_id)`).
- **Populated**: solid border, file icon, original filename + size + uploaded-by + DD/MM/YYYY date, three actions: Open (link to `/api/files/{file_blob_id}` in new tab), Replace (file picker → upload → bind, replacing existing), Delete (drafter+ only, with confirm).
- **Loading/error**: spinner during operations, inline `text-rose-700` error if the bind/clear call fails.

The Replace and Delete buttons are gated by `canWrite = me.auth_role in {drafter, manager, admin}`. Viewer/editor see only Open.

### 7.4 EditorFooter wiring

The three disabled `<button>` elements become `<a>` tags:

```tsx
<a href={`/api/items/${item.id}/cutlist.pdf`} target="_blank" rel="noopener"
   className="rounded border border-h-line px-3 py-1.5 text-sm text-h-ink hover:bg-h-line/40">
  Print Cutlist
</a>
```

Same for Hardware and Combined. The Combined link gets a tooltip showing which slots are populated/missing (from a prefetched `attachments` bundle on the editor page so the footer doesn't need its own fetch). If the item has zero parts, the Cutlist + Combined links are styled as disabled (the underlying endpoint would still render an empty cutlist; we hide the action because there's nothing useful to print).

The `printTitle` const ("PDF generation ships in sub-project #5") is removed.

### 7.5 No new dialogs

Attachment upload uses the file picker directly inside the slot card, not a modal — there's nothing to configure beyond picking the file. Confirms (Replace overwrite, Delete) use `window.confirm` for v1; a styled modal can come later if anyone asks.

---

## 8. RBAC, audit, and security

### 8.1 RBAC

- **Print routes** (`GET .../cutlist.pdf`, `.../hardware.pdf`, `.../combined.pdf`): `require_permission("list", "read")`. All authenticated workspace users with read on `list` can print. Workspace isolation enforced via the `(p.pm_id IS NULL OR pm.workspace_id = :w)` predicate in `build_context` (matches the wider repo pattern; the workspace-isolation hardening follow-up filed during #5a covers this).
- **Attachment GET** (`GET .../attachments`): `require_permission("list", "read")`.
- **Attachment POST/DELETE**: `require_permission("list", "write")`. Drafter is at PM-parity on `list` (Foundation matrix), so drafter/manager/admin can mutate; editor cannot.

### 8.2 Audit

Every mutation and every print writes one `audit_log` row:

| Action | `event` | `target` | `payload` |
|---|---|---|---|
| Print cutlist | `item.print.cutlist` | item_id | `{byte_size, part_count}` |
| Print hardware | `item.print.hardware` | item_id | `{byte_size, hardware_line_count, supplier_count}` |
| Print combined | `item.print.combined` | item_id | `{byte_size, attachments_present, has_painting}` |
| Bind attachment | `item_attachment.bind` | `{item_id}:{kind}` | `{file_blob_id, replaced_file_blob_id?}` |
| Clear attachment | `item_attachment.clear` | `{item_id}:{kind}` | `{file_blob_id}` |

### 8.3 Security checklist

- **No public PDF URLs.** Every print route enforces `require_permission("list", "read")` and workspace isolation via `build_context`.
- **PDF-only mime gate** on attachment bind. PNG/JPEG file_blobs (allowed by #5a's upload) cannot be bound to an item attachment slot.
- **WeasyPrint HTML autoescape** enabled. Item titles, part names, and notes are user-controlled text; Jinja2 autoescape prevents `<script>` injection in the rendered HTML, even though WeasyPrint doesn't execute JS — an unescaped `<` could still corrupt the layout.
- **No external resource loading.** WeasyPrint is configured with `base_url` pointing at the templates dir; no `http://` / `https://` resources resolve. Fonts are local.
- **pypdf import is bytes-only.** No filesystem reads from user-controlled paths. Storage_key reads go through the Task 3 `_safe_path` guard from #5a.
- **Workspace isolation** on file_blob fetch matches #5a download semantics.

---

## 9. Seed updates

The two fixture PDFs from #5a (`seed/hartwood_joinery/sample_drawings/{kitchen-base-run,bathroom-vanity}.pdf`) are reused. No new fixtures needed.

Append to the seed script after the items+parts+hardware block, before the shop_drawings block:

```python
# ── Item Attachments demo (sub-project #5b) ───────────────────────────────────
from app.files.seed_helper import put_seed_file as _put

_kitchen_pdf = "/code/seed/hartwood_joinery/sample_drawings/kitchen-base-run.pdf"
_bath_pdf    = "/code/seed/hartwood_joinery/sample_drawings/bathroom-vanity.pdf"

_blob_kit = _put(s, workspace_id=workspace_id, workspace_slug=workspace_slug,
                 app_user_id=_drafter_id, path=_kitchen_pdf)
_blob_bat = _put(s, workspace_id=workspace_id, workspace_slug=workspace_slug,
                 app_user_id=_drafter_id, path=_bath_pdf)

# Pick the first two ALF-001 items.
_items = s.execute(text("""
    SELECT item_id FROM items WHERE project_id = :p ORDER BY item_id LIMIT 2
"""), {"p": _alf_pid}).scalars().all()
_full, _partial = _items[0], _items[1]

# Item 1: all 3 slots populated
for kind in ("cv_drawing", "floor_plan", "site_measure"):
    s.execute(text("""
        INSERT INTO item_attachment(item_id, kind, file_blob_id, uploaded_by)
        VALUES (:i, :k, :b, :u)
        ON CONFLICT (item_id, kind) DO UPDATE SET file_blob_id = EXCLUDED.file_blob_id
    """), {"i": _full, "k": kind, "b": _blob_kit, "u": _drafter_id})

# Item 2: only cv_drawing (so Combined renders 2 placeholder pages)
s.execute(text("""
    INSERT INTO item_attachment(item_id, kind, file_blob_id, uploaded_by)
    VALUES (:i, 'cv_drawing', :b, :u)
    ON CONFLICT (item_id, kind) DO UPDATE SET file_blob_id = EXCLUDED.file_blob_id
"""), {"i": _partial, "b": _blob_bat, "u": _drafter_id})

s.commit()
print(f"seeded item attachments: full={_full} (3/3), partial={_partial} (1/3)")
```

Idempotent via `ON CONFLICT DO UPDATE`. Safe to re-seed.

---

## 10. Testing

### 10.1 Pytest suite

| File | Cases (~) | Focus |
|---|---|---|
| `test_item_attachments_crud.py` | 9 | Bind happy path, replace (UPSERT), delete, GET bundle returns all 3 slots correctly populated/empty, kind validation 422, file_blob workspace mismatch 404, non-PDF mime 415, ON DELETE CASCADE on item delete, RBAC editor cannot write |
| `test_printing_engine.py` | 6 | `render_html_to_pdf` returns valid PDF bytes (starts `%PDF-`), `merge_pdfs` concatenates correctly (page count = sum), template syntax error surfaces as 500-friendly exception, font @font-face resolves, painting template renders only when ctx flag set, missing_attachment placeholder renders |
| `test_print_routes.py` | 8 | Cutlist 200 + content-type, Hardware 200, Combined 200 with 0/1/2/3 attachments, Combined includes painting page when paint_required parts exist, Combined skips painting when no paint_required, RBAC viewer denied, item not found 404, audit row written per print |
| `test_print_workspace_isolation.py` | 3 | Cross-workspace cutlist/hardware/combined → 404, not 403 |

Total: ~26 new pytest cases. Following repo convention. Workspace truncation in `make test` continues to apply; `item_attachment` is added to the TRUNCATE_TABLES tuple in conftest (between `parts` and `modules` per FK ordering).

### 10.2 Playwright spec

`tests/e2e/pdf_generation.spec.ts`:

1. Login as `rin.park@hartwood.test` (drafter).
2. Navigate to ALF-001's first item's editor.
3. Click the new "Attachments" tab.
4. Verify three slot cards render. The seed pre-populates 3/3 for item 1, so the page shows three populated cards.
5. Replace the `cv_drawing` slot via file picker with a small fixture PDF.
6. Click "Print Combined PDF" in the footer. Wait for the network response.
7. Assert: response status 200, `Content-Type: application/pdf`, `Content-Length > 1000`.
8. (Asserting PDF visual content in Playwright is brittle; we just assert response shape + content-length.)

Runs via `make e2e-docker` like existing specs.

### 10.3 Manual smoke after merge

1. `make up && make migrate && make seed`.
2. Open `/items/<ALF-001 item 1 id>?tab=attachments`. See three populated cards.
3. Click Print Combined PDF. PDF opens in new tab: cover + cutlist + hardware + 3 attachments + (if any paint_required parts) painting list.
4. Open item 2 (1/3 slots). Print Combined. PDF shows two placeholder pages where slots are empty.
5. Try uploading a PNG to a slot → 415.
6. Try printing as a viewer (`/auth/login` as a viewer seed user) → 403.

---

## 11. Implementation order

1. **Migration 0014** (`item_attachment` + index) + Dockerfile pango libs + add `weasyprint`/`pypdf`/`jinja2` to `pyproject.toml`. Rebuild the api image.
2. **Item attachments backend**: schemas, queries, routes (CRUD + bind + clear). Tests.
3. **Print engine primitives** (`render_html_to_pdf` + `merge_pdfs`) + engine-layer tests.
4. **Print templates** (5 HTML + `print.css`) + 4 font files committed under `seed/fonts/`.
5. **Context builder** + print routes (cutlist, hardware, combined) + tests.
6. **Web `lib/`**: types, fetch wrappers, print download helper.
7. **AttachmentsTab + AttachmentSlotCard** + tab wiring in the item editor page.
8. **EditorFooter print buttons live** (replace 3 disabled buttons with download links).
9. **Seed update** (item attachments demo block).
10. **Playwright spec**.
11. **CLAUDE.md update** + reference doc entries.

---

## 12. Open follow-ups (not blocking #5b)

These are deliberately deferred:

- **PDF caching** — render-on-click is fine at this scale. If usage grows, add an `etag` derived from item content hash + attachments + paint_required flags.
- **Real attachment thumbnails** — requires `poppler-utils` (deferred from #5a for the same reason). Add when sparse cards become a real complaint.
- **PNG/JPEG attachments** — Combined PDF would need to render image attachments through a tiny intermediate HTML wrapper. Not requested.
- **Custom print templates / per-workspace branding** — would need a template authoring UI. Not on the roadmap.
- **Async render with status polling** — only worthwhile when render time exceeds ~10 s typical or concurrent renders saturate the worker.
- **Combined PDF with cross-section bookmarks** — pypdf supports `add_outline_item`. Cheap to add later if requested.
- **Attachment versioning** — would re-introduce the `_revision` table pattern from #5a. Defer until reviewers ask.
- **Print preview in the editor** — embed an `<iframe src="/api/items/{id}/cutlist.pdf">` next to the cutlist tab. UX win but not required.

---

## 13. Resolved decisions

- **PDF engine.** WeasyPrint + pypdf, not Headless Chrome. The legacy "merge flexibility" rationale conflated render with merge; pypdf does the merge cleanly, WeasyPrint does the render cleanly. Image growth ~25 MB vs. ~300 MB for Chrome. No new container.
- **Attachment slot model.** Three named slots per item (`UNIQUE (item_id, kind)`), replace-on-upload. Audit captures swaps. No revision history (different lifecycle from Shop Drawings).
- **Allowed kinds.** Exactly three: `cv_drawing`, `floor_plan`, `site_measure`. New kinds require migration + matrix update.
- **Sync vs async.** Sync. No job queue.
- **Caching.** None. Re-render every click.
- **Missing-attachment behavior in Combined.** Render placeholder page; cover manifest indicates missing slots.
- **Combined order.** Cover · Cutlist · Hardware · CV drawing · Floor plan · Site measure · Painting (conditional).
- **Painting auto-include.** Only when at least one part has `paint_instruction != 'NONE'`. The enum was introduced in migration 0001 with values `NONE / DOUBLE_SIDE / SINGLE_SIDE / EDGE_ONLY`.
- **Print template look.** Matches legacy "HARDWARE LIST sample PDF" and "CV export sample PDF" — Inter for body, JetBrains Mono for tabular columns + IDs.
- **RBAC.** Print = `list:read`. Attachment mutations = `list:write` (drafter+).
- **Attachment UI placement.** New tab in the item editor, alongside Cutlist / Hardware / Board / Log.
- **PDF storage.** Generated PDFs not persisted; uploaded attachments live in `file_blob` (#5a's table).
- **Audit.** Every print + every attachment mutation writes one row.
- **Mime constraint on attachments.** PDF only at the route layer (file_blob table itself remains generic).
- **Disposition.** `inline` (open in new tab); browser-Save-As still works.
