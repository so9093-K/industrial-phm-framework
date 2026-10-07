"""Operations product locale and stable display identity.

Domain identifiers, route identifiers, timestamps, and evidence remain locale-neutral.
This module translates only presentation-layer labels and formatting.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from enum import StrEnum
from numbers import Real
from typing import Final

from industrial_phm.application.operations_monitor import OperationsMonitorStatus


class OperationsLocale(StrEnum):
    EN_US = "en-US"
    KO_KR = "ko-KR"


class OperationsPageId(StrEnum):
    MONITOR = "monitor"
    ASSETS = "assets"
    INVESTIGATIONS = "investigations"
    MAINTENANCE = "maintenance"
    SYSTEM = "system"
    SETUP = "setup"


OPERATIONS_PAGE_IDS: Final = tuple(OperationsPageId)
DEFAULT_OPERATIONS_LOCALE = OperationsLocale.EN_US

_PAGE_LABELS: Final = {
    OperationsLocale.EN_US: {
        OperationsPageId.MONITOR: "Monitor",
        OperationsPageId.ASSETS: "Assets",
        OperationsPageId.INVESTIGATIONS: "Investigations",
        OperationsPageId.MAINTENANCE: "Maintenance review",
        OperationsPageId.SYSTEM: "System",
        OperationsPageId.SETUP: "Data connection",
    },
    OperationsLocale.KO_KR: {
        OperationsPageId.MONITOR: "관제",
        OperationsPageId.ASSETS: "설비",
        OperationsPageId.INVESTIGATIONS: "분석 근거",
        OperationsPageId.MAINTENANCE: "정비 검토",
        OperationsPageId.SYSTEM: "시스템",
        OperationsPageId.SETUP: "데이터 연결",
    },
}

_STATUS_LABELS: Final = {
    OperationsLocale.EN_US: {
        OperationsMonitorStatus.RUNNING: "Receiving",
        OperationsMonitorStatus.WAITING: "Waiting for data",
        OperationsMonitorStatus.DELAYED: "Delayed",
        OperationsMonitorStatus.STOPPED: "Stopped",
        OperationsMonitorStatus.NEEDS_ATTENTION: "Needs attention",
        OperationsMonitorStatus.ERROR: "Error",
        OperationsMonitorStatus.UNAVAILABLE: "Unavailable",
    },
    OperationsLocale.KO_KR: {
        OperationsMonitorStatus.RUNNING: "수신 중",
        OperationsMonitorStatus.WAITING: "데이터 대기 중",
        OperationsMonitorStatus.DELAYED: "수신 지연",
        OperationsMonitorStatus.STOPPED: "중지됨",
        OperationsMonitorStatus.NEEDS_ATTENTION: "확인 필요",
        OperationsMonitorStatus.ERROR: "오류",
        OperationsMonitorStatus.UNAVAILABLE: "사용 불가",
    },
}

_TEXT: Final = {
    OperationsLocale.EN_US: {
        "locale.label": "Language",
        "locale.en-US": "English",
        "locale.ko-KR": "한국어",
        "first_run.title": "Industrial PHM",
        "first_run.intro": (
            "Choose how to begin. You can explore the Operations path without learning "
            "internal workspace or process commands."
        ),
        "first_run.sample.title": "Explore with sample data",
        "first_run.sample.detail": (
            "Start the existing synthetic three-phase demo in a separate workspace and "
            "open its Monitor."
        ),
        "first_run.real.title": "Connect real data",
        "first_run.real.detail": (
            "Connect a prepared FILE source or a live OPC UA source, then verify signals "
            "and data flow."
        ),
        "first_run.resume": (
            "An existing configured workspace skips this first-run choice and resumes "
            "directly in Monitor."
        ),
        "first_run.sample.ready": "Sample Operations is ready",
        "first_run.sample.isolation": (
            "The sample runs in an isolated workspace and does not write synthetic "
            "observations into your real Operations workspace."
        ),
        "first_run.sample.open": "Open sample Monitor",
        "first_run.sample.stop": "Stop sample",
        "first_run.real.open": "Connect real data",
        "first_run.sample.error": "Sample could not start",
        "setup.open_monitor": "Open Monitor",
        "setup.source": "Data source",
        "setup.enable": "Enable source",
        "setup.pause": "Pause source",
        "setup.start_collection": "Start collection",
        "setup.stop_collection": "Stop collection",
        "common.not_recorded": "Not recorded",
        "common.time_not_comparable": "Time not comparable",
        "common.future_timestamp": "Future timestamp",
    },
    OperationsLocale.KO_KR: {
        "locale.label": "언어",
        "locale.en-US": "English",
        "locale.ko-KR": "한국어",
        "first_run.title": "Industrial PHM",
        "first_run.intro": (
            "내부 작업공간이나 프로세스 명령을 알지 않아도 시작할 수 있습니다. "
            "샘플을 둘러보거나 실제 데이터를 연결하세요."
        ),
        "first_run.sample.title": "샘플 데이터로 둘러보기",
        "first_run.sample.detail": (
            "기존 synthetic 3상 demo를 별도 작업공간에서 실행하고 관제 화면을 엽니다."
        ),
        "first_run.real.title": "실제 데이터 연결",
        "first_run.real.detail": (
            "준비된 FILE 데이터 또는 실시간 OPC UA source를 연결하고 신호와 데이터 수신을 확인합니다."
        ),
        "first_run.resume": (
            "이미 설정된 작업공간은 이 첫 실행 화면을 건너뛰고 관제 화면에서 바로 재개합니다."
        ),
        "first_run.sample.ready": "샘플 관제가 준비되었습니다",
        "first_run.sample.isolation": (
            "샘플은 별도 작업공간에서 실행되며 실제 Operations 작업공간에 synthetic 관측값을 기록하지 않습니다."
        ),
        "first_run.sample.open": "샘플 관제 열기",
        "first_run.sample.stop": "샘플 중지",
        "first_run.real.open": "실제 데이터 연결",
        "first_run.sample.error": "샘플을 시작하지 못했습니다",
        "setup.open_monitor": "관제 열기",
        "setup.source": "데이터 source",
        "setup.enable": "Source 활성화",
        "setup.pause": "Source 일시 중지",
        "setup.start_collection": "수집 시작",
        "setup.stop_collection": "수집 중지",
        "common.not_recorded": "기록 없음",
        "common.time_not_comparable": "시간 비교 불가",
        "common.future_timestamp": "미래 시각",
    },
}


def normalize_operations_locale(value: str | OperationsLocale | None) -> OperationsLocale | None:
    if value is None:
        return None
    if isinstance(value, OperationsLocale):
        return value
    if not isinstance(value, str):
        raise ValueError("locale must be a string or OperationsLocale")
    normalized = value.strip().replace("_", "-").lower()
    if normalized == "ko" or normalized.startswith("ko-"):
        return OperationsLocale.KO_KR
    if normalized == "en" or normalized.startswith("en-"):
        return OperationsLocale.EN_US
    return None


def resolve_operations_locale(
    *,
    preferred: str | OperationsLocale | None = None,
    browser_locale: str | None = None,
    environment_locale: str | None = None,
) -> OperationsLocale:
    """Resolve product locale without changing any stored identity or timestamp semantics."""

    for candidate in (preferred, browser_locale, environment_locale):
        resolved = normalize_operations_locale(candidate)
        if resolved is not None:
            return resolved
    return DEFAULT_OPERATIONS_LOCALE


def resolve_environment_operations_locale() -> OperationsLocale:
    explicit = os.environ.get("INDUSTRIAL_PHM_LOCALE")
    environment = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG")
    return resolve_operations_locale(preferred=explicit, environment_locale=environment)


def operations_page_label(
    page: OperationsPageId | str,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    page_id = OperationsPageId(page)
    resolved = _require_locale(locale)
    return _PAGE_LABELS[resolved][page_id]


def operations_status_label(
    status: OperationsMonitorStatus,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if not isinstance(status, OperationsMonitorStatus):
        raise ValueError("status must be an OperationsMonitorStatus")
    return _STATUS_LABELS[_require_locale(locale)][status]


def operations_text(
    key: str,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if not isinstance(key, str) or not key:
        raise ValueError("key must be a non-empty string")
    resolved = _require_locale(locale)
    try:
        return _TEXT[resolved][key]
    except KeyError as error:
        raise KeyError(f"unknown Operations text key: {key}") from error


def format_operations_number(
    value: Real,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("value must be a real number")
    resolved = _require_locale(locale)
    rendered = f"{value:,.5g}"
    if resolved == OperationsLocale.KO_KR:
        return rendered
    return rendered


def format_operations_utc(
    value: datetime | None,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if value is None:
        return "—"
    resolved = _require_locale(locale)
    if value.utcoffset() is None:
        return operations_text("common.time_not_comparable", resolved)
    utc_value = value.astimezone(UTC)
    if resolved == OperationsLocale.KO_KR:
        return utc_value.strftime("%Y-%m-%d %H:%M:%S UTC")
    return utc_value.strftime("%Y-%m-%d %H:%M:%S UTC")


def format_operations_age(
    value: datetime | None,
    *,
    now: datetime,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    resolved = _require_locale(locale)
    if now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if value is None:
        return operations_text("common.not_recorded", resolved)
    if value.utcoffset() is None:
        return operations_text("common.time_not_comparable", resolved)
    seconds = (now - value).total_seconds()
    if seconds < 0:
        return operations_text("common.future_timestamp", resolved)
    if seconds < 60:
        amount = f"{seconds:.0f}s"
    elif seconds < 3600:
        amount = f"{seconds / 60:.0f}m"
    else:
        amount = f"{seconds / 3600:.0f}h"
    return f"{amount} 전" if resolved == OperationsLocale.KO_KR else f"{amount} ago"


def _require_locale(locale: OperationsLocale | str) -> OperationsLocale:
    resolved = normalize_operations_locale(locale)
    if resolved is None:
        raise ValueError(f"unsupported Operations locale: {locale}")
    return resolved
