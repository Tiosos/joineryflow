# Build context is the repository root:
#   docker build -f apps/web/Dockerfile .

# ---- deps: full dependency set, no source (C12/C14) ----
FROM node:22-slim AS deps
ENV NEXT_TELEMETRY_DISABLED=1
# No pnpm version here on purpose: corepack reads packageManager from
# package.json, which is the one pin CI and the image share (D7).
RUN corepack enable
WORKDIR /code
# pnpm-workspace.yaml carries ignoredBuiltDependencies; without it the install
# runs with different settings than CI (C13).
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

# ---- dev: what the dev compose file builds (C14) ----
# WORKDIR stays /code, NODE_ENV stays development; source and node_modules
# arrive from the ./apps/web:/code bind mount.
FROM deps AS dev
ENV NODE_ENV=development

# ---- build: the production bundle ----
FROM deps AS build
COPY apps/web ./
# The one build-time value (C7). Default matches .env.example:19.
ARG NEXT_PUBLIC_PROCUREMENT_UI_READY=1
ENV NEXT_PUBLIC_PROCUREMENT_UI_READY=${NEXT_PUBLIC_PROCUREMENT_UI_READY}
RUN pnpm build

# ---- runtime ----
FROM node:22-slim AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /app
COPY --from=build /code/package.json /code/pnpm-lock.yaml /code/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile --prod
COPY --from=build /code/.next ./.next
COPY --from=build /code/public ./public
# Next writes ISR / fetch / image-optimisation caches under .next/cache at
# runtime. The COPY above lands as root, so UID 10001 would hit EACCES the
# first time a cache is written (C17). This must come after the COPY.
RUN mkdir -p /app/.next/cache && chown -R 10001:10001 /app/.next/cache
USER 10001
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/api/health').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"
# Do not use `pnpm start` here: corepack would have to resolve the pinned pnpm
# again as UID 10001, and its cache lives at /.cache (unwritable) while the
# build-time copy sits in /root/.cache. Calling next directly keeps the runtime
# free of any package-manager lookup — and of any network access at startup.
CMD ["node", "node_modules/next/dist/bin/next", "start"]
