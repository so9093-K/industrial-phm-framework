SHELL := /bin/sh
.DEFAULT_GOAL := help

UV ?= uv
PYTHON_VERSION ?= 3.14
WORKSPACE ?= artifacts/operations
include tools/verify/versions.env
VERIFY_IMAGE ?= industrial-phm-verify
VERIFY_STAGE ?= ci
VERIFY_PLATFORM ?=
_verify_platform = $(if $(VERIFY_PLATFORM),--platform $(VERIFY_PLATFORM),)

.PHONY: help up down status logs demo verify-linux _require-uv _prepare

help:
	@printf '%s\n' \
		'Industrial PHM' \
		'' \
		'  make up       Start or resume local Operations' \
		'  make down     Stop local Operations' \
		'  make status   Show local Operations status' \
		'  make logs     Show component logs' \
		'  make demo     Start the synthetic Operations demo' \
		'  make verify-linux  Run the CI checks in a Linux container (needs Docker)' \
		'' \
		'Variables:' \
		'  WORKSPACE=<path>   Local Operations workspace (default: artifacts/operations)' \
		'  UV=<command>       uv executable (default: uv)' \
		'  VERIFY_STAGE=<s>   ci (default), source, web-next, forecast, full or one step' \
		'  VERIFY_PLATFORM=<p>  e.g. linux/amd64 to match the CI architecture'

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

# The working tree (tracked and untracked, not ignored) is verified on Linux, where the
# supervisor's peer-credential checks run, with the same stages CI calls.
verify-linux:
	@command -v docker >/dev/null 2>&1 || { \
		echo "Docker (or a compatible engine) is required for make verify-linux." >&2; \
		exit 127; \
	}
	docker build $(_verify_platform) --build-arg UV_VERSION=$(UV_VERSION) \
		--build-arg NODE_VERSION=$(NODE_VERSION) --build-arg PLAYWRIGHT_VERSION=$(PLAYWRIGHT_VERSION) \
		-t $(VERIFY_IMAGE) tools/verify
	sh tools/verify/snapshot.sh | docker run --rm -i $(_verify_platform) --shm-size=1g \
		-v industrial-phm-verify-uv:/home/verify/.cache/uv \
		-v industrial-phm-verify-npm:/home/verify/.npm \
		$(VERIFY_IMAGE) $(VERIFY_STAGE)
