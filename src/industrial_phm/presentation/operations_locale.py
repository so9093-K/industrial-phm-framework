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
        "first_run.sample.workspace": "Sample workspace: `{workspace}`",
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
        "setup.collection.running": "Requested: Running",
        "setup.collection.stopped": "Requested: Stopped",
        "setup.data_flow_status": "Data flow confirmation",
        "setup.data_flow_confirmed": ("Data has been received for the currently enabled source."),
        "setup.data_flow_waiting": (
            "No data has been received for the current source yet. Run a bounded FILE "
            "diagnostic or start OPC UA collection, then refresh this status."
        ),
        "setup.refresh_data_flow": "Refresh data flow",
        "setup.observe_ready": "Data receipt is confirmed. Open Monitor to inspect it.",
        "setup.monitor_locked": (
            "Monitor becomes available after data is received for the current source."
        ),
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
        "system.status.running": "Running",
        "system.status.waiting": "Waiting",
        "system.status.delayed": "Delayed",
        "system.status.stopped": "Stopped",
        "system.status.needs_attention": "Needs attention",
        "system.status.error": "Error",
        "system.status.unavailable": "Unavailable",
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
        "first_run.sample.workspace": "샘플 workspace: `{workspace}`",
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
        "setup.collection.running": "요청: 수집 실행",
        "setup.collection.stopped": "요청: 수집 중지",
        "setup.data_flow_status": "데이터 수신 확인",
        "setup.data_flow_confirmed": "현재 활성화된 source에서 데이터 수신이 확인되었습니다.",
        "setup.data_flow_waiting": (
            "현재 source에서 아직 데이터 수신이 확인되지 않았습니다. FILE은 bounded diagnostic을 "
            "실행하고, OPC UA는 수집을 시작한 뒤 이 상태를 새로고침하세요."
        ),
        "setup.refresh_data_flow": "데이터 수신 새로고침",
        "setup.observe_ready": "데이터 수신이 확인되었습니다. 관제 화면에서 확인하세요.",
        "setup.monitor_locked": "현재 source에서 데이터가 수신되면 관제 화면을 열 수 있습니다.",
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
        "system.status.running": "실행 중",
        "system.status.waiting": "대기 중",
        "system.status.delayed": "지연",
        "system.status.stopped": "중지됨",
        "system.status.needs_attention": "확인 필요",
        "system.status.error": "오류",
        "system.status.unavailable": "사용 불가",
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


