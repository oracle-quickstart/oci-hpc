# Makefile for Grafana dashboard management
JSONNET := /usr/local/bin/jsonnet
JB := /usr/local/bin/jb
GRAFANA_URL := http://localhost:3000
VENDOR_DIR := vendor
JB_STAMP := $(VENDOR_DIR)/.jb_bootstrap

# Command line options
# Usage: make <dashboard-name>
# e.g. make workshop-dashboard
DASHBOARD_SRC ?= workshop-dashboard.jsonnet
# Use recursive assignment so this updates when DASHBOARD_SRC is overridden
DASHBOARD_OUT = $(DASHBOARD_SRC:.jsonnet=.json)
GRAFANA_PASSWORD ?=

.PHONY: all build deploy clean help vendor deps

all: build

# Ensure vendor deps (jb init/install) run only once
deps: $(JB_STAMP)

$(VENDOR_DIR):
	@mkdir -p $(VENDOR_DIR)

# Bootstrap jsonnet-bundler once and stamp it
$(JB_STAMP): | $(VENDOR_DIR)
	@test -f jsonnetfile.json || $(JB) init
	$(JB) install github.com/grafana/grafonnet-lib/grafonnet@master
	$(JB) install github.com/grafana/grafonnet/gen/grafonnet-latest@main
	@touch $@

## Build the dashboard JSON from jsonnet source
build: deps
	$(JSONNET) -J $(VENDOR_DIR) $(DASHBOARD_SRC) -o $(DASHBOARD_OUT)

## Deploy dashboard to Grafana (requires GRAFANA_PASSWORD)
deploy: build
	@if [ -z "$(GRAFANA_PASSWORD)" ]; then \
		echo "GRAFANA_PASSWORD is not set."; \
		echo "Usage: make deploy GRAFANA_PASSWORD=yourpassword"; \
		exit 1; \
	fi
	@curl -s -X POST \
		-H 'Content-Type: application/json' \
		-d '{"dashboard": '"$$(jq . $(DASHBOARD_OUT))"', "overwrite": true}' \
		"$(GRAFANA_URL)/api/dashboards/db" --user "admin:$(GRAFANA_PASSWORD)" | jq .

## Shortcut rule:
## "make <name>" will deploy <name>.jsonnet
## Example: `make workshop-dashboard` -> uses workshop-dashboard.jsonnet
%: %.jsonnet deps
	@echo "Deploying dashboard '$@' using source $< ..."
	@$(MAKE) DASHBOARD_SRC=$< deploy

## Remove generated files
clean:
	@rm -f *.json
	@rm -f $(JB_STAMP)

## Show available targets
help:
	@echo "Available targets:"
	@echo "  build            - Compile jsonnet to JSON (ensures jb deps are installed once)"
	@echo "  deploy           - Push dashboard to Grafana (requires GRAFANA_PASSWORD)"
	@echo "  <name>           - Build & deploy <name>.jsonnet (e.g. make workshop-dashboard)"
	@echo "  clean            - Remove generated files and jb stamp"
	@echo ""
	@echo "Environment:"
	@echo "  GRAFANA_PASSWORD - Grafana admin password (required for deploy)"
	@echo ""
	@echo "Quick start:"
	@echo "  1) Export your Grafana admin password:"
	@echo "       export GRAFANA_PASSWORD=yourpassword"
	@echo "  2) Deploy a dashboard by name (without jsonnet extension):"
	@echo "       make workshop-dashboard"
	@echo "       make my-dashboard"
	@echo ""
	@echo "Advanced usage:"
	@echo "  DASHBOARD_SRC    - Source jsonnet file (default: workshop-dashboard.jsonnet)"
	@echo "  GRAFANA_URL      - Grafana base URL (default: http://localhost:3000)"
	@echo ""
	@echo "Examples:"
	@echo "  make build"
	@echo "  make build DASHBOARD_SRC=other-dashboard.jsonnet"
	@echo "  make deploy DASHBOARD_SRC=my-dashboard.jsonnet GRAFANA_PASSWORD=secret"
	@echo "  export GRAFANA_PASSWORD=secret && make workshop-dashboard"

