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
    expect(
        review.get_by_role("button", name="검토 요청", exact=True).or_(
            review.get_by_role("link", name="정비 검토함에서 보기")
        )
    ).to_be_visible()
    if review.get_by_role("button", name="검토 요청", exact=True).count():
        review.get_by_role("button", name="검토 요청", exact=True).click()
    review.get_by_role("link", name="정비 검토함에서 보기").click()
    detail = page.get_by_role("region", name="고른 검토 항목")
    expect(detail.locator(".badge")).to_be_visible()
    if detail.get_by_role("button", name="확인함으로 표시").count():
        detail.get_by_role("radio", name="계속 관찰").check()
        detail.get_by_role("button", name="확인함으로 표시").click()
        expect(detail.locator(".badge")).to_have_text("확인함")
    if detail.get_by_role("button", name="검토 종료", exact=True).count():
        detail.get_by_role("button", name="검토 종료", exact=True).click()
        detail.get_by_role("button", name="종료하기", exact=True).click()
    # The stored close shows in the status badge; the confirmation hides the button at once.
    expect(detail.locator(".badge")).to_have_text("검토 종료")
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
