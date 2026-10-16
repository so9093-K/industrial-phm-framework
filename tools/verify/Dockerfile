# Reproducible Linux verification image: the CI runtime (Ubuntu 24.04, uv, Python 3.14,
# Node 22, Playwright Chromium) for hosts whose OS cannot run every check, such as macOS.
# Source is streamed in at run time, so the host's virtualenv and node_modules never leak in.
ARG UV_VERSION=0.12.13
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM ubuntu:24.04
ARG NODE_VERSION=22.23.3
ARG PLAYWRIGHT_VERSION=1.64.0
ARG TARGETARCH
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright PLAYWRIGHT_SYSTEM_DEPS=preinstalled

# tzdata: CI runners ship the IANA time zone database and zoneinfo readers rely on it.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git make tar tzdata xz-utils \
 && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /uvx /usr/local/bin/

# Official Node.js build, verified against the release checksums.
RUN set -eu; arch="x64"; [ "$TARGETARCH" = "arm64" ] && arch="arm64"; \
    file="node-v${NODE_VERSION}-linux-${arch}.tar.xz"; cd /tmp; \
    curl -fsSLO "https://nodejs.org/dist/v${NODE_VERSION}/${file}"; \
    curl -fsSLO "https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt"; \
    grep " ${file}\$" SHASUMS256.txt | sha256sum -c -; \
    tar -xJf "${file}" -C /usr/local --strip-components=1 --no-same-owner; \
    rm -f "${file}" SHASUMS256.txt; node --version

# Like the CI runner, tests run as an unprivileged user: permission checks must not pass as root.
RUN useradd --create-home --shell /bin/sh verify

# Chromium and its system libraries for the pinned Playwright. The test user owns the browser
# directory because Playwright takes a lock there even when the browser is already present.
RUN uvx --python 3.14 --from "playwright==${PLAYWRIGHT_VERSION}" playwright install --with-deps chromium \
 && chown -R verify:verify "$PLAYWRIGHT_BROWSERS_PATH" \
 && rm -rf /root/.cache /var/lib/apt/lists/*

COPY entrypoint.sh /usr/local/bin/verify-entrypoint
USER verify
RUN uv python install 3.14 && mkdir -p /home/verify/.cache/uv /home/verify/.npm /home/verify/work
WORKDIR /home/verify/work
ENTRYPOINT ["sh", "/usr/local/bin/verify-entrypoint"]
CMD ["ci"]
