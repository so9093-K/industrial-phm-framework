# Current Support Status

이 문서는 `industrial-phm-framework`의 **현재 구현·지원 범위**를 한 곳에서 확인하기 위한
authoritative status 문서입니다.

이 문서는 architecture나 roadmap이 아닙니다.

- 시스템 책임과 contract boundary는 [Architecture](architecture/overview.md)가 소유합니다.
- 구조 결정의 이유와 대안은 [ADR](adr/README.md)이 소유합니다.
- 실행 방법과 runtime path는 해당 subsystem README가 소유합니다.
- 변경 이력은 [CHANGELOG](../CHANGELOG.md)가 소유합니다.
- 계획된 작업, milestone, 일회성 migration 상태는 GitHub Issue/PR이 소유합니다.

README·Architecture·Product 문서는 아래 지원 표를 다시 복사하지 않고 이 문서를 참조합니다.
이 문서는 **지원 경계가 바뀔 때만** 갱신하며, 내부 refactor나 commit마다 현황을 추가하지 않습니다.

## 상태 정의

| 상태 | 의미 |
| --- | --- |
| **지원** | repository의 public/runtime 경로와 자동화된 검증이 존재함 |
| **조건부 지원** | 명시적 configuration 또는 제한된 contract 안에서 지원함 |
| **Research only** | 연구·평가 evidence 경로이며 operational capability로 주장하지 않음 |
| **미제공** | 현재 public/runtime 경로가 없음 |
| **현장 미검증** | synthetic/contract 검증은 있지만 실제 현장 설비 검증 근거는 아직 없음 |

## Operational data path

| 영역 | 상태 | 현재 경계 / 근거 |
| --- | --- | --- |
| FILE source 등록·검증·backfill | **지원** | prepared FILE source를 명시적 asset/channel/time mapping으로 검증하고 Asset History에 적재 |
| OPC UA one-shot / bounded subscription | **지원** | explicit NodeId mapping과 protocol quality/timestamp 보존 |
| OPC UA persistent collection | **지원** | 독립 collection service, reconnect, durable spool, telemetry, DuckLake writer, observation-window coordinator |
| Asset History | **지원** | FILE backfill과 OPC UA live observation을 DuckLake history에서 함께 조회 |
| Asset History manual small-file compaction | **조건부 지원** | explicit `compact-history`만 지원. snapshot expiration/cleanup 없이 table별 merge-only compaction을 수행하고 old snapshot evidence/retry를 검증. 자동 scheduling·retention은 미제공 |
| 측정 의미(semantic binding) | **조건부 지원** | source가 명시적으로 제공한 versioned binding만 사용. channel 이름에서 물리 의미를 추론하지 않음 |
| Asset History latest/page/aggregation 의미 표시 | **지원** | FILE/OPC UA raw evidence에 고정된 의미 snapshot을 fail-closed로 표시 |
| Finalized observation window | **지원** | accepted event set과 rejection/watermark evidence를 SQLite WAL에 보존. continuous coordinator는 bounded durable-ingestion cursor로 새 event만 처리하고 cursor/watermark/active buffer를 finalized window와 같은 transaction에 checkpoint |
| Live 분석 runner | **지원** | collection service와 별도 process. capability/algorithm/policy별 durable cursor 이후의 finalized window만 bounded page로 처리하고 분석 결과/SQLite skip ledger를 restart-safe하게 저장 |

세부 live stack 실행은 [OPC UA local stack](../tools/opcua/README.md)을 따릅니다.

## Analysis and Operations

| 영역 | 상태 | 현재 경계 / 근거 |
| --- | --- | --- |
| Registered FILE snapshot vibration feature AnalysisRun | **지원** | operational AnalysisRun/evidence 경로 |
| 3상 불평형 · historical Asset History | **지원** | fixed history snapshot + explicit/semantic-role channel selection |
| 3상 불평형 · finalized live window | **지원** | ADR-0008에 따라 window가 accept한 event set만 사용 |
| Temporal alignment `strict-v1` | **지원** | 같은 timestamp의 세 상만 계산 |
| Temporal alignment `bounded-previous-v1` | **조건부 지원** | explicit max age와 근거가 필요. causal event-transition reconstruction이며 synchronized acquisition cycle을 주장하지 않음 |
| window 시작 전 carry-in state | **미제공** | finalized window 밖의 이전 값을 analysis input으로 재조회하지 않음 |
| Operations source control/monitor | **지원** | desired collection request, collector-service heartbeat, OPC UA session, live receive silence, spool/history evidence를 서로 다른 사실로 표시 |
| Operations Asset History | **지원** | 최신값·raw page·UI aggregation·quality·provenance 조회 |
| Operations의 3상 불평형 결과 조회 | **조건부 지원** | runner와 Operations가 같은 phase-unbalance result repository path를 사용해야 함. 실행 중 새 결과는 명시적 refresh로 읽음(자동 polling 없음) |
| Operations 분석 시도/skip 이유 조회 | **조건부 지원** | Operations가 runner와 같은 finalized-window SQLite와 analysis-ledger SQLite를 읽을 때 Asset별 Analyzed/Skipped 시도와 exact skip reason을 표시 |
| Live runner lifecycle 전용 UI/자동 process 관리 | **미제공** | runner는 별도 CLI process로 실행 |
| Investigation / review finding / Maintenance Review | **지원** | AnalysisRun evidence를 사람이 조사·검토하고 review 기록을 남김 |

