# Changelog

이 프로젝트의 사용자 및 개발자에게 의미 있는 변경사항을 기록합니다. 형식은 Keep a Changelog의
분류 방식을 따릅니다.

개발 중 package version은 `0.0.1`로 유지하며 기능 PR이나 내부 구조 변경마다 버전을 올리지 않습니다.
릴리즈 가능한 public API와 배포 정책을 별도로 결정할 때 versioning 정책을 다시 검토합니다. 그 전까지
의미 있는 변경은 `[Unreleased]` 아래에 누적합니다.

## [Unreleased]

### Fixed

- Live window analysis와 Operations의 3상 불평형 결과 저장소를 SQLite(`SqlitePhaseUnbalanceRepository`, run마다
  한 row)로 바꿨습니다. 이전 JSON 저장소는 window마다 전체 결과를 다시 읽고 다시 써서 runner의 기록 비용과
  메모리가 누적 결과 수에 비례해 늘었습니다(결과 400건에서 기록 1건당 96 ms·7.7 MB; SQLite는 10,000건에서도
  0.8 ms·0.01 MB). 기본 경로는 `artifacts/operations/phase-unbalance.sqlite`입니다. 기존 JSON 결과는
  덮어쓰지 않고 `operations migrate-phase-unbalance-results`로 identity를 보존해 명시 이관하며, 기본 SQLite가
  아직 없고 legacy JSON만 남아 있으면 Operations System이 migration 필요 상태를 표시합니다.

- Fault harness가 발견한 손실을 고쳤습니다. Worker가 현재 notification을 spool에 기록하기 전에 다음
  notification을 요청해, 기록을 기다리는 사이 dequeue된 notification이 overflow·연결 상실·정상 stop으로
  worker가 끝날 때 버려졌습니다. 이제 기록 후에 다음을 요청하고, 종료 시 이미 dequeue된 notification을
  기록합니다. Collector는 SIGINT/SIGTERM에서 정상 종료 경로(소스 정지 → writer 정지 → 진단 flush)를 탑니다.

- Phase 10 queue-pressure 재현(AI-Hub replay + SIGSTOP fault + publish-ledger audit)에서 확인한 수집
  중단을 고쳤습니다(ADR-0010). asyncua 2.0.1 in-client 재연결은 burst overflow 뒤 영구 disconnected가 되거나,
  session 재활성화 뒤 subscription 불일치로 CONNECTED 상태에서 데이터를 무기한 버렸습니다. 연결 상실과
  queue overflow 시 worker가 명시적으로 종료하고 collection service가 새 session·epoch로 backoff(1~30초)
  재시작합니다(`CollectionServicePolicy.restart_backoff_*`). overflow hook은 `notify_transport_lost()` 폭주
  대신 한 번만 신호하고, 연결 상실과 같은 wakeup에 이미 dequeue된 notification은 종료 전에 기록합니다.
  Window coordinator 실패는 OPC UA session을 재시작하지 않고 coordinator만 backoff 재시작합니다.
- Subscription queue 기본값을 128에서 4096으로 올렸습니다(정상 high-watermark ≈ 33, 30초 stall burst 1,007건
  무손실 처리).
- 동시 accept 중 spool backlog 통계를 두 번의 autocommit 조회로 읽어 불변식 오류로 collection service가 멈추던
  race를 단일 read transaction으로 고쳤습니다.
- OPC UA `received_at`이 consumer dequeue 시각이던 것을 client 도착 시각으로 바로잡았습니다.

### Added

- Clean-workspace Operations product acceptance gate를 추가했습니다. `operations` extra 환경에서 packaged synthetic
  demo를 실제 subprocess로 실행해 runtime ready, finalized window/analysis evidence, graceful stop, 같은
  workspace restart와 evidence 보존을 검증합니다. 외부 dataset이나 remote endpoint는 사용하지 않습니다.

- `industrial-phm demo synthetic` one-command local demo를 추가했습니다. 전용 workspace를 안전하게 생성·재사용하고
  synthetic 3상 OPC UA source를 ACTIVE/RUNNING으로 준비한 뒤 loopback simulator readiness를 확인하고 기존
  Operations supervisor(collection + analysis + packaged UI)를 실행합니다. 기존 사용자 source가 섞인 workspace는
  자동 채택하지 않으며 synthetic 값은 실제 설비 측정이나 진단으로 해석하지 않습니다.

- Local Operations product-runtime foundation을 추가했습니다. `operations init <workspace>`가 versioned
  workspace/config를 만들고, collector/analysis launch policy와 foreground supervisor가 같은 workspace를
  사용합니다. 새 `operations status <workspace>`는 supervisor process identity와 collection/analysis
  component heartbeat를 분리해 표시하며, PID만으로 component health를 추정하지 않습니다.

- Local Operations lifecycle CLI를 추가했습니다. `operations start <workspace>`는 workspace config에서
  collection/analysis launch plan을 만들고 한 foreground supervisor로 실행하며, Ctrl-C 또는
  `operations stop <workspace>`으로 child process를 함께 graceful shutdown합니다. `stop`은 persisted PID만
  신뢰하지 않고 해당 workspace supervisor lock의 live ownership을 확인한 뒤 종료 signal을 요청합니다.

- Local Operations lifecycle에 packaged UI를 포함했습니다. runtime config v2의 `[ui] port`를 사용해 loopback에서
  marimo app을 `127.0.0.1` 전용 headless/no-token child로 실행하고, `status`는 UI PID와 TCP listener readiness를 분리해 표시합니다.
  기존 v1 workspace config는 `operations init` 재실행 시 비파괴적으로 v2로 승격됩니다. 새 `operations logs`
  명령은 collection/analysis/ui 로그를 bounded tail로 표시합니다.

- `tools/history/append_profile.py`와
  `docs/research/phase10-history-append-scaling.md`: live history append를 단계별로 분해하고
  N=0/2,000 full-data와 N=10,000 metadata-only 상태를 비교하는 #344 재현 도구/evidence입니다.

- DuckLake Asset History에 #317-A 비파괴 small-file maintenance를 추가했습니다. `compact-history`는
  같은 local catalog lease를 table별 provider call마다 사용해 `merge_adjacent_files`만 실행합니다.
  `--max-compacted-files`는 input-file 상한이 아니라 DuckLake의 table별 output-operation 상한이며,
  실제 resource bound는 RSS/HWM·lock-hold N-scale 실측으로 판정합니다. storage inspection은 active/scheduled/physical file과 snapshot을 분리하며,
  historical snapshot canonical fingerprint와 batch exact-retry로 compaction 전후 evidence 불변을 검증합니다.
  snapshot expiration, cleanup, CHECKPOINT, VACUUM, 자동 scheduler는 포함하지 않습니다.
- `tools/history/compaction_benchmark.py`: N=0/2,000/10,000 누적-state 비교용 benchmark. Git/Python/
  DuckDB/DuckLake/OS fingerprint, append/query/compaction 비용, storage population, snapshot SHA-256과
  destructive-operation 0회를 JSON evidence로 남깁니다.

- `tools/opcua/fault_harness.py`: Phase 10 repeatable fault gate. Collector/source stall, collector·runner
  kill/restart, forced overflow, spool backlog을 N회 주입하고 audit·손실 경계·dequeue 손실·window/analysis
  cursor·wedge·Operations 상태 구분, 결손상 이유(window 누락 채널 → 전류만 unresolved → Investigation note·
  provenance), 장애 후 Investigation → review request → Maintenance 연결을 machine verdict(JSON, exit code)로
  판정합니다. `--browser`는 실제 Chromium에서 네 상태가 5초 안에 읽히는지 확인하고, 전체 scenario·N≥3·browser를
  모두 포함한 실행만 `gate: full`입니다.
  Collector에 `--subscription-queue-maxsize`를 추가했습니다.
- Worker 종료 시 이미 dequeue된 notification의 spool 기록이 실패하면 log만 남기지 않고, 다른 종료 원인이 없으면
  `OpcUaUnpersistedNotificationError`로 실패(재시작)하고 있으면 그 예외에 note로 붙입니다.

- Collector `--pipeline-metrics` opt-in 진단(queue depth, 단계별 지연, event-loop lag; JSONL 기록은 event loop 밖),
  replay `--publish-ledger`(값·Good/Bad), `tools/opcua/replay_audit.py`(유실·중복·null 포함 값 불일치·품질 불일치,
  run 간 key 충돌 fail-fast). Replay는 null 기록을 0.0이 아닌 Null variant + Bad status로 publish합니다.

- Phase 10 AI-Hub replay soak/fault 검증에서 발견한 runtime 구분 문제를 고쳤습니다.
  - collector process가 종료되면 Monitor가 마지막 세션 보고("connected")를 그대로 보여 source 무소식과
    구분되지 않았습니다. Collection-service heartbeat(20초)·STOPPED·FAILED를 Collect 단계와 attention에
    반영하고, 그동안 source 상태는 Unavailable로, System 세션 수는 "last report"로 표시합니다. live
    telemetry가 있는데 heartbeat 기록이 아예 없으면(upgrade·유실·미기동) fail-closed로 Unavailable입니다.
  - source server 중단 시 이전의 무관한 worker 예외와 one-shot "waiting for data"가 표시됐습니다. 재연결 중
    세션은 "Source connection lost"로, 연결 거부로 멈춘 worker는 실제 연결 오류로 표시하고 live source에는
    one-shot receipt attention을 띄우지 않습니다. 새 worker가 빈 flow로 시작해도 이전 worker의 마지막 수신
    시각(receive clock)을 `last-receipt` telemetry로 유지하며, history commit 시각으로 대체하지 않습니다.
  - skip ledger가 가리키는 window가 없으면 전체 skip 목록을 버리지 않고 그 항목만 제외하고 System에 기록합니다.
  - incremental window coordinator 이후 System이 "Finalized windows 0"으로 보이던 window telemetry를
    누적값·마지막 finalized window 유지로 고쳤습니다.
  - 한 상이 빠져 series가 unresolved일 때 평가 0·제외 사유 없음으로만 보이던 결과에 이유를 표시하고,
    window에 상 channel이 없어 skip될 때 binding 문제로만 안내하던 사유 문구를 바로잡았습니다.
  - Monitor asset 표의 시각을 읽기 쉬운 UTC로 표시합니다.
- Monitor·Assets가 OPC UA 세션이 연결되어 있기만 하면 source를 "receiving data"로 표시하던 문제를
  고쳤습니다. **관측 시각 freshness**와 별개인 live-flow silence threshold로 마지막 실제 수신 이후
  무소식 시간을 판단하고, collector-service heartbeat / OPC UA session / receive flow를 서로 다른
  runtime 사실로 표시합니다. Phase 10 replay에서 collector가 장시간 연결 상태로 멈췄는데도 모든 단계가
  Running으로 보인 사례에서 발견했습니다.
- Operations V2가 분석 결과 또는 검토 요청이 하나라도 있으면 빈 화면이 되던 문제를 고쳤습니다.
  Investigations·Maintenance queue cell이 자신이 만든 selector 값을 같은 cell에서 읽어 marimo가 예외를
  냈고, 전체 화면이 그 cell에 의존했습니다. 모든 앱에 같은 패턴이 없는지 정적 검사를 추가했습니다.
- marimo 기본 light theme에서 V2 배경만 어둡고 marimo 위젯·markdown은 밝은 표면·어두운 글자로 그려져
  메뉴·표·제목이 읽히지 않던 문제를 고쳤습니다. V2 theme가 marimo의 dark palette를 고정합니다.

### Changed

- Canonical Operations app을 repository-local `apps/operations_v2.py`에서 wheel에 포함되는
  `industrial_phm.apps.operations_v2`로 이동하고, published `operations` extra가 history/OPC UA extras와
  marimo runtime을 함께 제공하도록 packaging 경계를 정리했습니다. Research Analysis Explorer는 기존
  repository app 경계를 유지합니다.

- Live Asset History writer의 새 batch preflight와 append 내부 identity check를 하나의
  `append-or-recover` 계약으로 합쳤습니다. Current batch recovery는 rebuildable
  `<catalog>.phm-batch-index.sqlite`의 batch→snapshot mapping을 사용하되 DuckLake commit
  provenance를 직접 검증하며, sidecar miss/손상은 source scan 후 self-heal합니다. N=10,000
  metadata-only profile에서 exact retry는 0.453 s → 0.279 s로 줄고 all-snapshot provenance scan이
  사라졌습니다. sidecar는 evidence가 아니며 삭제해도 durable history/recovery identity가 유지됩니다.

- Operations V2의 3상 분석 결과 조회를 누적 결과 전체 로드에서 최근 500건 bounded query로 바꿨습니다. 사람의 review가 참조하는 과거 AnalysisRun은 limit 밖이어도 exact lookup으로 다시 합쳐 Investigation/Maintenance evidence를 유지하며, 결과 저장·retention에는 영향을 주지 않습니다.
- Operations V2 **Phase 10 pre-soak hardening**을 완료했습니다. AI-Hub 239 recorded power를
  local OPC UA로 replay하는 개발 도구를 추가하고, first publish 전 node는
  `BadWaitingForInitialData`로 유지해 원본에 없는 Good 0.0 observation을 만들지 않습니다.
  Continuous observation-window coordinator는 full-history rebuild를 반복하지 않고 bounded durable-ingestion
  cursor로 새 event만 처리하며, finalized window와 cursor/watermark/active-buffer restart state를
  SQLite WAL의 같은 transaction에 기록합니다. Analysis runner도 capability/algorithm/policy cursor 이후
  window만 처리하고 SQLite skip ledger를 유지합니다.

