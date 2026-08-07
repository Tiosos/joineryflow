# Artifact sources

Standalone HTML pages published via the Claude Artifact tool. Each page is a
single self-contained file: no external scripts, styles, or fonts (the artifact
CSP blocks them).

Only the `.src.html` templates are committed. The built `.html` carries ~550 KB
of base64 font data and is regenerated on demand:

    python3 docs/artifacts/build.py architecture-map

## Pages

| Source | What it is |
| --- | --- |
| `architecture-map.src.html` | Repo orientation — request path, sub-project ledger, interactive RBAC matrix, the ten lifecycle stages, six state machines, terminology pins, and the data-model invariants. |

Both use the project's own H palette (`apps/web/app/globals.css`) and the Inter
/ JetBrains Mono faces already committed under `seed/fonts/`.
