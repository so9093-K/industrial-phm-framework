"""Chromium UX inspection of a completed recorded-data acceptance workspace.

Run acceptance_xjtu/acceptance_aihub first. This starts the same supervised node,
captures its saved results at three widths, and stops it without replaying data.
No model fitting or model-performance judgment is performed here.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from tools.phm.acceptance_common import Checks, Supervisor, write_evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--scenario", choices=("xjtu", "aihub"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    workspace, output = args.workspace.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    import tomllib

    config = tomllib.loads((workspace / "config.toml").read_text())
    url = f"http://127.0.0.1:{config['ui']['port']}/web/"
    checks = Checks()
    evidence: dict[str, Any] = {
        "scenario": args.scenario,
        "code_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "started_at": datetime.now(UTC).isoformat(),
        "source": "saved results from original recorded-data acceptance, not field input",
        "viewports": [],
    }
    supervisor = Supervisor(workspace, output / "supervisor.log")
    from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore

    package_ids = {
        item.binding_id: item.package_id
        for item in SqlitePhmAnalysisStore(workspace / "phm-analysis.sqlite").list_bindings()
    }
    from playwright.sync_api import expect, sync_playwright

    try:
        supervisor.start()
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            evidence["browser"] = {"name": "Chromium", "version": browser.version}
            try:
                views = (
                    [("anomaly", "aihub-1338")]
                    if args.scenario == "aihub"
                    else [
                        ("anomaly", "anomaly-score-Bearing1_1"),
                        ("rul", "rul-estimate-Bearing1_1"),
                        ("anomaly", "lstm-lstm-autoencoder-v1-Bearing1_1"),
                        ("rul", "lstm-lstm-rul-v1-Bearing1_1"),
                    ]
                )
                for width, height in ((1440, 900), (1024, 900), (390, 844)):
                    page = browser.new_page(
                        viewport={"width": width, "height": height}, locale="ko-KR"
                    )
                    errors: list[str] = []
                    page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
                    for view, binding in views:
                        label = f"{args.scenario}-{binding}-{width}"
                        page.goto(url + "#" + view)
                        select = page.locator(f"#{view}-binding")
                        expect(select.locator(f'option[value="{binding}"]')).to_have_count(1)
                        select.select_option(binding)
                        expect(page.locator(f"#{view}-model")).to_contain_text(package_ids[binding])
                        expect(page.locator(f"#{view}-freshness")).to_contain_text("최신 분석")
                        expect(page.locator(f"#{view}-replay")).to_be_visible()
                        panel = page.locator(f"#{view}-explanation")
                        expect(panel.locator(".phm-ai-details")).not_to_have_attribute("open", "")
                        expect(panel.locator(".phm-review-status")).not_to_contain_text("조회 중")
                        overflow = page.evaluate(
                            "({viewport: innerWidth, "
                            "document: document.documentElement.scrollWidth})"
                        )
                        checks.add(
                            label + "-no-horizontal-overflow",
                            overflow["document"] <= width,
                            overflow,
                        )
                        checks.add(
                            label + "-ai-secondary", not panel.locator(".phm-ai-text").is_visible()
                        )
                        text = page.locator(f"#{view}-state").inner_text()
                        if view == "rul":
                            expect(page.locator("#rul-state")).to_contain_text(
                                "물리 고장 시각 아님"
                            )
                            expect(page.locator("#rul-validation-note")).to_contain_text("MAE")
                            checks.add(label + "-rul-meaning-and-reference-mae", True, text)
                        else:
                            expect(page.locator("#anomaly-state")).to_contain_text(
                                "고장 확률이나 진단이 아닙니다"
                            )
                            checks.add(label + "-threshold-is-not-health-verdict", True, text)
                        page.screenshot(path=str(output / (label + ".png")), full_page=True)
                        page.locator(f"#{view}-review-options > summary").click()
                        # Real Tab/Enter navigation, not an element.focus() substitute.
                        select.focus()
                        page.keyboard.press("Tab")
                        checks.add(
                            label + "-keyboard-focus-visible",
                            page.evaluate(
                                "getComputedStyle(document.activeElement).outlineStyle !== 'none'"
                            ),
                        )
                        found = False
                        for _ in range(45):
                            found = panel.locator(".phm-ai-details summary").evaluate(
                                "e => e === document.activeElement"
                            )
                            if found:
                                break
                            page.keyboard.press("Tab")
                        checks.add(label + "-ai-summary-keyboard-reachable", found)
                        if found:
                            page.keyboard.press("Enter")
                            expect(panel.locator(".phm-ai-details")).to_have_attribute("open", "")
                        evidence["viewports"].append(
                            {
                                "view": view,
                                "binding": binding,
                                "width": width,
                                "height": height,
                                "asset": page.locator(f"#{view}-asset-title").inner_text(),
                                "observation": page.locator(f"#{view}-observation").inner_text(),
                                "freshness": page.locator(f"#{view}-freshness").inner_text(),
                                "screenshot": label + ".png",
                            }
                        )
                    checks.add(f"{args.scenario}-{width}-no-browser-errors", not errors, errors)
                    page.close()

                page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="ko-KR")
                page.goto(url + "#anomaly")
                binding = views[0][1]
                page.select_option("#anomaly-binding", binding)
                expect(page.locator("#anomaly-model")).to_contain_text(package_ids[binding])
                chart = page.locator("#anomaly-feature-chart svg").first
                expect(chart).to_be_visible()
                with page.expect_response(
                    lambda r: (
                        "/api/v1/phm/" + ("window?" if args.scenario == "aihub" else "snapshot?")
                        in r.url
                    )
                ) as response:
                    chart.click(position={"x": chart.bounding_box()["width"] * 0.45, "y": 30})
                raw = response.value.json()
                position = int(parse_qs(urlparse(response.value.url).query)["position"][0])
                expect(page.locator("#anomaly-detail")).to_contain_text("원본 신호")
                checks.add(
                    args.scenario + "-point-opens-raw-input",
                    response.value.ok and raw.get("available") is True,
                    {"position": position, "response_keys": sorted(raw)},
                )
                if args.scenario == "aihub":
                    expect(page.locator("#anomaly-detail .phm-raw svg")).to_have_count(1)
                    options = page.locator("#anomaly .phm-options summary").last
                    if options.count():
                        options.click()
                    # Three phases in amperes, then three phases in volts, share their own axes.
                    for phase in ("R", "S", "T"):
                        page.locator("#anomaly-features").get_by_text(
                            f"{phase}상 평균 전압 · V", exact=True
                        ).locator("input").check()
                    groups = page.locator("#anomaly-feature-chart .phm-feature")
                    checks.add(
                        "aihub-three-phases-per-unit",
                        groups.count() == 2
                        and all(
                            groups.nth(i).locator(".phm-phase-curve").count() == 3
                            for i in range(groups.count())
                        ),
                        page.locator("#anomaly-feature-chart").inner_text(),
                    )
                    evidence["phase_paths"] = page.locator(
                        "#anomaly-feature-chart .phm-phase-curve"
                    ).evaluate_all(
                        "es => es.map(e => ({class: e.getAttribute('class'), "
                        "path: e.getAttribute('d')}))"
                    )
                    series = page.request.get(
                        url.removesuffix("/web/") + "/api/v1/phm/series?binding_id=" + binding
                    ).json()
                    rows = [step for step in series["steps"] if step["state"] == "analyzed"]
                    evidence["phase_values"] = [
                        {
                            "event_start": step["event_start"],
                            "position": step["position"],
                            "features": {
                                key: value
                                for key, value in step["features"].items()
                                if key.startswith(("current.phase_", "voltage.phase_"))
                            },
                        }
                        for step in rows
                    ]
                    for index, (quantity, unit) in enumerate((("current", "A"), ("voltage", "V"))):
                        values = [
                            step["features"][f"{quantity}.phase_{phase}.mean_{unit.lower()}"]
                            for step in rows
                            for phase in ("r", "s", "t")
                        ]
                        ticks = groups.nth(index).locator("svg text").all_text_contents()
                        expected = page.evaluate(
                            "values => values.map(v => v.toLocaleString('ko-KR', "
                            "{maximumFractionDigits: 3}))",
                            [max(values), min(values)],
                        )
                        checks.add(
                            f"aihub-{quantity}-original-unit-axis",
                            ticks[:2] == [value + " " + unit for value in expected],
                            {"ticks": ticks, "source_min": min(values), "source_max": max(values)},
                        )
                else:
                    expect(page.locator("#anomaly-detail .phm-wave")).to_have_count(2)
                page.screenshot(
                    path=str(output / f"{args.scenario}-selected-input-1440.png"), full_page=True
                )
                # Simulate only the optional generation endpoint being unavailable.
                # Analysis reads and real supervisor review writes continue normally.
                panel = page.locator("#anomaly-explanation")
                page.locator("#anomaly-review-options > summary").click()
                panel.locator(".phm-ai-details summary").click()
                page.route(
                    "**/api/v1/phm/explanations/request",
                    lambda route: route.fulfill(
                        status=503, json={"error": "ux-acceptance-ai-unavailable"}
                    ),
                )
                panel.get_by_role("button", name="AI 설명 생성").click()
                expect(panel).to_contain_text("AI 설명 생성 불가 · 직접 검토는 계속할 수 있습니다")
                expect(page.locator("#anomaly-cards")).to_contain_text("참고 기준")
                panel.get_by_role("button", name="검토 요청").click()
                expect(panel.locator(".phm-review-status")).to_contain_text("확인 대기")
                panel.get_by_label("검토 메모").fill(
                    "UX 인수: AI 서비스 불가 중에도 원본 신호를 직접 검토"
                )
                panel.get_by_role("button", name="검토 확인").click()
                expect(panel.locator(".phm-review-status")).to_contain_text("종료 가능")
                panel.get_by_role("button", name="검토 종료").click()
                expect(panel.locator(".phm-review-status")).to_contain_text("정비 완료 아님")
                checks.add(args.scenario + "-ai-unavailable-does-not-block-review", True)
                page.screenshot(
                    path=str(output / f"{args.scenario}-ai-unavailable-review-1440.png"),
                    full_page=True,
                )
                page.close()
            finally:
                browser.close()
    except Exception as exc:
        checks.add("ux-run-completed", False, str(exc))
    finally:
        if supervisor.process is not None and supervisor.process.poll() is None:
            supervisor.stop()
        evidence.update(
            checks=checks.items, passed=checks.passed, finished_at=datetime.now(UTC).isoformat()
        )
        write_evidence(output / "evidence.json", evidence)
    return 0 if checks.passed else 1


if __name__ == "__main__":
    sys.exit(main())
