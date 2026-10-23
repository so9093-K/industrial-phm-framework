"""Development-only verification orchestration, never imported by product runtime."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "tools" / "verification" / "suites.json"
RUNNERS = {"pytest", "vitest", "playwright"}


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def revision() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def load_suites(path: Path = CONFIG) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("suite configuration must use schema_version=1")
    suites = data.get("suites")
    if not isinstance(suites, dict) or not suites:
        raise ValueError("suites must be a non-empty object")
    for name, suite in suites.items():
        if not isinstance(name, str) or re.fullmatch(r"[a-z][a-z0-9-]{0,63}", name) is None:
            raise ValueError(f"invalid suite name: {name!r}")
        if not isinstance(suite, dict) or suite.get("runner") not in RUNNERS:
            raise ValueError(f"{name}: invalid runner")
        command = suite.get("command")
        if not isinstance(command, list) or not command or any(
            not isinstance(part, str) or not part for part in command
        ):
            raise ValueError(f"{name}: command must be a non-empty argument array")
        timeout = suite.get("timeout_seconds")
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 3600:
            raise ValueError(f"{name}: invalid timeout")
        cwd = suite.get("cwd", ".")
        if not isinstance(cwd, str):
            raise ValueError(f"{name}: invalid cwd")
        target = (ROOT / cwd).resolve()
        if not target.is_relative_to(ROOT) or not target.is_dir():
            raise ValueError(f"{name}: cwd must exist inside the repository")
        environment = suite.get("environment", {})
        if not isinstance(environment, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in environment.items()
        ):
            raise ValueError(f"{name}: invalid environment")
        for key in environment:
            if key.startswith(("GITHUB_", "CI_", "INDUSTRIAL_PHM_")):
                raise ValueError(f"{name}: reserved environment key: {key}")
    return suites


def junit_summary(path: Path) -> dict[str, int]:
    """Require non-empty native JUnit rather than fabricating passing cases."""
    root = ET.parse(path).getroot()
    if root.tag not in {"testsuite", "testsuites"}:
        raise ValueError("unexpected JUnit root element")
    cases = list(root.iter("testcase"))
    if not cases:
        raise ValueError("JUnit contains no test cases")
    return {
        "tests": len(cases),
        "failures": sum(any(child.tag == "failure" for child in case) for case in cases),
        "errors": sum(any(child.tag == "error" for child in case) for case in cases),
        "skipped": sum(any(child.tag == "skipped" for child in case) for case in cases),
    }


def verdict(exit_code: int, summary: dict[str, int] | None) -> str:
    if summary is None:
        return "INCOMPLETE"
    if summary["failures"]:
        return "TEST_FAILED"
    if summary["errors"] or exit_code != 0:
        return "EXECUTION_ERROR"
    if summary["tests"] == summary["skipped"]:
        return "INCOMPLETE"
    return "PASSED"


def expand(value: str, *, junit: Path) -> str:
    return value.replace("{python}", sys.executable).replace("{junit}", str(junit))


def run_suite(name: str, *, output_root: Path, config: Path = CONFIG) -> int:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    folder = output_root / run_id
    folder.mkdir(parents=True, exist_ok=False)
    junit = folder / "junit.xml"
    log_path = folder / "runner.log"
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "suite_id": name,
        "started_at": now(),
        "finished_at": None,
        "revision": revision(),
        "runner": None,
        "command": None,
        "exit_code": None,
        "status": "CONFIG_ERROR",
        "junit": None,
        "summary": None,
        "log": "runner.log",
        "error": None,
    }
    try:
        suites = load_suites(config)
        if name not in suites:
            raise ValueError(f"unknown suite: {name}")
        spec = suites[name]
        manifest["runner"] = spec["runner"]
        cmd = [expand(value, junit=junit) for value in spec["command"]]
        manifest["command"] = cmd
        environment = os.environ.copy()
        environment.update(
            {key: expand(value, junit=junit) for key, value in spec.get("environment", {}).items()}
        )
        cwd = (ROOT / spec.get("cwd", ".")).resolve()
        try:
            with log_path.open("w", encoding="utf-8") as log:
                result = subprocess.run(
                    cmd,
                    cwd=cwd,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=spec["timeout_seconds"],
                    check=False,
                )
            manifest["exit_code"] = result.returncode
            try:
                summary = junit_summary(junit)
                manifest["summary"] = summary
                manifest["junit"] = "junit.xml"
                manifest["status"] = verdict(result.returncode, summary)
            except (ET.ParseError, OSError, ValueError) as exc:
                manifest["status"] = "INCOMPLETE" if result.returncode == 0 else "EXECUTION_ERROR"
                manifest["error"] = f"missing/invalid native JUnit result: {exc}"
        except FileNotFoundError as exc:
            manifest["status"] = "EXECUTION_ERROR"
            manifest["error"] = f"runner not installed: {exc.filename}"
        except subprocess.TimeoutExpired:
            manifest["status"] = "INTERRUPTED"
            manifest["error"] = f"runner exceeded {spec['timeout_seconds']} seconds"
    except (OSError, ValueError, TypeError) as exc:
        manifest["status"] = "CONFIG_ERROR"
        manifest["error"] = str(exc)
    except KeyboardInterrupt:
        manifest["status"] = "INTERRUPTED"
        manifest["error"] = "operator interrupted the run"
    finally:
        manifest["finished_at"] = now()
        target = folder / "run-manifest.json"
        temporary = folder / "run-manifest.json.tmp"
        temporary.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
        print(f"{name}: {manifest['status']} ({target})", flush=True)
        if manifest["error"]:
            print(manifest["error"], file=sys.stderr)
    return {"PASSED": 0, "TEST_FAILED": 1, "CONFIG_ERROR": 2}.get(
        manifest["status"], 3
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Development-only verification CLI")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list", help="list configured native suites")
    run = sub.add_parser("run", help="run one suite in an isolated evidence directory")
    run.add_argument("suite")
    run.add_argument("--output", type=Path, default=ROOT / "artifacts" / "verification")
    args = parser.parse_args()
    if args.action == "list":
        try:
            for name, spec in load_suites().items():
                print(f"{name}\t{spec['runner']}")
            return 0
        except (OSError, ValueError, TypeError) as exc:
            parser.error(str(exc))
    return run_suite(args.suite, output_root=args.output.resolve())


if __name__ == "__main__":
    sys.exit(main())