_PRODUCT_COPY: Final = {
    OperationsLocale.EN_US: {
        "common.name": "Name",
        "common.type": "Type",
        "common.signal": "Signal",
        "common.time_range": "Time range",
        "common.time": "Time",
        "common.value": "Value",
        "common.unit": "Unit",
        "common.quality": "Quality",
        "common.source_quality": "Source quality",
        "common.time_state": "Time state",
        "common.history_age_seconds": "History age (s)",
        "common.data": "Data",
        "common.signals": "Signals",
        "common.outcome": "Outcome",
        "common.observed_range": "Observed range",
        "common.why_no_result": "Why no result",
        "common.event": "Event",
        "common.detail": "Detail",
        "common.requested_from_evidence": "Requested from evidence",
        "common.last_review_activity": "Last review activity",
        "common.action": "Action",
        "common.note": "Note",
        "common.quantity": "Quantity",
        "common.median": "Median",
        "common.p95": "P95",
        "common.max": "Max",
        "common.from": "from",
        "common.to": "to",
        "common.analysis_evidence": "Analysis evidence",
        "common.queue_groups": "Queue groups",
        "error.what_happened": "What happened",
        "error.safety": "Known state",
        "error.next_action": "Next action",
        "error.technical_detail": "Technical detail",
        "first_run.sample.failure.what": "A sample launch error was reported.",
        "first_run.sample.failure.safety": (
            "A failed launch does not confirm whether the sample process stopped. "
            "Sample readings must not be treated as operational evidence."
        ),
        "first_run.sample.failure.next": (
            "Check whether the sample process is still running and stop it if necessary. Then "
            "retry the sample or choose Connect real data; inspect technical detail if it repeats."
        ),
        "setup.failure.what": "A data-connection action reported an error.",
        "setup.failure.safety": (
            "The saved source or collector state may require checking before retrying."
        ),
        "setup.failure.next": (
            "Check saved sources and input values to avoid duplicates, then retry only if needed."
        ),
        "setup.diagnostic.failure.what": "The bounded diagnostic did not complete successfully.",
        "setup.diagnostic.failure.safety": (
            "A failed diagnostic does not enable a source and is not asset-health evidence."
        ),
        "setup.diagnostic.failure.next": (
            "Check the source endpoint or FILE settings and runtime connectivity, then run "
            "the diagnostic again."
        ),
        "setup.mapping.failure.what": "The explicit OPC UA mapping could not be read.",
        "setup.mapping.failure.safety": (
            "Invalid mapping input does not confirm any source configuration change."
        ),
        "setup.mapping.failure.next": (
            "Use one signal_id,node_id pair per line, correct the invalid line, then retry."
        ),
        "asset.workspace.failure.what": "Asset evidence could not be loaded.",
        "asset.workspace.failure.safety": (
            "Unavailable evidence is not interpreted as asset health, fault, or alarm state."
        ),
        "asset.workspace.failure.next": (
            "Refresh the view. If it persists, inspect System and Data connection for source "
            "or history-read errors."
        ),
        "asset.analysis.failure.what": "The FILE snapshot analysis action reported an error.",
        "asset.analysis.failure.safety": (
            "A reported analysis failure does not establish whether prior results were saved or "
            "reviewed."
        ),
        "asset.analysis.failure.next": (
            "Check the selected FILE source and technical detail, then retry the analysis."
        ),
        "investigation.review.failure.what": "The review request reported an error.",
        "investigation.review.failure.safety": (
            "An error message does not establish the saved review state or asset health."
        ),
        "investigation.review.failure.next": (
            "Reload the selected evidence, confirm its review state, then request review again."
        ),
        "maintenance.failure.what": "The review action reported an error.",
        "maintenance.failure.safety": (
            "The persisted review state may differ from the displayed error; "
            "verify it before retrying."
        ),
        "maintenance.failure.next": (
            "Reload the review item, confirm its current state, then retry the appropriate action."
        ),
        "monitor.action_error.safety": (
            "Do not infer a data or asset-state change from this view update error."
        ),
        "monitor.action_error.next": (
            "Refresh the view. If the same error returns, inspect System or Data connection "
            "before retrying."
        ),
        "asset.no_selection": "No asset is selected.",
        "asset.history_unavailable": "Asset History unavailable",
        "asset.signals_unavailable": "Signals unavailable",
        "asset.recent_event_points": "Recent stored event-time points",
        "asset.latest_stored_value": "Latest stored value",
        "asset.no_observation_range": "No stored observation falls inside the selected time range.",
        "asset.file_snapshot_source": "FILE snapshot source",
        "asset.analyze_file_snapshot": "Analyze FILE snapshot",
        "asset.file_analysis_failed": "FILE analysis failed",
        "asset.analysis_recorded": "Analysis recorded",
        "asset.analyze_prepared_file": "Analyze prepared FILE snapshot",
        "asset.select_file_before_analysis": "Select a FILE snapshot source before analysis.",
        "asset.file_analysis_success": (
            "FILE snapshot analysis recorded. Assets and Investigations now use the persisted "
            "evidence. This does not create anomaly, fault, health, or maintenance meaning."
        ),
        "asset.file_analysis_help": (
            "This action computes and stores versioned vibration statistical feature evidence "
            "from the exact registered snapshot. It does not declare anomaly, fault, health "
            "state, or maintenance need."
        ),
        "asset.no_file_snapshot": (
            "No registered FILE snapshot source is available for on-demand feature analysis "
            "on this asset."
        ),
        "asset.no_signal": "No mapped or stored signal is available for this asset yet.",
        "asset.no_history_catalog": "No Asset History catalog is available for this workspace.",
        "asset.no_recent_persisted": (
            "No persisted observation is available in the live source's recent event-time "
            "window yet."
        ),
        "asset.live_evidence_help": (
            "Source flow uses collector/session evidence; selected-channel quality and event "
            "time use stored observation evidence. The trend draws raw points without "
            "interpolation, so unobserved intervals remain visually unfilled. Historical replay "
            "timestamps remain historical. This view does not infer asset health, fault, alarm, "
            "or expected missing samples."
        ),
        "asset.raw_observations": "Raw observations",
        "asset.data_details": "Data details",
        "asset.stored_measurements": "{count} stored measurements",
        "asset.channel_count": "{count} channel(s)",
        "asset.recorded_runs": "{count} recorded run(s)",
        "asset.open_count": "{count} open",
        "asset.attention_count": "{count} item(s) need attention",
        "asset.attempt.analyzed": "Analyzed",
        "asset.attempt.skipped": "Skipped",
        "asset.stored_evidence_help": (
            "Stored measurements and UI aggregates are observation evidence. "
            "This view does not infer asset health, fault, alarm, or missing samples."
        ),
        "asset.recent_analysis_attempts": "Recent analysis attempts",
        "asset.recorded_analysis_evidence": "Recorded analysis evidence",
        "asset.load_hint": "Select Assets to load this workspace.",
        "asset.workspace_unavailable": "Asset workspace unavailable",
        "asset.no_evidence": (
            "No asset evidence is available yet. Add a source in Data connection or load history."
        ),
        "investigation.request_review": "Request review",
        "investigation.no_filter_match": "No saved analysis result matches the current filters.",
        "investigation.evidence_summary": "Evidence summary",
        "investigation.vibration_evidence": "Vibration feature evidence",
        "investigation.renderer_unavailable": "Evidence renderer unavailable",
        "investigation.review_request_failed": "Review request failed",
        "investigation.review_requested": "Review requested",
        "investigation.human_review": "Human review",
        "investigation.queue": "Queue",
        "investigation.evidence_heading": "Analysis evidence",
        "investigation.select_result_for_review": (
            "Select an analysis result before requesting review."
        ),
        "investigation.review_requested_detail": (
            "Review requested. The analysis evidence itself was not reinterpreted."
        ),
        "investigation.queue_summary": "{groups} group(s) · {analyses} saved analyses",
        "investigation.group_run_count": "{runs} run(s) in this group",
        "investigation.grouping_help": (
            "Groups combine the same asset, capability, and human-review state. "
            "Exact analysis evidence remains selectable inside each group. "
            "Order is newest evidence first, not severity."
        ),
        "investigation.select_detail": "Select an analysis result from the queue.",
        "investigation.excluded_observations": "Excluded observations",
        "investigation.evidence_provenance": "Evidence & provenance",
        "investigation.feature": "Feature",
        "investigation.value": "Value",
        "investigation.vibration_help": (
            "These values are waveform statistics from one exact FILE snapshot. "
            "No threshold or state policy interprets them here as anomaly, fault, "
            "health, alert, or maintenance need."
        ),
        "investigation.renderer_detail": (
            "This capability has persisted evidence but no explicit Operations renderer. "
            "The evidence is not reinterpreted as another capability."
        ),
        "investigation.review_help": (
            "Requesting review records a workflow item linked to this evidence. "
            "It does not declare a fault, alarm, health state, or maintenance need."
        ),
        "investigation.current_review_state": "Current workflow state: **{state}**",
        "maintenance.open_evidence": "Open evidence in Investigations",
        "maintenance.review_note": "Review note",
        "maintenance.add_note": "Add note",
        "maintenance.acknowledge": "Acknowledge",
        "maintenance.close_review": "Close review",
        "maintenance.action.note": "Note",
        "maintenance.action.acknowledge": "Acknowledge",
        "maintenance.action.close": "Close",
        "maintenance.no_filter_match": "No review matches the current filters.",
        "maintenance.select_review": "Select a review from the queue.",
        "maintenance.action_failed": "Review action failed",
        "maintenance.updated": "Review updated",
        "maintenance.actions": "Review actions",
        "maintenance.counts": "Open {open} · Acknowledged {acknowledged} · Closed {closed}",
        "maintenance.review_heading": "Maintenance review",
        "maintenance.select_before_action": "Select a review before recording an action.",
        "maintenance.action_recorded": "Review action recorded: {action}.",
        "maintenance.workload": "Review workload",
        "maintenance.queue_summary": "{shown} shown · {total} total",
        "maintenance.closed_help": (
            "This review is closed. Closed review history is append-locked."
        ),
        "maintenance.review_identity": "Review identity",
        "maintenance.workflow_semantics": (
            "Acknowledge and Close change only the human review workflow. "
            "They do not confirm a fault, repair, asset health, or CMMS work order."
        ),
        "maintenance.evidence_not_loaded": (
            "Analysis run {analysis_run_id} is not in the loaded analysis results."
        ),
        "system.asset_name_conflict": "Asset display name conflict",
        "system.asset_name_conflict_detail": (
            "Registered sources declare different display names for the same asset, "
            "so the asset ID is shown instead:"
        ),
        "system.runtime_evidence_help": (
            "Runtime status is shown only where current evidence exists. "
            "A missing process heartbeat is displayed as unavailable rather than assumed healthy."
        ),
        "system.service.acquisition": "Live acquisition",
        "system.service.history": "History storage",
        "system.service.analysis": "Analysis service",
        "system.service.application": "Operations state read",
        "system.fact.collection_service": "Collection service",
        "system.fact.service_heartbeat": "Service heartbeat",
        "system.fact.configured_live_sources": "Configured live sources",
        "system.fact.connected_sessions": "Connected sessions",
        "system.fact.reconnecting": "Connecting / reconnecting",
        "system.fact.stopped": "Stopped / disconnected",
        "system.fact.last_received": "Last received data",
        "system.fact.waiting_store": "Waiting to store",
        "system.fact.oldest_waiting": "Oldest waiting age",
        "system.fact.latest_commit": "Latest commit",
        "system.fact.latest_finalized": "Latest finalized input",
        "system.fact.finalized_windows": "Finalized windows",
        "system.fact.heartbeat": "Heartbeat",
        "system.fact.completed_analyses": "Completed analyses",
        "system.fact.skipped_inputs": "Skipped inputs",
        "system.fact.last_result": "Last result",
        "system.fact.last_skip": "Last skip",
        "system.fact.last_skip_reason": "Last skip reason",
        "system.fact.last_failure": "Last failure",
        "system.fact.current_read_errors": "Current read errors",
        "system.fact.last_refresh": "Last refresh",
        "system.fact.process_heartbeat": "Process heartbeat",
        "system.fact.last_update": "Last update",
        "system.summary.no_live_source": "No live OPC UA source is configured",
        "system.summary.telemetry_unavailable": "Live acquisition telemetry is unavailable",
        "system.summary.worker_failures": "{count} collection worker failure(s)",
        "system.summary.reconnecting": "{count} live source session(s) reconnecting{connected}",
        "system.summary.connected_clause": " · {count} connected",
        "system.summary.connected": "{count} live source session(s) connected",
        "system.summary.collection_waiting": (
            "Collection enabled; waiting for live session evidence"
        ),
        "system.summary.collection_disabled": "Collection is not enabled",
        "system.summary.storage_unavailable": "No live storage telemetry available",
        "system.summary.history_failures": "{count} history writer failure(s)",
        "system.summary.history_current": "History current",
        "system.summary.waiting_store": "{count} event(s) waiting to store",
        "system.summary.waiting_first_commit": "{count} event(s) waiting for first history commit",
        "system.summary.waiting_collected": "Waiting for collected data",
        "system.summary.analysis_input_failures": "{count} analysis-input preparation failure(s)",
        "system.summary.analysis_unavailable": "Analysis service status unavailable",
        "system.summary.analysis_failed": "Analysis service failed",
        "system.summary.analysis_stopped": "Analysis service stopped",
        "system.summary.analysis_heartbeat_old": "Analysis service heartbeat is {age} old",
        "system.summary.analysis_waiting": "Analysis service running; waiting for analyzable data",
        "system.summary.analysis_results": "{count} analysis result(s) recorded",
        "system.summary.application_errors": "{count} current state-read error(s)",
        "system.summary.application_ok": "Current Operations state read succeeded",
        "system.value.unavailable": "Unavailable",
        "system.value.none": "None",
        "system.value.not_instrumented": "Not instrumented",
        "system.value.not_responding": "Not responding (last reported {state})",
        "system.value.unknown_last_report": "Unknown (last report {current} / {total})",
        "system.value.running": "Running",
        "system.value.stopped": "Stopped",
        "system.error.live_data": "Live data",
        "system.error.source_settings": "Source settings",
        "system.error.source_runtime": "Source runtime",
        "system.error.vibration_analysis": "Vibration analysis results",
        "system.error.phase_analysis": "Three-phase analysis results",
        "system.error.review_requests": "Review requests",
        "system.error.maintenance_review": "Maintenance review",
        "system.error.analysis_service": "Analysis service",
        "system.error.analysis_attempts": "Analysis attempts",
        "system.error.asset_history": "Asset History",
        "system.error.application": "Application state",
        "setup.maximum_data_age": "Maximum data age (seconds)",
        "setup.save_data_age": "Save data age policy",
        "setup.clear_policy": "Clear policy",
        "setup.data_age_saved": "Data age policy saved: {source_id} · {seconds:g} s.",
        "setup.data_age_cleared": "Data age policy cleared: {source_id}.",
        "setup.run_diagnostic": "Run one diagnostic cycle",
        "setup.collect_bounded": "Collect bounded subscription",
        "setup.source_use_changed": "Source use changed: {source_id} → {state}.",
        "setup.source_type": "Source type",
        "setup.source_id": "Source ID",
        "setup.name": "Name",
        "setup.measurement_point_optional": "Measurement point (optional)",
        "setup.file_path": "File or directory path",
        "setup.file_shape": "File shape",
        "setup.discover_file": "Discover file",
        "setup.timestamp_column_optional": "Timestamp column (optional for snapshot)",
        "setup.sampling_rate_optional": "Sampling rate Hz (optional)",
        "setup.endpoint": "Endpoint",
        "setup.endpoint_example": "Example: `opc.tcp://host:4840`",
        "setup.timeout_seconds": "Timeout seconds",
        "setup.connect_browse": "Connect & browse signals",
        "setup.advanced_mapping": "Advanced explicit mapping (signal_id,node_id)",
        "setup.signals_to_keep": "Signals to keep",
        "setup.observed_property": "Observed property",
        "setup.scope_optional": "Scope (optional)",
        "setup.statistic_optional": "Statistic (optional)",
        "setup.unit_optional": "Unit (optional)",
        "setup.unit_evidence": "Unit evidence (required when unit is known)",
        "setup.semantic_version": "Semantic version",
        "setup.interpretation_evidence": "Interpretation evidence",
        "setup.save_meaning": "Add / update meaning",
        "setup.keep_unresolved": "Keep unresolved",
        "setup.review_save_source": "Review & save source",
        "setup.source_saved": "Source saved: {source_id}. Enable it when ready to use.",
        "setup.select_source_for_age": "Select a data source before changing its data age policy.",
        "setup.select_source_for_use": "Select a data source before changing its use state.",
        "setup.select_opcua_for_collection": (
            "Select an OPC UA source before changing collection."
        ),
        "setup.explicit_meaning_required": (
            "Provide explicit measurement meaning or choose Keep unresolved."
        ),
        "setup.age_input_unavailable": "Data age policy input is unavailable.",
        "setup.maximum_age_required": "Maximum data age is required.",
        "setup.collection_saved": (
            "Collection request saved: {source_id} → {state}. "
            "The browser does not start or supervise the collector process."
        ),
        "setup.file_discovery_completed": ("File discovery completed. Select the signals to keep."),
        "setup.browse_completed_identity": (
            "Browse completed. This bounded session discovered signal identity only."
        ),
        "setup.meaning_saved": "Meaning saved for {channel_id}.",
        "setup.remain_unresolved": "{channel_id} will remain unresolved.",
        "setup.discover_before_save": "Discover the file source before saving.",
        "setup.select_file_signal": "Select at least one file signal.",
        "setup.timestamp_not_discovered": (
            "Timestamp column was not discovered in every CSV file."
        ),
        "setup.select_opcua_signal": (
            "Connect and select signals, or provide explicit advanced mapping."
        ),
        "setup.action_failed": "Setup action failed",
        "setup.updated": "Setup updated",
        "setup.diagnostic_failed": "Diagnostic action failed",
        "setup.diagnostic_completed": "Diagnostic action completed",
        "setup.select_source_for_diagnostic": "Select a data source before running diagnostics.",
        "setup.diagnostic_cycle_completed": "Diagnostic cycle completed.",
        "setup.subscription_completed": "Bounded subscription completed.",
        "setup.refresh_runtime_hint": (
            " Use Refresh to reload current runtime evidence in Monitor."
        ),
        "setup.diagnostic_skipped": "Diagnostic action skipped.",
        "setup.diagnostic_failed_default": "Diagnostic action failed.",
        "setup.diagnostic_failure": "{scope} failure · {detail}",
        "setup.add_data_source": "Add data source",
        "setup.connect_first_source": "Connect your first data source",
        "setup.connect_first_source_help": (
            "Operations needs an observation source before it can show asset state or analysis "
            "evidence. Choose a prepared FILE source or a live OPC UA source below."
        ),
        "setup.file.connect_help": (
            "Choose the prepared file boundary and declare the asset identity before discovery."
        ),
        "setup.file.select_help": (
            "Keep only discovered columns that belong to this source; "
            "column names are identifiers, not physical meaning."
        ),
        "setup.file.meaning_help": (
            "FILE registration preserves column identity. Record measurement meaning explicitly "
            "when it is known."
        ),
        "setup.file.review_help": (
            "The file is validated before its source registration is saved."
        ),
        "setup.mapping_invalid": "Explicit mapping invalid",
        "setup.mapping_line_format": ("Mapping line {line_number} must use signal_id,node_id."),
        "setup.no_mapping_selected": "No signal mapping selected yet.",
        "setup.select_mapping_first": "Select at least one mapped signal before defining meaning.",
        "setup.opcua.connect_help": (
            "Declare endpoint and asset identity, then run a bounded browse."
        ),
        "setup.opcua.select_help": (
            "Browse selection defines explicit NodeId mapping. NodeId and BrowseName do not "
            "establish physical meaning."
        ),
        "setup.no_browse_result": "No current browse result.",
        "setup.advanced_nodeid_mapping": "Advanced explicit NodeId mapping",
        "setup.opcua.meaning_help": (
            "Meaning is explicit, versioned, and evidence-backed. Leave channels unresolved "
            "when meaning is not established."
        ),
        "setup.opcua.review_help": (
            "Saving registers configuration only. It does not enable the source "
            "or start collection."
        ),
        "setup.connected_source": "Connected source",
        "setup.inspect_signals_title": "Inspect signals",
        "setup.inspect_signals_help": (
            "Confirm the exact source identity and the signals that were registered."
        ),
        "setup.confirm_meaning_title": "Confirm meaning",
        "setup.confirm_meaning_help": (
            "Explicit meaning is recorded for **{defined} / {total}** signal(s). "
            "Unresolved channels remain unresolved rather than being inferred from names."
        ),
        "setup.verify_flow_title": "Start or verify data flow",
        "setup.verify_flow_help": (
            "Enable the source when it is ready to be used. For OPC UA, request persistent "
            "collection. Bounded diagnostics remain available above for connection and "
            "data-contract checks."
        ),
        "setup.observe_title": "Observe",
        "setup.add_another_source": "Add another data source",
        "setup.analysis_configuration": "Analysis configuration",
        "setup.source_controls_help": (
            "Enable/Pause changes whether a runtime may use the source. Start/Stop collection "
            "writes desired collection state for OPC UA; it does not prove the collector "
            "process is running or connected."
        ),
        "setup.data_age_policy": "Data age policy",
        "setup.data_age_help": (
            "This policy compares the latest comparable observation time with the current "
            "assessment time. It does not prove connection health or asset health."
        ),
        "setup.advanced_diagnostics": "Advanced diagnostics",
        "setup.diagnostics_help": (
            "These bounded actions are for connection/data-contract diagnostics. They do not "
            "start the persistent collection service, and a successful attempt is not current "
            "connection health."
        ),
        "setup.discovered_file_summary": (
            "Discovered **{files}** file(s), **{columns}** common column(s)."
        ),
        "setup.run_discovery_help": (
            "Run discovery after choosing a file or history directory. "
            "No column meaning is inferred during discovery."
        ),
        "setup.step.source": "1 · Source",
        "setup.step.select_signals": "2 · Select signals",
        "setup.step.time_sampling": "3 · Define time & sampling",
        "setup.step.review_save": "4 · Review & save",
        "setup.step.connect": "1 · Connect",
        "setup.step.define_meaning": "3 · Define meaning",
        "setup.browse_summary": (
            "Browse completed: **{variables}** variable candidate(s), "
            "visited **{nodes}** node(s){truncated}."
        ),
        "setup.result_truncated": " · result truncated",
        "setup.browse_help": (
            "Connect & browse uses one bounded anonymous session to discover variable identity. "
            "It does not read signal values or prove ongoing connection health."
        ),
        "setup.semantic_empty": (
            "No explicit measurement meaning has been added. "
            "Unmapped meaning remains **Unresolved**."
        ),
        "setup.analysis_policy_help": (
            "Operational analysis policies are versioned outside this Data connection workspace "
            "today. The live three-phase runner and FILE analysis preserve their policy/version "
            "in evidence; this screen does not expose controls that the application contract "
            "cannot persist safely."
        ),
        "setup.analysis_navigation_help": (
            "Use **System** to verify analysis-service runtime status and **Investigations** "
            "to inspect the exact policy/evidence of completed analyses."
        ),
        "setup.connect_data_title": "Connect data",
        "setup.connect_data_help": (
            "Choose FILE for prepared local observations or OPC UA for a live source."
        ),
        "setup.title": "Data connection",
        "setup.intro": (
            "Connect data, inspect signal identity, record only known measurement meaning, "
            "then verify data flow before moving to Monitor."
        ),
        "monitor.stored_signals_snapshot": "{count} stored signals · observation snapshot",
        "monitor.inspect_channel": "Inspect {channel}",
        "monitor.all_origins": "All origins · {count} source/point records",
        "monitor.meaning_not_confirmed": "Meaning not confirmed",
        "monitor.origins": "{count} origins",
        "monitor.kept_separate": "kept separate",
        "monitor.compare_channel": "Compare {channel}",
        "monitor.remove_channel": "Remove {channel}",
        "monitor.loaded_evidence_count": "{count} loaded items in this event-time window",
        "monitor.open_analysis_evidence": "Open {label} analysis evidence",
        "monitor.bucket_stats": "Min {min} · max {max} · mean {mean}",
        "monitor.bucket_counts": (
            "{source} · {usable} usable · null {null} · non-good {non_good} · conflict {conflict}"
        ),
        "monitor.group_multiple_meanings": "Multiple recorded meanings",
        "monitor.group_unresolved": "Unresolved signals",
        "monitor.event": "Event",
        "monitor.event_time": "event time",
        "monitor.bucket_summary": "BUCKET SUMMARY · UTC",
        "monitor.cursor": "Cursor {time}",
        "investigation.group_option": (
            "{asset} · {capability} · {review} · {runs} run(s) · latest {completed}"
        ),
    },
    OperationsLocale.KO_KR: {
        "common.name": "이름",
        "common.type": "유형",
        "common.signal": "신호",
        "common.time_range": "시간 범위",
        "common.time": "시각",
        "common.value": "값",
        "common.unit": "단위",
        "common.quality": "품질",
        "common.source_quality": "Source 품질",
        "common.time_state": "시각 상태",
        "common.history_age_seconds": "History 경과(초)",
        "common.data": "데이터",
        "common.signals": "신호",
        "common.outcome": "결과",
        "common.observed_range": "관측 구간",
        "common.why_no_result": "결과 없음 사유",
        "common.event": "이벤트",
        "common.detail": "상세",
        "common.requested_from_evidence": "근거 기준 요청",
        "common.last_review_activity": "최근 검토 활동",
        "common.action": "작업",
        "common.note": "메모",
        "common.quantity": "항목",
        "common.median": "중앙값",
        "common.p95": "P95",
        "common.max": "최대",
        "common.from": "시작",
        "common.to": "종료",
        "common.analysis_evidence": "분석 근거",
        "common.queue_groups": "대기열 그룹",
        "error.what_happened": "발생 상황",
        "error.safety": "확인된 상태",
        "error.next_action": "다음 행동",
        "error.technical_detail": "기술 상세",
        "first_run.sample.failure.what": "샘플 시작 과정에서 오류가 보고됐습니다.",
        "first_run.sample.failure.safety": (
            "샘플 시작 실패만으로 자식 프로세스 종료 여부는 확인되지 않습니다. "
            "샘플 관측값은 운영 근거가 아닙니다."
        ),
        "first_run.sample.failure.next": (
            "샘플 프로세스가 실행 중인지 확인하고 필요하면 먼저 종료하세요. 그런 다음 샘플을 "
            "재시도하거나 실제 데이터 연결을 선택하세요. 반복되면 기술 상세를 확인하세요."
        ),
        "setup.failure.what": "데이터 연결 작업에서 오류가 보고됐습니다.",
        "setup.failure.safety": ("재시도 전에 저장된 source와 수집 요청 상태를 확인해야 합니다."),
        "setup.failure.next": (
            "중복 등록을 피하도록 저장된 source와 입력값을 확인하고 "
            "필요한 경우에만 다시 시도하세요."
        ),
        "setup.diagnostic.failure.what": "제한된 진단을 정상적으로 완료하지 못했습니다.",
        "setup.diagnostic.failure.safety": (
            "진단 실패만으로 source가 활성화되지 않으며 설비 상태 근거로 사용하지 않습니다."
        ),
        "setup.diagnostic.failure.next": (
            "Source endpoint 또는 FILE 설정과 runtime 연결 상태를 확인한 뒤 진단을 다시 실행하세요."
        ),
        "setup.mapping.failure.what": "명시적인 OPC UA mapping을 읽지 못했습니다.",
        "setup.mapping.failure.safety": (
            "잘못된 mapping 입력만으로 source 설정 변경 여부를 판단하지 마세요."
        ),
        "setup.mapping.failure.next": (
            "각 줄을 signal_id,node_id 한 쌍으로 작성하고 잘못된 줄을 수정한 뒤 다시 시도하세요."
        ),
        "asset.workspace.failure.what": "설비 evidence를 불러오지 못했습니다.",
        "asset.workspace.failure.safety": (
            "불러오지 못한 evidence를 설비 health, fault 또는 alarm 상태로 해석하지 않습니다."
        ),
        "asset.workspace.failure.next": (
            "화면을 새로고침하세요. 계속되면 시스템과 데이터 연결에서 source 또는 history 읽기 "
            "오류를 확인하세요."
        ),
        "asset.analysis.failure.what": "FILE snapshot 분석 작업에서 오류가 보고됐습니다.",
        "asset.analysis.failure.safety": (
            "분석 실패 메시지만으로 기존 결과의 저장 여부나 설비 상태를 판단할 수 없습니다."
        ),
        "asset.analysis.failure.next": (
            "선택한 FILE source와 기술 상세를 확인한 뒤 분석을 다시 실행하세요."
        ),
        "investigation.review.failure.what": "검토 요청 과정에서 오류가 보고됐습니다.",
        "investigation.review.failure.safety": (
            "오류 메시지만으로 저장된 검토 상태나 설비 상태를 판단할 수 없습니다."
        ),
        "investigation.review.failure.next": (
            "선택한 evidence를 다시 불러와 현재 검토 상태를 확인한 뒤 다시 요청하세요."
        ),
        "maintenance.failure.what": "검토 작업에서 오류가 보고됐습니다.",
        "maintenance.failure.safety": (
            "표시된 오류와 저장된 검토 상태가 다를 수 있으니 재시도 전에 확인하세요."
        ),
        "maintenance.failure.next": (
            "검토 항목을 다시 불러와 현재 상태를 확인한 뒤 가능한 작업을 다시 시도하세요."
        ),
        "monitor.action_error.safety": (
            "이 화면 갱신 오류만으로 데이터나 설비 상태가 바뀌었다고 판단하지 마세요."
        ),
        "monitor.action_error.next": (
            "화면을 새로고침하세요. 같은 오류가 반복되면 시스템 또는 데이터 연결 상태를 "
            "확인한 뒤 다시 시도하세요."
        ),
        "asset.no_selection": "선택된 설비가 없습니다.",
        "asset.history_unavailable": "설비 이력을 불러올 수 없습니다",
        "asset.signals_unavailable": "신호를 불러올 수 없습니다",
        "asset.recent_event_points": "최근 저장 event-time 관측값",
        "asset.latest_stored_value": "최근 저장값",
        "asset.no_observation_range": "선택한 시간 범위에 저장된 관측값이 없습니다.",
        "asset.file_snapshot_source": "FILE snapshot source",
        "asset.analyze_file_snapshot": "FILE snapshot 분석",
        "asset.file_analysis_failed": "FILE 분석 실패",
        "asset.analysis_recorded": "분석 기록 완료",
        "asset.analyze_prepared_file": "준비된 FILE snapshot 분석",
        "asset.select_file_before_analysis": "분석할 FILE snapshot source를 먼저 선택하세요.",
        "asset.file_analysis_success": (
            "FILE snapshot 분석을 기록했습니다. 설비와 분석 근거 화면은 이제 저장된 evidence를 "
            "사용합니다. 이 결과만으로 anomaly, fault, health, maintenance 의미를 만들지 않습니다."
        ),
        "asset.file_analysis_help": (
            "이 작업은 정확히 등록된 snapshot에서 versioned 진동 통계 feature evidence를 계산해 "
            "저장합니다. anomaly, fault, health state 또는 maintenance 필요성을 선언하지 않습니다."
        ),
        "asset.no_file_snapshot": (
            "이 설비에서 필요 시 feature 분석에 사용할 등록된 FILE snapshot source가 없습니다."
        ),
        "asset.no_signal": "이 설비에 mapping되거나 저장된 신호가 아직 없습니다.",
        "asset.no_history_catalog": (
            "이 workspace에서 사용할 수 있는 Asset History catalog가 없습니다."
        ),
        "asset.no_recent_persisted": (
            "Live source의 최근 event-time 구간에 저장된 관측값이 아직 없습니다."
        ),
        "asset.live_evidence_help": (
            "데이터 수신 상태는 collector/session evidence를 사용하고, 선택 채널의 품질과 "
            "event time은 저장 관측 evidence를 사용합니다. Trend는 보간 없이 raw point를 "
            "구간은 비워 둡니다. Historical replay timestamp는 과거 시각으로 유지됩니다. 이 화면은 "
            "설비 health, fault, alarm 또는 예상 missing sample을 추론하지 않습니다."
        ),
        "asset.raw_observations": "Raw 관측값",
        "asset.data_details": "데이터 상세",
        "asset.stored_measurements": "저장 측정값 {count}개",
        "asset.channel_count": "채널 {count}개",
        "asset.recorded_runs": "기록된 실행 {count}개",
        "asset.open_count": "열림 {count}개",
        "asset.attention_count": "확인 필요 {count}개",
        "asset.attempt.analyzed": "분석 완료",
        "asset.attempt.skipped": "건너뜀",
        "asset.stored_evidence_help": (
            "저장 측정값과 UI 집계값은 관측 evidence입니다. 이 화면은 설비 health, fault, alarm "
            "또는 missing sample을 추론하지 않습니다."
        ),
        "asset.recent_analysis_attempts": "최근 분석 시도",
        "asset.recorded_analysis_evidence": "기록된 분석 근거",
        "asset.load_hint": "설비 페이지를 선택하면 이 workspace를 불러옵니다.",
        "asset.workspace_unavailable": "설비 workspace를 불러올 수 없습니다",
        "asset.no_evidence": (
            "아직 설비 근거가 없습니다. 데이터 연결에서 source를 추가하거나 history를 불러오세요."
        ),
        "investigation.request_review": "검토 요청",
        "investigation.no_filter_match": "현재 필터와 일치하는 저장 분석 결과가 없습니다.",
        "investigation.evidence_summary": "근거 요약",
        "investigation.vibration_evidence": "진동 feature 근거",
        "investigation.renderer_unavailable": "근거 화면을 표시할 수 없습니다",
        "investigation.review_request_failed": "검토 요청 실패",
        "investigation.review_requested": "검토 요청 완료",
        "investigation.human_review": "사람 검토",
        "investigation.queue": "대기열",
        "investigation.evidence_heading": "분석 근거",
        "investigation.select_result_for_review": "검토를 요청할 분석 결과를 먼저 선택하세요.",
        "investigation.review_requested_detail": (
            "검토를 요청했습니다. 분석 evidence 자체를 다시 해석하지 않았습니다."
        ),
        "investigation.queue_summary": "그룹 {groups}개 · 저장 분석 {analyses}개",
        "investigation.group_run_count": "이 그룹의 실행 {runs}개",
        "investigation.grouping_help": (
            "그룹은 같은 설비, capability, 사람 검토 상태를 묶습니다. 그룹 안에서 정확한 분석 "
            "evidence를 선택할 수 있습니다. 순서는 severity가 아니라 최신 evidence 우선입니다."
        ),
        "investigation.select_detail": "대기열에서 분석 결과를 선택하세요.",
        "investigation.excluded_observations": "제외된 관측값",
        "investigation.evidence_provenance": "Evidence 및 provenance",
        "investigation.feature": "Feature",
        "investigation.value": "값",
        "investigation.vibration_help": (
            "이 값은 하나의 정확한 FILE snapshot에서 계산한 waveform 통계입니다. "
            "여기서는 threshold나 state policy로 anomaly, fault, health, alert 또는 "
            "maintenance 필요성을 해석하지 않습니다."
        ),
        "investigation.renderer_detail": (
            "이 capability에는 저장된 evidence가 있지만 명시적인 Operations renderer가 없습니다. "
            "다른 capability로 다시 해석하지 않습니다."
        ),
        "investigation.review_help": (
            "검토 요청은 이 evidence에 연결된 workflow item을 기록합니다. "
            "fault, alarm, health state 또는 maintenance 필요성을 선언하지 않습니다."
        ),
        "investigation.current_review_state": "현재 workflow 상태: **{state}**",
        "maintenance.open_evidence": "분석 근거에서 열기",
        "maintenance.review_note": "검토 메모",
        "maintenance.add_note": "메모 추가",
        "maintenance.acknowledge": "확인",
        "maintenance.close_review": "검토 종료",
        "maintenance.action.note": "메모",
        "maintenance.action.acknowledge": "확인",
        "maintenance.action.close": "종료",
        "maintenance.no_filter_match": "현재 필터와 일치하는 검토가 없습니다.",
        "maintenance.select_review": "대기열에서 검토 항목을 선택하세요.",
        "maintenance.action_failed": "검토 작업 실패",
        "maintenance.updated": "검토 갱신 완료",
        "maintenance.actions": "검토 작업",
        "maintenance.counts": "열림 {open} · 확인됨 {acknowledged} · 종료됨 {closed}",
        "maintenance.review_heading": "정비 검토",
        "maintenance.select_before_action": "작업을 기록할 검토 항목을 먼저 선택하세요.",
        "maintenance.action_recorded": "검토 작업 기록: {action}.",
        "maintenance.workload": "검토 현황",
        "maintenance.queue_summary": "{shown}개 표시 · 전체 {total}개",
        "maintenance.closed_help": (
            "이 검토는 종료되었습니다. 종료된 검토 이력은 추가 기록이 잠겨 있습니다."
        ),
        "maintenance.review_identity": "검토 식별 정보",
        "maintenance.workflow_semantics": (
            "확인과 검토 종료는 사람 검토 workflow만 변경합니다. fault, repair, asset health 또는 "
            "CMMS work order를 확인하는 동작이 아닙니다."
        ),
        "maintenance.evidence_not_loaded": (
            "분석 실행 {analysis_run_id}을 현재 로드된 분석 결과에서 찾을 수 없습니다."
        ),
        "system.asset_name_conflict": "설비 표시 이름 충돌",
        "system.asset_name_conflict_detail": (
            "등록된 source들이 같은 설비에 서로 다른 표시 이름을 선언해 asset ID를 대신 표시합니다:"
        ),
        "system.runtime_evidence_help": (
            "Runtime 상태는 현재 evidence가 있는 경우에만 표시합니다. Process heartbeat가 없으면 "
            "정상으로 추정하지 않고 사용 불가로 표시합니다."
        ),
        "system.service.acquisition": "실시간 수집",
        "system.service.history": "이력 저장",
        "system.service.analysis": "분석 service",
        "system.service.application": "Operations 상태 읽기",
        "system.fact.collection_service": "수집 service",
        "system.fact.service_heartbeat": "Service heartbeat",
        "system.fact.configured_live_sources": "설정된 live source",
        "system.fact.connected_sessions": "연결된 session",
        "system.fact.reconnecting": "연결 / 재연결 중",
        "system.fact.stopped": "중지 / 연결 해제",
        "system.fact.last_received": "최근 데이터 수신",
        "system.fact.waiting_store": "저장 대기",
        "system.fact.oldest_waiting": "최장 대기 시간",
        "system.fact.latest_commit": "최근 commit",
        "system.fact.latest_finalized": "최근 finalized input",
        "system.fact.finalized_windows": "Finalized window",
        "system.fact.heartbeat": "Heartbeat",
        "system.fact.completed_analyses": "완료된 분석",
        "system.fact.skipped_inputs": "건너뛴 input",
        "system.fact.last_result": "최근 결과",
        "system.fact.last_skip": "최근 건너뜀",
        "system.fact.last_skip_reason": "최근 건너뜀 사유",
        "system.fact.last_failure": "최근 실패",
        "system.fact.current_read_errors": "현재 읽기 오류",
        "system.fact.last_refresh": "최근 새로고침",
        "system.fact.process_heartbeat": "Process heartbeat",
        "system.fact.last_update": "최근 갱신",
        "system.summary.no_live_source": "설정된 실시간 OPC UA source가 없습니다",
        "system.summary.telemetry_unavailable": "실시간 수집 telemetry를 사용할 수 없습니다",
        "system.summary.worker_failures": "수집 worker 실패 {count}건",
        "system.summary.reconnecting": "Live source session {count}개 재연결 중{connected}",
        "system.summary.connected_clause": " · {count}개 연결됨",
        "system.summary.connected": "Live source session {count}개 연결됨",
        "system.summary.collection_waiting": "수집 활성화됨 · live session evidence 대기 중",
        "system.summary.collection_disabled": "수집이 활성화되지 않았습니다",
        "system.summary.storage_unavailable": "Live 저장 telemetry가 없습니다",
        "system.summary.history_failures": "History writer 실패 {count}건",
        "system.summary.history_current": "History 최신 상태",
        "system.summary.waiting_store": "저장 대기 event {count}개",
        "system.summary.waiting_first_commit": "첫 history commit 대기 event {count}개",
        "system.summary.waiting_collected": "수집 데이터 대기 중",
        "system.summary.analysis_input_failures": "분석 input 준비 실패 {count}건",
        "system.summary.analysis_unavailable": "분석 service 상태를 확인할 수 없습니다",
        "system.summary.analysis_failed": "분석 service 실패",
        "system.summary.analysis_stopped": "분석 service 중지됨",
        "system.summary.analysis_heartbeat_old": "분석 service heartbeat 경과 {age}",
        "system.summary.analysis_waiting": "분석 service 실행 중 · 분석 가능한 데이터 대기",
        "system.summary.analysis_results": "분석 결과 {count}건 기록됨",
        "system.summary.application_errors": "현재 상태 읽기 오류 {count}건",
        "system.summary.application_ok": "현재 Operations 상태 읽기 성공",
        "system.value.unavailable": "사용 불가",
        "system.value.none": "없음",
        "system.value.not_instrumented": "계측 안 됨",
        "system.value.not_responding": "응답 없음 (최근 보고: {state})",
        "system.value.unknown_last_report": "확인 불가 (최근 보고 {current} / {total})",
        "system.value.running": "실행 중",
        "system.value.stopped": "중지됨",
        "system.error.live_data": "Live 데이터",
        "system.error.source_settings": "Source 설정",
        "system.error.source_runtime": "Source runtime",
        "system.error.vibration_analysis": "진동 분석 결과",
        "system.error.phase_analysis": "3상 분석 결과",
        "system.error.review_requests": "검토 요청",
        "system.error.maintenance_review": "정비 검토",
        "system.error.analysis_service": "분석 service",
        "system.error.analysis_attempts": "분석 시도",
        "system.error.asset_history": "설비 이력",
        "system.error.application": "애플리케이션 상태",
        "setup.maximum_data_age": "데이터 최대 경과 시간(초)",
        "setup.save_data_age": "데이터 경과 정책 저장",
        "setup.clear_policy": "정책 지우기",
        "setup.data_age_saved": "데이터 경과 정책 저장: {source_id} · {seconds:g}초.",
        "setup.data_age_cleared": "데이터 경과 정책 삭제: {source_id}.",
        "setup.run_diagnostic": "진단 1회 실행",
        "setup.collect_bounded": "제한된 subscription 수집",
        "setup.source_use_changed": "Source 사용 상태 변경: {source_id} → {state}.",
        "setup.source_type": "Source 유형",
        "setup.source_id": "Source ID",
        "setup.name": "이름",
        "setup.measurement_point_optional": "측정 지점(선택)",
        "setup.file_path": "파일 또는 디렉터리 경로",
        "setup.file_shape": "FILE 형태",
        "setup.discover_file": "파일 탐색",
        "setup.timestamp_column_optional": "Timestamp 열(snapshot은 선택)",
        "setup.sampling_rate_optional": "Sampling rate Hz(선택)",
