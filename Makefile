.PHONY: up down logs migrate seed test e2e fmt

up:        ; docker compose up -d --build
down:      ; docker compose down
logs:      ; docker compose logs -f
migrate:   ; docker compose exec api alembic upgrade head
seed:      ; docker compose exec api python -m seed.hartwood_joinery
test:      ; docker compose exec api pytest -q
e2e:       ; pnpm --dir apps/web exec playwright test
