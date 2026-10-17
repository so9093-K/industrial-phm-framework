# Local Operations with Docker Compose

The Compose deployment runs the Linux supervisor, collection, analysis, supervised Web and embedded
DuckLake together. macOS uses this path automatically through `make up`; Linux can select it explicitly
with `make container-up` or `OPERATIONS_BACKEND=container`. Native supervision still requires Linux.

## Start and stop

Start Docker Desktop on macOS (or Docker Engine on Linux), then run from the repository root:

```sh
make container-up
make container-status
make container-logs
make container-down
```

Open <http://127.0.0.1:2718/web/>. The first build downloads the pinned Python/Node tools and locked
Operations dependencies, including CPU PyTorch. Later unchanged builds use Docker's cache. Startup
waits for the packaged Web to respond; it does not install dependencies into the running container.
`make container-up` also builds changed sources before starting the node. No host uv, Python or Node is
required. The build context excludes host environments, data, artifacts and `.env` files.

On macOS the shorter `make up/status/logs/down` commands select the same Compose deployment. The node
runs in the background; closing the terminal does not stop it. `down` allows 60 seconds for the existing
supervisor to coordinate child shutdown. No automatic restart policy hides a failed node; inspect
`container-status` and `container-logs`, then explicitly start again after resolving the failure.

## Workspace and recovery

The default Compose project is `industrial-phm`. Its named volume `industrial-phm_workspace` contains:

```text
/var/lib/industrial-phm/operations/             real Operations workspace
/var/lib/industrial-phm/demo-synthetic-*/       isolated first-run sample
```

The runtime runs as UID 10001. The new volume inherits the image directory's ownership. `down` removes
containers and the network, retaining the volume. Rebuilding or recreating the image also retains it.
Do not use `docker compose down --volumes` for a workspace you want to keep. Docker Desktop's disk reset
or deletion of the named volume also destroys its contents. Use offline application backups for recovery.

The container does not mount or migrate host `artifacts/operations`, `data/`, model packages, or `.env`.
Use browser CSV upload for a first connection. Workspace-relative CSV paths refer to container paths.
Existing model packages or workspaces need explicit provisioning; the supported backup/restore contract
remains the application CLI and ADR-0015. Keep the internal Web port in `config.toml` at 2718: this local
Compose reference and its Host/Origin checks intentionally use fixed ports 2718 and 2719.

For an offline backup, stop the node without deleting its volume, run the CLI against that volume,
then copy the backup directory out of the stopped service container:

```sh
docker compose --env-file /dev/null stop --timeout 60
docker compose --env-file /dev/null run --rm --no-deps operations \
  maintenance backup /var/lib/industrial-phm/operations /var/lib/industrial-phm/backup
docker compose --env-file /dev/null cp operations:/var/lib/industrial-phm/backup ./backup
make container-up
```

Choose a new backup destination if one already exists. `WORKSPACE` controls native commands only.
Use `COMPOSE_PROJECT_NAME` consistently if changing the Compose project name; it also changes the
volume name. Separate projects still cannot publish the same host ports simultaneously.

## Local transport and optional services

The Python Web continues to listen on Linux loopback. An unprivileged nginx sidecar shares the
Operations network namespace and forwards ports 8080/8081 to loopback 2718/2719. Docker publishes only
`127.0.0.1:2718` and `127.0.0.1:2719` on the host. The second port serves the isolated first-run sample;
its OPC UA simulator remains internal. Docker Desktop host networking is not required.

The proxy preserves the original Host, Origin, Sec-Fetch-Site and CSRF headers. The application retains
its exact localhost allowlist and Linux PID/UID peer credential broker. Neither writable preview mode
nor remote UI access is enabled. Remote authentication/TLS and multi-user hosting remain outside this
reference. See [Docker's localhost port publishing semantics](https://docs.docker.com/engine/network/port-publishing/).

External OPC UA endpoints must be reachable **from the container**. `127.0.0.1` in a source URL means
the container, not the Mac. For a Mac-hosted OPC UA server, use Docker Desktop's `host.docker.internal`
address and configure that server's listener accordingly. Remote industrial sources and their credentials
are not provisioned automatically.

AI explanation is optional and still requires a separately provisioned compatible model server. The
default endpoint `http://127.0.0.1:9400/v1` means this container network namespace. A Mac-hosted server is
not automatically connected. The existing provider accepts a loopback endpoint, or an explicitly enabled
HTTPS remote endpoint (`INDUSTRIAL_PHM_GENAI_BASE_URL`, `INDUSTRIAL_PHM_GENAI_ALLOW_REMOTE=1`, model and
optional API key). Supply these to `operations` using a local Compose override; do not bake credentials
into the image. Arbitrary plain HTTP remote endpoints, including `http://host.docker.internal:9400`,
remain rejected by the provider. This deployment does not download an AI model or claim AI validation.

## Verification

With host ports 2718/2719 free:

```sh
. tools/verify/versions.env
uvx --from "playwright==$PLAYWRIGHT_VERSION" playwright install chromium
uvx --from "playwright==$PLAYWRIGHT_VERSION" python tools/verify/container_smoke.py
```

The test creates a unique temporary Compose project, builds the runtime, performs browser CSV upload,
history storage, statistical analysis, review and sample browsing, checks hostile headers and missing
CSRF rejection, and stops/recreates containers to read the same measurements and review note. It checks
clean supervisor exit and Node-free runtime, then removes only its own project and volume. CI repeats
this path on Linux amd64; local Docker Desktop verification covers Apple Silicon arm64.
