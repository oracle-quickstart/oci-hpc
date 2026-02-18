# Grafana Dashboard Makefile
JSONNET := jsonnet
JB := jb
GRAFANA_URL := http://localhost:3000
VENDOR := vendor

SOURCES := $(wildcard *.jsonnet)
DASHBOARDS := $(SOURCES:.jsonnet=.json)
NAMES := $(SOURCES:.jsonnet=)

.PHONY: all clean help $(NAMES)

# Build all dashboards
all: $(DASHBOARDS)

# Vendor deps - auto-install if missing
$(VENDOR):
	@echo "Installing jsonnet dependencies..."
	@$(JB) init 2>/dev/null || true
	@$(JB) install github.com/grafana/grafonnet-lib/grafonnet@master
	@$(JB) install github.com/grafana/grafonnet/gen/grafonnet-latest@main

# Pattern rule: build .json from .jsonnet
%.json: %.jsonnet | $(VENDOR)
	@echo "Building $@"
	@$(JSONNET) -J $(VENDOR) $< -o $@

# Pattern rule: build and deploy by name
$(NAMES): %: %.json
	@test -n "$(GRAFANA_PASSWORD)" || { echo "Error: export GRAFANA_PASSWORD first"; exit 1; }
	@echo "Deploying $< to $(GRAFANA_URL)"
	@curl -sf -X POST -H 'Content-Type: application/json' \
		-d '{"dashboard": '"$$(cat $<)"', "overwrite": true}' \
		"$(GRAFANA_URL)/api/dashboards/db" -u "admin:$(GRAFANA_PASSWORD)" | jq -r '.status // .message'

clean:
	rm -f $(DASHBOARDS)

clean-all: clean
	rm -rf $(VENDOR) jsonnetfile.json jsonnetfile.lock.json

help:
	@echo "Usage:"
	@echo "  make <name>       Build and deploy dashboard (e.g., make command-center)"
	@echo "  make all          Build all dashboards (no deploy)"
	@echo "  make clean        Remove built JSON files"
	@echo "  make clean-all    Remove JSON + vendor"
	@echo ""
	@echo "Setup: export GRAFANA_PASSWORD=<password>"