- Operations V2 Phase 10 UX 검증에서 발견된 운영 gap을 보강했습니다. Collection request와 실제
  collector heartbeat/session/live receive를 분리하고, Assets → Analysis에서 Analyzed/Skipped attempt와
  exact skip reason을 확인할 수 있게 했습니다. Investigations는 30초 window 결과를 flat queue로
  나열하지 않고 asset + capability + human-review state로 그룹화하되 exact AnalysisRun evidence를
  그룹 안에서 선택할 수 있습니다. Needs attention 상세문구, readable UTC time, responsive/dark evidence
  graph, Setup desired-state wording도 함께 정리했습니다.

- Operations V2 **Phase 9 legacy migration**을 완료했습니다. `apps/operations_v2.py`를 canonical
  Operations surface로 승격하고 Interactive Analysis의 registered-source export도 V2를 검증하도록
  전환했습니다. Source별 데이터 경과 시간 정책을 Setup으로, one-shot source cycle과 bounded OPC UA
  subscription을 Setup **Advanced diagnostics**로, FILE snapshot vibration feature analysis를
  **Assets → Analysis**로 이관했습니다. V2 session은 새 FILE analysis evidence를 Assets와
  Investigations에 즉시 반영하며, legacy `apps/operations.py` application은 제거했습니다.

- Operations V2 **Setup**을 Data Sources / Signal Mapping / Measurement Semantics / Analysis Configuration으로
  분리하고 source registration/control workflow를 이관했습니다. Add Source는 FILE discovery 또는 bounded
  OPC UA browse 후 explicit signal mapping을 선택하고, OPC UA measurement meaning은 channel별 version과
  interpretation/unit evidence가 있을 때만 `ChannelSemanticBinding`으로 저장합니다. 미확정 signal은
  `Unresolved`로 유지하며 BrowseName·NodeId에서 의미를 추론하지 않습니다. Enable/Pause는 administrative
  use state, Start/Stop collection은 collector desired-state request로 유지해 connection/process-running
  증거와 구분합니다. 기존 등록 config와 analysis policy는 안전한 update contract가 없는 범위에서 read-only로
  표시합니다.

- Operations V2 **System**을 live acquisition / history storage / analysis service / current state read로
  분리한 runtime workspace로 연결했습니다. Persistent acquisition telemetry와 analysis-runner heartbeat처럼
  실제 계측된 evidence만 primary 상태로 사용하고, Operations application process heartbeat는 계측되지 않은
  상태를 **Not instrumented**로 명시합니다. 현재 state-read 오류는 별도 error 목록으로 표시하며 repository
  path와 local state 위치는 **Advanced diagnostics**로 내려 primary 운영 화면에서 숨깁니다.

- Operations V2 **Maintenance**를 Open / Acknowledged / Closed review 업무 queue로 이관했습니다.
  Status / Asset filter, selected review summary, append-only timeline, note / acknowledge / close action을 같은
  workspace에서 처리합니다. 상태 변경 후 같은 finding selection을 유지하고 Investigation과 review-event
  state를 공유합니다. Internal finding/run identity는 detail로 내려 primary queue에서 숨기며, acknowledge와
  close는 fault·repair·asset health·CMMS work order를 확정하지 않습니다.

- Operations V2 **Investigations**를 queue + selected detail workspace로 이관했습니다. 저장된 operational
  analysis를 Review / Asset / Capability로 필터링하고, review workflow 상태와 analysis evidence 의미를
  분리합니다. Three-phase unbalance와 FILE vibration feature evidence를 capability별로 검토할 수 있고
  run/evidence/finding identity는 detail로 내려 primary queue에서 숨깁니다. `Not requested` 결과에 대한
  **Request review**만 명시적 write action으로 제공하며, 저장 직후 queue를 다시 읽어 `Open` 상태를
  반영합니다. 이 action은 fault/alarm/health/maintenance verdict를 생성하지 않습니다.

- Operations V2 **Assets**를 실제 read-only workspace로 연결했습니다. Monitor/history의 asset 합집합을
  선택하고 Overview / Signals / Analysis / Events / Maintenance를 같은 설비 context에서 확인합니다.
  Signals는 기존 DuckLake Asset History의 raw/aggregate/latest semantics를 재사용하고, history-only asset은
  live status를 추론하지 않습니다. Source 상태는 Monitor와 같은 persistent acquisition telemetry projection을
  사용하며 history query failure는 Signals에만 격리합니다.

- Operations V2 foundation을 추가했습니다. `apps/operations_v2.py`는 메인 배경 `#292827`의
  Monitor 중심 shell에서 Source → Collect → Store → Analyze → Review 흐름, 현재 attention, asset 요약과
  recent activity를 기존 operational evidence로 읽습니다. 기존 Operations action UI는 마이그레이션 동안
  유지하며 V2 Monitor는 state를 직접 변경하지 않습니다. 독립 `run-window-analysis` process는 별도
  runtime telemetry에 heartbeat, 최근 성공/skip/failure와 누적 처리 수를 기록해 수집과 분석 중단을
  화면에서 구분할 수 있게 했습니다.

- Operations의 Asset Detail·Investigation에 **Refresh analysis results**를 추가했습니다. 별도
  `run-window-analysis` process가 기록한 3상 불평형 결과를 앱 재시작 없이 다시 읽고, 선택 중인 분석은
  refresh 후에도 유지합니다. 읽기 실패 시 마지막 성공 결과와 실패 상태를 구분해 표시하며 Operations는 runner
  lifecycle을 소유하지 않습니다.

- Operations의 OPC UA **Add source**에서 channel별 measurement semantics를 explicit CSV row로 등록할 수
  있습니다. observed property/scope/statistic/unit, semantic version과 interpretation/unit evidence를
  versioned `ChannelSemanticBinding`으로 저장하며 browse name·channel ID·NodeId에서는 물리 의미를
  추론하지 않습니다. 입력하지 않은 channel은 기존처럼 unresolved로 유지하고 등록된 binding은 Source
  detail에서 확인할 수 있습니다.

- 문서 Source of Truth를 재정리했습니다. `docs/status.md`가 현재 구현·지원·현장검증 상태를 단독 소유하고,
  README는 제품 목적/진입점, Architecture는 장기 책임/contract, ADR은 구조 결정, subsystem README는 실행
  절차를 소유합니다. 계획된 작업·milestone은 Issue/PR에서 관리하며 Architecture에 PR 번호나 진행 상태를
  복제하지 않습니다. OPC UA three-phase runbook은 live runner와 Operations가 같은 analysis result path를
  사용하도록 명시합니다.

- Asset Detail의 최신 관측·이력 page·집계가 OPC UA 값에도 수집 시 raw evidence에 고정한 semantic snapshot
  (측정 의미·단위·version)을 표시합니다. Snapshot의 source/channel이 raw row와 다르면 FILE과 같이
  `unresolved`/`unknown`으로 표시합니다.

- ADR-0009: 다채널 시간 정렬을 protocol과 무관한 versioned 정책으로 분리했습니다(`application/alignment.py`,
  새 dependency 없음). 기본 `strict-v1`은 기존 결과·분석 identity와 같고, `bounded-previous-v1`은 이전 값만
  명시적 `max_age`·근거 안에서 carry합니다. Evidence에는 kind·max age·basis와 carried 값 수·age를 남기고,
  계산 identity에는 결과를 바꾸는 kind·max age만 포함합니다. `bounded-previous-v1`은 모든 requested channel
  event timestamp를 anchor로 쓰는 event-transition state reconstruction이며 synchronized acquisition-cycle을
  주장하지 않습니다. `run-window-analysis`에 `--alignment` 옵션을 추가했습니다.

- `industrial-phm operations run-window-analysis`: finalized live window를 collection service와 별도 process로
  분석합니다. 결과 저장소 기준 idempotency(window·capability·algorithm·analysis policy identity당 1회 persist,
  파일 lock), 분석 불가 window의 policy-scoped skip ledger로 재시작에도 동일 identity 중복이 없습니다.
  Collection service에 window 길이·lateness
  옵션, OPC UA demo에 semantic binding이 있는 three-phase profile을 추가하고 loopback E2E로 검증했습니다.

- ADR-0008: live 분석의 입력은 finalized window가 accept한 event 집합이며 history 재조회를 하지 않습니다.
  `run_phase_unbalance_on_window`가 window event를 history와 같은 입력 형태로 투영해 같은 capability core로
  분석하고, window ID·accept/reject 수·accept event digest를 입력 근거로 기록합니다. Live runner의
  중복 방지용 analysis policy digest는 role 선택 전 요청 설정(channel override·저신호 기준·bucket 수)을
  canonical하게 고정해 설정 변경 재분석이 이전 결과에 막히지 않게 합니다.

- 3상 불평형 입력 channel을 AI-Hub 이름 대신 bound meaning(phase voltage/current, scope phase R/S/T,
  V/A)으로 고릅니다. 모호한 역할은 명시적 설정을 요구하고, evidence에 quantity별 사용 channel과 선택 방식을
  남깁니다. 같은 규칙이 현장 OPC UA channel 이름에도 적용됩니다.

- OPC UA DataChange의 semantic binding snapshot을 DuckLake raw evidence에 보존하고 복원합니다. History에서
  다시 만든 window도 같은 의미를 가지며, 분석 입력 조회가 FILE과 OPC UA 의미를 같은 형태로 읽어 OPC UA
  source도 3상 불평형 eligibility를 통과할 수 있습니다. 기존 catalog는 컬럼을 한 번 추가하고 이전 행과
  이전 snapshot은 미확정으로 읽습니다. OPC UA batch fingerprint에 version(`opcua-semantic-v2`)을 두어,
  이전 writer가 semantic 포함 spool batch를 의미 없이 commit한 뒤 ACK 전에 멈춘 경우도 업그레이드 후
  복구되며 그 행은 의미를 소급하지 않습니다. 분석 입력은 binding의 source/channel이 raw 행과 일치할
  때만 의미를 인정합니다.
- 제품 문서의 포지셔닝 문장을 목적 중심으로 바꾸고 evidence·provenance는 설계 원칙으로 내렸습니다.
  현재 운영 경로, architecture 상세 runtime 그림, registry v5 표기를 main 기준으로 맞췄습니다.
- README 현재 구현 범위를 main 기준(측정 의미, 3상 불평형, Investigation·사람의 검토)으로 갱신했습니다.

- 3상 불평형의 analysis exclusion과 source data quality를 분리했습니다. 미확정 semantics, 불완전한 3상 정렬, 저신호 구간은 capability eligibility 근거로 유지하되 `AnalysisRun.data_quality` warning으로 승격하지 않고, null·conflicting value·protocol non-good만 source-quality issue로 기록합니다.

- 3상 불평형 분석의 p95를 작은 표본에서도 관측 min/max 범위를 벗어나지 않는 inclusive empirical quantile로 고정하고 algorithm version을 `phase-unbalance-max-deviation-v2`로 올렸습니다. 한 source에 여러 measurement point가 있으면 명시적으로 point를 선택하지 않는 분석은 fail-closed해 서로 다른 측정점의 분포가 한 결과로 합쳐지지 않게 했습니다.

- 분석 결과를 capability와 무관하게 다룹니다(`OperationalAnalysisResult`). Asset Detail·Overview 분석 수,
  Investigation의 검토 대상 선택·근거 표시·review finding 생성이 FILE 특징 분석과 3상 불평형을 함께
  지원하며, Maintenance Review는 finding의 capability·분석 run·evidence를 보여줍니다.

- Operations Asset Detail에 전력 품질 분석 · 3상 불평형을 추가했습니다. Source·구간을 골라 실행하고
  요약, 시간 구간 그래프, 제외 사유, 입력·버전·설정 근거와 이전 분석 기록을 확인합니다.

- 첫 label-free 전력 분석 capability `three-phase-unbalance-v1`을 추가했습니다. 확정된 상전압(V)·상전류(A)만
  고정된 history snapshot에서 읽어 timestamp별 불평형률 분포와 제외 사유, 입력·버전·설정을 evidence로
  남기며 같은 snapshot으로 동일하게 재현됩니다. 고장·건강·alarm 판정이 아닙니다.
- History 조회의 raw FILE join을 equality key만 쓰도록 바꿔 결과는 같고 전체 기간 집계가 0.59초 → 0.17초가
  됐습니다.

- AI-Hub 239 측정 의미 근거를 전체 archive relation profile(`tools/aihub/relation_profile.py`, 29 member)로
  재현 가능하게 만들었습니다. 5개 member로 만든 `semantics-v1`이 몰랐던 4개 member 예외(전압 관계, 선간전압
  평균, 전류 스케일)를 반영해 `semantics-v2`(metadata v4, 기본값)를 추가하고 v1은 수정하지 않았습니다.
  Version별 payload digest를 고정하고, import 결과에 schema·semantic version·dictionary digest를 기록합니다.

- AI-Hub 239 구축·활용 가이드라인의 단위 표와 실제 데이터의 물리 관계(선간/상 √3, P=V·I·PF, 3상 평균)를
  대조해, 둘이 일치하는 주파수(Hz)·상전압/선간전압 평균(V)·상전류(A)만 `aihub-239-semantics-v1`로
  확정했습니다(history metadata v3). 유효/무효전력(문서 kW·kVar, 실제 W·var 스케일, "평균"은 3상 합),
  역률(문서 %, 실제 비율)과 누적전력량은 불일치로 미확정 유지합니다. Label 산정 방법(1시간 구간 사람
  labeling, SOH는 전력 품질 기준 등급)을 문서 근거로 기록했습니다.

- README와 architecture overview가 같은 대표 시스템 구조(Data Sources → Acquisition & History → PHM
  Analysis & Evidence → Operations & Review → Human Decision)를 사용합니다. 상세 runtime은 overview로
  옮기고, production/research path 경계와 provider annotation·ground truth vocabulary를 정리했습니다.

- AI-Hub 239 보일러·압출기 라벨링 데이터 acquisition preset과 streaming label profiler를 추가했습니다.
  기동패턴(Stop/Loading/Unloading)·SOH(정상/주의/경고) label 구조, 설비 metadata, raw와의 device·기간
  대응을 기록했습니다. Label 산정 방법과 측정 단위는 여전히 미확정으로 유지합니다.

