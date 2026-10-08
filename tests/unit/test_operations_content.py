"""Localized Operations errors describe recoverable states without claiming asset safety."""

from html import escape

import pytest

from industrial_phm.presentation.operations_content import (
    operations_error_css,
    render_operations_error_html,
    render_operations_recovery_html,
)
from industrial_phm.presentation.operations_locale import operations_text

SCENARIOS = (
    "first_run.sample",
    "setup",
    "setup.diagnostic",
    "setup.mapping",
    "asset.workspace",
    "asset.analysis",
    "investigation.review",
    "maintenance",
)


@pytest.mark.parametrize("locale", ["en-US", "ko-KR"])
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_recovery_scenarios_render_all_localized_actions(scenario: str, locale: str) -> None:
    rendered = render_operations_recovery_html(
        scenario, technical_detail="source is unavailable", locale=locale
    )

    assert rendered.startswith('<section class="phm-error-content" role="alert">')
    for key in ("error.what_happened", "error.safety", "error.next_action"):
        assert operations_text(key, locale) in rendered
    for suffix in ("what", "safety", "next"):
        assert escape(operations_text(f"{scenario}.failure.{suffix}", locale)) in rendered
    assert operations_text("error.technical_detail", locale) in rendered
    assert "<details " in rendered
    assert "<code>source is unavailable</code>" in rendered
    assert rendered.endswith("</section>")


@pytest.mark.parametrize("locale", ["en-US", "ko-KR"])
def test_technical_details_are_escaped_and_hidden_by_default(locale: str) -> None:
    untrusted = '<script>alert("unsafe")</script> & <asset id="x">'
    result = render_operations_recovery_html("setup", technical_detail=untrusted, locale=locale)

    assert "<script>" not in result
    assert "<asset" not in result
    assert escape(untrusted) in result
    assert '<details class="phm-error-technical">' in result
    assert "<details open" not in result


def test_recovery_panel_has_no_technical_details_when_not_provided() -> None:
    content = render_operations_recovery_html("asset.workspace", locale="en-US")
    assert "<details" not in content
    assert "<code>" not in content


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("what_happened", ""),
        ("safety", "  "),
        ("next_action", " retry"),
        ("technical_detail", "  "),
    ],
)
def test_renderer_rejects_missing_or_untrimmed_content(field: str, value: str) -> None:
    args = {
        "what_happened": "An operation failed",
        "safety": "Result is not confirmed",
        "next_action": "Check the source status",
        "technical_detail": "Connection refused",
    }
    args[field] = value
    with pytest.raises(ValueError, match=field):
        render_operations_error_html(**args)


@pytest.mark.parametrize("scenario", ["", "monitor", "system", "setup.bad", " setup"])
def test_unknown_recovery_scenarios_fail_closed(scenario: str) -> None:
    with pytest.raises(ValueError, match="unsupported Operations recovery scenario"):
        render_operations_recovery_html(scenario)


def test_recovery_panel_uses_operations_theme_and_focusable_native_detail() -> None:
    css = operations_error_css()
    assert ".phm-error-content" in css
    assert "--phm-error" in css
    assert "--phm-text" in css
    assert ".phm-error-technical summary" in css
    assert "cursor: pointer" in css


def test_recovery_copy_does_not_infer_success_or_asset_health_from_an_error() -> None:
    for locale in ("en-US", "ko-KR"):
        assert operations_text("setup.failure.safety", locale)
        assert operations_text("investigation.review.failure.safety", locale)
        assert operations_text("asset.workspace.failure.safety", locale)
        assert operations_text("error.safety", locale) in {"Known state", "확인된 상태"}
