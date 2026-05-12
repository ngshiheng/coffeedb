NAME    := coffeedb
DB      := coffee.db
UV      := uv
FRESH_FLAG :=
DATASETTE := $(shell command -v datasette 2> /dev/null)

.DEFAULT_GOAL := help
.PHONY: help
help:  ## display this help message.
	@awk 'BEGIN {FS = ":.*##"; printf "\nWelcome to $(NAME).\nUse make <target> where <target> is one of:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "\033[36m  %-20s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Helper

##@ Usage
.PHONY: init
init:  ## initialise the database schema at $(DB).
	@$(UV) run coffeedb init --db $(DB)

.PHONY: scrape-live
scrape-live:  ## scrape the current live site into $(DB).
	@$(UV) run coffeedb scrape live --db $(DB)

.PHONY: scrape-historical
scrape-historical:  ## scrape all Wayback Machine snapshots into $(DB).
	@$(UV) run coffeedb scrape historical --db $(DB) $(FRESH_FLAG)

.PHONY: datasette
datasette:  ## run datasette with metadata.json for local development.
	@if [ -z "$(DATASETTE)" ]; then echo "Datasette could not be found. See https://docs.datasette.io/en/stable/installation.html"; exit 2; fi
	@PORT=8001; \
	while lsof -iTCP:$$PORT -sTCP:LISTEN >/dev/null 2>&1; do \
	  PORT=$$((PORT+1)); \
	done; \
	echo "Starting datasette on port $$PORT"; \
	$(DATASETTE) --root $(DB) --metadata data/metadata.json --port $$PORT

##@ Contributing
.PHONY: install
install:  ## install project dependencies.
	@$(UV) sync

.PHONY: test
test:  ## install test dependencies and run the test suite.
	@$(UV) sync --extra test
	@$(UV) run pytest