- 이력 적재·조회 속도를 개선했습니다. DuckDB의 값별 pandas import 탐색을 제거하고 열 단위 insert로 바꿔
  압출기 48시간 적재가 161초 → 36초가 됐습니다(저장 결과 동일). 조회는 raw 근거 join 전에 같은
  설비·채널·시간으로 걸러 120만 건 기준 전체 기간 집계 14.9초 → 0.59초가 됐습니다.

- DuckLake Asset History에 inlined data flush를 추가했습니다. AI-Hub 적재는 10배치마다 Parquet으로
  옮기며, `industrial-phm operations flush-history`로 live/backfill 이력도 옮길 수 있습니다. snapshot
  time travel과 배치 재시도 복구는 유지됩니다. 실제 압출기 48시간 기준 catalog 240MB → 45MB + Parquet 21MB.

- 2,000개를 넘는 직접 지정 이력 범위는 첫 2,000개 대신 전체 기간 UI 집계로 표시해 과거 적재 설비도
  긴 기간을 대표할 수 있습니다. 이력 표의 event time을 그래프와 같은 UTC로 통일했습니다.
- 실제 압출기 48시간(100,800건) 적재 측정을 기록했습니다. DuckLake inlining으로 관측 1건당 약 2.4KB가
  SQLite catalog에 남으며, flush 시 약 11배 감소함을 근거로 저장 개선 우선순위를 조정했습니다.

- AI-Hub 의미 계약은 `observed_property=None`으로 미해석 상태를 표현합니다. 기존 raw label과
  metadata v1을 보존하며 legacy import 재개 옵션을 제공합니다. FILE source quality는 unknown으로
  읽고 numeric/null availability와 구분합니다.
- 최신 저장 관측은 history age로 표시하고 live freshness와 분리합니다. 24시간/7일은 전체 기간의
  UI min/max/mean bucket을 조회하며 원시 조회는 요청/반환 범위와 개수를 명시합니다.
- README 구조도를 현재 수집·history·Operations·검토 흐름의 Mermaid로 갱신하고 연구 PNG는 이전
  참고자료로 구분했습니다. 목표 사용자 요구와 현재 capability, metadata normalization 전환 조건을 문서화했습니다.

- 최신 저장 관측에도 원본 파일·checksum, 설비/시간대 매핑 근거, 단위 및 해석 version을 연결해
  차트 구간 밖의 최신값에서도 미확정 단위와 normalization 가정을 확인할 수 있습니다.

- 로컬 DuckLake SQLite catalog의 connection/transaction 수명 동안 프로세스 간 파일 잠금을 유지해
  독립 collector·window reader·Operations 조회의 metadata 잠금 충돌을 방지합니다. 기본 대기 한도는
  10초이며 timeout은 명시적으로 실패합니다. 여러 collector의 leadership을 대신하지 않습니다.

- FILE raw history는 null 값과 source-specific JSON provenance를 보존합니다. 기존 DuckLake 카탈로그의
  FILE 테이블을 확장하고 기존 batch fingerprint를 유지합니다. 새 연결에서 현재 history snapshot을
  조회할 때 connection-local last commit 대신 catalog의 최신 snapshot을 사용합니다.

- Continuous observation-window coordinator에서 current registered source mapping에 없는 unexpected OPC UA channel이 observation watermark를 전진시키지 않도록 수정했습니다. Unexpected event는 #257 `UNEXPECTED_CHANNEL` evidence로 유지하며, 기존 window buffer가 없을 때는 rejected event만으로 먼 미래 빈 window를 만들지 않습니다.

- Persistent OPC UA worker의 connection epoch를 source별 durable spool metadata에서 atomic reserve하도록 변경했습니다. Worker process restart가 epoch를 1부터 다시 사용해 과거 DuckLake raw delivery identity와 충돌할 수 있던 문제를 막고, stale expected epoch를 가진 concurrent worker는 fail-fast합니다. Epoch reservation 직후 crash로 생기는 gap은 허용하지만 `(source_id, connection_epoch, event_index)` identity 재사용은 허용하지 않습니다.

- Operations primary navigation에서 독립 **Data Quality** destination을 제거하고 품질/provenance evidence를 Sources, Assets, Investigation context로 이동했습니다. Sources는 선택 source와 일치하는 current loaded observation의 quality/source snapshot/validation policy를, Investigation은 실제 AnalysisRun input quality와 recorded source snapshot provenance를, Assets는 asset-scoped loaded observation provenance를 표시합니다. Quality evidence는 asset health나 diagnosis로 승격하지 않습니다.
- Operations의 Attention Queue, source data-flow, observation, data-quality Markdown 조립을 `industrial_phm.presentation`의 pure presenter로 분리했습니다. Presenter는 application read model을 표시 형식으로만 변환하고 PHM 의미를 만들지 않으며, `marimo`를 runtime dependency로 추가하지 않습니다. Interactive callout/layout/state wiring은 계속 `apps/operations.py`가 소유합니다.
- Operations를 `Source → Analyze → Results → Finding → Maintenance Review` vertical slice 중심으로 정리하고 primary navigation을 **Overview / Sources / Investigation / Data Quality / Maintenance Review / Operational State**로 축소했습니다. 사용자 action이 없던 Assets/Asset placeholder와 research-only Development RUL/review bridge는 Operations에서 제거했습니다. Persistent OPC UA session/continuous ingestion과 validated automatic PHM semantics는 별도 후속 영역입니다.
- Source runtime state는 current `industrial-phm-source-runtime-v3`만 읽고 쓰며 latest bounded connection-attempt evidence에 producer operation을 필수로 기록합니다. OPC UA one-shot read는 `opcua-read`, bounded subscription runtime은 `opcua-subscription`을 기록하고 Operations Sources는 operation/outcome/timing/detail을 표시합니다. Pre-alpha v1/v2 runtime state는 자동 migration하지 않습니다.
- OPC UA read, bounded browse, bounded subscription의 `completed_at`을 client/subscription context teardown이 성공적으로 끝난 뒤 기록하도록 정리했습니다. 따라서 successful bounded result의 completion time은 connector 작업뿐 아니라 해당 context의 정상 종료까지 포함합니다.
- OPC UA one-shot runtime에서 failure ownership과 administrative lifecycle을 분리했습니다. Explicit OPC UA data-contract failure는 기존처럼 `FAILED/SOURCE`와 함께 `ACTIVE → ERROR`로 전이하지만, connection refused 같은 transport `OSError`는 failed connection-attempt evidence와 `SOURCE` scope를 보존하면서 lifecycle은 `ACTIVE`로 유지합니다. 현재 polling은 여전히 failed cycle에서 중지하며 자동 retry/backoff는 추가하지 않았습니다.
- Operations의 source entry point를 **Sources** 하나로 통일했습니다. Overview의 별도 prepared-source path/mapping 입력과 direct load path는 제거했고 FILE snapshot/history-directory와 OPC UA 모두 Sources의 registration/load/runtime 경계를 사용합니다.
- Operational `AnalysisRun`의 observation/execution window와 `OperationalFinding.observed_at`을 timezone-aware absolute time으로 강제하고, finding/run validator가 `finding.capability_id`가 해당 run의 declared `capability_ids`에 포함되는지 확인하도록 강화했습니다. Ambiguous naive operational time과 run이 생산하지 않은 capability finding의 provenance 승격을 fail-fast로 차단합니다.

### Added

- `tools/opcua/aihub_replay.py`: AI-Hub 239 전력 원본 selection을 로컬 OPC UA server로 replay합니다.
  값은 그대로, 시간만 replay clock으로 옮기며(`--speed`, 원본 시각 대응은 `replay-log.jsonl`) 같은 시각에
  서로 다른 값이 기록된 channel은 Bad status로 publish합니다. AI-Hub semantics-v2가 근거를 가진 channel만
  semantic binding으로 등록하고, 누락 phase(`--omit-channel`)·stale data(`--freeze-after-records`)
  시나리오를 제공합니다. 첫 실제 publish 전 node는 BadWaitingForInitialData로 유지해 synthetic Good
  observation을 만들지 않습니다. Operations V2 Phase 10 로컬 검증용 도구이며 production connector가 아닙니다.

- OPC UA source registration에 versioned channel semantic binding을 추가하고, 수집 시점의 binding snapshot을 각 DataChange event에 복사해 durable spool과 finalized observation window 재시작 이후에도 같은 의미 근거를 보존합니다. NodeId/channel 이름에서 물리 의미를 추론하지 않으며 source/channel identity가 맞지 않는 binding은 fail-closed합니다. Source registry schema는 v5로 갱신됩니다.

- Operations 측정 이력에 최근 15분/24시간/7일 범위와 source별 최신 저장값·event-time freshness를
  추가했습니다. 최신값은 그래프의 범위/점 개수 제한과 별도로 조회하고 값 충돌을 임의로 해결하지 않습니다.
- 합성 FILE 이력과 loopback OPC UA simulator를 사용하는 로컬 스택 및 독립 collector process 회귀
  검증을 추가했습니다. 서버 재연결, collector restart/epoch, 동시 history 조회와 Stop Collection을 확인합니다.

- AI-Hub 239 ZIP의 streaming reader, 전체 archive profiler와 명시적인 설비·timezone binding을 사용하는
  소구간 history importer를 추가했습니다. 원본 null·중복을 보존하며 단위는 추정하지 않습니다.
- Operations Asset Detail에 FILE/OPC UA 공통 측정 이력 조회를 추가했습니다. 시간·채널 선택,
  2,000개 관측 한도, null·충돌 표시와 매핑 provenance를 제공하며 보간하거나 건강 판정을 만들지 않습니다.

- Live Acquisition & Asset History v1의 bounded live-acquisition reliability profile을 추가했습니다. 192 durable deliveries, collector epoch restart, identical retry, replay, out-of-order event time, temporary DuckLake failure, stable active-batch writer restart, full history drain, deterministic window rebuild, telemetry consistency를 CI에서 검증합니다. Continuous history writer는 transient downstream exception을 동일 active batch로 재시도하며 identity/spool invariant 오류는 fail-fast합니다. 상세 data-loss/duplicate claims와 기존 reconnect/overflow/backfill tests의 scenario matrix는 `docs/architecture/live-acquisition-reliability-v1.md`에 정리했습니다.

- Registered timestamped FILE source를 DuckLake Asset History로 backfill하는 경계를 추가했습니다. CSV adapter의 timezone-aware source timestamp와 기존 asset/measurement-point/channel mapping을 재사용해 source-specific `raw.file_measurement` evidence와 common `history.measurement`을 하나의 DuckLake transaction에 기록합니다. Source ID/file name/exact SHA-256/sample/channel identity로 stable raw evidence와 batch checkpoint를 만들며 동일 snapshot 재실행은 기존 snapshot을 idempotent하게 복구합니다. 다른 FILE snapshot이나 live OPC UA delivery가 같은 event time/value와 겹쳐도 provenance가 다르면 삭제하지 않습니다. `HistoricalInputReference`가 현재 DuckLake snapshot ID와 half-open asset/time/channel input range를 baseline/analysis provenance로 기록할 수 있게 합니다.

- Operations에 durable desired collection control-plane과 independent collection service를 추가했습니다. OPC UA ACTIVE source의 Start/Stop Collection은 SQLite WAL control store의 RUNNING/STOPPED intent만 갱신하며 lifecycle을 변경하거나 UI process에서 collector를 실행하지 않습니다. 별도 `industrial-phm operations run-collection-service` process가 desired state를 reconcile해 persistent worker/window coordinator를 source별로 소유하고 shared spool→DuckLake writer를 유지합니다. Sources live monitor는 #264 telemetry와 durable spool snapshot을 읽어 lifecycle / desired state / observed session / event flow / backlog / DuckLake snapshot / watermark를 분리해 표시하고 UI 종료를 collector stop으로 해석하지 않습니다.

- SQLite WAL 기반 live acquisition telemetry boundary를 추가했습니다. Persistent OPC UA session/flow, reconnect/overflow, replay/bad-status count, latest DuckLake acknowledged batch/snapshot, window/watermark/#257 disposition, runtime failure를 source별 독립 latest component로 restart-safe하게 보존하고 durable spool backlog/oldest age/active batch는 spool DB에서 직접 sample합니다. Event rate는 worker-start 이후 lifetime average로 명시하며 asyncua private queue API에는 의존하지 않아 callback queue depth/high-watermark는 현재 uninstrumented이고 configured maxsize/overflow만 factual evidence로 제공합니다. Telemetry에는 synthetic healthy boolean이 없고 telemetry write failure가 spool/DuckLake/window data-plane truth를 rollback하지 않습니다.

- DuckLake raw OPC UA history를 deterministic durable-ingestion order로 replay하는 continuous observation-window coordinator를 추가했습니다. Fixed alignment window와 `max(valid event_at seen) - allowed_lateness` watermark policy를 적용하고 #257의 IN_ORDER / OUT_OF_ORDER / LATE / TIMING_UNAVAILABLE / UNEXPECTED_CHANNEL / FUTURE_TIMESTAMP / BUFFER_FULL 의미를 유지합니다. Finalization 시각은 wall clock이 아니라 watermark를 전진시킨 durable event의 `ingested_at`을 사용해 restart 후 동일 history에서 동일 finalized window를 재구성합니다. Closed-window late event는 factual LATE evidence로 반환하지만 이미 persisted된 window를 사후 수정하지 않습니다.

- spool-to-DuckLake micro-batch writer를 추가했습니다. Durable spool의 unassigned event를 max events / max bytes / max interval policy로 stable batch에 묶고, DuckLake historical transaction이 성공한 뒤에만 spool에서 acknowledge합니다. DuckLake snapshot commit_extra_info에 batch ID, ingestion mode, event count와 canonical event fingerprint를 기록해 commit 성공 직후/ACK 직전 crash가 발생해도 같은 active batch를 기존 snapshot으로 복구하고 중복 historical row 없이 ACK를 완료합니다. 같은 batch ID의 다른 payload는 conflict로 fail-fast합니다.

