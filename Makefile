# Aegis dev workflow (speckit T1/T2). Run from repo root.
.PHONY: up down nuke bootstrap ps logs install test lint-ontology

ENVFILE := $(wildcard .env)
COMPOSE = docker compose $(if $(ENVFILE),--env-file $(ENVFILE)) -f infra/docker-compose.yml
PY = .venv/bin/python

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
	uv pip install -p $(PY) -e ".[dev]"

test:
	$(PY) -m pytest -q

lint-ontology:
	.venv/bin/aegis ontology validate
