.PHONY: help install format lint typecheck test test-unit test-contract test-architecture quality-gate clean build

PYTHON ?= python3
VENV ?= .venv
BIN ?= $(VENV)/bin

help:
	@echo "NexusAI Build & Maintenance Command Reference"
	@echo "============================================="
	@echo "make install          - Install virtual environment and dependencies"
	@echo "make format           - Run code formatters (ruff, black, isort)"
	@echo "make lint             - Run static analysis (ruff)"
	@echo "make typecheck        - Run static type checker (mypy)"
	@echo "make test             - Run full test suite"
	@echo "make test-unit        - Run pure unit tests"
	@echo "make test-contract    - Run public API contract tests"
	@echo "make test-architecture- Run architecture complexity & DAG checks"
	@echo "make quality-gate     - Run master quality gate sequence"
	@echo "make clean            - Clean build & cache artifacts"
	@echo "make build            - Build Python wheel and source package"

install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip setuptools wheel
	$(BIN)/pip install -e ".[dev]"

format:
	$(BIN)/ruff check --fix src tests examples
	$(BIN)/black src tests examples
	$(BIN)/isort src tests examples

lint:
	$(BIN)/ruff check src tests examples

typecheck:
	$(BIN)/mypy src/nexusai

test:
	$(BIN)/pytest

test-unit:
	$(BIN)/pytest -m unit tests/unit/brain

test-contract:
	$(BIN)/pytest tests/architecture/test_public_api_contract.py

test-architecture:
	$(BIN)/pytest tests/architecture/test_architecture_complexity.py

quality-gate: format lint typecheck test-contract test-architecture test

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .coverage htmlcov .mypy_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +

build: clean
	$(BIN)/python -m build