- ACTIVE registered OPC UA source를 위한 long-lived OPC UA acquisition worker를 추가했습니다. asyncua 2.0.1의 auto-reconnect와 subscription recreation/Republish를 사용하고, 공개 connection state transition을 #256 `RECONNECT_WAIT → CONNECTING → CONNECTED` evidence로 projection합니다. DataChange는 replay flag와 protocol timestamp/quality를 보존해 #260 SQLite WAL spool에 durable acceptance하며 connection epoch별 local event index를 관리합니다. Bounded subscription queue overflow는 명시적 evidence로 기록한 뒤 reconnect를 강제하고, graceful stop/spool failure는 source lifecycle이나 asset health verdict로 승격하지 않습니다.

- SQLite WAL 기반 durable acquisition spool을 추가했습니다. OPC UA DataChange는 durable transaction 안에서 #256 persistent/event-time contract로 projection되고 local delivery identity로 idempotent하게 저장됩니다. Spool은 bounded capacity와 `synchronous=FULL`을 사용하며, oldest pending event를 하나의 stable active batch에 assign해 process restart 후에도 같은 batch ID와 event order를 복원합니다. DuckLake/history commit 전까지 event를 유지하고 explicit downstream acknowledgement 이후에만 제거합니다.

- DuckLake 기반 historical Asset History boundary를 추가했습니다. Optional `history` runtime은 SQLite catalog + local Parquet DuckLake를 bootstrap하고 OPC UA persistent DataChange batch의 raw protocol/timing/replay evidence와 normalized asset/measurement/channel history를 하나의 transaction에 기록합니다. Commit은 DuckLake snapshot ID/time을 반환하며 asset event-time range query와 local delivery identity 기반 raw-event round-trip을 제공합니다. DuckLake는 ingress queue/WAL 역할을 하지 않으며 동일 batch ID 재시도는 snapshot provenance와 event fingerprint가 정확히 일치할 때만 idempotent하게 복구하고, 다른 payload는 conflict로 거부합니다.

- `Live Acquisition & DuckLake Asset History v1` architecture boundary를 추가했습니다. Continuous source worker, bounded callback queue, SQLite WAL durable ingress spool, DuckLake historical Asset History, derived observation window와 PHM evidence의 ownership을 분리하고, Live/Backfill 통합 provenance, at-least-once compatible delivery, restart semantics와 #259~#267 구현 순서를 고정했습니다. DuckLake를 callback queue/WAL로 사용하거나 acquisition health를 asset health로 승격하지 않습니다.

