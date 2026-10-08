"""Opt-in local read-only Web UI preview. Does not modify the Operations supervisor."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from industrial_phm.runtime.operations_web_http import create_operations_web_read_server


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the read-only Operations Web monitor without replacing marimo"
    )
    parser.add_argument("workspace", type=Path, help="existing Operations workspace")
    parser.add_argument("--port", type=int, default=8765, help="loopback port (default: 8765)")
    args = parser.parse_args(argv)
    server = create_operations_web_read_server(args.workspace, port=args.port)
    print(f"Read-only Web monitor: http://127.0.0.1:{server.server_port}/web/", flush=True)
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
