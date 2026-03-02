.PHONY: install run test test-unit test-int lint typecheck security migrate build help

PYTHON = python
PIP = pip
FLASK_APP = main.py
PORT = 5678

help:
	@echo "Ved.io Python Backend — Available commands:"
	@echo ""
	@echo "  make install      Install all dependencies"
	@echo "  make run          Start development server (hot reload)"
	@echo "  make build        Build production Docker image"
	@echo "  make migrate      Run Alembic DB migrations"
	@echo "  make test         Run full test suite"
	@echo "  make test-unit    Run unit tests only"
	@echo "  make test-int     Run integration tests only"
	@echo "  make lint         Run black + ruff linters"
	@echo "  make typecheck    Run mypy type checker"
	@echo "  make security     Run bandit security scan"
	@echo ""

install:
	$(PIP) install -e ".[dev]"
	pre-commit install || true

run:
	uvicorn $(APP) --host 0.0.0.0 --port $(PORT) --reload

run-prod:
	uvicorn $(APP) --host 0.0.0.0 --port $(PORT) --workers 4

migrate:
	alembic upgrade head

migrate-create:
	alembic revision --autogenerate -m "$(MSG)"

test: test-unit test-int

test-unit:
	pytest tests/unit/ -v --cov=. --cov-report=term-missing --cov-report=html

test-int:
	pytest tests/integration/ -v -m "not slow"

lint:
	black --check .
	ruff check .

format:
	black .
	ruff check --fix .

typecheck:
	mypy . --ignore-missing-imports

security:
	bandit -r . -ll --exclude .venv,tests,alembic

build:
	docker build -t ved-io-backend:latest ..

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .coverage htmlcov/ .mypy_cache/ .ruff_cache/ dist/ build/
