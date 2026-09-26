.PHONY: env up down logs ps test lint scenario scenario-live clone burst onboard dev-backend dev-frontend reset

env:            ## generate .env with random secrets
	./scripts/gen-env.sh

up: env         ## build and start the full stack
	docker compose up -d --build
	@echo "\nNetra is starting at https://localhost:$${HTTPS_PORT:-8443}  (API docs: /api/docs)"

down:
	docker compose down

reset:          ## stop and wipe all data volumes
	docker compose down -v

logs:
	docker compose logs -f --tail=100 backend simulator

ps:
	docker compose ps

test:           ## backend unit/integration tests
	cd backend && python -m pytest -q

lint:
	cd backend && ruff check app tests && ruff format --check app tests
	cd simulator && ruff check sim && ruff format --check sim
	cd frontend && npm run lint --silent && npm run typecheck --silent

scenario:       ## GJ01XX0001 crosses C001 -> C002 -> C005 (brief's 10:02/10:18/10:41 example)
	docker compose exec simulator python -m sim.scenario trace GJ01XX0001

scenario-live:  ## same, paced 8 s apart so alerts pop up live (for the demo video)
	docker compose exec simulator python -m sim.scenario trace GJ01XX0001 --live --extend

clone:          ## cloned-plate scenario (impossible travel)
	docker compose exec simulator python -m sim.scenario clone GJ01XX2468

burst:          ## 10 repeat ANPR reads -> 1 stored event (dedup)
	docker compose exec simulator python -m sim.scenario burst GJ01AB0001 C001

onboard:        ## API-based bulk onboarding of two extra cameras
	docker compose cp docs/samples/cameras_bulk.json simulator:/tmp/cameras_bulk.json
	docker compose exec simulator python -m sim.scenario onboard /tmp/cameras_bulk.json

dev-backend:
	cd backend && uvicorn app.main:app --reload

dev-frontend:
	cd frontend && npm run dev
