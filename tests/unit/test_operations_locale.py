from datetime import UTC, datetime

import pytest

from industrial_phm.application.operations_monitor import OperationsMonitorStatus
from industrial_phm.presentation.operations_locale import (
    OperationsLocale,
    OperationsPageId,
    format_operations_age,
    format_operations_utc,
    operations_messages,
    operations_page_label,
    operations_status_label,
    operations_text,
    resolve_operations_locale,
)


def test_locale_resolver_prefers_explicit_locale_and_normalizes_language_tags() -> None:
    assert (
        resolve_operations_locale(
            preferred="ko_KR.UTF-8",
            browser_locale="en-US",
            environment_locale="en_US.UTF-8",
        )
        == OperationsLocale.KO_KR
    )
    assert resolve_operations_locale(browser_locale="ko") == OperationsLocale.KO_KR
    assert resolve_operations_locale(environment_locale="en_GB.UTF-8") == OperationsLocale.EN_US
    assert resolve_operations_locale(browser_locale="fr-FR") == OperationsLocale.EN_US


def test_locale_resource_keys_match_across_supported_locales() -> None:
    assert operations_messages("en-US").keys() == operations_messages("ko-KR").keys()


def test_supplemental_product_copy_is_localized_with_stable_placeholders() -> None:
    assert operations_text("setup.connect_first_source", "en-US") == "Connect your first data source"
    assert operations_text("setup.connect_first_source", "ko-KR") == "첫 데이터 source 연결"
    assert operations_text("monitor.inspect_channel", "ko-KR").format(channel="vibration_x") == (
        "vibration_x 확인"
    )


def test_page_identity_is_locale_neutral_while_display_label_changes() -> None:
    assert OperationsPageId.MONITOR.value == "monitor"
    assert operations_page_label(OperationsPageId.MONITOR, "en-US") == "Monitor"
    assert operations_page_label(OperationsPageId.MONITOR, "ko-KR") == "관제"
    assert operations_page_label("maintenance", "ko-KR") == "정비 검토"


def test_status_and_first_run_copy_are_localized_without_changing_status_identity() -> None:
    status = OperationsMonitorStatus.NEEDS_ATTENTION

    assert status.value == "needs-attention"
    assert operations_status_label(status, "en-US") == "Needs attention"
    assert operations_status_label(status, "ko-KR") == "확인 필요"
    assert operations_text("first_run.sample.title", "ko-KR") == "샘플 데이터로 둘러보기"


def test_utc_storage_semantics_are_preserved_while_age_copy_is_localized() -> None:
    observed = datetime(2026, 10, 7, 8, 0, tzinfo=UTC)
    now = datetime(2026, 10, 7, 8, 5, tzinfo=UTC)

    assert format_operations_utc(observed, "ko-KR").endswith(" UTC")
    assert format_operations_utc(observed, "en-US").endswith(" UTC")
    assert format_operations_age(observed, now=now, locale="en-US") == "5m ago"
    assert format_operations_age(observed, now=now, locale="ko-KR") == "5m 전"


def test_unknown_resource_or_locale_fails_closed() -> None:
    with pytest.raises(KeyError, match="unknown Operations text key"):
        operations_text("missing", "en-US")
    with pytest.raises(ValueError, match="unsupported Operations locale"):
        operations_page_label("monitor", "fr-FR")
