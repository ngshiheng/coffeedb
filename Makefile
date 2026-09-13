NAME := coffeedb
DB_PATH ?= data/coffee.db
UV ?= uv
PYTHON := $(UV) run python
FRESH_FLAG :=
DATASETTE := $(shell command -v datasette 2> /dev/null)
DOCKER := $(shell command -v docker 2> /dev/null)
KAGGLE := $(shell command -v kaggle 2> /dev/null)
IMAGE_NAME ?= ngshiheng/coffeedb
TAG_DATE := $(shell date -u +%Y%m%d)
DATASETTE_EXTRA_OPTIONS := --setting allow_download off --setting allow_csv_stream off --setting max_csv_mb 1 --setting default_cache_ttl 86400 --setting sql_time_limit_ms 2000

.DEFAULT_GOAL := help
.PHONY: help
help:  ## display this help message.
	@awk 'BEGIN {FS = ":.*##"; printf "\nWelcome to $(NAME).\nUse make <target> where <target> is one of:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "\033[36m  %-20s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Helper

##@ Usage
.PHONY: init
init:  ## initialise the database schema at $(DB_PATH).
	@mkdir -p "$(dir $(DB_PATH))"
	@$(UV) run coffeedb init --db "$(DB_PATH)"

.PHONY: scrape-live
scrape-live:  ## scrape the current live site into $(DB_PATH).
	@$(UV) run coffeedb scrape live --db "$(DB_PATH)"

.PHONY: scrape-historical
scrape-historical:  ## scrape all Wayback Machine snapshots into $(DB_PATH).
	@$(UV) run coffeedb scrape historical --db "$(DB_PATH)" $(FRESH_FLAG)

.PHONY: datasette
datasette:  ## run datasette with metadata.yml for local development.
	@if [ ! -f "$(DB_PATH)" ]; then echo "Database not found: $(DB_PATH)"; exit 1; fi
	@if [ -z "$(DATASETTE)" ]; then echo "Datasette could not be found. See https://docs.datasette.io/en/stable/installation.html"; exit 2; fi
	@PORT=8001; \
	while lsof -iTCP:$$PORT -sTCP:LISTEN >/dev/null 2>&1; do \
	  PORT=$$((PORT+1)); \
	done; \
	echo "Starting datasette on port $$PORT"; \
	$(DATASETTE) --root "$(DB_PATH)" --metadata data/metadata.yml --port $$PORT

##@ Docker
.PHONY: docker-build
docker-build:  ## build dated and latest Datasette images.
	@if [ ! -f "$(DB_PATH)" ]; then echo "Database not found: $(DB_PATH)" >&2; exit 1; fi
	@if [ ! -f data/metadata.yml ]; then echo "Datasette metadata not found: data/metadata.yml" >&2; exit 1; fi
	@if [ -z "$(DOCKER)" ]; then echo "Docker could not be found. See https://docs.docker.com/get-docker/" >&2; exit 2; fi
	@if [ -z "$(DATASETTE)" ]; then echo "Datasette could not be found. See https://docs.datasette.io/en/stable/installation.html" >&2; exit 2; fi
	$(DATASETTE) package "$(DB_PATH)" --extra-options '$(DATASETTE_EXTRA_OPTIONS)' --metadata data/metadata.yml --install=datasette-block-robots --install=datasette-gzip --install=datasette-vega --tag "$(IMAGE_NAME):$(TAG_DATE)"
	$(DATASETTE) package "$(DB_PATH)" --extra-options '$(DATASETTE_EXTRA_OPTIONS)' --metadata data/metadata.yml --install=datasette-block-robots --install=datasette-gzip --install=datasette-vega --tag "$(IMAGE_NAME):latest"

.PHONY: docker-push
docker-push:  ## push dated and latest Datasette images to Docker Hub.
	@if [ -z "$(DOCKER)" ]; then echo "Docker could not be found. See https://docs.docker.com/get-docker/" >&2; exit 2; fi
	$(DOCKER) push "$(IMAGE_NAME):$(TAG_DATE)"
	$(DOCKER) push "$(IMAGE_NAME):latest"

##@ Kaggle
.PHONY: kaggle-export
kaggle-export:  ## export current and historical CSVs into kaggle/.
	@$(PYTHON) scripts/export_kaggle.py --db "$(DB_PATH)" --output-dir kaggle

.PHONY: kaggle-push
kaggle-push:  ## publish a new version of the configured Kaggle dataset.
	@if [ -z "$(KAGGLE)" ]; then echo "Kaggle could not be found. Install the Kaggle CLI first." >&2; exit 2; fi
	$(KAGGLE) datasets version --path kaggle --message "chore(data): update generated csv $$(date -u +%Y-%m-%d)"

.PHONY: kaggle-create
kaggle-create:  ## create the configured Kaggle dataset for the first time.
	@if [ -z "$(KAGGLE)" ]; then echo "Kaggle could not be found. Install the Kaggle CLI first." >&2; exit 2; fi
	$(KAGGLE) datasets create --path kaggle --public

##@ Contributing
.PHONY: install
install:  ## install project dependencies.
	@$(UV) sync

.PHONY: test
test:  ## install test dependencies and run the test suite.
	@$(UV) sync --extra test
	@$(UV) run pytest
