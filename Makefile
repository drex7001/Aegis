# Aegis dev workflow (speckit T1/T2). Run from repo root.
.PHONY: up down nuke bootstrap ps logs install test test-fast test-integration test-system test-coverage lint-ontology

ENVFILE := $(wildcard .env)
COMPOSE = docker compose $(if $(ENVFILE),--env-file $(ENVFILE)) -f infra/docker-compose.yml
PYTEST = uv run pytest

up:            ## start postgres+postgis, minio, keycloak, openfga; wait for health
	$(COMPOSE) up -d --wait

down:          ## stop services (data volumes kept)
	$(COMPOSE) down

nuke:          ## stop services AND DELETE data volumes
	$(COMPOSE) down -v

bootstrap:     ## one-time setup: buckets, realm check, FGA store+model
	bash infra/bootstrap.sh

ps:
	$(COMPOSE) ps

logs:          ## make logs S=keycloak
	$(COMPOSE) logs -f $(S)

install:       ## install the aegis package (editable) + dev deps into .venv
	uv sync --locked --extra dev

test:
	$(PYTEST) -q tests/unit tests/component tests/contract tests/integration tests/system

test-fast:
	$(PYTEST) -q tests/unit tests/component tests/contract

test-integration:
	$(PYTEST) -q tests/integration

test-system:
	$(PYTEST) -q tests/system

test-coverage:
	$(PYTEST) -q tests/unit tests/component tests/contract tests/integration tests/system \
		--cov=aegis --cov-branch --cov-report=term-missing --cov-report=xml
	uv run coverage report

lint-ontology:
	.venv/bin/aegis ontology validate
