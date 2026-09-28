# Architecture Overview

이 문서는 `industrial-phm-framework`의 현재 reference architecture를 설명합니다.
특정 설비나 특정 데이터셋을 구조 자체에 고정하지 않고 책임과 데이터 흐름을 기준으로 유지합니다.

아키텍처 그림은 다음 질문에 빠르게 답하는 것을 우선합니다.

1. 데이터셋별 차이는 어디에서 다루는가?
2. 어떤 처리가 공통 PHM 기능으로 이어지는가?
3. 모델 학습과 평가는 어떤 흐름으로 구성되는가?
4. 분석 결과는 서비스와 생성형 AI에 어떻게 전달되는가?
5. 최종 사용자는 어떤 결과를 소비하는가?

`CanonicalTimeSeries`의 현재 가정, XJTU-SY에 과적합되지 않기 위한 확장 규칙, 실제 비공개/현장 데이터에서 확인할
quality·provenance·security boundary는
[`canonical-data-contract.md`](canonical-data-contract.md)를 기준으로 검토합니다. Canonical contract는 모든 산업
데이터를 미리 포괄하는 universal schema가 아니라 실제 source가 추가될 때 공통 의미만 유지하는 adapter/core
boundary입니다.

Continuous source runtime과 Live/Backfill history의 다음 단계는
[`live-acquisition-ducklake-v1.md`](live-acquisition-ducklake-v1.md)에서 control plane, durable ingress,
DuckLake Asset History, window/PHM의 ownership과 restart semantics를 정의합니다. 현재 #256/#257 contract를
유지한 채 이 경계 위에서 구현합니다.

## 1. 시스템 아키텍처

![산업 설비 데이터부터 사용자까지 이어지는 시스템 아키텍처](../../assets/system-architecture.png)

원천 산업 설비 데이터는 Domain Adapter에서 공통 데이터 구조로 변환됩니다. 이후 공통 PHM 코어는
전처리·특징 생성, 이상 탐지, 건전성 평가, RUL 예측 등 데이터가 지원하는 PHM 기능을 수행하고,
평가 및 분석 계층에서 모델 성능과 결과를 검증합니다.

서비스 계층은 분석 결과를 API와 대시보드 등 사용자 접점으로 전달합니다. 생성형 AI는 PHM 모델의 수치
계산을 대신하지 않고, 계산된 분석 결과와 정비 지식을 바탕으로 설명·질의응답·정비 지원을 제공하는 상위
계층으로 취급합니다.

Isolation Forest, LSTM Autoencoder, RUL Ridge와 temporal LSTM은 현재 evidence path에서 사용되는
reference implementations이며 공통 PHM 코어 자체를 정의하지 않습니다. 새로운 모델도 동일한 contract/evaluation
경계를 지키고 기존 evidence gap을 실제로 해결하는 경우에 추가합니다.

## 2. 모델 학습 및 평가

![입력 데이터부터 모델 비교와 선택까지 이어지는 모델 학습 및 평가 파이프라인](../../assets/model-training-evaluation.png)

그림은 입력 데이터에서 전처리·특징 생성, 데이터 분할, 모델 학습, 분석 결과 생성, 모델 평가, 비교·선택으로
이어지는 전체 실험 수명주기를 보여줍니다. 실제 split strategy는 deployment scenario와 데이터 구조에 맞게
asset/run/time/site/cohort 같은 leakage boundary를 명시적으로 정합니다. XJTU-SY의 bearing-run split을 모든
industrial dataset의 공통 split 규칙으로 일반화하지 않습니다.

그림의 `전처리 및 특징 생성`은 파이프라인 책임을 나타내는 개념 단계입니다. scaler, normalizer, threshold,
feature statistics처럼 데이터로부터 학습되는 상태는 split 이후 **train 범위에서만 fit**하고 validation/test에는
학습된 상태만 적용해야 합니다. 따라서 도식의 좌→우 순서를 "전체 데이터에 먼저 fit한다"는 의미로 해석하지
않습니다.

모델 평가는 모델 구현과 분리합니다. Isolation Forest와 LSTM Autoencoder를 비교할 때도 같은 split과 같은
평가 프로토콜을 사용합니다. anomaly, early detection, prognostics 지표는 데이터가 실제로 지원하는 capability와
ground truth가 정의된 경우에만 사용합니다.

