SHELL := /bin/sh
.DEFAULT_GOAL := help

UV ?= uv
PYTHON_VERSION ?= 3.14
WORKSPACE ?= artifacts/operations
# macOS runs the Linux supervisor in Docker; Linux keeps the native workflow.
OPERATIONS_BACKEND ?= $(if $(filter Darwin,$(shell uname -s)),container,native)
COMPOSE = docker compose --env-file /dev/null -f compose.yaml
include tools/verify/versions.env
VERIFY_IMAGE ?= industrial-phm-verify
VERIFY_STAGE ?= ci
VERIFY_PLATFORM ?=
_verify_platform = $(if $(VERIFY_PLATFORM),--platform $(VERIFY_PLATFORM),)

.PHONY: help up down status logs demo showcase verify-linux _require-uv _require-npm frontend _prepare \
	_require-linux _require-docker container-up container-down container-status container-logs

help:
	@printf '%s\n' \
		'Industrial PHM' \
		'' \
		'  make up       Start Operations (macOS: Docker, Linux: native)' \
		'  make down     Stop local Operations' \
		'  make status   Show local Operations status' \
		'  make logs     Show component logs' \
		'  make demo     Start the synthetic Operations demo' \
		'  make showcase Open the guided read-only product experience (Node/npm only)' \
		'  make frontend Build the Operations Web static assets (needs Node.js and npm)' \
		'  make container-up/down/status/logs  Explicit Docker Compose lifecycle' \
		'  make verify-linux  Run the CI checks in a Linux container (needs Docker)' \
		'' \
		'Variables:' \
		'  OPERATIONS_BACKEND=container|native  Override the platform default' \
		'  WORKSPACE=<path>   Local Operations workspace (default: artifacts/operations)' \
		'  UV=<command>       uv executable (default: uv)' \
		'  VERIFY_STAGE=<s>   ci (default), source, web-next, forecast, full or one step' \
		'  VERIFY_PLATFORM=<p>  e.g. linux/amd64 to match the CI architecture'

_require-uv:
	@command -v "$(UV)" >/dev/null 2>&1 || { \
		echo "uv is required. Install uv, then run make again." >&2; \
		exit 127; \
	}

_require-npm:
	@command -v npm >/dev/null 2>&1 || { \
		echo "Node.js >=22.12 and npm are required to build Operations Web from source." >&2; \
		exit 127; \
	}

frontend: _require-npm
	npm ci --prefix frontend --no-audit --no-fund
	npm run --prefix frontend build

showcase: _require-npm
	npm ci --prefix frontend --no-audit --no-fund
	npm run --prefix frontend showcase

_prepare: _require-uv frontend
	$(UV) python install $(PYTHON_VERSION)
	$(UV) sync --locked --extra operations

_require-linux:
	@test "$$(uname -s)" = Linux || { \
		echo 'Native Operations requires Linux peer credentials. Use make container-up.' >&2; exit 1; \
	}

_require-docker:
	@docker compose version >/dev/null 2>&1 && docker info >/dev/null 2>&1 || { \
		echo 'Docker with Compose and a running Linux engine is required. Start Docker Desktop, then retry.' >&2; exit 1; \
	}

ifeq ($(OPERATIONS_BACKEND),container)
up: container-up
down: container-down
status: container-status
logs: container-logs
else ifeq ($(OPERATIONS_BACKEND),native)
up: _require-linux
	$(MAKE) _prepare
	$(UV) run --no-sync industrial-phm operations up "$(WORKSPACE)"

down: _require-uv
	$(UV) run --locked --extra operations industrial-phm operations stop "$(WORKSPACE)"

status: _require-uv
	$(UV) run --locked --extra operations industrial-phm operations status "$(WORKSPACE)"

logs: _require-uv
	$(UV) run --locked --extra operations industrial-phm operations logs "$(WORKSPACE)"
else
$(error OPERATIONS_BACKEND must be container or native)
endif

container-up: _require-docker
	$(COMPOSE) up --build --detach --wait --wait-timeout 180
	@printf '%s\n' 'Operations: http://127.0.0.1:2718/web/ (persistent Docker workspace)'

container-down: _require-docker
	$(COMPOSE) down --timeout 60

container-status: _require-docker
	$(COMPOSE) ps --all
	$(COMPOSE) exec -T operations industrial-phm operations status /var/lib/industrial-phm/operations

container-logs: _require-docker
	$(COMPOSE) logs --tail 100
	$(COMPOSE) run --rm --no-deps operations operations logs /var/lib/industrial-phm/operations

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
