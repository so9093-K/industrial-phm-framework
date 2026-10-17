"""Exercise the packaged Compose node through a host browser, including volume recovery.

Run with Playwright installed, while host ports 2718 and 2719 are free. Only the
unique smoke project's containers and volume are removed; other workspaces are untouched.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:2718"
WORKSPACE = "/var/lib/industrial-phm/operations"


def main() -> None:
    project = f"industrial-phm-smoke-{uuid4().hex[:10]}"
    command = [
        "docker",
        "compose",
        "--env-file",
        "/dev/null",
        "-f",
        str(ROOT / "compose.yaml"),
        "--project-name",
        project,
    ]

    def compose(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*command, *args],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=capture,
        )

    def up() -> None:
        compose("up", "--build", "--detach", "--wait", "--wait-timeout", "180")

    def down() -> None:
        compose("down", "--timeout", "60")

    def stop_cleanly() -> None:
        compose("stop", "--timeout", "60")
        result = compose("ps", "--all", "--format", "json", capture=True).stdout
        # Compose v2+ emits one JSON object per line (or a JSON array).
        states = (
            json.loads(result)
            if result.startswith("[")
            else [json.loads(line) for line in result.splitlines() if line.strip()]
        )
        operations = next(item for item in states if item["Service"] == "operations")
        assert operations["ExitCode"] == 0, operations
        down()

    try:
        up()
        compose("exec", "-T", "operations", "sh", "-c", "! command -v node && ! command -v npm")
        compose(
            "exec",
            "-T",
            "operations",
            "python",
            "-c",
            "import asyncua, duckdb, numpy, pandas as pd, torch; from prophet import Prophet; "
            "assert torch.ones(2).sum().item() == 2; "
            "data = pd.DataFrame({'ds': pd.date_range('2026-01-01', periods=30, freq='h'), "
            "'y': numpy.arange(30, dtype=float)}); model = Prophet(); model.fit(data); "
            "assert len(model.predict(model.make_future_dataframe(periods=2, freq='h'))) == 32",
        )
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 390, "height": 900}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(BASE + "/web/")
                # Proxy headers must preserve the server's browser authority checks.
                assert (
                    page.request.get(
                        BASE + "/api/v1/session", headers={"Host": "evil.invalid"}
                    ).status
                    == 403
                )
                assert (
                    page.request.get(
                        BASE + "/api/v1/session", headers={"Origin": "http://evil.invalid"}
                    ).status
                    == 403
                )
                assert (
                    page.request.post(BASE + "/api/v1/demo/synthetic/start", data={}).status == 403
                )
                page.get_by_role("link", name="데이터 연결하기").click()
                start = page.get_by_role("region", name="CSV 파일로 시작")
                at = datetime(2026, 10, 11, tzinfo=UTC)
                lines = ["timestamp,current_a,voltage_v,label"] + [
                    f"{(at + timedelta(seconds=i)).isoformat()},"
                    f"{1.5 + 0.01 * i:.2f},{220 + i % 3},run"
                    for i in range(40)
                ]
                start.get_by_label("CSV 파일 (UTF-8 · 20MiB 이하)").set_input_files(
                    {
                        "name": "container.csv",
                        "mimeType": "text/csv",
                        "buffer": ("\n".join(lines) + "\n").encode(),
                    }
                )
                start.get_by_label("설비 이름·번호").fill("container-pump")
                start.get_by_role("button", name="서버에서 점검 (저장 안 함)").click()
                expect(start.get_by_text("점검 통과")).to_be_visible()
                start.get_by_role("button", name="등록하고 이력 저장").click()
                expect(start).to_contain_text("저장했습니다", timeout=60_000)
                card = page.get_by_role("article", name="container.csv")
                card.get_by_role("button", name="신호 통계 분석").click()
                expect(card).to_contain_text("분석을 저장했습니다")
                page.get_by_role("link", name="분석 기록에서 보기").click()
                record = page.get_by_role("region", name="분석 결과").get_by_role("article")
                expect(record).to_contain_text("container-pump")
                record.get_by_role("button", name="검토 요청").click()
                record.get_by_role("link", name="정비 검토함에서 보기").click()
                detail = page.get_by_role("region", name="고른 검토 항목")
                detail.get_by_label("메모 (최대 1000자)").fill("Docker 재생성 후 보존 확인")
                detail.get_by_role("button", name="메모 남기기").click()
                expect(detail).to_contain_text("검토 기록을 남겼습니다")
                detail.get_by_role("button", name="확인함으로 표시").click()
                expect(detail.locator(".badge")).to_have_text("확인함")
                review_url = page.url
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")

                # Exercise the separate loopback sample, not a mocked launch URL.
                page.goto(BASE + "/web/?page=system")
                sample = page.get_by_role("region", name="예시로 둘러보기")
                sample.get_by_role("button", name="예시 시작").click()
                link = sample.get_by_role("link", name="예시 화면 열기 (새 탭)")
                expect(link).to_be_visible(timeout=60_000)
                with page.expect_popup() as popup:
                    link.click()
                example = popup.value
                expect(
                    example.get_by_text("합성 예시 데이터 · 별도 작업공간 · 보기 전용")
                ).to_be_visible(timeout=30_000)
                expect(example.locator("a.row").first).to_be_visible(timeout=30_000)
                example.close()
                sample.get_by_role("button", name="예시 종료").click()
                sample.get_by_role("button", name="종료하기").click()
                expect(sample.get_by_role("button", name="예시 시작")).to_be_visible(timeout=45_000)

                stop_cleanly()
                # Preflight is a stopped-service check: a live supervisor owns its lock.
                compose(
                    "run", "--rm", "--no-deps", "operations", "validate", "deployment", WORKSPACE
                )
                up()
                compose(
                    "exec", "-T", "operations", "industrial-phm", "operations", "status", WORKSPACE
                )
                page.goto(review_url)
                detail = page.get_by_role("region", name="고른 검토 항목")
                expect(detail).to_contain_text("Docker 재생성 후 보존 확인", timeout=30_000)
                expect(detail.locator(".badge")).to_have_text("확인함")
                page.goto(BASE + "/web/?page=system")
                expect(page.get_by_role("article", name="container.csv")).to_be_visible()
                channels = page.request.get(
                    BASE + "/api/v1/history/channels?asset_id=container-pump"
                ).json()
                assert channels["channels"]["items"] == ["current_a", "voltage_v"], channels
                assert not errors, errors
                stop_cleanly()
            finally:
                browser.close()
        print(
            "PASS: packaged Web, CSV, analysis, review, sample, guards, "
            "clean stop and volume recovery"
        )
    except BaseException:
        compose("logs", "--tail", "100")
        raise
    finally:
        # This unique project/volume was created only by this verification run.
        compose("down", "--volumes", "--timeout", "60")


if __name__ == "__main__":
    main()