## 3. 서비스 아키텍처

![모델 산출물부터 대시보드와 생성형 AI를 거쳐 사용자에게 전달되는 서비스 아키텍처](../../assets/service-architecture.png)

이 도식의 서비스/추론 계층은 향후 operational deployment에서 필요한 책임 경계를 설명하는 reference이며,
현재 pre-alpha application이 이미 service API나 live inference runtime을 제공한다는 의미는 아닙니다.

현재 presentation loading 경계는 두 단계입니다. 모든 supported artifact는 schema-specific inspector를 통해
`ExperimentInspection`으로 검증되고, `AnalysisSurface`는 이 inspection과 optional detailed `AnalysisView`를
함께 전달합니다. observation-level anomaly trajectory나 RUL evidence를 실제 artifact가 보존하고 projector가
존재할 때만 `AnalysisView`가 구성됩니다.

```text
versioned evidence artifact
  -> schema-specific inspection
  -> ExperimentInspection
  -> AnalysisSurface
       ├ inspection
       └ AnalysisView? -> report / GenAI / detailed Explorer
```

따라서 Analysis Explorer는 IMS/MIMII처럼 detailed projector가 없는 artifact도 inspection-only surface로 열 수
있지만, artifact에 없는 trajectory·RUL·진단 근거를 재구성하지 않습니다. report/GenAI처럼 detailed numerical
evidence가 필요한 consumer는 validated `AnalysisView`를 요구합니다.

Experiment/anomaly/prognostics evidence는 capability-specific artifact와 read model로 유지합니다. 서로 다른 실제
operational output을 하나의 universal `PHMResult`로 합치지 않습니다.

Prepared field source에는 observation data plane과 분리된 source-registration control-plane contract를 두고,
live protocol requirement는 generic connector framework를 먼저 만들지 않고 concrete connector slice에서
검증합니다. 첫 concrete live-protocol slice는 OPC UA입니다.

