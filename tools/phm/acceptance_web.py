"""Task-based Operations Web interactions shared by opt-in recorded-data acceptance runs."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode


def open_model(page: Any, url: str, binding: str) -> Any:
    from playwright.sync_api import expect

    page.goto(
        url
        + "?"
        + urlencode(
            {"page": "assets", "tab": "anomaly", "method": "model", "model_binding": binding}
        )
    )
    expect(page.get_by_role("heading", name="모델 이상 점수")).to_be_visible(timeout=30_000)
    return page.get_by_role("region", name="AI 해설")


def review_explained_result(
    page: Any, panel: Any, checks: Any, suffix: str, *, window: bool
) -> dict[str, Any]:
    from playwright.sync_api import expect

    from tools.phm.acceptance_common import check_explanation

    expect(
        panel.locator("p.summary").or_(panel.get_by_role("button", name="해설 만들기", exact=True))
    ).to_be_visible(timeout=30_000)
    if panel.get_by_role("button", name="해설 만들기", exact=True).count():
        panel.get_by_role("button", name="해설 만들기", exact=True).click()
    expect(panel.locator("p.summary")).not_to_be_empty(timeout=180_000)
    answer = check_explanation(checks, suffix, panel, window=window)
    answer["model_url"] = page.url
    review = page.get_by_role("region", name="사람 검토")
    if review.get_by_role("button", name="검토 요청", exact=True).count():
        review.get_by_role("button", name="검토 요청", exact=True).click()
    review.get_by_role("link", name="정비 검토함에서 보기").click()
    detail = page.get_by_role("region", name="고른 검토 항목")
    if detail.get_by_role("button", name="메모 남기기").count():
        detail.get_by_label("메모 (최대 1000자)").fill("원본 측정과 선택 구간을 확인함")
        detail.get_by_role("button", name="메모 남기기").click()
        expect(detail).to_contain_text("검토 기록을 남겼습니다")
    if detail.get_by_role("button", name="확인함으로 표시").count():
        detail.get_by_role("button", name="확인함으로 표시").click()
        expect(detail.get_by_role("button", name="검토 종료", exact=True)).to_be_visible()
    if detail.get_by_role("button", name="검토 종료", exact=True).count():
        detail.get_by_role("button", name="검토 종료", exact=True).click()
        detail.get_by_role("button", name="종료하기", exact=True).click()
    expect(detail.get_by_role("button", name="메모 남기기")).to_have_count(0)
    expect(detail).to_contain_text("검토 종료")
    answer["review_url"] = page.url
    return answer


def expect_saved_review(page: Any, answer: dict[str, Any]) -> None:
    from playwright.sync_api import expect

    page.goto(answer["model_url"])
    expect(page.get_by_role("region", name="AI 해설").locator("p.summary")).to_have_text(
        answer["text"], timeout=30_000
    )
    page.goto(answer["review_url"])
    expect(page.get_by_role("region", name="고른 검토 항목")).to_contain_text("검토 종료")
