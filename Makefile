.PHONY: dev-frontend dev-backend dev install-frontend install-backend db-init lint

install-frontend:
	cd frontend && npm install

install-backend:
	cd backend && pip install -e ".[dev]"

install: install-frontend install-backend

dev-frontend:
	cd frontend && npm run dev

dev-backend:
	cd backend && uvicorn wex_platform.app.main:app --reload --port 8000

dev:
	@echo "Run in two terminals:"
	@echo "  make dev-backend"
	@echo "  make dev-frontend"

db-init:
	cd backend && python -c "import asyncio; from wex_platform.infra.database import init_db; asyncio.run(init_db())"

lint-backend:
	cd backend && ruff check src/ tests/

lint-frontend:
	cd frontend && npm run lint

lint: lint-backend lint-frontend