```text
OPC UA one-shot connector
  OpcUaReadConfig
    ├ anonymous / SecurityPolicy None endpoint
    └ explicit channel_id -> variable NodeId mapping
  -> optional asyncua runtime
  -> read_data_value(raise_on_bad_status=False)
  -> OpcUaReadSnapshot
       └ OpcUaNodeObservation[]
            ├ finite numeric value?   # Good status only
            ├ StatusCode / quality
            ├ SourceTimestamp?
            ├ ServerTimestamp?
            └ platform received_at

RegisteredSource
  ├ FileSourceConfig
  │    ├ source path / snapshot-or-history mode
  │    ├ asset / measurement-point mapping
  │    └ existing CsvSensorLayout validation semantics
  └ OpcUaSourceConfig
       ├ opc.tcp endpoint / request timeout
       ├ asset / measurement-point mapping
       └ explicit channel_id -> variable NodeId mapping

SourceRepository
  ├ register
  ├ get
  └ list_sources

SourceLifecycleRepository
  ├ get_lifecycle
  └ set_lifecycle

SourceLifecycleRecord
  ├ REGISTERED
  ├ ACTIVE
  ├ PAUSED
  └ ERROR

SourceFreshnessPolicyRepository
  ├ get_freshness_policy
  ├ set_freshness_policy
  └ clear_freshness_policy

SourceFreshnessPolicy
  └ max_observation_age_seconds

SourceRuntimeRepository
  ├ get_latest_receipt / list_latest_receipts / record_receipt
  └ get_latest_connection_attempt /
    list_latest_connection_attempts /
    record_connection_attempt

SourceHealthAssessment
  ├ lifecycle
  ├ connection = NOT_INSTRUMENTED
  ├ data_flow
  ├ latest receipt?
  └ freshness?

JsonSourceRuntimeRepository
  └ industrial-phm-source-runtime-v3
       ├ latest SourceReceiptEvidence per source
       └ latest SourceConnectionAttemptEvidence per source
          (historical bounded attempt, not current connection state)

File registration use case
  source path / mode
    -> header discovery + representative preview
    -> asset / measurement-point / channel / time mapping
    -> existing CsvSensorLayout + observation/timeline validation
    -> SourceRepository.register

Registered file observation use case
  RegisteredSource
    -> current source bytes
    -> existing CsvSensorLayout + observation/timeline validation
    -> RegisteredFileObservation
         ├ latest AssetObservationSummary
         └ AssetObservationTimeline?

On-demand receipt timing
  RegisteredFileObservation
    -> successful application acceptance
    -> SourceReceiptEvidence
         ├ latest observed_at?
         ├ received_at
         └ delivery lag? = received_at - observed_at

Freshness assessment
  SourceReceiptEvidence + SourceFreshnessPolicy? + assessed_at
    -> SourceFreshnessAssessment
         ├ NOT_CONFIGURED
         ├ FRESH
         ├ STALE
         └ UNAVAILABLE

  observation age = assessed_at - observed_at

Source health read model
  SourceLifecycleRecord + latest SourceReceiptEvidence? + SourceFreshnessPolicy? + assessed_at
    -> SourceHealthAssessment
         ├ connection = NOT_INSTRUMENTED
         ├ lifecycle
         ├ data flow = INACTIVE / SOURCE_ERROR / NO_RECEIPT /
         │             FRESHNESS_NOT_CONFIGURED / FRESH / STALE /
         │             TIMING_UNAVAILABLE
         ├ receipt before current ACTIVE transition -> NO_RECEIPT for current epoch
         └ no boolean healthy flag

Active file source runtime cycle
  SourceRepository + SourceLifecycleRepository + SourceRuntimeRepository
    -> lifecycle != ACTIVE : SKIPPED, no source I/O
    -> lifecycle == ACTIVE
         -> receive_registered_file_source_observation
         -> record latest SourceReceiptEvidence
         -> success : SUCCEEDED, lifecycle remains ACTIVE
         -> source validation/I/O failure : FAILED/SOURCE, ACTIVE -> ERROR
         -> runtime unavailable / caller-contract / unexpected internal / runtime-state failure : FAILED/PLATFORM, lifecycle remains ACTIVE

Registered-source polling runtime
  SourcePollingPolicy + poll_registered_source
    -> FILE : run_registered_file_source_cycle
    -> OPC UA : fresh async one-shot cycle per iteration
    -> SUCCEEDED : sleep interval -> next cycle
    -> SKIPPED : stop
    -> FAILED/SOURCE : stop; lifecycle may remain ACTIVE for transient transport failure
                        or transition to ERROR for source config/data-contract failure
    -> FAILED/PLATFORM : stop, lifecycle unchanged
    -> optional max_cycles : bounded deterministic run

Bounded OPC UA subscription connector
  OpcUaSubscriptionConfig
    -> explicit NodeId mappings
    -> publishing interval + queue bound
    -> max DataChange events + notification collection timeout
    -> auto_reconnect = false
    -> OpcUaSubscriptionResult
         ├ protocol quality/source/server timestamps preserved
         ├ completion = MAX_EVENTS / TIMEOUT
         └ replayed flag preserved
Registered OPC UA bounded subscription application
  RegisteredSource(OPCUA) + ACTIVE lifecycle
    -> persisted endpoint / NodeId mapping / timeout
    -> caller-supplied bounded session controls
    -> collect_opcua_subscription_notifications
    -> RegisteredOpcUaSubscription
         ├ source / asset / measurement-point identity
         ├ registered endpoint / mapping identity
         └ RegisteredOpcUaDataChangeEvent*
              ├ connector notification quality/timestamps/replayed preserved
              └ collection_index = local bounded collection order only
  collection_index is not an OPC UA server sequence and does not prove gap-free delivery.
  RegisteredOpcUaSubscriptionCoverage
    -> configured / observed / missing channel IDs
    -> notification count
    -> full coverage only when every registered channel appeared at least once
  Full channel coverage still does not imply timestamp alignment, synchronized snapshot,
  gap-free delivery, or an analysis-ready observation/window.
  Lifecycle-aware bounded subscription runtime cycle
    -> ACTIVE registered OPC UA source only
    -> same bounded subscription application boundary
    -> latest SourceConnectionAttemptEvidence persistence
    -> success keeps ACTIVE
    -> OPC UA data-contract failure: FAILED/SOURCE, ACTIVE -> ERROR
    -> transport OSError: FAILED/SOURCE, lifecycle remains ACTIVE
    -> platform/runtime-state failure: FAILED/PLATFORM, lifecycle unchanged
    -> no SourceReceiptEvidence or freshness update
  Operations Sources exposes this bounded cycle as an explicit on-demand action.
  이 bounded connector 자체에는 notification persistence, reconnect, continuous ingestion을 추가하지 않습니다.

Persistent OPC UA acquisition worker
  RegisteredSource(OPCUA) + ACTIVE lifecycle
    -> asyncua Client(auto_reconnect=true)
    -> long-lived DataChange subscription
         ├ bounded iterator queue
         ├ overflow -> explicit evidence + reconnect
         └ Republish replay flag preserved
    -> #256 persistent session evidence
         DISCONNECTED -> CONNECTING -> CONNECTED
         CONNECTED -> RECONNECT_WAIT -> CONNECTING -> CONNECTED
    -> RegisteredOpcUaDataChangeEvent
    -> SQLite WAL durable acquisition spool
         └ successful durable acceptance -> OpcUaPersistentDataChangeEvent
    -> bounded micro-batch writer
         ├ max events / max bytes / max interval
         ├ DuckLake snapshot commit + batch fingerprint provenance
         └ successful commit/recovery 이후에만 spool ACK
    -> DuckLake raw OPC UA evidence + normalized Asset History
  transport/session/subscription recovery는 asyncua가 소유하고 application은 connection epoch,
  reconnect-attempt evidence, local event index와 event-time semantics를 소유합니다.
  Worker failure/stop은 administrative SourceLifecycle ACTIVE를 asset-health verdict로 바꾸지 않습니다.
  Current session evidence의 durable telemetry/UI projection은 후속 #264/#265 경계입니다.

Registered OPC UA one-shot runtime
  RegisteredSource(OPCUA) + ACTIVE lifecycle
    -> read_opcua_snapshot
    -> RegisteredOpcUaObservation
         ├ protocol value/quality/timestamps preserved
         └ observed_at = earliest mapped SourceTimestamp only when every mapped node provides one
    -> SourceReceiptEvidence
    -> latest runtime receipt persistence
    -> success : SUCCEEDED, lifecycle remains ACTIVE
    -> explicit OPC UA data-contract failure : FAILED/SOURCE, ACTIVE -> ERROR
    -> transport OSError : FAILED/SOURCE, lifecycle remains ACTIVE
    -> platform runtime-state failure : FAILED/PLATFORM, lifecycle remains ACTIVE
```