- Explicit event-time range와 caller-owned monotonic watermark를 사용하는 bounded `ObservationWindowBuffer`와 finalized `DurableObservationWindow`, `industrial-phm-observation-window-v1` JSON repository를 추가했습니다. In-order/out-of-order, late, local-delivery duplicate, timing unavailable, unexpected channel, outside-window, future clock-skew, buffer-full을 factual disposition으로 구분하고 finalized window에 rejection count와 accepted event의 원본 protocol/timing evidence를 보존합니다. COMPLETE는 expected-channel coverage일 뿐 synchronized/gap-free/exactly-once/analysis-ready 의미가 아니며 partial in-memory buffer는 아직 durable하지 않습니다.
- Persistent OPC UA 구현 전에 `OpcUaPersistentSessionPolicy/Evidence`, reconnect state transition validator와 `OpcUaEventTimeEvidence` / `OpcUaPersistentDataChangeEvent` 계약을 추가했습니다. Successful connect에서만 connection epoch를, retry 시작에서만 reconnect attempt를 증가시키며 SourceTimestamp를 event time으로 우선합니다. ServerTimestamp fallback은 explicit opt-in이고 received_at/ingested_at은 event time으로 승격하지 않습니다. Local event index는 server sequence나 gap-free delivery를 의미하지 않으며 실제 reconnect daemon/persistence/windowing은 아직 구현하지 않습니다.
- Operations primary navigation에 **Assets**를 추가하고 source/loaded observation/AnalysisRun/OperationalFinding의 asset identity union에서 Asset Detail을 구성합니다. Detail은 source mapping/data-flow, contextual data quality, analysis/finding/review evidence를 같은 physical asset context에 모으며, Evidence Timeline은 registration/lifecycle/source observation/platform receipt/analysis/capability/finding/review의 time basis를 분리합니다. Timezone-naive 또는 missing time은 chronology에 섞지 않고 **Time not comparable** evidence로 보존합니다.
- Operations Overview에 evidence-based **Attention Queue**를 추가했습니다. `SOURCE_ERROR / NO_RECEIPT / STALE / DATA_QUALITY_ISSUE / REVIEW_REQUIRED / SYSTEM_STATE_ERROR`만 factual category로 projection하고, OPEN review를 UNHANDLED로 구분한 뒤 evidence time으로 deterministic ordering합니다. PHM severity/risk score/alarm priority는 만들지 않으며 Data Quality attention은 현재 로드된 observation evidence 범위로 명시적으로 제한합니다.
- Operations Overview의 source/lifecycle/runtime/analysis/finding/review 집계를 `OperationsOverview` application read model로 분리했습니다. 이미 로드된 operational fact를 deterministic하게 결합하고 기존 `SourceHealthAssessment` data-flow dimension과 human review disposition을 재사용하며, UI가 repository state를 직접 집계하거나 source freshness를 asset health/fleet risk로 승격하지 않도록 경계를 고정했습니다.
- Operations v2의 asset-centric read model 기반으로 `AssetIdentity`, `ComponentIdentity`, `MeasurementPointIdentity`, `ChannelIdentity` application contract를 추가했습니다. 기존 source registry/runtime JSON schema를 변경하지 않고 RegisteredSource, AssetObservationSummary/Timeline, AnalysisRun과 OperationalFinding이 동일한 physical asset/measurement-point/channel identity를 projection합니다. 현재 mapping에 없는 component hierarchy는 추론하지 않습니다.
- Operations Overview에 **Prepare bundled demo source** onboarding action을 추가했습니다. 저장소의 `examples/operations/demo-bearing-snapshot.csv` synthetic snapshot을 정상 FILE registration/validation 경로로 등록 또는 재검증하고 current observation을 로드해, 외부 데이터 없이 Sources analysis → Investigation review finding → Maintenance Review note/acknowledge/close → Operational State까지 제품 workflow를 따라갈 수 있습니다. Contract test는 bundled input이 32-sample timezone-aware snapshot으로 validation과 `vibration-statistical-v1` operational feature analysis를 통과하는지 검증합니다. Demo signal은 실제 fault/degradation/RUL evidence가 아닙니다.
- Operations **Operational State**가 source registry/runtime, operational analysis history, finding history, Maintenance Review state의 readable/error 상태와 저장 경로/recorded population을 표시합니다. Registered/ACTIVE source 수, latest analysis, finding 수와 review OPEN/ACKNOWLEDGED/CLOSED 집계도 제공하지만 AVAILABLE은 local repository read 가능성을 뜻할 뿐 service SLA나 asset health가 아닙니다. Persistent OPC UA session, ingestion backlog/latency, worker/process, logs/metrics/traces는 아직 instrumented telemetry가 아닙니다.
- Operations에 실제 **Maintenance Review** workflow를 추가했습니다. Durable `REVIEW_REQUIRED` finding을 선택해 append-only note를 남기고 `OPEN → ACKNOWLEDGED → CLOSED`로 human review disposition을 기록하며, `industrial-phm-finding-review-v1` local state에 재시작 가능한 event history를 보존합니다. Acknowledge는 검토 책임 수락, Close는 review workflow 종료만 뜻하며 fault 확인, repair completion, asset health, work order/CMMS 실행으로 해석하지 않습니다.
- Operations Investigation에 **Create review finding** 사용자 action을 추가했습니다. 저장된 operational feature `AnalysisRun`을 사용자가 직접 검토 대상으로 승격하면 `human-review-request-v1 / REVIEW_REQUIRED` `OperationalFinding`을 evidence-linked 형태로 생성하고 `industrial-phm-operational-findings-v1` local JSON history에 영속합니다. 이 finding은 수동 workflow request이며 feature 값에 대한 anomaly/fault/health/alarm 자동 판정이 아닙니다.
- Operational FILE feature analysis 결과를 `industrial-phm-field-feature-analysis-v1` local JSON history에 영속하는 `JsonFieldFeatureAnalysisRepository`를 추가했습니다. `AnalysisRun`, data-quality issues, source snapshot provenance와 capability-specific feature evidence를 round-trip하고 run/evidence identity 충돌을 차단합니다. Operations는 기본 `artifacts/operations/field-analysis.json`을 사용하며 `INDUSTRIAL_PHM_OPERATIONS_ANALYSIS_STATE`로 경로를 바꿀 수 있고, Investigation에서 재시작 후 latest run과 recent history를 다시 표시합니다.
- Registered **FILE snapshot**을 현재 bytes에서 다시 검증하고 existing `CsvSensorAdapter → CanonicalTimeSeries → vibration-statistical-v1` 경계로 분석하는 `run_registered_file_feature_analysis`를 추가했습니다. Timezone-aware source timestamp가 있는 snapshot에서 실제 `AnalysisRun`과 `field-vibration-statistical-features-v1` evidence를 만들며 Operations Sources의 **Analyze FILE snapshot** action과 Investigation에서 run/provenance/feature values를 표시합니다. 이 v1은 history-directory/OPC UA/naive timestamp를 지원하지 않고 feature evidence를 anomaly/fault/health/finding으로 자동 승격하지 않습니다. 후속 analysis-history state가 run/evidence를 durable local history로 보존합니다.
- Analysis review acknowledgement를 `industrial-phm-analysis-review-v1` local JSON state에 영속합니다. Record는 exact analysis artifact SHA-256, artifact path, asset, versioned review-policy ID/threshold, review interval count, timezone-aware reviewed-at과 optional note를 보존하며 같은 evidence/asset/policy의 최신 review만 갱신합니다. Analysis Explorer는 앱 재시작 후 이 기록을 복원하고 `INDUSTRIAL_PHM_ANALYSIS_REVIEW_STATE`로 저장 경로를 바꿀 수 있습니다. 이 state는 OperationalFinding이나 maintenance work order가 아닙니다.
- Analysis Explorer에 **검토 및 조치** 화면을 추가했습니다. Existing descriptive review interval이 있으면 우선 확인 구간과 threshold를 보고 메모를 남긴 뒤 검토 완료로 표시할 수 있습니다. acknowledgement는 후속 durable review state에 저장되지만 `OperationalFinding`, fault diagnosis, maintenance work order/CMMS 기록으로 승격하지 않으며, interval 부재도 정상 판정으로 승격하지 않습니다.
- Operations Sources에 ACTIVE OPC UA source용 **Collect bounded subscription** action을 추가했습니다. UI는 5초 timeout, 500 ms publishing interval, registered channel 수와 동일한 max-events bound로 한 번 실행하고 completion reason, notification count, configured/observed/missing channel coverage, collected channel value/OPC UA status/SourceTimestamp/received_at/replayed evidence를 표시합니다. Full coverage도 synchronized snapshot이나 analysis-ready window로 해석하지 않으며, 성공 시 latest `opcua-subscription` connection-attempt evidence만 갱신하고 receipt/freshness는 변경하지 않습니다.
- ACTIVE registered OPC UA source의 bounded subscription을 lifecycle-aware runtime cycle로 실행하는 `run_registered_opcua_subscription_cycle`을 추가했습니다. 성공 cycle은 latest `SourceConnectionAttemptEvidence`만 기록하고 `SourceReceiptEvidence`나 freshness는 갱신하지 않습니다. 현재 writer에서는 이 attempt를 runtime-state v3의 `opcua-subscription` operation으로 보존합니다. OPC UA data-contract failure는 `FAILED/SOURCE`와 `ACTIVE → ERROR`, transport `OSError`는 `FAILED/SOURCE`와 ACTIVE 유지, runtime/persistence failure는 `FAILED/PLATFORM`과 lifecycle 유지로 one-shot runtime 의미를 재사용합니다. Real asyncua contract는 실제 bounded subscription cycle의 attempt persistence와 receipt 부재를 검증합니다.
- Registered OPC UA bounded subscription에 `RegisteredOpcUaSubscriptionCoverage`를 추가해 configured/observed/missing channel과 notification count를 명시적으로 계산합니다. `has_full_channel_coverage`는 모든 registered channel이 해당 bounded collection에서 최소 한 번 관측됐다는 뜻만 가지며 timestamp alignment, synchronized snapshot, gap-free delivery, analysis-ready observation/window를 의미하지 않습니다. `MAX_EVENTS` 종료도 full coverage를 보장하지 않는 회귀 테스트를 추가했습니다.
- Registered OPC UA bounded subscription notification을 source/asset/measurement-point/endpoint identity와 결합하는 `RegisteredOpcUaDataChangeEvent` application contract를 추가했습니다. `RegisteredOpcUaSubscription.events`는 connector quality/timestamp/replayed evidence를 그대로 보존하면서 zero-based `collection_index`를 부여합니다. 이 index는 bounded result 안의 로컬 수집 순서일 뿐 OPC UA server sequence나 gap-free delivery evidence로 해석하지 않습니다.
- ACTIVE registered OPC UA source의 persisted endpoint/NodeId mapping과 timeout을 재사용해 bounded DataChange session을 한 번 수집하는 `collect_registered_opcua_source_subscription` application boundary를 추가했습니다. 결과는 source/asset/measurement-point와 registered mapping identity를 connector notification sequence에 결합하지만 notification 수를 complete-channel observation/window로 해석하지 않습니다. 현재 lifecycle-aware runtime과 Operations의 explicit bounded collection action까지 연결됐고 notification persistence, reconnect/continuous ingestion은 포함하지 않습니다. Integration test는 lifecycle/type/transport failure 경계를, real asyncua contract는 실제 registered source 경로를 검증합니다.
- OPC UA connector에 bounded DataChange subscription boundary를 추가했습니다. `OpcUaSubscriptionConfig`는 anonymous endpoint/explicit NodeId mapping을 기존 read contract와 동일하게 검증하면서 publishing interval, notification collection timeout, max events와 iterator queue bound를 명시합니다. `collect_opcua_subscription_notifications`는 `auto_reconnect=False`인 한 세션에서 DataChange만 bounded하게 수집하고 각 DataValue의 quality, SourceTimestamp, ServerTimestamp와 asyncua `replayed` flag를 보존하며 `MAX_EVENTS` 또는 `TIMEOUT` 종료 이유를 반환합니다. Unit fake-runtime과 real asyncua contract로 good/bad status와 bounded 종료를 검증합니다. Registered-source application/runtime과 Operations bounded action까지 연결됐지만 notification persistence, reconnect/continuous ingestion은 아직 별도 범위입니다.
- `poll_registered_source`를 FILE/OPC UA 공통 polling boundary로 사용하고 CLI `operations poll-source`를 type-specific runtime dispatch로 연결했습니다. FILE-only compatibility wrapper는 제거해 polling entry point를 하나로 통일했습니다. OPC UA polling은 synchronous caller-owned loop 안에서 iteration마다 fresh `asyncio.run`으로 one-shot connect/read/disconnect를 실행하며 connection/session/subscription을 cycle 사이에 유지하지 않습니다. SKIPPED/FAILED에서는 즉시 종료하고 platform failure를 자동 retry하지 않습니다. Integration test는 FILE/OPC UA generic dispatch와 CLI output을 검증하고 real asyncua contract는 실제 server에 대해 bounded OPC UA polling과 latest receipt/connection-attempt persistence를 검증합니다.
- Registered OPC UA one-shot snapshot을 canonical `AssetObservationSummary`로 projection하는 `project_registered_opcua_observation_summary`를 추가하고 Operations Run action에 연결했습니다. One-shot iteration은 `sample_count=1`로 표현하고 asset/source/measurement-point/channel identity를 보존합니다. 모든 mapped node에 SourceTimestamp가 있을 때만 conservative complete-channel watermark를 observed start/end로 사용하며 sampling rate, file snapshot provenance, validation policy는 추정하지 않습니다. Bad/Uncertain 등 non-good OPC UA status가 하나라도 있으면 numeric value를 승격하지 않는 기존 connector 의미와 함께 `opcua-non-good-status` data-quality ERROR를 aggregate합니다. Operations Overview/Data Quality는 FILE과 OPC UA canonical summary를 같은 read surface에서 소비합니다.
- Operations Sources는 runtime-state v3의 latest bounded connection-attempt evidence를 시작 시 복원하고 one-shot/bounded runtime 실행 후 즉시 refresh합니다. Selected source에는 operation/outcome, attempted/connected/completed timing과 failure detail을 별도 evidence block으로 표시하고 `SourceHealthAssessment`에도 같은 historical attempt를 전달합니다. Successful attempt도 current connection state가 아니므로 Connection dimension은 계속 `NOT_INSTRUMENTED`입니다.
- Registered OPC UA one-shot runtime은 runtime-state v3에 `opcua-read` operation-tagged connection-attempt evidence를 기록합니다. 성공 cycle은 connector snapshot의 measured `connected_at`/`completed_at`과 application attempt start를 결합한 SUCCEEDED attempt를 receipt보다 먼저 기록하고, source-owned connector/transport failure는 FAILED attempt와 concrete detail을 기록합니다. Runtime unavailable, caller-contract error, unexpected internal platform failure처럼 connector attempt 사실을 신뢰할 수 없는 경로는 attempt evidence를 만들지 않습니다. `SourceHealthAssessment`는 latest attempt를 historical evidence로 보존하지만 current/session connection telemetry로 승격하지 않습니다.
- Operations **Run active source once**를 FILE/OPC UA type-specific runtime dispatch로 확장했습니다. FILE은 current-byte validation cycle을 유지하고 OPC UA는 registered one-shot connect/read/disconnect cycle을 isolated async runner에서 실행합니다. 두 경로 모두 latest receipt/lifecycle/runtime-state를 갱신하며, OPC UA 성공 시 one-shot snapshot을 canonical `AssetObservationSummary`로 projection하고 timeline은 비워 단일 bounded read와 FILE history timeline을 구분합니다. One-shot read success는 persistent connection telemetry를 의미하지 않으며 CLI polling도 현재 `poll_registered_source`를 통해 FILE/OPC UA를 같은 entry point에서 dispatch합니다.
- ACTIVE registered OPC UA source의 data-plane one-shot runtime을 추가했습니다. `RegisteredOpcUaObservation` / `ReceivedRegisteredOpcUaObservation`은 protocol snapshot과 asset/source identity를 보존하고, 모든 mapped node가 `SourceTimestamp`를 제공할 때만 earliest timestamp를 complete-channel event-time watermark인 source-level `observed_at`으로 사용합니다. `receive_registered_opcua_source_observation`은 one-shot `read_opcua_snapshot` 뒤 platform acceptance `SourceReceiptEvidence`를 만들고, `run_registered_opcua_source_cycle`은 ACTIVE source만 실행해 latest receipt를 runtime repository에 저장합니다. CLI polling과 Operations Run action은 이 one-shot runtime을 사용할 수 있고 bounded subscription도 별도 on-demand action으로 연결됐습니다. Persistent session telemetry/reconnect/continuous ingestion은 아직 별도 범위입니다.
- Operations OPC UA Add source에 bounded browse 결과 selection을 연결했습니다. Endpoint/timeout이 현재 입력과 일치하는 browse 결과만 사용하며, discovered Variable 후보를 multiselect로 선택하면 BrowseName→NodeId mapping으로 `OpcUaSourceConfig`에 전달합니다. Endpoint/timeout이 바뀌면 browse 결과는 stale로 표시하고 자동 mapping에 사용하지 않습니다. 선택이 없으면 기존 explicit `channel_id,node_id` textarea가 fallback으로 유지됩니다. Browse는 value read나 health 판정을 수행하지 않습니다.
- OPC UA connector에 bounded variable browse boundary를 추가했습니다. `OpcUaBrowseConfig`는 anonymous `opc.tcp` endpoint, start NodeId, max depth/node budget과 timeout을 검증하고 `browse_opcua_variables`는 hierarchical Object/Variable만 순회해 Variable NodeId, browse/display name과 browse path를 반환합니다. 값은 읽지 않으며 node budget을 넘으면 `truncated=True`로 명시합니다. Real asyncua contract에서 nested Variable discovery를 검증하고 Operations registration은 현재 browse candidate selection을 mapping UX에 사용할 수 있습니다.
- `RegisteredSource`가 FILE뿐 아니라 OPC UA source identity도 표현할 수 있도록 `SourceType.OPCUA`와 `OpcUaSourceConfig`를 추가했습니다. OPC UA config는 anonymous `opc.tcp` endpoint, explicit channel→NodeId, timeout invariant와 asset/optional measurement-point mapping을 보존하지만 registration 자체를 reachability/connection/health로 해석하지 않습니다. `JsonSourceRepository`는 current `industrial-phm-source-registry-v4`에서 FILE/OPC UA config를 strict type-specific schema로 round-trip하며 pre-alpha v1/v2/v3 registry는 자동 migration하지 않습니다. Operations Sources는 persisted OPC UA endpoint/node mapping을 표시하고 registration browse, one-shot read/runtime, bounded subscription action을 type-specific하게 제공합니다. Persistent session/reconnect/continuous ingestion은 포함하지 않습니다.
- 첫 live-protocol vertical slice로 optional `opcua` extra(`asyncua>=2.0.1,<2.1`)와 `industrial_phm.connectors.opcua` one-shot read boundary를 추가했습니다. Anonymous/NoSecurity `opc.tcp` endpoint와 explicit channel→variable NodeId mapping만 지원하며 `read_data_value(raise_on_bad_status=False)`로 OPC UA quality를 예외로 버리지 않고 보존합니다. Good status의 finite numeric scalar만 PHM value로 승격하고 Bad/Uncertain status는 numeric value를 `None`으로 유지하면서 StatusCode, timezone-aware SourceTimestamp/ServerTimestamp와 platform `received_at`을 분리해 기록합니다. Core import는 `asyncua`를 요구하지 않으며 optional runtime 부재는 명시적 설치 안내와 함께 fail-fast합니다. Local in-process asyncua server contract test를 별도 extra CI에서 실행합니다. 현재 이 connector는 registry/Operations one-shot runtime, canonical observation projection, browse와 bounded subscription까지 연결됐지만 credentials/certificates, persistent session, reconnect/backoff/buffering과 continuous ingestion은 포함하지 않습니다.
- ACTIVE registered source의 one-shot runtime cycle을 반복하는 synchronous `SourcePollingPolicy` / `poll_registered_source` boundary를 `industrial-phm operations poll-source` CLI로 노출했습니다. FILE과 OPC UA를 같은 entry point에서 type-specific cycle로 dispatch하며 success 사이에서만 configured interval을 기다리고, non-ACTIVE SKIPPED, SOURCE failure, PLATFORM failure에서는 즉시 종료합니다. Optional `max_cycles`로 bounded 실행을 지원하며 생략 시 현재 process가 failure/non-ACTIVE/Ctrl+C까지 loop를 소유합니다. Platform failure 자동 retry/backoff, background daemon, buffering, persistent connector session은 아직 구현하지 않습니다.
- Registered source monitoring을 위한 `SourceHealthAssessment`를 추가했습니다. Lifecycle, latest receipt, source-specific freshness를 한 read model로 조합하지만 단일 healthy/unhealthy boolean은 만들지 않습니다. Prepared-file runtime에는 connector telemetry가 없으므로 `SourceConnectionState.NOT_INSTRUMENTED`를 유지하고, data-flow state는 INACTIVE/SOURCE_ERROR/NO_RECEIPT/FRESHNESS_NOT_CONFIGURED/FRESH/STALE/TIMING_UNAVAILABLE로 evidence가 실제로 지원하는 범위만 표현합니다. Operations Sources는 lifecycle/connection/data-flow/freshness/latest observed_at/received_at을 별도 차원으로 표시하며 asset health나 connection success를 추론하지 않습니다.
- ACTIVE registered file/history source를 실제로 소비하는 one-shot runtime execution boundary를 `SourceRuntimeCycleResult` / `SourceRuntimeCycleState` / `run_registered_file_source_cycle`로 추가했습니다. REGISTERED/PAUSED/ERROR source는 source I/O 없이 SKIPPED되고, ACTIVE source는 current bytes를 재검증해 latest receipt를 runtime repository에 기록합니다. 성공 시 lifecycle은 ACTIVE를 유지합니다. Source validation/I/O failure는 SOURCE scope로 concrete detail과 함께 ACTIVE → ERROR로 전이하고, runtime-state persistence failure는 PLATFORM scope로 cycle을 FAILED 처리하되 source lifecycle은 ACTIVE로 유지합니다. Caller가 전달한 invalid/회귀/same-time conflicting received_at override는 source failure로 기록하지 않고 fail-fast합니다. Operations는 **Run active source once**와 manual **Load registered source**를 분리하며, 성공/skip/failure를 별도 상태로 표시합니다. 이는 explicit single iteration이며 background polling/retry/buffering/live connector는 포함하지 않습니다.
- Registered source의 latest accepted receipt를 control-plane registry와 분리해 재시작 이후에도 복원하는 `SourceRuntimeRepository` / `JsonSourceRuntimeRepository`를 추가했습니다. Current `industrial-phm-source-runtime-v3`는 source별 최신 `SourceReceiptEvidence`와 operation-tagged latest bounded connection-attempt evidence를 deterministic하게 저장하고 received_at/completed_at regression과 same-time conflicting evidence를 거부하며 atomic replace를 사용합니다. Operations는 registered-source load/runtime 성공 시 evidence를 기록하고 시작 시 복원합니다. Registry와 runtime-state가 같은 파일로 resolve되는 설정은 fail-closed로 거부하며 runtime state는 current connection health, retry/buffer state, throughput, receipt/attempt history 또는 freshness assessment 자체를 저장하지 않습니다.
- Registered source별 freshness 정책을 `SourceFreshnessPolicy` / `SourceFreshnessPolicyRepository`로 추가하고, `SourceReceiptEvidence`와 explicit assessment time에서 `SourceFreshnessAssessment`를 계산하도록 했습니다. Freshness age는 `assessed_at - observed_at`이며 observed→received delivery lag와 분리합니다. Policy가 없으면 NOT_CONFIGURED, timestamp/timezone이 없거나 source clock이 assessment time보다 미래면 UNAVAILABLE, policy threshold 이내/초과는 FRESH/STALE로 판정합니다. Current registry v4가 optional freshness policy를 영속하며 Operations Sources에서 policy save/clear와 현재 receipt 기반 assessment를 제공합니다.
- Registered file/history source의 현재 load에 대해 `SourceReceiptEvidence`와 `ReceivedRegisteredFileObservation`을 추가했습니다. Validation이 성공한 뒤 application boundary가 source bytes를 수락한 시각을 timezone-aware `received_at`으로 기록하고 latest `observed_at`과 비교 가능한 경우 signed observed→received lag를 제공합니다. Naive source timestamp 또는 timestamp 부재 시 lag를 만들지 않고 이유를 명시하며, negative lag도 clock evidence로 그대로 보존합니다. 이 receipt는 원래 sensor transport arrival이나 continuous ingestion을 소급 주장하지 않으며, source-specific freshness policy가 설정된 경우 별도 assessment boundary에서 FRESH/STALE/UNAVAILABLE을 계산합니다.
- Registered source의 administrative lifecycle을 `SourceLifecycleRecord` / `SourceLifecycleState` / `SourceLifecycleRepository`로 추가했습니다. REGISTERED → ACTIVE/PAUSED, ACTIVE → PAUSED/ERROR, PAUSED → ACTIVE, ERROR → ACTIVE/PAUSED 전이만 허용하고 ERROR에는 detail을 요구합니다. ACTIVE는 runtime enablement intent일 뿐 connection/health/freshness/active-ingestion 증거가 아닙니다. Current registry v4가 lifecycle을 함께 보존하며 Sources UI에서 Activate/Pause를 수행할 수 있습니다.
- Registered file/history source를 별도 mapping 재입력 없이 현재 Observation/Timeline으로 로드하는 `RegisteredFileObservation`과 `load_registered_file_source_observation` use case를 추가했습니다. Snapshot은 latest `AssetObservationSummary`, history-directory는 timestamp-ordered `AssetObservationTimeline`과 latest segment를 반환합니다. Registration 시점의 validation을 현재 관측으로 캐시하지 않고 매 load마다 현재 source bytes를 기존 CSV/timeline validator로 재검증하며, Operations Sources의 **Load registered source**가 이 경계를 사용해 Overview/Data Quality/Investigation 상태에 연결됩니다. 실패 시 이전 observation을 새 source 결과처럼 남기지 않으며, 이 동작은 continuous ingestion/source health를 의미하지 않습니다.
- PHM Operations Sources에 prepared CSV **Add source** workflow를 추가했습니다. File 또는 timestamped history-directory path를 대상으로 header/file-count/total-bytes/common-column/header-variant/representative-row를 Discover & Preview하고, asset/measurement-point/channel/timestamp/sampling policy를 Mapping한 뒤 기존 field CSV/observation timeline validation을 전체 source에 재사용해 성공한 candidate만 `JsonSourceRepository`에 저장합니다. Discovery 이후 path/mode/delimiter가 바뀌면 stale로 차단하며 등록 성공 후 Sources 목록을 즉시 갱신합니다. Browser upload/file-picker와 live connector는 아직 포함하지 않습니다.
- PHM Operations에 persistent `JsonSourceRepository`를 읽는 **Sources** 화면을 추가했습니다. Registered source 수/type, source ID/name/mode/asset/measurement-point/path/channel/time mapping과 registration time을 목록/상세로 표시하고 registry가 비어 있거나 손상된 경우를 명시적으로 구분합니다. Registration record만으로 online/healthy/fresh/active-ingestion 상태를 만들지 않으며, 현재 Operations의 FILE/OPC UA source entry point는 Sources로 통일돼 있습니다.
- Registered source를 재시작 이후에도 복원하는 `JsonSourceRepository`를 추가했습니다. Current `industrial-phm-source-registry-v4`는 FILE/OPC UA config, lifecycle과 optional freshness policy를 deterministic하게 기록하며 malformed JSON, unsupported schema/source type, schema key drift, duplicate source ID와 state alignment 오류를 fail-fast로 거부합니다. Write는 same-directory temporary file을 flush/fsync한 뒤 `os.replace`로 교체해 partial registry 노출을 피합니다. 현재 범위는 single-writer local persistence이며 cross-process coordination과 credential 저장은 포함하지 않습니다.
- Prepared file/file-directory source를 application control plane에 등록하기 위한 최소 `RegisteredSource`, `FileSourceConfig`, `SourceRepository` 계약과 비영속 `InMemorySourceRepository` reference implementation을 추가했습니다. File config는 기존 `CsvSensorLayout`의 time/channel/validation invariant를 재사용하고 history-directory에는 explicit timestamp를 요구합니다. 등록 record 자체를 connection/health/active ingestion으로 해석하지 않으며 durable registry, Sources UI와 freshness/runtime boundaries는 이후 current product 경로에 연결됐습니다.
- Research artifact와 분리된 최소 operational analysis contract로 `AnalysisRun`과 `OperationalFinding`을 추가했습니다. AnalysisRun은 observation/execution identity, data quality, source snapshot provenance, optional model deployment와 produced capability IDs만 소유하며, OperationalFinding은 versioned finding semantics/state/evidence linkage만 소유합니다. Generic finding에 score/threshold/severity/RUL/maintenance priority를 넣지 않습니다.
- Prepared field CSV 여러 segment를 explicit recorded timestamp 기준으로 정렬하는 `AssetObservationTimeline`과 history-directory loader를 추가했습니다. 동일 asset/measurement point, explicit timestamp, strict non-overlap을 요구하며 filename 순서를 시간으로 사용하지 않습니다. Operations Investigation에서 segment timeline과 latest observation을 확인할 수 있지만 이를 PHM trend로 승격하지 않습니다.
- Operations observation read model에 prepared source snapshot filename/SHA-256/byte size와 declared validation policy(timestamp field, minimum sample count, sampling-rate tolerance)를 보존하고 Data Quality 화면에서 직접 확인할 수 있게 했습니다. Absolute local path는 노출하지 않습니다.
- PHM Operations interactive surface를 추가했습니다. 현재 primary navigation은 Overview/Sources/Investigation/Data Quality/Maintenance Review/Operational State에 집중하고, evidence가 없는 automatic condition/fault/alert/RUL semantics를 제품 기능처럼 자리표시자로 노출하지 않습니다. Prepared/registered source observation과 data-quality 사실, explicit review workflow와 local operational state만 현재 evidence 범위에서 표시합니다.
- Prepared field CSV validation 결과를 Operations가 직접 artifact를 해석하지 않고 소비할 수 있도록 AssetObservationSummary application read model을 추가했습니다. Asset/source/measurement-point/time/channel/sample과 aggregate data-quality state만 전달하며 anomaly, alarm, diagnosis, RUL 또는 maintenance 의미는 만들지 않습니다. Adapter → application 경계를 첫 integration test로 고정했습니다.
- Prepared field CSV export를 Python 코드 없이 검증하는 `industrial-phm data validate-csv` CLI. Asset/channel/time mapping을 명시적으로 받고 sample/channel/time basis, source SHA-256, quality PASS/WARN을 출력하며 모델 fitting이나 thresholding은 실행하지 않습니다.
- Dataset-neutral RUL endpoint semantics. `RulTargetSeries`가 `observed-record-end`, `confirmed-failure`, `right-censored`, `unknown` endpoint 의미를 구분하며, exact RUL target으로 표현할 수 없는 right-censored lifecycle은 fail-fast로 차단합니다. XJTU-SY `N-k` target은 기존 수치/JSON을 바꾸지 않고 `observed-record-end`를 명시합니다.
- 일반 산업 센서 export를 위한 `CsvSensorAdapter`와 최소 data-quality/provenance boundary. 한 CSV 파일을 한 asset segment로 mapping하고 channel/time basis를 명시적으로 요구하며, missing/non-numeric/non-finite 값과 timestamp 역행을 차단합니다. Irregular timestamp interval은 재격자화하지 않고 warning으로 보존하며 source SHA-256과 byte size를 canonical metadata/validation report에 기록합니다.
- XJTU-SY RUL v1 held-out benchmark의 실제 numerical artifact
  `docs/research/results/xjtu-sy-rul-lstm-fold-1-benchmark-v1.json`. Prepared local source(3 conditions /
  15 bearing runs / 9,216 acquisitions, profile PASS)에서 clean tracked revision
  `2ae41acc16c45bf922f3b6ad8a228103d16d0982`로 runbook 절차를 실행했고, 독립 실행 두 개가 byte-identical
  (SHA-256 `874860c9a959e62311e959dc4609b022058cfb75ca4f107cf901d43b641b0fbf`)이며 두 artifact 모두 shared
  inspection read model을 통과했습니다. Validation-selected temporal LSTM을 fold-1 held-out
  Bearing1_1 / Bearing2_1 / Bearing3_1에 적용해 3,131개 prediction에서 equal-bearing mean MAE 458.251
  acquisition interval, normalized MAE 0.3313을 기록했습니다. Lifecycle-position diagnostic은 early 790.831 →
  middle 455.316 → late 133.096으로 감소합니다. 이 bearing들은 project history의 anomaly/robustness 연구에
  노출된 적이 있어 pristine external holdout이 아니며, `operational_primary_method_id`는 `null`로 유지되고
  prediction interval / uncertainty calibration / validated physical failure threshold / field RUL validation /
  maintenance decision recommendation은 모두 unsupported입니다.

