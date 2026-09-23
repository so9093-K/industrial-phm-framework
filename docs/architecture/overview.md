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

Prepared field source에는 observation data plane과 분리된 첫 source-registration control-plane contract도
둡니다.

```text
RegisteredSource
  └ FileSourceConfig
       ├ source path / snapshot-or-history mode
       ├ asset / measurement-point mapping
       └ existing CsvSensorLayout validation semantics

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
         └ signed lag?  # only when timestamps are timezone-comparable
```

현재 `RegisteredSource`는 file/file-directory source만 표현하며, 등록 record가 존재한다는 사실을
connection/health/active-ingestion 상태로 해석하지 않습니다. `InMemorySourceRepository`는 application
workflow와 contract test를 위한 비영속 reference implementation이고, `JsonSourceRepository`는
`industrial-phm-source-registry-v2` schema로 registration과 lifecycle을 재시작 이후에도 복원합니다.
기존 v1 registry는 읽을 때 각 source를 implicit REGISTERED state로 해석하고 다음 write에서 v2로
승격합니다. JSON writer는 same-directory temporary file을 flush/fsync한 뒤 `os.replace`로 교체해 partial
write를 노출하지 않으며 reader는 schema/key/source type/duplicate ID/lifecycle alignment를 fail-fast
검증합니다. 현재 구현은 single-writer local persistence 경계이며 cross-process write coordination은 아직
지원하지 않습니다.

Operations Sources UI는 현재 file/history registration의 Discover → Mapping → Validate & Register,
REGISTERED/ACTIVE/PAUSED/ERROR lifecycle control, registry read surface와 selected registered source의
on-demand Observation load까지 연결합니다. ACTIVE는 runtime consumption을 허용하는 administrative
state이며 connection/health/ingestion 성공을 뜻하지 않습니다.
`load_registered_file_source_observation`은 registration-time 검증을 현재 상태로 재사용하지 않고 매 load마다
현재 source bytes를 기존 field CSV/timeline 경계로 재검증합니다. 따라서 registration은 observation cache나
source-health evidence가 아닙니다. `receive_registered_file_source_observation`은 이 검증이 성공한 뒤
application acceptance 시각을 timezone-aware `received_at`으로 기록합니다. Latest `observed_at`이
timezone-aware일 때만 signed lag를 계산하고, timestamp/timezone이 없으면 lag를 unavailable로 남깁니다.
Prepared-file receipt는 원래 sensor transport arrival을 소급 표현하지 않으며 source-specific freshness
threshold가 아직 없으므로 fresh/stale 상태도 만들지 않습니다. Browser upload/file-picker, source edit/delete,
lifecycle을 실제로 소비하는 ingestion runtime, freshness policy, OPC UA/MQTT connector는 후속 경계입니다.
또한 registration config는 기존 `CsvSensorLayout` invariant를 재사용하며 unit/sensor identity 같은 아직
지원하지 않는 field semantics를 새로 만들어내지 않습니다.

Prepared field source 쪽에는 research artifact와 분리된 첫 operational application contract가 생겼습니다.

```text
prepared field observation / timeline
  -> source-appropriate analysis producer (아직 미구현)
  -> AnalysisRun
       ├ execution / observation identity
       ├ data quality / source provenance
       ├ model deployment?
       └ produced capability IDs
  -> OperationalFinding?  # validated state-like capability만
       └ evidence refs -> capability-specific evidence
  -> Operations
```

`OperationalFinding`은 numerical payload container가 아닙니다. Score, threshold, residual, diagnosis evidence는
각 capability가 소유하고 finding은 versioned semantics와 evidence linkage만 보존합니다. Prognostics도 같은
finding에 억지로 넣지 않고 별도 capability contract가 실제 field requirement에서 필요할 때 추가합니다.
Generic workflow engine이나 결과 registry도 아직 만들지 않습니다.

생성형 AI는 상태 해석, 가능한 원인 정리, 정비 권고 초안과 보고서 생성을 지원할 수 있지만 PHM 수치를 다시
계산하는 source of truth가 되지 않습니다. 실제 정비 작업이나 설비 제어로 이어지는 조치는 별도의 사용자 승인
및 운영 절차를 거쳐야 합니다.

## Reference Diagrams

세 그림은 framework의 전체 책임과 흐름을 설명하는 reference diagram입니다. 구현 진행 상태는 README Roadmap에서 관리합니다.
