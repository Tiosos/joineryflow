.PHONY: up down logs migrate seed test e2e e2e-docker fmt

up:        ; docker compose up -d --build
down:      ; docker compose down
logs:      ; docker compose logs -f
migrate:   ; docker compose exec api alembic upgrade head
seed:      ; docker compose exec api python -m seed.hartwood_joinery
test:      ; docker compose exec api pytest -q
e2e:       ; pnpm --dir apps/web exec playwright test
e2e-docker: ; docker run --rm --ipc=host --add-host=host.docker.internal:host-gateway -v "$$(pwd)":/work -w /work/apps/web -e PW_BASE_URL=http://host.docker.internal:3000 -e NODE_PATH=/work/apps/web/node_modules mcr.microsoft.com/playwright:v1.59.1-noble npx playwright test --reporter=list
