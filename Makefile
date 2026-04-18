NAME := coffeeedb
DOCKER := $(shell command -v docker 2> /dev/null)
DATASETTE := $(shell command -v datasette 2> /dev/null)
SQLITE := $(shell command -v sqlite3 2> /dev/null)

.DEFAULT_GOAL := help
.PHONY: help
help:   ## display this help message.
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-25s\033[0m\t%s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Usage
.PHONY: datasette
datasette:  ## run datasette with metadata.json for local development.
	@if [ -z $(DATASETTE) ]; then echo "Datasette could not be found. See https://docs.datasette.io/en/stable/installation.html"; exit 2; fi
	@PORT=8001; \
	while lsof -iTCP:$$PORT -sTCP:LISTEN >/dev/null 2>&1; do \
	  PORT=$$((PORT+1)); \
	done; \
	echo "Starting datasette on port $$PORT"; \
	$(DATASETTE) --root coffee.db --metadata data/metadata.json --port $$PORT

.PHONY: test
test:  ## install test dependencies and run the test suite.
	uv sync --extra test
	uv run pytest