`RegisteredSource`는 prepared file과 OPC UA source identity를 표현하지만, 등록 record가 존재한다는 사실을
connection/health/active-ingestion 상태로 해석하지 않습니다. `OpcUaSourceConfig`는 기존 `OpcUaReadConfig`의
anonymous `opc.tcp` endpoint/NodeId/timeout invariant를 재사용하며 endpoint reachability나 subscription을
검증하지 않습니다. Endpoint userinfo credential은 connector contract에서 거부하므로 registry config에
credential을 포함하지 않습니다. `InMemorySourceRepository`는 두 source type을 모두 보존하는 비영속 reference
implementation이고 `JsonSourceRepository`는 `industrial-phm-source-registry-v4`에서 FILE과 OPC UA config,
lifecycle, optional source-specific freshness policy를 strict type-specific schema로 보존합니다. Registry
reader/writer는 current v4만 허용하며 pre-alpha 구버전 state를 자동 migration하지 않습니다. JSON writer는
same-directory temporary file을 flush/fsync한 뒤 `os.replace`로 교체해 partial write를 노출하지 않으며,
reader는 schema/key/source type/duplicate ID/lifecycle alignment/freshness-policy source alignment를
fail-fast 검증합니다.

Runtime receipt evidence는 registry에 저장하지 않습니다. 별도 `JsonSourceRuntimeRepository`가 source별
latest `SourceReceiptEvidence`와 latest bounded `SourceConnectionAttemptEvidence`를
`industrial-phm-source-runtime-v3`로 보존합니다. Attempt evidence는 producer operation을
`opcua-read` / `opcua-subscription`으로 반드시 명시하며, runtime reader/writer도 current v3만 허용하고
pre-alpha 구버전 state를 자동 migration하지 않습니다. Runtime writer는 same-directory temp + flush/fsync +
`os.replace`를 사용하고 received_at regression과 same-time conflicting evidence를 거부합니다. Registry와
runtime-state path가 같은 파일로 resolve되면 control-plane overwrite를 막기 위해 fail-closed로 거부합니다.
두 repository 모두 현재 single-writer local persistence 경계이며 cross-process write coordination은 아직
지원하지 않습니다.

