# Reverse-proxy configuration (customer-owned)

Q1 settled on **one hostname** with TLS terminated by the reverse proxy the
customer already runs. `docker-compose.prod.yml` therefore publishes only the web
tier, bound to `127.0.0.1:3000` by default (`JF_WEB_BIND:JF_WEB_PORT`). If the
customer changes `JF_WEB_PORT` because 3000 is taken, update the `upstream`
address below to match — the container itself still listens on 3000.
Everything else stays inside the compose network.

`nginx.conf.snippet` is a **snippet**, not a drop-in site config. Merge it into
the customer's existing `http { }` / `server { }` blocks. Certificates, TLS
policy, HSTS and WAF rules are theirs; we have no lever on that tier, which is
why `GET /version` exists — "is it up on your side?" has to be answerable
without shell access.

## Three defaults that break the app before anyone suspects the proxy

| Setting | nginx default | Why it must change |
| --- | --- | --- |
| `client_max_body_size` | `1m` | Uploads go through `apps/web/app/api/[...proxy]/route.ts:20`, which does `await req.arrayBuffer()` — the whole body is buffered. nginx returns 413 before the app sees the request. The snippet sets `25m`; adjust to the customer's largest attachment. |
| `proxy_read_timeout` | `60s` | PDF and export routes are inherently slow (`docs/REVIEW-2026-10.md` §C: a 300-line quote PDF ≈ 3.3 s). The snippet raises it to `120s` **only** for the three `*.pdf` paths and keeps the 60 s ceiling everywhere else. |
| `X-Forwarded-Proto` / `X-Forwarded-For` | absent | Nothing reads `request.url` / `base_url` today, so these are not *required* yet — but uvicorn already runs with `--proxy-headers` and `--forwarded-allow-ips=*` (production design D4). Sending them now means the first feature that builds an absolute URL does not emit `http://` links behind https. |

WebSockets and SSE are not used. A plain HTTP reverse proxy is sufficient; no
`Upgrade` headers are in the snippet.

## If the proxy is on a different host

1. Set `JF_WEB_BIND` in `.env` to the compose host's **internal** IP.
2. Change the `upstream joineryflow_web` address in the snippet to that IP.
3. Firewall port 3000 so only the proxy can reach it.
4. Confirm from outside the host that 5432 and 8000 are unreachable.

## Verification after merging

```
nginx -t
curl -I https://jf.customer.com/version        # must answer, no shell access needed
curl -I https://jf.customer.com/login          # 200
```

Then, logged in:

- Upload a file larger than 1 MB — it must not return 413.
- Print a cutlist / hardware / combined PDF — it must return 200 well within
  120 s (check `apps/api/app/printing/routes.py` for the three paths).
- `curl -I` on the login response must show `Set-Cookie` with `Secure;
  HttpOnly; SameSite` (requires `COOKIE_SECURE=true` in `.env`).

If TLS, certificate renewal or a WAF rule misbehaves, it looks like an outage in
JoineryFlow. Ask for the customer's actual proxy config as part of the install
checklist — we cannot see it.
