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

_CAPABILITY_LABELS: Final = {
    OperationsLocale.EN_US: {
        "three-phase-unbalance-v1": "Three-phase unbalance",
        "field-vibration-statistical-features-v1": "Vibration features",
    },
    OperationsLocale.KO_KR: {
        "three-phase-unbalance-v1": "3상 불평형",
        "field-vibration-statistical-features-v1": "진동 feature",
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
        "common.all": "All",
        "common.asset": "Asset",
        "common.source": "Source",
        "common.point": "Point",
        "common.queue": "Queue",
        "common.status": "Status",
        "common.data_quality": "Data quality",
        "common.review": "Review",
        "common.completed": "Completed",
        "common.observed": "Observed",
        "common.analysis_run": "Analysis run",
        "common.capability": "Capability",
        "common.evidence": "Evidence",
        "common.finding": "Finding",
        "common.review_updated": "Review updated",
        "common.not_requested": "Not requested",
        "common.open": "Open",
        "common.acknowledged": "Acknowledged",
        "common.closed": "Closed",
        "common.unresolved": "Unresolved",
        "common.not_configured": "Not configured",
        "asset.title": "Asset",
        "asset.view": "View",
        "asset.section.overview": "Overview",
        "asset.section.signals": "Signals",
        "asset.section.analysis": "Analysis",
        "asset.section.events": "Events",
        "asset.section.maintenance": "Maintenance review",
        "asset.data_status": "Data status",
        "asset.last_data": "Last data",
        "asset.sources": "Sources",
        "asset.latest_analysis": "Latest analysis",
        "asset.open_reviews": "Open reviews",
        "asset.history": "History",
        "asset.analysis": "Analysis",
        "asset.reviews": "Reviews",
        "asset.events": "Events",
        "asset.maintenance": "Maintenance review",
        "asset.no_history": "No stored history",
        "asset.no_source_mapping": "No active source mapping is recorded for this asset.",
        "asset.no_analysis_attempt": "No analysis attempt has been recorded for this asset yet.",
        "asset.no_analysis_evidence": "No analysis evidence has been recorded for this asset yet.",
        "asset.no_event": "No operational event is recorded for this asset.",
        "asset.no_maintenance_review": "No maintenance review is recorded for this asset.",
        "investigation.title": "Investigation",
        "investigation.evidence_identity": "Evidence identity",
        "maintenance.title": "Maintenance review",
        "maintenance.requested": "Requested",
        "maintenance.last_activity": "Last activity",
        "maintenance.notes": "Notes",
        "maintenance.reviewed_evidence": "Reviewed evidence",
        "maintenance.review_timeline": "Review timeline",
        "maintenance.review_identity": "Review identity",
        "maintenance.no_review_activity": "No review activity has been recorded yet.",
        "setup.data_sources": "Data sources",
        "setup.no_sources": "No data source is configured yet. Connect one below to begin.",
        "setup.data_source": "Data source",
        "setup.type": "Type",
        "setup.use": "Use",
        "setup.asset": "Asset",
        "setup.point": "Point",
        "setup.meaning": "Meaning",
        "setup.data_age_limit": "Data age limit",
        "setup.connection_target": "Connection target",
        "setup.signal_mapping": "Signal mapping & meaning",
        "setup.signal": "Signal",
        "setup.source_locator": "Source locator",
        "setup.observed_property": "Observed property",
        "setup.scope": "Scope",
        "setup.statistic": "Statistic",
        "setup.unit": "Unit",
        "setup.version": "Version",
        "setup.no_signal_mapping": "No signal mapping recorded.",
        "setup.collection_request": "Collection request",
        "setup.not_enabled": "Not enabled",
        "setup.enabled": "Enabled",
        "setup.paused": "Paused",
        "setup.needs_attention": "Needs attention",
        "setup.not_applicable": "Not applicable",
        "system.runtime": "Runtime",
        "system.errors": "Current application errors",
        "system.no_errors": "No current state-read error is recorded.",
        "system.detected": "Detected",
        "system.area": "Area",
        "system.detail": "Detail",
        "system.advanced_diagnostics": "Advanced diagnostics",
        "system.state": "State",
        "system.path": "Path",
        "monitor.operations_pages": "Operations pages",
        "monitor.refresh": "Refresh",
        "monitor.refresh_aria": "Refresh observations",
        "monitor.eyebrow": "OPERATIONS / MONITOR",
        "monitor.choose_asset": "Choose an asset",
        "monitor.choose_asset_aria": "Choose asset",
        "monitor.no_source_context": "No source context",
        "monitor.source_flow": "Source flow",
        "monitor.source_receipt": "SOURCE RECEIPT",
        "monitor.no_receive_timestamp": "No receive timestamp",
        "monitor.status_at": "Status at",
        "monitor.manual_snapshot": "Manual snapshot · Refresh to reassess",
        "monitor.signal_explorer": "Signal explorer",
        "monitor.signals": "Signals",
        "monitor.find_signal": "Find a signal",
        "monitor.select_signal": "Select a signal to inspect",
        "monitor.compare_help": "Use + to compare · up to 6 signals",
        "monitor.no_matching_signals": "No matching signals. Try a channel or measurement name.",
        "monitor.observation_workspace": "OBSERVATION WORKSPACE",
        "monitor.signal_comparison": "Signal comparison",
        "monitor.event_time_range": "Event-time range",
        "monitor.channel_scope": (
            "Channel scope: all recorded sources/points · origins remain separate"
        ),
        "monitor.unit_unknown": "unit unknown",
        "monitor.quality": "Quality",
        "monitor.unknown": "unknown",
        "monitor.event_time_unavailable": "Event time unavailable",
        "monitor.stored_event_time": "STORED EVENT TIME · UTC",
        "monitor.no_event_time_window": "No event-time window",
        "monitor.recorded_signal_comparison": "Recorded signal comparison",
        "monitor.chart_caption": (
            "Mean · min/max · top marks: analysis windows (arrow keys move) · amber: exclusions"
        ),
        "monitor.bucket_note": "Bucket summaries are not synchronized raw samples",
        "monitor.snapshot": "Snapshot",
        "monitor.inspect_signal": "Inspect selected signal",
        "monitor.analysis_evidence": "Analysis evidence",
        "monitor.analysis_evidence_region": "Analysis evidence in this window",
        "monitor.no_analysis_overlap": "No loaded analysis overlaps this window.",
        "monitor.needs_inspection": "Needs inspection",
        "monitor.no_inspection_items": "No recorded inspection items for this context.",
        "monitor.close_asset_picker": "Close asset picker",
        "monitor.search_assets": "Search assets",
        "monitor.no_stored_observations": (
            "No stored observations in this window. Select an available signal or another range."
        ),
        "monitor.stored_bucket_summaries": "Stored bucket summaries",
        "monitor.no_usable_bucket_values": "No usable bucket values",
        "monitor.no_observations_bucket": "No observations in this bucket.",
        "monitor.no_usable_value": "No usable value",
        "monitor.observed": "Observed",
        "monitor.retry_refresh": "Retry refresh",
        "monitor.update_timeout": "The view did not finish updating. Refresh to retry.",
        "monitor.update_failed": "The update failed. Refresh to retry.",
        "monitor.selection_unavailable": "This selection is unavailable. Refresh the view.",
        "monitor.future_timestamp": "Future timestamp",
        "monitor.no_receipt_recorded": "No receipt recorded",
        "monitor.not_recorded": "Not recorded",
        "monitor.ago": "ago",
        "monitor.in_future": "in future",
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
            "준비된 FILE 데이터 또는 실시간 OPC UA source를 연결하고 "
            "신호와 데이터 수신을 확인합니다."
        ),
        "first_run.resume": (
            "이미 설정된 작업공간은 이 첫 실행 화면을 건너뛰고 관제 화면에서 바로 재개합니다."
        ),
        "first_run.sample.ready": "샘플 관제가 준비되었습니다",
        "first_run.sample.isolation": (
            "샘플은 별도 작업공간에서 실행되며 실제 Operations 작업공간에 "
            "synthetic 관측값을 기록하지 않습니다."
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
        "common.all": "전체",
        "common.asset": "설비",
        "common.source": "Source",
        "common.point": "측정 지점",
        "common.queue": "대기열",
        "common.status": "상태",
        "common.data_quality": "데이터 품질",
        "common.review": "검토",
        "common.completed": "완료",
        "common.observed": "관측 구간",
        "common.analysis_run": "분석 실행",
        "common.capability": "분석 capability",
        "common.evidence": "근거",
        "common.finding": "검토 항목",
        "common.review_updated": "검토 갱신",
        "common.not_requested": "요청 안 됨",
        "common.open": "열림",
        "common.acknowledged": "확인됨",
        "common.closed": "종료됨",
        "common.unresolved": "미확인",
        "common.not_configured": "설정 안 됨",
        "asset.title": "설비",
        "asset.view": "보기",
        "asset.section.overview": "개요",
        "asset.section.signals": "신호",
        "asset.section.analysis": "분석",
        "asset.section.events": "이벤트",
        "asset.section.maintenance": "정비 검토",
        "asset.data_status": "데이터 상태",
        "asset.last_data": "최근 데이터",
        "asset.sources": "Source",
        "asset.latest_analysis": "최근 분석",
        "asset.open_reviews": "열린 검토",
        "asset.history": "이력",
        "asset.analysis": "분석",
        "asset.reviews": "검토",
        "asset.events": "이벤트",
        "asset.maintenance": "정비 검토",
        "asset.no_history": "저장된 이력이 없습니다",
        "asset.no_source_mapping": "이 설비에 기록된 활성 source mapping이 없습니다.",
        "asset.no_analysis_attempt": "이 설비에 기록된 분석 시도가 아직 없습니다.",
        "asset.no_analysis_evidence": "이 설비에 기록된 분석 근거가 아직 없습니다.",
        "asset.no_event": "이 설비에 기록된 운영 이벤트가 없습니다.",
        "asset.no_maintenance_review": "이 설비에 기록된 정비 검토가 없습니다.",
        "investigation.title": "분석 근거",
        "investigation.evidence_identity": "근거 식별 정보",
        "maintenance.title": "정비 검토",
        "maintenance.requested": "요청 시각",
        "maintenance.last_activity": "최근 활동",
        "maintenance.notes": "메모",
        "maintenance.reviewed_evidence": "검토 대상 근거",
        "maintenance.review_timeline": "검토 이력",
        "maintenance.review_identity": "검토 식별 정보",
        "maintenance.no_review_activity": "기록된 검토 활동이 아직 없습니다.",
        "setup.data_sources": "데이터 source",
        "setup.no_sources": "설정된 데이터 source가 없습니다. 아래에서 연결을 시작하세요.",
        "setup.data_source": "데이터 source",
        "setup.type": "유형",
        "setup.use": "사용 상태",
        "setup.asset": "설비",
        "setup.point": "측정 지점",
        "setup.meaning": "측정 의미",
        "setup.data_age_limit": "데이터 최대 경과 시간",
        "setup.connection_target": "연결 대상",
        "setup.signal_mapping": "신호 mapping 및 의미",
        "setup.signal": "신호",
        "setup.source_locator": "Source 위치",
        "setup.observed_property": "관측 속성",
        "setup.scope": "범위",
        "setup.statistic": "통계량",
        "setup.unit": "단위",
        "setup.version": "버전",
        "setup.no_signal_mapping": "기록된 신호 mapping이 없습니다.",
        "setup.collection_request": "수집 요청",
        "setup.not_enabled": "활성화 안 됨",
        "setup.enabled": "활성화됨",
        "setup.paused": "일시 중지",
        "setup.needs_attention": "확인 필요",
        "setup.not_applicable": "해당 없음",
        "system.runtime": "Runtime",
        "system.errors": "현재 애플리케이션 오류",
        "system.no_errors": "현재 기록된 상태 읽기 오류가 없습니다.",
        "system.detected": "감지 시각",
        "system.area": "영역",
        "system.detail": "상세",
        "system.advanced_diagnostics": "고급 진단",
        "system.state": "상태",
        "system.path": "경로",
        "monitor.operations_pages": "Operations 페이지",
        "monitor.refresh": "새로고침",
        "monitor.refresh_aria": "관측값 새로고침",
        "monitor.eyebrow": "OPERATIONS / 관제",
        "monitor.choose_asset": "설비 선택",
        "monitor.choose_asset_aria": "설비 선택",
        "monitor.no_source_context": "Source 정보 없음",
        "monitor.source_flow": "데이터 수신",
        "monitor.source_receipt": "최근 수신",
        "monitor.no_receive_timestamp": "수신 시각 기록 없음",
        "monitor.status_at": "상태 기준 시각",
        "monitor.manual_snapshot": "수동 snapshot · 새로고침하면 다시 평가합니다",
        "monitor.signal_explorer": "신호 탐색",
        "monitor.signals": "신호",
        "monitor.find_signal": "신호 검색",
        "monitor.select_signal": "확인할 신호를 선택하세요",
        "monitor.compare_help": "+로 비교 · 최대 6개 신호",
        "monitor.no_matching_signals": (
            "일치하는 신호가 없습니다. 채널 또는 측정 이름을 검색하세요."
        ),
        "monitor.observation_workspace": "관측 WORKSPACE",
        "monitor.signal_comparison": "신호 비교",
        "monitor.event_time_range": "이벤트 시각 범위",
        "monitor.channel_scope": "채널 범위: 기록된 모든 source/point · origin은 분리 유지",
        "monitor.unit_unknown": "단위 미확인",
        "monitor.quality": "품질",
        "monitor.unknown": "미확인",
        "monitor.event_time_unavailable": "이벤트 시각 없음",
        "monitor.stored_event_time": "저장 이벤트 시각 · UTC",
        "monitor.no_event_time_window": "이벤트 시각 구간 없음",
        "monitor.recorded_signal_comparison": "기록 신호 비교",
        "monitor.chart_caption": (
            "평균 · 최소/최대 · 상단 표시: 분석 구간(방향키 이동) · 황색: 제외 구간"
        ),
        "monitor.bucket_note": "Bucket 요약은 동기화된 raw sample이 아닙니다",
        "monitor.snapshot": "Snapshot",
        "monitor.inspect_signal": "선택 신호 자세히 보기",
        "monitor.analysis_evidence": "분석 근거",
        "monitor.analysis_evidence_region": "현재 구간의 분석 근거",
        "monitor.no_analysis_overlap": "현재 구간과 겹치는 분석 근거가 없습니다.",
        "monitor.needs_inspection": "확인 필요",
        "monitor.no_inspection_items": "현재 맥락에 기록된 확인 항목이 없습니다.",
        "monitor.close_asset_picker": "설비 선택 닫기",
        "monitor.search_assets": "설비 검색",
        "monitor.no_stored_observations": (
            "현재 구간에 저장된 관측값이 없습니다. 사용 가능한 신호나 다른 범위를 선택하세요."
        ),
        "monitor.stored_bucket_summaries": "저장 bucket 요약",
        "monitor.no_usable_bucket_values": "사용 가능한 bucket 값 없음",
        "monitor.no_observations_bucket": "이 bucket에는 관측값이 없습니다.",
        "monitor.no_usable_value": "사용 가능한 값 없음",
        "monitor.observed": "관측",
        "monitor.retry_refresh": "새로고침 재시도",
        "monitor.update_timeout": "화면 갱신이 끝나지 않았습니다. 새로고침해 다시 시도하세요.",
        "monitor.update_failed": "갱신하지 못했습니다. 새로고침해 다시 시도하세요.",
        "monitor.selection_unavailable": "현재 선택을 사용할 수 없습니다. 화면을 새로고침하세요.",
        "monitor.future_timestamp": "미래 시각",
        "monitor.no_receipt_recorded": "수신 기록 없음",
        "monitor.not_recorded": "기록 없음",
        "monitor.ago": "전",
        "monitor.in_future": "후",
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
    environment = (
        os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG")
    )
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


def operations_capability_label(
    capability_id: str,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if not isinstance(capability_id, str) or not capability_id:
        raise ValueError("capability_id must be a non-empty string")
    resolved = _require_locale(locale)
    return _CAPABILITY_LABELS[resolved].get(capability_id, capability_id)


def operations_messages(
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> dict[str, str]:
    """Return a copy safe to pass to the browser presentation boundary."""

    return dict(_TEXT[_require_locale(locale)])


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
        return utc_value.strftime("%Y. %m. %d. %H:%M:%S UTC")
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