OPC UA connector proof와 registration identity는 registry v4를 통해 persistence와 Operations Sources read
surface까지 연결되었습니다. 현재 connector는 explicit variable NodeId를 한 번 읽어 protocol
quality/timestamp를 보존하고, application/registry는 같은 endpoint/NodeId mapping을 `RegisteredSource`로
round-trip합니다. Operations는 FILE과 OPC UA detail을 type별로 표시합니다. FILE 전용 manual Load action은 OPC UA에서 노출하지 않지만 type-specific Run action은 OPC UA one-shot runtime을 실행합니다. Operations Add source는 OPC UA endpoint와 browse candidate 또는 explicit `channel_id,node_id`
mapping을 `OpcUaSourceConfig` validation 후 registry v4에 저장할 수 있습니다. Application의 `run_registered_opcua_source_cycle`은 ACTIVE registered OPC UA source를 explicit one-shot read하고 latest receipt를 runtime repository에 기록하며 Operations Run action에서도 실행됩니다. 모든 mapped DataValue에 SourceTimestamp가 있을 때만 earliest SourceTimestamp를 complete-channel watermark인 source-level `observed_at`으로 사용하고 하나라도 없으면 timing을 unavailable로 남깁니다. CLI `operations poll-source`는 FILE/OPC UA registered source를 type-specific one-shot cycle로 동기 반복합니다. OPC UA polling은 iteration마다 fresh connect/read/disconnect를 수행하며 connection/session을 유지하지 않습니다. OPC UA one-shot snapshot은 `project_registered_opcua_observation_summary`로 canonical `AssetObservationSummary`에 projection하며 one iteration을 `sample_count=1`로 표현하고 complete-channel watermark만 observed start/end로 사용합니다. Non-good status는 data-quality ERROR로 보존하고 sampling rate/file provenance는 추정하지 않습니다. OPC UA read/browse/subscription connector의 `completed_at`은 successful context teardown 이후에 기록합니다. OPC UA read/subscription cycle은 successful bounded attempt와 source-owned connector/transport failure를 operation-tagged latest `SourceConnectionAttemptEvidence`로 runtime v3에 기록합니다. `SourceHealthAssessment`는 이 historical attempt evidence를 optional inspection fact로 보존하지만 current/session connection state는 계속 `NOT_INSTRUMENTED`입니다. Operations Sources는 latest attempt operation/outcome/timing/detail을 persisted runtime evidence에서 읽어 표시하지만 이를 current connection state로 승격하지 않습니다. Bounded registered-source subscription collection은 Operations Sources의 explicit **Collect bounded subscription** action까지 연결됐습니다. UI는 completion reason, notification count, channel coverage와 event-level value/status/timing을 현재 app session에서 보여주지만 notification persistence나 current session connection telemetry로 승격하지 않습니다. 별도 persistent acquisition worker는 asyncua auto-reconnect와 #260 durable spool까지 연결하지만,
current session evidence의 durable telemetry, continuous window assembly와 Operations control/monitor surface는
아직 후속 #263~#265 경계입니다. `asyncua`는 계속 `opcua` optional extra에만 있고 core dependency가 아닙니다.
One-shot/bounded connector는 계속 `auto_reconnect=False`이고 persistent worker만 `auto_reconnect=True`를 사용합니다.
username/password, certificate/security policy configuration은 아직 지원하지 않습니다.