- Frozen XJTU RUL held-out benchmark result를 기존 `ExperimentInspection` stage vocabulary로 검증·요약하는 reader. Validation-selected LSTM identity, null operational primary, test-bearing population, point/lifecycle aggregate, capability boundary와 retrospective benchmark limitation을 확인하며 aggregate/capability drift를 거부합니다.
- Validated AnalysisView를 deterministic Markdown으로 내보내는 `analysis report` CLI와 report renderer. Anomaly artifact를 primary scope로 사용하고 compatible한 prognostics artifact만 attached evidence로 포함하며, 별도 revision/source-byte-identity 한계와 capability/inspection warning을 report에 보존합니다.
- Analysis evidence compatibility/provenance contract. AnalysisView가 dataset/split/fold/revision과 train/evaluation population, excluded scope, verified source acquisition count를 artifact에서 보존하고, 서로 다른 anomaly/prognostics artifact는 population scope가 맞을 때만 같은 Explorer surface에서 attached evidence로 표시합니다. Exact source byte identity는 현재 artifact가 기록하지 않으므로 미검증 상태를 명시하며, revision이 달라도 하나의 실행으로 합치지 않습니다.
- Validation-selected temporal LSTM을 fold-1 held-out bearing에 적용하는 XJTU RUL benchmark result schema/runner/CLI와 execution runbook. Point error와 protocol-fixed early/middle/late lifecycle diagnostics를 기록하고, operational primary와 uncertainty/physical-failure/field/maintenance capability는 승격하지 않습니다.
- XJTU RUL protocol §9.1 lifecycle-position evaluator. Complete recorded lifecycle을 `early/middle/late` thirds로 고정하고, sequence dropped prefix로 boundary를 다시 나누지 않은 채 bearing별 prediction count·MAE·RMSE·signed error·normalized MAE와 equal-bearing aggregate를 기록할 수 있게 했습니다.
- XJTU RUL v1 finalization decision. Protocol §8의 frozen equal-bearing validation MAE rule을 그대로 적용해 `xjtu-sy-rul-lstm-fold-1-v1`을 validation-selected candidate로 기록하되 operational primary와 분리하고, 현재 calibration population으로 nominal coverage를 정당화하지 않아 v1 prediction interval/uncertainty calibration을 `unsupported/not validated`로 freeze했습니다. 당시 다음 단계로 lifecycle-position diagnostics와 frozen candidate held-out benchmark를 고정했으며, 해당 benchmark 실행은 이후 canonical numerical artifact로 완료되었습니다.
- Generative AI explanation의 prognostics evidence scope. Analysis Explorer `AI Explanation` 화면에서
  anomaly evidence와 prognostics evidence 중 설명 대상을 고르며, prognostics context는 validated read model에서
  읽은 method별 recorded estimate와 as-of acquisition, target 의미/unit/formula/clipping 여부, common support,
  retrospective validation 오차, unavailable capability, 그리고 아직 `None`인 `primary_method_id`만 전달합니다.
  Boundary 지시는 RUL 재계산·외삽·단위 변환, physical failure time이나 calendar date로의 번역, failure
  threshold·alarm/state·maintenance deadline·confidence interval 생성, 검증되지 않은 primary method 선택을
  금지하고, clipping이 없는 target이므로 음수 추정도 0으로 올리지 않고 기록된 대로 보고하게 합니다.

- 기존 `xjtu-rul-baseline-validation-result-v1`을 변경하지 않고 age-only, feature-Ridge, temporal-LSTM을
  같은 fold-1 validation target/evaluator에서 비교하는 `xjtu-rul-three-model-validation-result-v1` evidence
  schema/runner/CLI. Temporal method의 train-only preprocessing, right-edge sequence population, deterministic
  PyTorch training provenance와 acquisition-8..N prediction subset을 보존합니다. 기존 age/Ridge full-run
  비교는 별도로 유지하고, 세 method의 pairwise MAE/RMSE/normalized-MAE delta는 모두 동일 acquisition-8..N
  common support에서 계산해 support mismatch를 비교 결과에 섞지 않습니다. Held-out test와 uncertainty/field
  validation은 결과 범위에서 제외합니다.
- XJTU RUL protocol의 frozen temporal LSTM comparator. Complete fold-1 train acquisition에서만 robust scaling을
  fit하고 8-acquisition right-edge sequence window를 구성해 raw `N - k` target을 aligned source identity에
  결합합니다. Dataset-neutral supervised LSTM regressor는 deterministic CPU execution과 final-epoch provenance를
  보존하며 prediction을 clamp하지 않습니다. Validation/test의 첫 7 acquisition은 필요한 sequence context가
  없으므로 prediction subset에서 제외하고 기존 bearing-first RUL evaluator가 동일 target 의미로 평가합니다.
- XJTU RUL age-only/feature-Ridge fold-1 validation을 실제 prepared source에서 동일 target/evaluator로 실행하는
  versioned evidence schema, deterministic JSON writer와 CLI. Artifact는 clean tracked Git revision, train/validation
  source scope, test exclusion, target semantics, preprocessing/model provenance, per-bearing prediction/evaluation과
  baseline delta를 보존하며 prediction interval/field validation을 지원 범위로 승격하지 않습니다.
- XJTU RUL protocol의 frozen acquisition-feature Ridge comparator. 전체 16개 vibration-statistical feature를
  complete train partition에서 robust scaling하고 bearing-balanced resampling으로 fit하며, raw `N - k` target을
  source observation identity로 정렬합니다. Validation/test에서는 동일 preprocessing state와 model을 사용하고
  output을 clamp하지 않은 채 기존 bearing-first RUL evaluator에 전달합니다.
