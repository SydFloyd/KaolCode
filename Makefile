SHELL := /bin/bash

.PHONY: install test lint run up down logs

install:
	python -m pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check src tests

run:
	python -m codex_home.orchestrator

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f orchestrator worker
