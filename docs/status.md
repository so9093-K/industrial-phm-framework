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
| **대상 source 미검증** | synthetic/replay/contract 검증은 있지만 대상 운영 source validation 근거는 아직 없음 |

## Operational data path

| 영역 | 상태 | 현재 경계 / 근거 |
| --- | --- | --- |
| FILE source 등록·검증·backfill | **지원** | prepared FILE source를 명시적 asset/channel/time mapping으로 검증하고 Asset History에 적재 |
| OPC UA one-shot / bounded subscription | **지원** | explicit NodeId mapping과 protocol quality/timestamp 보존 |
| OPC UA persistent collection | **지원** | 독립 collection service, reconnect, durable spool, telemetry, DuckLake writer, observation-window coordinator |
| Asset History | **지원** | FILE backfill과 OPC UA live observation을 DuckLake history에서 함께 조회 |
| Asset History manual small-file compaction | **조건부 지원** | explicit `maintenance history compact`만 지원. snapshot expiration/cleanup 없이 table별 merge-only compaction을 수행하고 old snapshot evidence/retry를 검증. 자동 scheduling·retention은 미제공 |
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
| Operations live signal observation | **지원** | mapped OPC UA signal의 latest stored observation과 current session/receive telemetry를 함께 표시하고, latest event-time 기준 bounded recent trend를 1/2/5초 refresh로 조회. replay의 원래 event time과 현재 receive clock을 분리하며 collector callback을 UI가 직접 소비하지 않음 |
| Operations의 3상 불평형 결과 조회 | **조건부 지원** | runner와 Operations가 같은 phase-unbalance result repository path를 사용해야 함. 실행 중 새 결과는 명시적 refresh로 읽음(자동 polling 없음) |
| Operations 분석 시도/skip 이유 조회 | **조건부 지원** | Operations가 runner와 같은 finalized-window SQLite와 analysis-ledger SQLite를 읽을 때 Asset별 Analyzed/Skipped 시도와 exact skip reason을 표시 |
| Live runner process lifecycle | **지원** | `operations start <root>`의 supervisor가 collection과 별도 analysis runner process를 함께 소유. analysis health는 runner-owned heartbeat가 authoritative |
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
| one-command synthetic Operations demo | **지원** | `industrial-phm demo synthetic`이 전용 workspace에 synthetic 3상 OPC UA source를 등록하고 simulator + collection + analysis + packaged UI를 한 foreground lifecycle로 실행. 물리 설비 측정/고장 진단 evidence가 아님 |
| AI-Hub boiler recorded replay demo | **조건부 지원** | local AI-Hub 239 boiler archive + `aihub` extra가 있을 때 `industrial-phm demo aihub-boiler`가 검증된 device 2297/member/time-range preset을 replay server + normal Operations runtime으로 실행. recorded provider data replay이며 대상 운영 OPC UA source validation/diagnosis가 아님 |
| clean-workspace Operations product acceptance | **지원** | external data 없이 fresh synthetic workspace에서 실제 demo process → runtime ready → finalized window/analysis evidence → stop → 같은 workspace restart/state 보존을 CI에서 검증 |
| AI-Hub replay repeatable fault gate | **지원** | `tools/opcua/fault_harness.py`: stall·kill/restart·overflow·spool backlog N회 주입, 결손상 이유·review→Maintenance 연결·실제 브라우저 5초 확인, machine verdict(`full`/`diagnostic`). 결과는 `docs/research/phase10-acquisition-stress.md` |
| Local Operations workspace 초기화 | **지원** | `industrial-phm operations init <root>`가 versioned `config.toml`과 managed data/log directory를 만들고 기존 유효 workspace에는 idempotent하게 동작. config 없는 비어 있지 않은 directory는 자동 채택하지 않음 |
| Local Operations runtime status | **지원** | `industrial-phm operations status <root>`가 supervisor process identity, collection/analysis heartbeat, UI loopback listener readiness를 분리해 표시. PID 존재만으로 component health/readiness를 추정하지 않음 |
| 통합 local Operations lifecycle | **지원** | `operations start <root>`가 workspace config에서 collection → analysis → packaged UI launch plan을 만들고 한 foreground supervisor로 실행. Ctrl-C 또는 `operations stop <root>`은 child를 역순으로 graceful shutdown. stop은 persisted PID만 믿지 않고 workspace supervisor lock owner PID까지 검증 후 signal 요청 |
| Local Operations logs | **지원** | `operations logs <root>`가 collection/analysis/ui의 workspace-owned log를 component별 최대 10,000줄 bounded tail로 표시. 내부 log path를 정상 사용자가 직접 지정하지 않음 |
| stopped workspace backup/restore | **지원** | `maintenance backup <workspace> <backup>`이 stopped local node의 durable workspace state/history를 manifest+SHA-256으로 capture. SQLite는 backup API 사용. logs/supervisor identity/locks/rebuildable batch index는 제외. `maintenance restore <backup> <new-root>`는 검증 후 새 root에 atomic restore하며 기존 workspace는 덮어쓰지 않음 |
| deployment preflight / systemd reference | **지원** | `validate deployment <absolute-root>`가 실제 service user 기준 runtime dependency, config/plan, workspace access, supervisor/history lock, UI port를 검증. reference unit은 foreground `operations start`, `Restart=on-failure`, `KillMode=mixed`, bounded restart/stop policy를 사용 |
| installable Operations application | **지원** | canonical Operations app이 wheel의 `industrial_phm.apps`에 포함되고 `operations` extra가 marimo + history/OPC UA runtime dependencies를 제공. local supervisor가 packaged app을 `127.0.0.1` loopback-only, no-token UI child로 실행. shared/public host 노출은 미지원 |
| operational CLI taxonomy | **지원** | normal node lifecycle=`operations`, recovery/history=`maintenance`, deployment gates=`validate`, service/source plumbing=`internal`. 이동 전 `operations` spelling은 더 이상 rewrite하지 않음 |
| 대상 운영 OPC UA source validation | **대상 source 미검증** | 대상 source의 update/deadband/timestamp/security 특성에 대한 검증 근거가 아직 없음 |
| local multi-process coordination | **조건부 지원** | SQLite WAL과 local file lock 기반. 같은 state/catalog에 대한 협조 프로세스 전제 |
| HA / distributed coordination / leader election | **미제공** | local-first runtime 경계 |
| OPC UA username/password/certificate/security-policy configuration | **미제공** | 현재 connector는 anonymous local/dev 경계를 사용 |
| MQTT connector | **미제공** | 현재 operational protocol slice는 FILE과 OPC UA |

지원 여부를 새 문서에 추가하기 전에 production code, contract test 또는 subsystem 실행 경로가 실제로
존재하는지 확인합니다. 계획만 있는 항목은 이 표에 “예정”으로 넣지 않고 Issue/PR에서 관리합니다.
