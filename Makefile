# Aegis dev workflow (speckit T1/T2). Run from repo root.
.PHONY: up down nuke bootstrap ps logs install test test-fast test-integration test-mvp test-er-evaluation test-search-quality test-system test-coverage lint-ontology ontology-generate ui-install ui-build ui-test openapi check-contract

ENVFILE := $(wildcard .env)
COMPOSE = docker compose $(if $(ENVFILE),--env-file $(ENVFILE)) -f infra/docker-compose.yml

# 127.0.0.1, never localhost. On Windows `localhost` resolves to ::1 first and
# the compose ports bind IPv4 only, so every connection pays a ~2s failed-IPv6
# stall: measured 2.05s vs 0.01s per connection. The suite opens thousands.
AEGIS_TEST_DATABASE_URL ?= postgresql+psycopg://aegis:aegis-dev@127.0.0.1:5433/aegis
export AEGIS_TEST_DATABASE_URL

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

test-mvp:          ## deterministic offline ingest → review → accept → projection smoke (T25)
	$(PYTEST) -q tests/integration/test_mvp_fixture.py

test-search-quality:   ## blocking search precision/recall/latency gates + report (T68)
	# The gate runs as tests, not through `aegis search evaluate`: the CLI reads
	# AEGIS_DATABASE_URL while this suite migrates its own test database. The
	# report lands in output/ either way, written by the fixture.
	$(PYTEST) -q tests/unit/test_search_quality_math.py tests/integration/test_search_quality.py

test-er-evaluation:    ## blocking precision/recall/review-load gates + report (T26)
	uv run aegis identity evaluate --output output/er-evaluation.json
	$(PYTEST) -q tests/unit/test_er_evaluation.py tests/integration/test_er_evaluation.py

test-system:
	$(PYTEST) -q tests/system

test-coverage:
	$(PYTEST) -q tests/unit tests/component tests/contract tests/integration tests/system \
		--cov=aegis --cov-branch --cov-report=term-missing --cov-report=xml
	uv run coverage report

lint-ontology:     ## validate the composition + the second-domain fixture (Article XI/XIV)
	uv run aegis ontology validate
	uv run aegis ontology validate tests/fixtures/ontology/border-cargo-composition.yaml
	uv run aegis ontology generate --check
	uv run aegis ontology check-release

ontology-generate: ## regenerate the artifacts derived from the ontology (spec 08 §8)
	uv run aegis ontology generate

# ── workspace (ui/, T22) ────────────────────────────────────────────────────

openapi:       ## re-export the OpenAPI document + regenerate the typed client
	uv run aegis api export-openapi
	cd ui && npm run generate:api

check-contract: ## fail on a breaking change to the committed OpenAPI document
	uv run aegis api check-contract

ui-install:
	cd ui && npm ci

ui-build:      ## type-check + production build into ui/dist (served by `aegis serve`)
	cd ui && npm run build

ui-test:       ## hermetic browser smoke journey (stubs Keycloak and the API)
	cd ui && npm run test:e2e
