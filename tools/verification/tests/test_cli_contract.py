"""Fresh contracts for the development verification orchestrator."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.verification.verify import ROOT, junit_summary, load_suites, run_suite, verdict


def write_junit(path: Path, body: str) -> None:
    path.write_text(f'<testsuite name="contract">{body}</testsuite>', encoding="utf-8")


def test_registry_declares_three_native_runners() -> None:
    suites = load_suites()
    assert {suite["runner"] for suite in suites.values()} == {
        "pytest",
        "vitest",
        "playwright",
    }


def test_junit_verdict_is_native_result_not_process_exit_alone(tmp_path: Path) -> None:
    path = tmp_path / "junit.xml"
    write_junit(path, '<testcase name="fails"><failure message="bad"/></testcase>')
    summary = junit_summary(path)
    assert summary["failures"] == 1
    assert verdict(0, summary) == "TEST_FAILED"
    assert verdict(1, summary) == "TEST_FAILED"


def test_junit_error_does_not_become_test_failure(tmp_path: Path) -> None:
    path = tmp_path / "junit.xml"
    write_junit(path, '<testcase name="errors"><error message="setup"/></testcase>')
    assert verdict(1, junit_summary(path)) == "EXECUTION_ERROR"


def test_missing_or_all_skipped_evidence_cannot_pass(tmp_path: Path) -> None:
    path = tmp_path / "junit.xml"
    write_junit(path, '<testcase name="skip"><skipped/></testcase>')
    assert verdict(0, junit_summary(path)) == "INCOMPLETE"
    assert verdict(0, None) == "INCOMPLETE"
    path.write_text('<testsuite name="empty" />', encoding="utf-8")
    with pytest.raises(ValueError, match="no test cases"):
        junit_summary(path)


def test_invalid_suite_config_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "suites.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "suites": {
                    "bad": {
                        "runner": "pytest",
                        "state": "active",
                        "cwd": "..",
                        "timeout_seconds": 10,
                        "command": [sys.executable],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="cwd"):
        load_suites(config)


def test_missing_runner_produces_manifest_not_false_pass(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "suites": {
                    "missing": {
                        "runner": "pytest",
                        "state": "active",
                        "cwd": ".",
                        "timeout_seconds": 5,
                        "command": ["/definitely/no/verification-runner"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    assert run_suite("missing", output_root=tmp_path / "results", config=config) == 3
    manifests = list((tmp_path / "results").glob("*/run-manifest.json"))
    assert len(manifests) == 1
    state = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert state["status"] == "EXECUTION_ERROR"
    assert state["junit"] is None


def test_unknown_suite_is_configuration_error_with_evidence(tmp_path: Path) -> None:
    assert run_suite("unknown", output_root=tmp_path / "results") == 2
    manifests = list((tmp_path / "results").glob("*/run-manifest.json"))
    state = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert state["status"] == "CONFIG_ERROR"


def test_verifier_is_outside_product_package() -> None:
    assert (ROOT / "tools/verification/verify.py").is_file()
    assert not (ROOT / "src/industrial_phm/verification").exists()


def test_cli_lists_without_importing_product(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/verification/verify.py"), "list"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "verification-smoke" in result.stdout


def test_declared_unavailable_suites_are_not_runnable(tmp_path: Path) -> None:
    suites = load_suites()
    assert suites["verification-smoke"]["state"] == "active"
    for name in ("frontend-vitest", "browser-playwright"):
        assert suites[name]["state"] == "planned"
        assert run_suite(name, output_root=tmp_path / name) == 2
        states = list((tmp_path / name).glob("*/run-manifest.json"))
        assert len(states) == 1
        result = json.loads(states[0].read_text(encoding="utf-8"))
        assert result["status"] == "CONFIG_ERROR"
        assert result["command"] is None


def test_junit_rejects_mismatched_declared_test_count(tmp_path: Path) -> None:
    path = tmp_path / "junit.xml"
    path.write_text(
        '<testsuite tests="3"><testcase name="only-one"/></testsuite>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="does not match"):
        junit_summary(path)


def test_junit_rejects_unnamed_or_contradictory_cases(tmp_path: Path) -> None:
    path = tmp_path / "junit.xml"
    write_junit(path, "<testcase><skipped/></testcase>")
    with pytest.raises(ValueError, match="no name"):
        junit_summary(path)
    write_junit(path, '<testcase name="bad"><failure/><skipped/></testcase>')
    with pytest.raises(ValueError, match="contradictory"):
        junit_summary(path)


def test_unrecognized_placeholder_is_rejected(tmp_path: Path) -> None:
    spec = load_suites()["verification-smoke"].copy()
    spec["command"] = ["{python}", "-m", "pytest", "--bad={secret}"]
    config = tmp_path / "suites.json"
    config.write_text(
        json.dumps({"schema_version": 1, "suites": {"bad": spec}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="placeholder"):
        load_suites(config)


def test_run_manifest_has_a_suite_fingerprint(tmp_path: Path) -> None:
    config = tmp_path / "suites.json"
    spec = {
        "runner": "pytest",
        "state": "active",
        "cwd": ".",
        "timeout_seconds": 10,
        "command": [
            "{python}",
            "-c",
            "import os; from pathlib import Path; "
            "Path(os.environ['NATIVE_JUNIT_PATH']).write_text("
            '\'<testsuite tests=\\"1\\"><testcase name=\\"example\\"/></testsuite>\')',
        ],
        "environment": {"NATIVE_JUNIT_PATH": "{junit}"},
    }
    config.write_text(
        json.dumps({"schema_version": 1, "suites": {"stub": spec}}),
        encoding="utf-8",
    )
    assert run_suite("stub", output_root=tmp_path / "runs", config=config) == 0
    manifests = list((tmp_path / "runs").glob("*/run-manifest.json"))
    assert len(manifests) == 1
    result = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert result["status"] == "PASSED"
    assert len(result["suite_definition_sha256"]) == 64
    assert result["summary"]["tests"] > 0
    assert result["python_version"] and result["platform"]