- XJTU RUL protocol의 first age-only comparator. Complete train bearing target에서 endpoint를 equal-bearing mean으로
  fit하고 validation/test prediction에는 current acquisition index만 사용합니다. Target bearing endpoint,
  operating condition과 vibration feature value를 prediction input에서 제외하고 negative prediction도 clamp하지
  않아 sensor-aware baseline의 실제 추가 가치를 비교할 수 있게 합니다.
- Dataset-neutral RUL prediction contract와 identity-aligned point evaluator. Sequence model의 dropped prefix를 허용하는
  ordered prediction subset을 target lifecycle에 결합하고 asset별 MAE/RMSE/mean signed error를 먼저 계산한 뒤
  equal-asset 평균으로 집계합니다. XJTU policy edge는 complete recorded-end target을 재검증하고 bearing별
  `N - 1` normalization scale만 제공해 model implementation과 평가 의미를 분리합니다.
- Dataset-neutral `RulTargetObservation` / `RulTargetSeries` contract와 기존 XJTU bearing-run split/source profile을
  재사용하는 fold-1 recorded-end RUL target construction. 각 acquisition을 canonical source identity에 맞춰
  `N - k` acquisition interval target으로 정렬하고 complete partition coverage, dataset/feature schema와
  duplicate/missing acquisition을 fail-fast 검증합니다.
- XJTU-SY RUL / Prognostics numerical implementation 전에 마지막 recorded acquisition을 dataset-observed endpoint로
  사용하는 `N - k` acquisition-interval target, bearing-run leakage boundary, age/feature/sequence baseline ladder,
  bearing-first evaluation, uncertainty evidence 요구와 UI/GenAI dependency boundary를 고정한 protocol v1.

- XJTU LSTM anomaly-evidence trajectory의 earliest-third scored-window q95를 descriptive review threshold로 사용해
  threshold 초과 acquisition-contiguous observation을 score-exceedance interval로 표시하는 Analysis Explorer
  기능. 이 interval은 retrospective review aid이며 validated fault/state/alarm semantics를 만들지 않습니다.
- Analysis Explorer의 `Run Analysis` view에서 prepared XJTU-SY source를 기존 frozen LSTM pipeline으로 실행하고,
  생성 result를 동일한 `AnalysisView`로 재검증해 Summary/Evidence/AI Explanation에 즉시 연결하는
  source-to-analysis product vertical slice.
- Analysis Explorer의 선택 asset에 대해 bounded structured PHM evidence만 전송하는 Generative AI 설명/Q&A.
  API credential과 model이 명시적으로 설정된 경우에만 run button으로 OpenAI Responses API를 호출하고,
  `store=false` stateless request와 capability/limitation instruction boundary를 적용합니다.
- Validated XJTU LSTM analysis evidence를 사용자 결과 중심으로 검토하는 첫 PHM Analysis Explorer.
  Acquisition-aligned anomaly-evidence trajectory, high-score observation, feature residual과 capability를 표시하고
  기존 `ExperimentInspection` pipeline/provenance를 Analysis Details drill-down으로 재사용합니다.
- XJTU/IMS Isolation Forest와 XJTU LSTM evidence를 같은 Experiment Overview와 Pipeline Lineage vocabulary로 검토하는
  marimo 기반 Developer Workbench. Acquisition-level model의 Sequence Construction을 `not applicable`로 표시하고,
  raw trajectory/residual이 없는 result의 detailed evidence를 `not recorded`로 구분합니다.
- Python 3.14 기반 installable package, uv lockfile, CLI와 CI 기준선.
- dataset manifest 기반 `data list/status/fetch/verify/inspect/validate` acquisition·inspection workflow.
- dataset/source 차이를 격리하는 `DomainAdapter`와 domain-neutral `CanonicalTimeSeries` contract.
- 실제 XJTU-SY와 IMS source profile, dataset-specific validator와 canonical Adapter.
- XJTU-SY condition-stratified 5-fold bearing-run split과 leakage-aware experiment protocol.
- acquisition별 `vibration-statistical-v1` feature와 split-aware characterization artifact workflow.
- generated characterization artifact를 소비하는 optional marimo/Matplotlib research tooling environment.
- dataset-neutral `ExperimentConfig v1`과 XJTU fold-1 Isolation Forest candidate configuration.
- train provenance와 feature order를 고정하는 identity/robust `PreprocessingState`.
- sampling-aware `ModelFitInput`과 unsampled `ModelScoringInput`의 dataset-neutral model input contract.
- scikit-learn 1.9 기반 Isolation Forest baseline과 observation-aligned `AnomalyScores` contract.
- XJTU fold-1 candidate validation 실행, 결과 artifact와 deterministic selection rule.
- XJTU validation을 bearing-first로 평가하는 acquisition-order Spearman ρ development evaluator.
- `experiment validate --score-trajectory-dir`로 생성하는 train/validation acquisition별 anomaly-score
  trajectory artifact. Candidate selection과 분리된 development diagnosis이며 holdout test는 scoring하지 않습니다.

- `ReferenceStrategy.train-bearing-early-third-v1`과 `experiment reference-compare`로 실행하는 fold-1
  reference-only H0/H1 development 비교. complete train / reference-eligible / model-fit population을
  `ModelFitInput`에서 의미상 분리합니다.

- fold-1 development가 확정한 단일 `xjtu-sy-iforest-fold-1-finalized-v1` experiment configuration과
  축 drift를 로드 시점에 차단하는 검증. 비교용 v2/v3 manifest는 역사적 evidence로 보존합니다.

- `experiment holdout`으로 실행하는 fold-1 holdout evaluation 경로. finalized configuration 하나만
  소비하며 candidate/reference selection, threshold calibration, tunable parameter가 없습니다.

- finalized configuration의 `fold-1` holdout test 1회 실행 결과 artifact.

- `experiment cross-fold`로 folds 2~5의 test partition을 한 번에 실행하는 post-holdout robustness 경로와
  결과 artifact. fold별로 preprocessing을 새로 fit하며 `fold-1 test`는 다시 scoring하지 않습니다.

- verified IMS source profile과 canonical mapping을 기준으로 확인한 feature 계층의 cross-dataset
  portability 관찰과, IMS experiment protocol이 결정해야 할 항목 정리. feature 계층이 dataset-neutral하게
  유지됨을 두 domain의 channel 구성으로 고정하는 contract 테스트를 함께 추가합니다.

- IMS single-channel 첫 model experiment의 source scope와 평가 경계를 결과 전에 고정한
  `ims-experiment-protocol.md`. Set 2 complete train을 fit/reference로 사용하고 Set 3의
  `readme-documented` 4,448 acquisitions만 one-time cross-test evaluation에 사용하며, Set 1과
  archive-extension은 v1에서 제외합니다.

- PHM/ML 개발자·연구자를 위한 pipeline transparency UX baseline. Source → canonicalization → feature →
  preprocessing → reference/sampling → model fit/scoring → evaluation/result를 stage별로 검토하고,
  complete/reference/fit/scoring population flow, effective configuration, provenance, unsupported capability를
  일관되게 표시하는 information architecture를 정의합니다.

- `experiment cross-test`로 실행하는 IMS single-channel fixed cross-test 경로. Set 2 complete train에서
  preprocessing과 Isolation Forest를 fit하고 Set 3의 `readme-documented` scope만 scoring하며,
  source/reference/fit/scoring population과 effective configuration, capability scope, code revision을
  developer-transparent result JSON에 기록합니다.

- IMS Set 2 → Set 3 one-time cross-test evaluation 결과 artifact.

- XJTU finalized holdout와 IMS fixed cross-test result를 schema별로 검증하고 Source → Canonical → Feature →
  Preprocessing → Reference → Sequence Construction → Population → Model → Scoring → Evaluation → Capability →
  Provenance 순서의 immutable read model로 해석하는 inspection capability와 첫 presentation surface인
  `experiment inspect` CLI.

- XJTU `fold-1 train/validation`에 한정한 LSTM Autoencoder development protocol v1. Robust-scaled full 16-feature
  input, train-bearing early-third reference, length 8 / stride 1 / right-edge sequence construction, deterministic
  reconstruction training, residual evidence와 retrospective evaluation 경계를 numerical execution 전에 고정합니다.

- Python 3.14 CPU reference execution에서 LSTM forward/backward와 seeded deterministic update를 검증하는 PyTorch
  2.14 `deep-learning` optional runtime, CPU-only lock source와 CI compatibility contract.

- ordered feature observations를 asset·partition·sequence boundary 안에서 fixed-length window로 변환하고 source row,
  start/end identity, right-edge alignment, stride와 source observation→window population provenance를 보존하는
  dataset-neutral sequence contract.
- XJTU fold-1 complete train을 train-fitted preprocessing state로 transform한 뒤 bearing별 early-third reference
  1,084 acquisitions를 1,021 fit windows로, validation 2,818 acquisitions를 2,797 scoring windows로 구성하는
  dataset-specific boundary와 frozen population validation.
- XJTU LSTM protocol v1의 단일 packaged configuration과 complete-train preprocessing fit부터 sequence construction,
  deterministic CPU LSTM Autoencoder fit까지 연결하는 protocol-defined execution path.
- Immutable windows를 float32 tensor로 변환하고 fixed 50 epochs의 Adam, global-norm gradient clipping과 final-epoch
  model state를 적용하며 runtime·seed·loss·parameter count provenance를 보존하는 LSTM model contract.
- Sequence input과 reconstruction의 schema·window identity를 정확히 결합하고, 실제 model runtime이 소비한
  float32 input을 기준으로 feature별 시간축 MSE와 right-edge source observation에 정렬된
  higher-is-more-anomalous window score를 생성하는 reconstruction scoring contract.
- XJTU LSTM validation score를 original full-run lifecycle thirds에 정렬해 bearing별 acquisition-order Spearman ρ,
  late-vs-middle rank probability와 feature residual mean을 계산하고 3-bearing equal-weight summary를 보존하는
  development evaluation contract.
- XJTU LSTM preprocessing state, sequence population, deterministic training provenance, acquisition-aligned score
  trajectory, per-window feature residual과 evaluation을 `xjtu-lstm-development-result-v1` JSON으로 보존하고 source
  validation부터 artifact write까지 연결하는 one-shot retrospective development execution contract.
- `xjtu-lstm-development-result-v1`의 raw score/residual evidence에서 bearing-first statistic을 다시 계산하고 Sequence
  Construction, model training, reconstruction scoring, retrospective evaluation과 capability/provenance를 같은
  immutable `ExperimentInspection` read model로 노출하는 LSTM result inspection reader.
- Clean `main`의 frozen XJTU LSTM protocol을 두 번 실행해 byte-identical SHA-256을 확인한 fold-1 train/validation
  retrospective evidence. 세 validation bearing의 equal-weight mean Spearman ρ는 `0.627559`, mean late-vs-middle
  rank probability는 `0.681636`이며 acquisition-aligned score와 16-feature residual을 함께 보존합니다.

- `mimii-due` dataset manifest(`provider = "manual"`, CC BY-NC-SA 4.0)와 Zenodo record·file checksum·local
  inventory를 기록한 MIMII DUE source profile.
- MIMII DUE prepared source의 directory·filename grammar, observed clip population과 16-bit mono 16 kHz WAV
  header compatibility를 검증하는 dataset-specific validator와 `data validate mimii-due` CLI.
- MIMII DUE WAV clip을 `pcm_amplitude` single-channel `CanonicalTimeSeries`로 변환하고 source
  group·machine·section·domain·split·clip label·원문 attribute와 PCM encoding provenance를 metadata에 보존하는
  audio `DomainAdapter`. Clip label은 sample `labels`로 투영하지 않고 PCM amplitude도 Adapter에서 정규화하지 않습니다.
- XJTU LSTM retrospective evidence를 정비 엔지니어 역할의 Evidence Summary / Trend & Observations /
  Limits & Provenance로 재배치하는 Maintenance Evidence Review low-fidelity prototype. Threshold/state,
  diagnosis, maintenance priority, RUL을 생성하지 않고 experiment evidence와 future operational result 경계를
  product contract에 명시합니다.
- MIMII DUE sections 00–02를 development, sections 03–05를 external evaluation으로 분리하고
  label-blind scoring, `audio-logmel-statistical-v1` 128-feature representation, section-level Isolation Forest,
  machine/section/domain AUC·pAUC와 evaluation ground-truth late-binding을 numerical result 전에 고정한
  experiment protocol v1.
- 16 kHz mono signed-PCM 10-second clip을 symmetric-Hann STFT, 64 HTK mel bands와 log-energy mean/std로
  128-feature vector로 변환하는 `audio-logmel-statistical-v1` representation. Waveform은 clip 단위로 소비하고
  dataset 전체 waveform materialization이나 audio-specific runtime dependency를 추가하지 않습니다.
- `AnomalyScores`와 binary labels를 source observation ID로 late-bind해 full ROC AUC와 standardized
  partial ROC AUC를 계산하는 dataset-neutral evaluator 및 zero를 epsilon으로 바꾸지 않는 unit-interval
  harmonic-mean helper.
- MIMII development v1의 하나의 packaged base configuration을 15개 machine type × section model config로
  결정적으로 resolve하는 dataset-specific contract. Section별 source normal train 전체와 target normal 3개를
  complete population으로 검증해 robust preprocessing/all-train model input을 만들고, test `clip_label`을
  읽지 않는 source/target scoring input을 분리합니다.
- MIMII dev source를 machine/section 단위로 lazy decode→log-mel feature→robust preprocessing→Isolation Forest
  fit/score하고 test label을 evaluator에서 source identity로 late-bind하는 development runner. 30개
  machine/section/domain AUC·pAUC strata, section별 fitted preprocessing provenance, machine/domain/global harmonic
  summaries와 capability boundary를 `mimii-due-domain-shift-development-result-v1` JSON으로 기록합니다.