Operations Sources UI는 현재 file/history registration의 Discover → Mapping → Validate & Register,
REGISTERED/ACTIVE/PAUSED/ERROR lifecycle control, ACTIVE one-shot runtime cycle, registry read surface와
selected registered source의 on-demand Observation load까지 연결합니다. ACTIVE는 runtime execution을
허용하는 administrative state이며 one-shot cycle이 실제로 이를 소비하지만 connection/health/continuous
ingestion 성공을 뜻하지 않습니다. One-shot failure의 SOURCE/PLATFORM scope는 failure ownership을 나타내며
lifecycle 전이와 동일한 개념이 아닙니다. Current file bytes의 validation/I/O 또는 OPC UA data-contract
failure는 lifecycle을 ERROR로 전이하지만 transient OPC UA transport `OSError`와 runtime-state persistence
같은 platform failure는 cycle만 FAILED로 만들고 source lifecycle은 ACTIVE로 유지합니다.
`load_registered_file_source_observation`은 registration-time 검증을 현재 상태로 재사용하지 않고 매 load마다
현재 source bytes를 기존 field CSV/timeline 경계로 재검증합니다. 따라서 registration은 observation cache나
source-health evidence가 아닙니다. `receive_registered_file_source_observation`은 이 검증이 성공한 뒤
application acceptance 시각을 timezone-aware `received_at`으로 기록합니다. Latest `observed_at`이
timezone-aware일 때만 signed lag를 계산하고, timestamp/timezone이 없으면 lag를 unavailable로 남깁니다.
Prepared-file receipt는 원래 sensor transport arrival을 소급 표현하지 않습니다. Source-specific
`SourceFreshnessPolicy`가 설정되면 freshness는 delivery lag가 아니라
`assessed_at - observed_at` observation age를 policy max age와 비교해 계산합니다. Timestamp/timezone이
없거나 observed_at이 assessment time보다 미래면 fail-closed로 UNAVAILABLE을 반환하고, policy가 없으면
NOT_CONFIGURED를 반환합니다. FRESH/STALE은 timing-policy result이며 connection/health/ingestion 성공을
뜻하지 않습니다. `SourceHealthAssessment`는 lifecycle, latest receipt와 freshness를 한 read model에
모으지만 boolean healthy/unhealthy를 만들지 않고 prepared-file runtime의 connection state는
NOT_INSTRUMENTED로 유지합니다. Manual load 또는 successful ACTIVE runtime cycle의 latest receipt는 runtime repository에
기록되고 앱 재시작 후 Sources monitoring에서 다시 사용됩니다. Freshness assessment는 persisted receipt + policy + 현재
assessment time으로 재계산하며 assessment 자체는 저장하지 않습니다. Prepared-file polling은
`SourcePollingPolicy`가 one-shot cycle을 caller-owned synchronous loop로 반복하는 수준까지 구현됐고,
non-success에서 즉시 중지합니다. Browser upload/file-picker, source edit/delete, background service,
retry/backoff/buffering, receipt history, persistent OPC UA subscription/continuous ingestion과 MQTT connector는 후속 경계입니다.
또한 registration config는 기존 `CsvSensorLayout` invariant를 재사용하며 unit/sensor identity 같은 아직
지원하지 않는 field semantics를 새로 만들어내지 않습니다.

Prepared field source 쪽에는 research artifact와 분리된 첫 operational application contract가 생겼습니다.

```text
registered FILE snapshot
  -> on-demand vibration feature analysis
  -> AnalysisRun
       ├ execution / observation identity
       ├ data quality / source provenance
       └ produced capability ID
  -> explicit human-review OperationalFinding?
       └ evidence ref -> vibration feature evidence
  -> finding review workflow
       └ note / acknowledge / close
  -> Operations
```

`AnalysisRun`의 observation/execution window와 `OperationalFinding.observed_at`은 operational absolute time으로
사용하므로 timezone-aware datetime만 허용합니다. Finding은 run과 동일한 identity/measurement-point와 observation
window에 연결되어야 하고, `finding.capability_id`도 해당 run의 `capability_ids`에 실제로 선언되어 있어야 합니다.

`OperationalFinding`은 numerical payload container가 아닙니다. Score, threshold, residual, diagnosis evidence는
각 capability가 소유하고 finding은 versioned semantics와 evidence linkage만 보존합니다. Prognostics도 같은
finding에 억지로 넣지 않고 별도 capability contract가 실제 field requirement에서 필요할 때 추가합니다.
Generic workflow engine이나 결과 registry도 아직 만들지 않습니다.

생성형 AI는 상태 해석, 가능한 원인 정리, 정비 권고 초안과 보고서 생성을 지원할 수 있지만 PHM 수치를 다시
계산하는 source of truth가 되지 않습니다. 실제 정비 작업이나 설비 제어로 이어지는 조치는 별도의 사용자 승인
및 운영 절차를 거쳐야 합니다.

## Reference Diagrams

세 그림은 framework의 전체 책임과 흐름을 설명하는 reference diagram입니다. 현재 구현 범위는 root README의 제품 milestone과 이 문서의 구체적인 runtime 경계에서 확인합니다.
