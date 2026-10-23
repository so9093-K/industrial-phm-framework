"""Development-only verification orchestration, never imported by product runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from contextlib import suppress
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
    except OSError, subprocess.TimeoutExpired:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def load_suites(path: Path = CONFIG) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("suite configuration must use schema_version=1")
    if set(data) != {"schema_version", "suites"}:
        raise ValueError("suite configuration has missing or unsupported fields")
    suites = data.get("suites")
    if not isinstance(suites, dict) or not suites:
        raise ValueError("suites must be a non-empty object")
    for name, suite in suites.items():
        if not isinstance(name, str) or re.fullmatch(r"[a-z][a-z0-9-]{0,63}", name) is None:
            raise ValueError(f"invalid suite name: {name!r}")
        if not isinstance(suite, dict) or suite.get("runner") not in RUNNERS:
            raise ValueError(f"{name}: invalid runner")
        supported = {
            "runner", "state", "cwd", "timeout_seconds", "command",
            "environment", "allow_skips",
        }
        if set(suite) - supported:
            raise ValueError(f"{name}: unsupported suite fields")
        if suite.get("state") not in {"active", "planned"}:
            raise ValueError(f"{name}: state must be active or planned")
        command = suite.get("command")
        if (
            not isinstance(command, list)
            or not command
            or any(not isinstance(part, str) or not part for part in command)
        ):
            raise ValueError(f"{name}: command must be a non-empty argument array")
        if not isinstance(suite.get("allow_skips", False), bool):
            raise ValueError(f"{name}: allow_skips must be boolean")
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
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) is None:
                raise ValueError(f"{name}: invalid environment key: {key!r}")
            if key.startswith(("GITHUB_", "CI_", "INDUSTRIAL_PHM_")):
                raise ValueError(f"{name}: reserved environment key: {key}")
        for value in [*command, *environment.values()]:
            if "{" in re.sub(r"\{(?:python|junit)\}", "", value) or "}" in re.sub(
                r"\{(?:python|junit)\}", "", value
            ):
                raise ValueError(f"{name}: unknown command/environment placeholder")
    return suites


def junit_summary(path: Path) -> dict[str, int]:
    """Require non-empty native JUnit rather than fabricating passing cases."""
    root = ET.parse(path).getroot()
    if root.tag not in {"testsuite", "testsuites"}:
        raise ValueError("unexpected JUnit root element")
    cases = list(root.iter("testcase"))
    if not cases:
        raise ValueError("JUnit contains no test cases")
    declared_suites = [root] if root.tag == "testsuite" else [root, *root.iter("testsuite")]
    for suite in declared_suites:
        suite_cases = list(suite.iter("testcase"))
        counts = {
            "tests": len(suite_cases),
            "failures": sum(any(child.tag == "failure" for child in case) for case in suite_cases),
            "errors": sum(any(child.tag == "error" for child in case) for case in suite_cases),
            "skipped": sum(any(child.tag == "skipped" for child in case) for case in suite_cases),
        }
        for field, observed in counts.items():
            declared = suite.get(field)
            if declared is not None:
                try:
                    count = int(declared)
                except ValueError as exc:
                    raise ValueError(f"JUnit {field} count is invalid") from exc
                if count < 0 or count != observed:
                    raise ValueError(f"JUnit declared {field} count does not match actual cases")
    if any(not case.get("name") for case in cases):
        raise ValueError("JUnit testcase has no name")
    if any(
        sum(child.tag in {"failure", "error", "skipped"} for child in case) > 1 for case in cases
    ):
        raise ValueError("JUnit testcase has contradictory outcomes")
    return {
        "tests": len(cases),
        "failures": sum(any(child.tag == "failure" for child in case) for case in cases),
        "errors": sum(any(child.tag == "error" for child in case) for case in cases),
        "skipped": sum(any(child.tag == "skipped" for child in case) for case in cases),
    }


def verdict(exit_code: int, summary: dict[str, int] | None, *, allow_skips: bool = False) -> str:
    if summary is None:
        return "INCOMPLETE"
    if summary["errors"]:
        return "EXECUTION_ERROR"
    if summary["failures"]:
        return "TEST_FAILED"
    if exit_code != 0:
        return "EXECUTION_ERROR"
    if summary["tests"] == summary["skipped"] or (summary["skipped"] and not allow_skips):
        return "INCOMPLETE"
    return "PASSED"


def expand(value: str, *, junit: Path) -> str:
    return value.replace("{python}", sys.executable).replace("{junit}", str(junit))


def invoke_runner(
    cmd: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    log: Any,
    timeout_seconds: int,
) -> int:
    """Terminate the runner process group on timeout or operator interruption."""
    with subprocess.Popen(
        cmd,
        cwd=cwd,
        env=environment,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=os.name == "posix",
    ) as process:
        try:
            return process.wait(timeout=timeout_seconds)
        except BaseException:
            if process.poll() is None:
                if os.name == "posix":
                    with suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            process.wait()
            raise


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
        "suite_definition_sha256": None,
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "command": None,
        "exit_code": None,
        "status": "CONFIG_ERROR",
        "junit": None,
        "summary": None,
        "log": None,
        "error": None,
    }
    try:
        suites = load_suites(config)
        if name not in suites:
            raise ValueError(f"unknown suite: {name}")
        spec = suites[name]
        manifest["runner"] = spec["runner"]
        manifest["suite_definition_sha256"] = hashlib.sha256(
            json.dumps(spec, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        if spec["state"] != "active":
            raise ValueError(f"suite {name} is planned, not activated")
        cmd = [expand(value, junit=junit) for value in spec["command"]]
        manifest["command"] = cmd
        environment = os.environ.copy()
        environment.update(
            {key: expand(value, junit=junit) for key, value in spec.get("environment", {}).items()}
        )
        cwd = (ROOT / spec.get("cwd", ".")).resolve()
        try:
            with log_path.open("w", encoding="utf-8") as log:
                manifest["log"] = "runner.log"
                exit_code = invoke_runner(
                    cmd,
                    cwd=cwd,
                    environment=environment,
                    log=log,
                    timeout_seconds=spec["timeout_seconds"],
                )
            manifest["exit_code"] = exit_code
            try:
                summary = junit_summary(junit)
                manifest["summary"] = summary
                manifest["junit"] = "junit.xml"
                manifest["status"] = verdict(
                    exit_code, summary, allow_skips=spec.get("allow_skips", False)
                )
            except (ET.ParseError, OSError, ValueError) as exc:
                manifest["status"] = "INCOMPLETE" if exit_code == 0 else "EXECUTION_ERROR"
                manifest["error"] = f"missing/invalid native JUnit result: {exc}"
        except FileNotFoundError as exc:
            manifest["status"] = "EXECUTION_ERROR"
            manifest["error"] = f"runner or execution file unavailable: {exc.filename}"
        except OSError as exc:
            manifest["status"] = "EXECUTION_ERROR"
            manifest["error"] = f"runner execution failure: {exc}"
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
    return {"PASSED": 0, "TEST_FAILED": 1, "CONFIG_ERROR": 2}.get(manifest["status"], 3)


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
                print(f"{name}\t{spec['runner']}\t{spec['state']}")
            return 0
        except (OSError, ValueError, TypeError) as exc:
            parser.error(str(exc))
    return run_suite(args.suite, output_root=args.output.resolve())


if __name__ == "__main__":
    sys.exit(main())