- `industrial-phm experiment mimii-development` CLI와 representation parameter spec을 추가해 clean revision의
  numerical execution이 protocol/feature/model/evaluator 설정을 결과 artifact에서 재현할 수 있게 했습니다.
- MIMII development result inspection reader. 15 section exact coverage와 population/preprocessing state,
  30 machine/section/domain AUC·pAUC, harmonic summaries, evaluator-only label join, DCASE non-official flag,
  capability와 code provenance를 다시 검증한 뒤 기존 ExperimentInspection stage vocabulary로 노출합니다.
- MIMII development result에 packaged dataset manifest의 version, provider, source URL, citation DOI와 license를
  source-record provenance로 보존하고 inspection 시 동일 manifest와 재검증합니다. Prepared source 실행은
  record checksum을 다시 계산한다고 주장하지 않으며, archive MD5 evidence는 source profile이 계속 소유합니다.
- `experiment mimii-development`가 expensive numerical execution 전에 declared code revision과 current Git
  HEAD의 일치 및 tracked working tree clean 상태를 확인하는 authoritative-evidence revision guard.

- MIMII development numerical evidence의 authoritative 실행 절차를 full source validation → clean revision
  verification → 두 번의 독립 execution → byte/SHA-256 reproducibility → result inspection → repository artifact
  승격 순서로 고정한 execution runbook.

- MIMII DUE sections 00–02 development numerical evidence artifact. 두 번의 deterministic 실행이 byte-identical이며
  full source validation과 inspection을 통과한 결과만 승격했습니다.

- MIMII DUE development evidence 검토와 sections 03–05 external evaluation을 위한 v1 configuration freeze 결정.

- MIMII DUE evaluation test audio(Zenodo 4884786)와 ground truth(5257674) record 검증 기록. evaluation test
  filename에 label이 없어 late-binding이 source 구조로 보장됨을 확인했습니다.

- label 없는 MIMII evaluation-test source reader와 validator. clip record에 label field가 없어 scorer가
  label을 복원할 수 없습니다.

- `experiment mimii-external-score`로 생성하는 label-blind MIMII external score artifact.

- `experiment mimii-external-evaluate`로 생성하는 sections 03–05 late-bound external evaluation evidence.

- XJTU fold-1 three-model RUL validation numerical artifact. age-only / feature-Ridge / temporal LSTM을
  acquisition 8..N common support에서 비교한 development evidence입니다.

- XJTU three-model RUL validation result를 공통 `ExperimentInspection` stage vocabulary로 읽는 inspection
  reader.

- `AnalysisView`의 capability composition과 XJTU RUL prognostics evidence read model.

- Analysis Explorer Prognostics 화면과 presentation-independent prognostics summary helper.

### Removed

- 역할 검증용으로 유지하던 `notebooks/03_maintenance_evidence_review.py`를 제거했습니다. 해당 prototype의 목적이었던 정비 관점 operational 정보구조 검증은 `apps/operations.py`로 이관했고, retrospective experiment evidence 검토는 Analysis Explorer/Developer Workbench에 남깁니다.

### Changed

- Field CSV validation provenance에 CSV delimiter, minimum sample count, optional sampling-rate tolerance를 추가했습니다. Validation report, canonical metadata와 `data validate-csv` 출력이 같은 policy를 보존해 quality PASS/WARN이 어떤 입력 정책에서 결정됐는지 추적할 수 있습니다.
- Field CSV parsing과 SHA-256/byte-size provenance를 동일 byte snapshot에서 계산하도록 바꿔, source file이 실행 중 변경될 때 parsed values와 기록된 digest가 서로 다른 file state를 가리킬 수 있는 TOCTOU 간극을 제거했습니다.
- Field CSV validation에서 관찰한 source-quality state/issue code와 sampling interval 최대 편차를 canonical metadata에 보존하고, 기존 vibration feature projection이 해당 provenance를 그대로 전달하도록 계약 테스트를 추가했습니다.
- Field CSV timestamp quality 검증에 explicit sampling-rate consistency check를 추가했습니다. Timestamp와 `sampling_rate_hz`를 함께 제공하면서 사용자가 `sampling_rate_tolerance_ratio`를 명시한 경우에만 관측 interval 편차를 계산하고, 허용 범위를 넘으면 `sampling-rate-mismatch` warning을 남깁니다. 자동 resampling이나 metadata 보정은 하지 않습니다.
- Analysis Explorer가 detailed projector가 없는 inspectable artifact를 오류로 종료하지 않고 inspection-only 화면으로 엽니다. IMS/MIMII 같은 schema에서는 저장된 pipeline/capability/provenance만 표시하고, artifact에 없는 observation-level trajectory나 RUL evidence는 재구성하지 않습니다.
- Analysis Explorer의 새 분석 실행 흐름을 `데이터 입력 -> 사전 검증/실행 계획 -> 실제 실행`으로 분리했습니다. 실행 계획은 application-level source validation을 재사용하며, 입력이 변경된 stale plan이나 blocker가 있는 plan으로 실제 LSTM 실행을 시작하지 않습니다.
- Analysis Explorer의 첫 화면을 기술 지표 중심에서 사용자 검토 흐름 중심으로 재구성했습니다. 집중 확인 구간과 가장 높은 구간을 먼저 보여주고 Spearman rho/검토 기준값은 상세 정보로 이동했으며, AI 설명은 독립 메뉴 대신 이상 근거와 RUL 결과 문맥 안에서 사용하도록 배치했습니다.
- Generative AI explanation 요청에 API credential을 붙일 수 있는 endpoint를 configured OpenAI Responses API endpoint로 제한해, 호출자가 임의 host로 secret-bearing request를 보낼 수 없도록 경계를 강화했습니다.
- `CanonicalTimeSeries` canonical boundary가 sensor `values`, optional RUL과 sampling rate의 NaN/Inf를 거부하고, sensor/RUL payload의 non-numeric 및 boolean 값을 fail-fast 처리하도록 numeric/finite invariant를 강화했습니다.
- Analysis Explorer에서 저장하는 Markdown 보고서를 사용자 결과 중심 한국어 구조로 개편했습니다. 이상 변화와 RUL 모델 비교를 먼저 보여주고 split/revision/artifact/capability와 inspection warning은 뒤쪽 기술 정보로 이동했습니다.
- CLI onboarding을 개선했습니다. `doctor`가 Python, repository checkout, data root, research/deep-learning runtime 상태와 다음 Explorer 실행 명령을 보여주고, `data status/fetch/verify/inspect/validate`가 실패 또는 완료 후 다음 데이터 준비·검증 행동을 안내합니다.
- Git clone부터 Analysis Explorer 실행까지의 사용자 여정을 정리했습니다. README의 첫 실행을 `clone → Python 3.14 → marimo run`으로 단순화하고, Explorer 주요 화면을 한국어 결과 중심으로 재구성했습니다. 새 XJTU 분석은 데이터 폴더만 입력하면 현재 clean Git revision을 자동 기록하며, 결과 화면에서 Markdown 보고서를 바로 저장할 수 있습니다.
- Root README를 한국 사용자 중심의 제품 소개 흐름으로 다시 구성했습니다. 영문 섹션 제목과 미지원 기능/신뢰 경계 중심 설명을 제거하고 전체 구조, 주요 기능, 빠른 시작, 사용 데이터, 개발 방향과 문서 링크에 집중했습니다. Analysis Explorer 화면 캡처는 향후 `assets/analysis-explorer.png`만 추가하면 상단 소개 영역에 연결할 수 있도록 위치와 자산 규칙을 준비했습니다.
- Root README를 197-line minimal landing page로 다시 압축했습니다. Capability, architecture, quickstart, evidence/limits, roadmap과 핵심 docs만 남기고 중복된 RUL 상세·research direction·repository layout 설명을 authoritative 문서로 이동했습니다.
- Root README를 experiment history 중심 문서에서 capability/status, quickstart, evidence boundary와 roadmap 중심의 product landing page로 재구성했습니다. 2025–2026 PHM의 uncertainty·robustness·domain shift·human-in-the-loop·LLM copilot·industrial integration 흐름과 관련 표준/산업 사례는 별도 research note로 분리했습니다.
- CLI implementation handler를 `commands/data.py`, `commands/feature.py`, `commands/experiment.py`, `commands/analysis.py`로 분리했습니다. Public command/parser surface는 유지하고 `cli.py`는 parser wiring과 entrypoint 중심으로 축소했습니다. Evidence artifact는 canonical machine evidence와 deterministic human-review representation을 분리하는 저장·리뷰 정책을 추가했습니다.
- Prognostics GenAI context가 retrospective development validation scope, holdout 사용 여부, field validation 여부와 Scoring/Evaluation inspection warnings를 구조화해 전달합니다. 모델 instruction은 이 범위를 넓혀 해석하지 못하도록 명시합니다.
- Prognostics presentation capability는 `available` 목록에 명시된 경우에만 활성화되는 fail-closed 규칙으로 판정합니다. `target_clipping`/`target_normalization`도 result artifact의 target semantics를 `PrognosticsEvidence`까지 그대로 전달해 summary/GenAI 계층이 같은 사실을 별도로 하드코딩하지 않도록 정리했습니다.
- 첫 end-to-end Analysis Application vertical slice를 완료 상태로 전환하고, 현재 제품/연구 우선순위를
  XJTU run-to-failure 기반 RUL/prognostics v1 통합으로 이동했습니다.
- 프로젝트의 현재 제품 단계를 experiment/dataset 확장 중심에서 end-to-end PHM Analysis Application vertical slice로
  전환했습니다. 기존 analysis/evidence를 사용자 결과·시각화·Generative AI 설명으로 연결하고,
  `ExperimentInspection`은 transparency drill-down으로 재사용하며, RUL/prognostics는 지원 가능한 source에서
  같은 application에 추가되는 핵심 PHM capability로 정렬합니다.
- Dataset-specific execution boundary와 authoritative evidence artifact 용어를 문서 전반에서 정렬하고, dataset
  validation 순서를 Workbench cross-schema 검토 → MIMII DUE → 근거 기반 Health Indicator/RUL 재검토로 갱신했습니다.
- LSTM training provenance의 모호한 `final_loss` property를 실제 집계 의미가 드러나는
  `final_epoch_mean_training_loss`로 변경하고 protocol/terminology의 evidence 전 구현 순서를 현재 계약과 정렬.
- Developer Workbench의 low-fidelity information architecture를 Experiment Overview, Pipeline Lineage와 Evidence
  Explorer로 구체화하고 acquisition→window population unit transition, capability availability와 provenance를
  검토하는 acceptance criteria를 정의.

- XJTU finalized holdout과 IMS cross-test lineage를 같은 developer pipeline stage로 비교하고 schema-specific
  experiment inspection에 필요한 information gap을 명시.

- XJTU 내부에 있던 Spearman ρ와 late-vs-middle rank probability의 순수 수학 계산을 두 번째 dataset
  consumer가 생긴 시점에 dataset-neutral score-statistics helper로 승격하고 XJTU public wrapper는 유지합니다.
- regular sampling rate가 제공되면 `CanonicalTimeSeries`가 explicit sample timestamp 없이도 waveform segment를
  표현할 수 있도록 확장.
- XJTU source/profile 검사를 production validator와 CLI로 이동하고 Notebook은 generated artifact를 소비하는
  exploratory interface로 제한.
- 첫 numerical baseline은 `fold-1` development/holdout 경계를 사용하며 configuration finalization 전에는
  다른 fold와 holdout test를 development decision에 사용하지 않도록 protocol을 명확화.
- `fold-1` holdout을 열기 전에 reference semantics만 한 번 더 비교하도록 configuration finalization 결정을
  고정. H0는 `all-train-observations`, H1은 train bearing별 early-third heuristic reference를 사용하며
  feature/sampling/scaling/model parameter/seed는 selected v2에 고정하고 H0/H1 판정 규칙도 결과 전에 명시.
- `fold-1` holdout 소진 이후 `fold-2`~`fold-5`는 fresh holdout이 아니라 post-holdout robustness evidence로
  만 사용하도록 규칙을 고정. 각 fold의 test partition만 한 번의 동일 실행에서 평가하고 finalized
  configuration의 model/feature/reference/sampling/scaling/seed semantics와 descriptive metric을 유지합니다.
- 정확한 experiment parameter와 seed는 version-controlled config가, train-fitted scaling statistics는
  `PreprocessingState`가 소유하도록 Source of Truth를 분리.
- XJTU model-fit/scoring 준비가 research characterization artifact가 아니라 production `VibrationFeatureVector`를
  직접 소비하도록 경계를 정리하고, Isolation Forest active candidate를 sampling × feature subset 4개 v2로 축소.
- model input의 `rows`, `input/output observation count`를 `feature_rows`, `source/fit observation count`로
  명확화해 sampling 전후 의미를 이름에서 구분.
- XJTU model input이 source profile의 acquisition sequence 전체성을 검증하고, train feature vectors에서
  preprocessing fit과 sampling-aware model input을 함께 생성하도록 실행 경계를 강화.
- architecture PNG는 reference diagram으로 유지하고 이미지 전용 binary/canvas 검증을 CI에서 제거.

### Fixed

- FILE 특징 분석은 관측 요약과 특징 입력의 SHA-256/크기를 대조합니다. 두 번의 읽기 사이에
  파일이 교체되거나 snapshot 근거가 없으면 결과를 생성하지 않아, 이전 파일의 시각·품질·출처에
  새로운 값의 특징이 연결되는 문제를 방지합니다.

- Isolation Forest integer `max_samples`가 model-fit observation 수를 초과할 때 estimator가 silently fallback하지 않도록 fail-fast.
- `CanonicalTimeSeries`가 mutable input container를 그대로 보관해 생성 이후 invariant가 깨질 수 있던 문제.
- dataset acquisition User-Agent가 package version과 별도의 값을 사용하던 중복 version 문제.
- `data inspect`가 empty directory를 usable source처럼 성공 처리하던 동작.
