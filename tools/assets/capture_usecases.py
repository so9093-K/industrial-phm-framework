"""Capture the use-case screens in assets/ from running Operations workspaces.

Each use case drives the real Web in Chromium (ko-KR, 1440x1000) and writes PNG files and a
capture.json with the conditions. Nothing is drawn onto the images.
Use isolated capture workspaces: models/csv write illustrative human review records, and csv
registers data. Live starts and stops the isolated built-in synthetic OPC UA example.

    # XJTU-SY Bearing1_1 replayed to #100 with both models (demo xjtu --until 100);
    # AI explanations need the configured model server.
    uv run --no-sync python -m tools.assets.capture_usecases models --base http://127.0.0.1:2742
    # An empty workspace: registers the synthetic pump CSV (tools.assets.pump_csv) through the Web.
    uv run --no-sync python -m tools.assets.capture_usecases csv --base http://127.0.0.1:2741 \\
        --csv /path/to/cooling-pump.csv
    # The live OPC UA example started from the same workspace's 운영 관리.
    uv run --no-sync python -m tools.assets.capture_usecases live --base http://127.0.0.1:2741
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[2]
VIEWPORT = {"width": 1440, "height": 1000}
AI_TIMEOUT = 180_000


def _top(locator: Any) -> None:
    """Scroll a region to the top of the viewport so the shot shows it first."""
    locator.evaluate("e => { e.scrollIntoView({block: 'start'}); window.scrollBy(0, -12); }")
    time.sleep(0.6)


def _shot(page: Any, out: Path, name: str, frames: list[Path]) -> None:
    page.evaluate("document.fonts.ready")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2"), name
    path = out / name
    page.screenshot(path=str(path), animations="disabled")
    frames.append(path)
    print(path.relative_to(ROOT))


def _record(
    out: Path, use_case: str, base: str, extra: dict[str, object], frames: list[Path]
) -> None:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    body = {
        "use_case": use_case,
        "captured_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "code_revision": revision or None,
        "browser": "Chromium (Playwright), ko-KR",
        "viewport": VIEWPORT,
        "base": urlsplit(base).hostname + " (local)",
        "capture_tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "screens": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in frames},
        **extra,
    }
    (out / "capture.json").write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n")


def _gif(frames: list[Path], target: Path) -> None:
    from PIL import Image

    images = [Image.open(frame).convert("RGB").resize((960, 667)) for frame in frames]
    images[0].save(
        target, save_all=True, append_images=images[1:], duration=2200, loop=0, optimize=True
    )
    print(target.relative_to(ROOT))


def capture_models(page: Any, base: str, out: Path, asset: str) -> None:
    """관측 → 모델 점수·기준 → 원본·전후 변화 → AI 해설 → 담당자 판단, then the outlook."""
    from playwright.sync_api import expect

    frames: list[Path] = []
    page.goto(base + "/web/")
    attention = page.get_by_role("region", name="확인이 필요한 설비")
    subject = attention.get_by_role("article").filter(has_text=asset)
    expect(subject).to_contain_text("부터 계속 기준 초과")
    _shot(page, out, "01-attention.png", frames)

    subject.get_by_role("link", name="점수 추이 보기").click()
    expect(page.get_by_label("기준 초과 상태").first).to_be_visible(timeout=30_000)
    _top(page.get_by_role("heading", name="모델별 점수 비교"))
    _shot(page, out, "02-models.png", frames)

    raw = page.locator("section.input").first
    expect(raw.locator("p.check")).to_be_visible(timeout=30_000)
    _top(raw)
    _shot(page, out, "03-measurement.png", frames)

    _top(page.get_by_text("측정 특징 비교", exact=False).first)
    _shot(page, out, "04-changes.png", frames)

    explanation = page.locator("section.explanation").first
    expect(explanation.get_by_role("heading", name="AI 해설")).to_be_visible()
    if explanation.get_by_role("button", name="해설 만들기", exact=True).count():
        explanation.get_by_role("button", name="해설 만들기", exact=True).click()
        expect(explanation.locator("p.summary")).to_be_visible(timeout=AI_TIMEOUT)
    explanation.get_by_text("이어서 질문하기").click()
    explanation.get_by_label("AI에게 물을 질문 (최대 600자)").fill(
        "같은 측정에서 다른 모델의 기준 판단과 이 모델의 결과가 어떻게 다른지 설명해 주세요."
    )
    explanation.get_by_role("button", name="질문 보내기").click()
    expect(explanation.locator("p.question")).to_contain_text(
        "같은 측정에서 다른 모델", timeout=AI_TIMEOUT
    )
    expect(explanation.locator("p.summary")).to_be_visible(timeout=AI_TIMEOUT)
    _top(explanation)
    _shot(page, out, "05-explanation.png", frames)
    explained = explanation.locator(".meta").inner_text()

    request = page.get_by_role("button", name="검토 요청", exact=True)
    if request.count():
        request.click()
    review_link = page.get_by_role("link", name="정비 검토함에서 보기 →")
    expect(review_link).to_be_visible(timeout=30_000)
    page.goto(urljoin(base, review_link.get_attribute("href")))
    detail = page.get_by_role("region", name="고른 검토 항목")
    expect(detail.get_by_label("판단 근거")).to_be_visible(timeout=30_000)
    if detail.get_by_role("button", name="확인함으로 표시").count():
        detail.get_by_role("radio", name="추가 점검 필요").check()
        detail.get_by_text("판단 이유 함께 남기기 (선택)").click()
        detail.get_by_label("판단 이유 (선택)").fill(
            "캡처용 예시 판단: 저장된 초과 구간·전후 비교·모델 차이를 검토하고 "
            "추가 점검이 필요하다고 가정합니다. 실제 정비 지시는 아닙니다."
        )
        detail.get_by_role("button", name="확인함으로 표시").click()
    expect(detail.locator(".events li").first).to_contain_text("추가 점검 필요")
    _top(detail)
    _shot(page, out, "06-review.png", frames)

    page.goto(
        base
        + "/web/?"
        + urlencode(
            {
                "page": "assets",
                "tab": "outlook",
                "data": "vibration",
                "monitor_asset": asset,
                "acq_forecast_feature": "feature.Horizontal_vibration_signals.rms",
                "acq_forecast_count": 30,
            }
        )
    )
    page.get_by_label("관리 기준 (선택)").fill("4")
    page.get_by_label("종료 기준 (선택)").fill("6")
    page.get_by_role("button", name="계산하기").click()
    expect(page.get_by_text("조건부 잔여수명(RUL)").first).to_be_visible(timeout=120_000)
    briefing = page.get_by_role("button", name="해설 만들기")
    if briefing.count():
        briefing.first.click()
        expect(page.locator("p.summary").first).to_be_visible(timeout=AI_TIMEOUT)
    _top(page.get_by_role("heading", name="기준 도달 전망").first)
    _shot(page, out, "07-outlook.png", frames)
    _gif(frames, out / "walkthrough.gif")
    options = page.request.get(
        base + "/api/v1/forecast/options?" + urlencode({"asset_id": asset})
    ).json()
    acquired = options["acquisition"]
    _record(
        out,
        "models",
        base,
        {
            "asset": asset,
            "measurements": {
                "first": acquired["first"],
                "last": acquired["last"],
                "count": acquired["count"],
            },
            "ai_display": explained,
            "human_decision": "illustrative inspect, not maintenance execution",
        },
        frames,
    )


def capture_csv(page: Any, base: str, out: Path, csv: Path) -> None:
    """A CSV without timezone registered through the Web, then the change it shows."""
    from playwright.sync_api import expect

    frames: list[Path] = []
    page.goto(base + "/web/?page=system&section=connections")
    page.locator("input[aria-labelledby=csv-file-label]").set_input_files(str(csv))
    expect(page.get_by_label("시각의 시간대 (파일에 시간대가 없음)")).to_be_visible()
    page.get_by_label("설비 이름·번호").fill("P-201 냉각수 펌프")
    for column, unit in (
        ("current_a", "A"),
        ("motor_temp_c", "°C"),
        ("vibration_mm_s", "mm/s"),
        ("pressure_bar", "bar"),
    ):
        page.get_by_label(column + " 단위").fill(unit)
    _top(page.get_by_role("heading", name="파일 미리보기"))
    _shot(page, out, "01-register.png", frames)
    page.get_by_role("button", name="서버에서 점검 (저장 안 함)").click()
    save = page.get_by_role("button", name="등록하고 이력 저장")
    expect(save).to_be_enabled(timeout=60_000)
    save.click()
    expect(page.get_by_role("link", name="설비 화면에서 신호 보기 →")).to_be_visible(
        timeout=120_000
    )

    page.goto(base + "/web/")
    attention = page.get_by_role("region", name="확인이 필요한 설비")
    expect(attention).to_contain_text("기준 구간에서 크게 벗어남", timeout=60_000)
    _shot(page, out, "02-attention.png", frames)
    attention.get_by_role("link", name="기준 구간 이탈 보기").first.click()
    expect(page.get_by_text("기준에서 크게 벗어난 구간").first).to_be_visible(timeout=60_000)
    _top(page.get_by_role("heading", name="기준 구간 이탈"))
    _shot(page, out, "03-departure.png", frames)
    page.get_by_role("link", name="상태 요약").click()
    expect(page.get_by_role("heading", name="기록 현황")).to_be_visible(timeout=30_000)
    _shot(page, out, "04-summary.png", frames)
    page.get_by_role("navigation", name="설비 화면").get_by_role("link", name="상태 전망").click()
    page.locator("#projection-channel").select_option("vibration_mm_s")
    page.get_by_label("관리 기준 (선택)").fill("6")
    page.get_by_label("종료 기준 (선택)").fill("7")
    page.get_by_role("button", name="계산하기", exact=True).click()
    expect(page.get_by_role("heading", name="결과", exact=True)).to_be_visible(timeout=120_000)
    _top(page.get_by_role("heading", name="기준 도달 전망"))
    _shot(page, out, "05-outlook.png", frames)
    page.get_by_role("button", name="검토 요청", exact=True).click()
    link = page.get_by_role("link", name="정비 검토함에서 보기 →")
    expect(link).to_be_visible(timeout=60_000)
    link.click()
    detail = page.get_by_role("region", name="고른 검토 항목")
    detail.get_by_role("radio", name="계속 관찰").check()
    detail.get_by_text("판단 이유 함께 남기기 (선택)").click()
    detail.get_by_label("판단 이유 (선택)").fill(
        "캡처용 예시 판단: 합성 펌프 기록의 변화와 전망을 검토하고 계속 관찰한다고 가정합니다."
    )
    detail.get_by_role("button", name="확인함으로 표시").click()
    expect(detail).to_contain_text("현재 판단 · 계속 관찰")
    detail.get_by_role("button", name="검토 종료", exact=True).click()
    detail.get_by_role("button", name="종료하기", exact=True).click()
    expect(detail).to_contain_text("검토가 종료되어 기록을 더 남길 수 없습니다.")
    page.reload()
    expect(detail).to_contain_text("캡처용 예시 판단")
    _top(detail)
    _shot(page, out, "06-review.png", frames)
    _gif(frames, out / "walkthrough.gif")
    _record(
        out,
        "csv",
        base,
        {
            "input": "tools/assets/pump_csv.py (synthetic, no timezone)",
            "input_sha256": hashlib.sha256(csv.read_bytes()).hexdigest(),
            "human_decision": "illustrative observe, not maintenance execution",
        },
        frames,
    )


def capture_live(page: Any, base: str, out: Path) -> None:
    """The local OPC UA example: a three-phase motor received live in its own workspace."""
    from playwright.sync_api import expect

    frames: list[Path] = []
    page.goto(base + "/web/?page=system&section=connections")
    sample = page.get_by_role("region", name="예시로 둘러보기")
    if sample.get_by_role("button", name="예시 시작").count():
        sample.get_by_role("button", name="예시 시작").click()
    opened = sample.get_by_role("link", name="예시 화면 열기 (새 탭)")
    expect(opened).to_be_visible(timeout=180_000)
    url = opened.get_attribute("href").split("?", 1)[0]
    page.goto(url + "?page=system&section=connections")
    expect(page.get_by_role("heading", name="등록한 연결")).to_be_visible(timeout=60_000)
    time.sleep(8)
    _top(page.get_by_role("heading", name="등록한 연결"))
    _shot(page, out, "01-connection.png", frames)
    page.goto(url)
    page.wait_for_load_state("networkidle")
    time.sleep(4)
    _shot(page, out, "02-monitor.png", frames)
    page.get_by_role("link", name="설비·신호").click()
    page.get_by_role("link").filter(has_text="마지막").first.click()
    page.get_by_role("link", name="신호", exact=True).click()
    time.sleep(6)
    _shot(page, out, "03-signals.png", frames)
    _gif(frames, out / "walkthrough.gif")
    _record(
        out, "live", base, {"input": "local OPC UA example (synthetic three-phase motor)"}, frames
    )
    page.goto(base + "/web/?page=system&section=connections")
    sample = page.get_by_role("region", name="예시로 둘러보기")
    sample.get_by_role("button", name="예시 종료", exact=True).click()
    sample.get_by_role("button", name="종료하기", exact=True).click()
    expect(sample.get_by_role("button", name="예시 시작", exact=True)).to_be_visible(timeout=60_000)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("use_case", choices=("models", "csv", "live"))
    parser.add_argument("--base", required=True)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--asset", default="Bearing1_1")
    args = parser.parse_args()
    out = ROOT / "assets" / args.use_case
    out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT, locale="ko-KR")
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        if args.use_case == "models":
            capture_models(page, args.base, out, args.asset)
        elif args.use_case == "csv":
            if args.csv is None:
                parser.error("csv needs --csv")
            capture_csv(page, args.base, out, args.csv)
        else:
            capture_live(page, args.base, out)
        assert not errors, errors
        browser.close()


if __name__ == "__main__":
    main()