3상 불평형의 계산·eligibility·alignment 계약은
[capability 문서](architecture/phase-unbalance-capability.md), live input 결정은
[ADR-0008](adr/0008-analyze-finalized-window-accepted-events.md), temporal alignment는
[ADR-0009](adr/0009-temporal-alignment-policy.md)을 따릅니다.

## Research / operational boundary

| 영역 | 상태 | 현재 경계 |
| --- | --- | --- |
| XJTU/IMS/MIMII anomaly·RUL experiment evidence | **Research only** | Analysis Explorer에서 연구 결과·pipeline·provenance 검토 |
| provider label을 production 분석 입력으로 사용 | **미제공** | label은 research evaluation에만 사용 |
| validated fault diagnosis | **미제공** | 관측·분석 evidence를 진단으로 자동 승격하지 않음 |
| operational alarm / fleet risk scoring | **미제공** | source 상태나 analysis output을 alarm/risk verdict로 자동 승격하지 않음 |
| operational RUL | **미제공** | 연구 RUL evidence와 operational capability를 분리 |
| 자동 정비 권고·설비 제어 실행 | **미제공** | 사람의 review/승인을 대체하지 않음 |

## Validation and deployment boundary

| 영역 | 상태 | 현재 경계 |
| --- | --- | --- |
| synthetic OPC UA loopback E2E | **지원** | 실제 asyncua server와 별도 collector process를 사용하는 contract test |
| AI-Hub replay repeatable fault gate | **지원** | `tools/opcua/fault_harness.py`: stall·kill/restart·overflow·spool backlog N회 주입, 결손상 이유·review→Maintenance 연결·실제 브라우저 5초 확인, machine verdict(`full`/`diagnostic`). 결과는 `docs/research/phase10-acquisition-stress.md` |
| Local Operations workspace 초기화 | **지원** | `industrial-phm operations init <root>`가 versioned `config.toml`과 managed data/log directory를 만들고 기존 유효 workspace에는 idempotent하게 동작. config 없는 비어 있지 않은 directory는 자동 채택하지 않음 |
| Local Operations runtime status | **지원** | `industrial-phm operations status <root>`가 supervisor process identity와 collection/analysis component heartbeat를 분리해 표시. PID 존재만으로 component health를 추정하지 않음 |
| 통합 local Operations lifecycle | **미제공** | collection/analysis/UI의 `start/logs/stop` product runtime은 아직 없음. 현재는 workspace root와 read-only status까지 제공하지만 전체 process lifecycle은 아직 user-facing command로 통합되지 않음 |
| installable Operations application | **조건부 지원** | canonical Operations app을 wheel의 `industrial_phm.apps`에 포함하고 `operations` extra가 marimo + history/OPC UA runtime dependencies를 제공. 통합 `operations start` lifecycle은 아직 미제공 |
| 실제 현장 OPC UA 설비 validation | **현장 미검증** | 현장 update/deadband/timestamp/security 특성에 대한 검증 근거가 아직 없음 |
| local multi-process coordination | **조건부 지원** | SQLite WAL과 local file lock 기반. 같은 state/catalog에 대한 협조 프로세스 전제 |
| HA / distributed coordination / leader election | **미제공** | local-first runtime 경계 |
| OPC UA username/password/certificate/security-policy configuration | **미제공** | 현재 connector는 anonymous local/dev 경계를 사용 |
| MQTT connector | **미제공** | 현재 operational protocol slice는 FILE과 OPC UA |

지원 여부를 새 문서에 추가하기 전에 production code, contract test 또는 subsystem 실행 경로가 실제로
존재하는지 확인합니다. 계획만 있는 항목은 이 표에 “예정”으로 넣지 않고 Issue/PR에서 관리합니다.
