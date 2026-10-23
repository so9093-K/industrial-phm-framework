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
