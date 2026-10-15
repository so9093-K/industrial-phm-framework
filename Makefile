SHELL := /bin/sh
.DEFAULT_GOAL := help

UV ?= uv
PYTHON_VERSION ?= 3.14
WORKSPACE ?= artifacts/operations

.PHONY: help up down status logs demo _require-uv _prepare

help:
	@printf '%s\n' \
		'Industrial PHM' \
		'' \
		'  make up       Start or resume local Operations' \
		'  make down     Stop local Operations' \
		'  make status   Show local Operations status' \
		'  make logs     Show component logs' \
		'  make demo     Start the synthetic Operations demo' \
		'' \
		'Variables:' \
		'  WORKSPACE=<path>   Local Operations workspace (default: artifacts/operations)' \
		'  UV=<command>       uv executable (default: uv)'

_require-uv:
	@command -v "$(UV)" >/dev/null 2>&1 || { \
		echo "uv is required. Install uv, then run make again." >&2; \
		exit 127; \
	}

_prepare: _require-uv
	$(UV) python install $(PYTHON_VERSION)
	$(UV) sync --locked --extra operations

up: _prepare
	$(UV) run --no-sync industrial-phm operations up "$(WORKSPACE)"

down: _require-uv
	$(UV) run --locked --extra operations industrial-phm operations stop "$(WORKSPACE)"

status: _require-uv
	$(UV) run --locked --extra operations industrial-phm operations status "$(WORKSPACE)"

logs: _require-uv
	$(UV) run --locked --extra operations industrial-phm operations logs "$(WORKSPACE)"

demo: _prepare
	$(UV) run --no-sync industrial-phm demo synthetic
