# syntax=docker/dockerfile:1
FROM node:22.23.3-bookworm-slim AS node
FROM ghcr.io/astral-sh/uv:0.12.13-python3.14-trixie-slim AS build
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm
WORKDIR /opt/industrial-phm
COPY pyproject.toml uv.lock hatch_build.py README.md LICENSE ./
COPY frontend ./frontend
COPY src ./src
# The normal wheel hook compiles the locked frontend into the installed package.
RUN --mount=type=cache,target=/root/.cache/uv --mount=type=cache,target=/root/.npm \
    UV_LINK_MODE=copy uv sync --locked --no-dev --no-editable --extra operations

FROM python:3.14-slim-trixie AS runtime
ENV PATH="/opt/industrial-phm/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin phm \
 && mkdir -p /var/lib/industrial-phm \
 && chown phm:phm /var/lib/industrial-phm
COPY --from=build /opt/industrial-phm/.venv /opt/industrial-phm/.venv
USER phm
WORKDIR /var/lib/industrial-phm
ENTRYPOINT ["industrial-phm"]
CMD ["operations", "up", "/var/lib/industrial-phm/operations"]
