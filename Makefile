.PHONY: install backend worker sla-checker infra up down logs frontend frontend-install frontend-build test test-unit test-integration test-e2e lint migrate seed keycloak-bootstrap

PYTHON := .venv/bin/python
PIP    := .venv/bin/pip

# ── Backend ──────────────────────────────────────────────────────────────────
install:
	python3 -m venv .venv
	$(PIP) install dist/qf-1.0.2-py3-none-any.whl
	$(PIP) install -r requirements.txt

backend:
	$(PYTHON) main.py

worker:
	ROLE=worker $(PYTHON) worker.py

sla-checker:
	ROLE=sla_checker $(PYTHON) sla_checker.py

# ── Infrastructure ───────────────────────────────────────────────────────────
infra:
	docker compose up -d postgres redis keycloak

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

# ── Frontend ─────────────────────────────────────────────────────────────────
frontend-install:
	cd frontend && npm install

frontend:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

# ── Tests ────────────────────────────────────────────────────────────────────
test:
	$(PYTHON) -m pytest tests/ -v --tb=short

test-unit:
	$(PYTHON) -m pytest tests/unit/ -v --tb=short

test-integration:
	$(PYTHON) -m pytest tests/integration/ -v --tb=short -m "not slow"

test-e2e:
	$(PYTHON) -m pytest tests/e2e/ -v --tb=short

lint:
	$(PYTHON) -m py_compile main.py $$(find src -name '*.py') && echo "Syntax OK"

# ── DB / data ────────────────────────────────────────────────────────────────
migrate:
	.venv/bin/alembic upgrade head

migrate-revision:
	.venv/bin/alembic revision --autogenerate -m "$(m)"

seed:
	$(PYTHON) scripts/seed_dev.py

keycloak-bootstrap:
	$(PYTHON) scripts/keycloak_bootstrap.py
