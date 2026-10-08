"""Opt-in loopback Operations Web preview; does not supervise collection or analysis."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from industrial_phm.runtime.operations_web_http import create_operations_web_read_server


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the opt-in Operations Web preview without replacing marimo"
    )
    parser.add_argument("workspace", type=Path, help="existing Operations workspace")
    parser.add_argument("--port", type=int, default=8765, help="loopback port (default: 8765)")
    args = parser.parse_args(argv)
    server = create_operations_web_read_server(args.workspace, port=args.port)
    print(f"Operations Web preview: http://127.0.0.1:{server.server_port}/web/", flush=True)
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
