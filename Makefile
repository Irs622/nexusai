.PHONY: help install format lint typecheck test test-unit test-contract test-architecture quality-gate clean build vault mcp-list mcp-ping soak p5-live web release-check tui cluster-status

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
	@echo "make build            - Build Python wheel and source package"
	@echo "make vault            - Open AI Second Brain in Obsidian app"
	@echo "make mcp-list         - List all configured Model Context Protocol servers"
	@echo "make mcp-ping         - Ping all built-in MCP servers (filesystem, sqlite, web_fetcher)"
	@echo "make soak             - Run continuous endurance soak test harness"
	@echo "make p5-live          - Run Level 4 staging chaos test scenarios"
	@echo "make web              - Launch FastAPI Web OS Dashboard with SSE stream"
	@echo "make tui              - Launch interactive Live Terminal UI (TUI) cluster monitor"
	@echo "make cluster-status   - Display distributed worker cluster status snapshot"
	@echo "make release-check    - Run automated release candidate verification gate"


vault:
	open -a "Obsidian" vault || open "obsidian://open?path=$(shell pwd)/vault"

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

mcp-list:
	$(BIN)/nexusai mcp list

mcp-ping:
	$(BIN)/nexusai mcp ping filesystem
	$(BIN)/nexusai mcp ping sqlite
	$(BIN)/nexusai mcp ping web_fetcher

soak:
	$(BIN)/python tools/run_soak_test.py --cycles 1000

p5-live:
	$(BIN)/python tools/run_p5_live.py

web:
	$(BIN)/uvicorn nexusai.api.server:app --port 8000 --reload

release-check:
	$(BIN)/python tools/verify_release.py

tui:
	$(BIN)/nexusai cluster top

cluster-status:
	$(BIN)/nexusai cluster status

quality-gate: format lint typecheck test-contract test-architecture test

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .coverage htmlcov .mypy_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +

build: clean
	$(BIN)/python -m build

