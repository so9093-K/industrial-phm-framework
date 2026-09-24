# industrial-phm-framework

산업 설비의 센서 데이터를 분석해 **이상 변화와 RUL(잔여수명)**을 살펴보고,
분석 결과를 화면·보고서·생성형 AI 설명으로 확인할 수 있는 Python 기반 PHM(고장예지·건전성 관리) 프레임워크입니다.

현재는 공개 데이터셋을 중심으로 분석 흐름과 결과 검증 방식을 개발하고 있으며,
주 사용자는 PHM/ML 개발자와 연구자입니다.

> 현재 버전: pre-alpha `0.0.1`

<!--
Analysis Explorer 화면 캡처가 준비되면 이 위치에 추가합니다.
권장 파일: assets/analysis-explorer.png
자산 관리 규칙은 assets/README.md를 참조합니다.
-->

## 전체 구조

![산업 설비 데이터부터 분석 결과까지 이어지는 시스템 구조](assets/system-architecture.png)

센서 데이터는 데이터셋별 변환 단계를 거쳐 공통 분석 흐름으로 들어갑니다.
분석 결과는 파일로 기록되고, 같은 결과를 Analysis Explorer·보고서·생성형 AI 설명에서 함께 사용합니다.

자세한 설계는 [아키텍처 문서](docs/architecture/overview.md)에서 확인할 수 있습니다.

## 주요 기능

- **센서 데이터 준비** — XJTU-SY, IMS Bearings, MIMII DUE와 명시적으로 mapping한 일반 CSV export의 구조·기본 품질을 확인하고 canonical 분석 입력으로 변환합니다.
- **OPC UA protocol/control-plane boundary** — optional `opcua` extra에서 anonymous/NoSecurity endpoint one-shot probe, bounded Variable browse, explicit NodeId one-shot read를 제공합니다. Read는 value, StatusCode, SourceTimestamp, ServerTimestamp와 platform receipt timing을 분리해 보존합니다. `RegisteredSource(OPCUA)`를 registry v4에 영속하고 Operations Add source에서 browse 후보 또는 explicit `channel_id,node_id` mapping으로 등록할 수 있으며, application에는 ACTIVE registered OPC UA source를 한 번 읽어 latest `SourceReceiptEvidence`를 기록하고 protocol snapshot을 conservative one-shot `AssetObservationSummary`로 projection하는 async runtime cycle까지 연결했습니다. 이는 지속 connection/health/continuous ingestion을 의미하지 않습니다.
- **이상 변화 분석** — 진동·음향 센서 데이터에서 시간에 따른 이상 점수와 특징 변화를 분석합니다.
- **RUL 분석** — 베어링 수명 데이터를 이용해 잔여수명 모델을 비교하고 평가 결과를 기록합니다.
- **분석 결과 탐색** — Analysis Explorer에서 요약, 주요 관측값, 모델 결과, 실행 정보를 단계별로 확인합니다.
- **운영 관측 화면** — PHM Operations에서 asset/source 관측, data quality, PHM finding, RUL, maintenance, system health 자리를 같은 운영 구조에서 확인합니다. 아직 검증되지 않은 capability는 숨기지 않고 명시적 상태로 표시합니다.
- **보고서 생성** — 분석 결과를 같은 수치와 내용으로 재현 가능한 Markdown 보고서로 저장합니다.
- **생성형 AI 설명** — 계산이 끝난 분석 결과를 바탕으로 요약과 질의응답을 제공합니다.

현재 구현된 분석 화면과 실행 방법은 [Analysis Explorer 안내](apps/README.md)에 정리되어 있습니다.

## 가장 빠르게 실행하기

GitHub 저장소 접근 권한, Git, [uv](https://docs.astral.sh/uv/)가 필요합니다.
원본 센서 데이터를 내려받지 않아도 저장소에 포함된 예제 분석 결과를 바로 볼 수 있습니다.

### 1. 저장소 가져오기

```bash
git clone https://github.com/so9093-K/industrial-phm-framework.git
cd industrial-phm-framework
```

### 2. Python 준비

```bash
uv python install 3.14
```

### 3. Analysis Explorer 실행

```bash
uv run --locked --group research marimo run apps/analysis_explorer.py
```

브라우저에서 기본 제공 XJTU-SY 분석 결과를 바로 확인할 수 있습니다.
`uv run`이 lockfile 기준 프로젝트 환경을 확인하고 필요한 의존성을 준비합니다.

운영 관측 surface는 별도 앱으로 실행합니다.

```bash
uv run --locked --group research marimo run apps/operations.py
```

현재 Operations 앱은 prepared single-asset CSV snapshot 또는 같은 asset/measurement point의 timestamped
CSV history directory를 bootstrap으로 사용할 수 있습니다. History directory의 각 파일은 독립 segment로
검증되고 filename이 아니라 recorded timestamp로 정렬됩니다. 화면은 latest observation, segment timeline,
data quality, exact source snapshot provenance(SHA-256/byte size), declared validation policy를 표시합니다.
또한 **Sources** 화면에서 prepared CSV file/history directory를
`Source → Discover & Preview → Mapping → Validate & Register` 순서로 등록하고, versioned local registry의
registered source 목록과 mapping/configuration을 확인할 수 있습니다. 등록 전에 기존 field CSV/timeline
validation을 그대로 통과해야 하며, 등록된 file/history source는 Sources에서 **Load registered source**로
현재 bytes를 다시 검증해 existing Observation/Timeline surface에 직접 연결할 수 있습니다. 성공한 registered
source load는 application acceptance 시각을 timezone-aware `received_at`으로 기록하고 latest
`observed_at`과 비교 가능한 경우 signed lag를 표시합니다. Timestamp/timezone이 없으면 lag를 만들지
않습니다. Source lifecycle은 `REGISTERED / ACTIVE / PAUSED / ERROR` control-plane state로 별도 보존하며
Operations에서 Activate/Pause를 수행할 수 있습니다. ACTIVE source는 **Run active source once**로 한 번의
runtime cycle을 실행할 수 있고, 성공하면 current observation/latest receipt를 갱신하며 ACTIVE를 유지합니다.
FILE validation/I/O 또는 OPC UA data-contract failure처럼 현재 source 입력/config를 그대로 다시 실행해도
성공할 수 없는 source failure는 concrete detail과 함께 lifecycle을 ERROR로 전이합니다. OPC UA transport
`OSError`는 failed connection-attempt evidence를 기록하되 administrative ACTIVE intent를 유지합니다. 반면
runtime-state persistence 같은 platform failure도 cycle을 FAILED로 만들되 source lifecycle은 ACTIVE로
유지합니다. 이 one-shot cycle은 connection/health/continuous-ingestion의 증거가 아니며 background
scheduler도 아닙니다.
Sources에서 source별 max observation age policy를 설정하면 현재 receipt evidence와 평가 시각을 사용해
`FRESH / STALE / UNAVAILABLE / NOT_CONFIGURED` freshness state를 계산합니다. Freshness age는
`assessment time - observed_at`이며 observed→received delivery lag와 분리합니다. Timestamp/timezone이 없거나
source clock이 평가 시각보다 미래면 임의 상태를 만들지 않고 `UNAVAILABLE`로 남깁니다. Registered-source
load가 성공하면 latest receipt는 control-plane registry와 분리된 local runtime state에도 기록되어 앱 재시작
후 Last received/lag/freshness를 다시 계산할 수 있습니다. Runtime state v2는 source별 latest receipt와 latest bounded connection-attempt evidence를 별도 보존합니다. OPC UA one-shot cycle은 successful connect/read/disconnect와 source-owned connector/transport failure에 대해 latest attempt evidence를 자동 기록합니다. 이 evidence는 historical attempt fact이며 current connection status가 아닙니다. Retry/buffer 상태와 receipt/attempt history도 저장하지 않습니다. Sources는 lifecycle,
latest receipt, source-specific freshness를 조합한 `SourceHealthAssessment`를 표시하지만 단일
healthy/unhealthy 판정은 만들지 않습니다. 현재 FILE/OPC UA one-shot runtime은 persistent connection telemetry를 기록하지 않으므로
Connection은 `NOT_INSTRUMENTED`로 남고, Data flow는 INACTIVE/SOURCE_ERROR/NO_RECEIPT/FRESH/
STALE/TIMING_UNAVAILABLE/FRESHNESS_NOT_CONFIGURED 중 실제 evidence에 맞는 상태만 표시합니다. Operations UI는 FILE/OPC UA one-shot 실행을 지원하고, CLI의 `operations poll-source`도 registered source type에 따라 FILE 또는 OPC UA one-shot runtime cycle을 caller-owned synchronous loop로 반복합니다. 이 polling runtime은 background service나 live connector가 아니며,
retry/backoff/buffering/connector telemetry는 아직 구현하지 않습니다. 별도
`industrial_phm.connectors.opcua` module의 OPC UA one-shot read proof와 같은 endpoint/NodeId mapping은
`industrial-phm-source-registry-v4`에 영속할 수 있고 Operations Sources에서 type-specific detail로 확인할 수
있습니다. Add source는 prepared file/history와 OPC UA browse/explicit-NodeId registration을 지원합니다. Application에는
ACTIVE OPC UA source의 one-shot read → receipt persistence cycle을 Operations의 **Run active source once**에서 실행할 수 있습니다. UI action은 selected source type에 따라 FILE current-byte validation 또는 OPC UA one-shot connect/read/disconnect를 dispatch합니다. CLI polling도 FILE/OPC UA one-shot cycle을 source type에 맞게 반복합니다. Application에는 ACTIVE registered OPC UA source의 persisted endpoint/NodeId mapping을 재사용해 bounded DataChange session을 한 번 수집하는 경계도 있지만, 이 호출은 notification을 persist하거나 complete observation으로 승격하지 않으며 Operations action, reconnect, continuous ingestion을 시작하지 않습니다.

Observation timeline 자체는 PHM trend가 아닙니다. Condition, Finding, RUL, Maintenance와 System Health 영역은
처음부터 존재하며 검증 또는 연결이 없는 capability는 `Not validated`, `Unavailable`, `Not connected`로
표시합니다.

ACTIVE registered FILE 또는 OPC UA source를 CLI에서 동기 polling하려면 registry/runtime-state 경로를
명시합니다. `--max-cycles`를 생략하면 failure/non-ACTIVE/Ctrl+C까지 계속 실행합니다.

```bash
uv run --locked industrial-phm operations poll-source \
  --registry artifacts/operations/source-registry.json \
  --runtime-state artifacts/operations/source-runtime.json \
  --source-id pump-source \
  --interval-seconds 5
```

이 명령은 background daemon이 아니며 실행 중인 process가 polling loop를 소유합니다. Source failure나
platform failure에서는 자동 retry하지 않고 종료합니다.

CLI에서 저장된 결과의 기술 정보를 확인하려면 다음 명령을 사용할 수 있습니다.

```bash
uv run --locked industrial-phm experiment inspect \
  docs/research/results/xjtu-sy-rul-lstm-fold-1-benchmark-v1.json
```

직접 준비한 XJTU-SY 데이터로 새 분석을 실행하려면
[Analysis Explorer 안내](apps/README.md)의 **내 데이터로 분석하기**를 따릅니다.

## 사용한 데이터

| 데이터 | 이 프로젝트에서의 활용 |
| --- | --- |
| **XJTU-SY** | 베어링 진동 데이터의 이상 변화 분석과 RUL 연구 |
| **IMS Bearings** | 서로 다른 베어링 실행 데이터에서 분석 흐름과 결과 변화를 확인 |
| **MIMII DUE** | 기계 음향 데이터의 이상 분석과 환경 차이에 따른 변화 확인 |
| **AI4I 2020** | 데이터 등록·다운로드·무결성 확인 흐름의 간단한 예제 |

데이터 준비 방법과 출처는 [데이터 안내](data/README.md),
데이터셋을 선택한 배경은 [연구 문서](docs/research/dataset-selection.md)를 참조합니다.

## 현재 개발 방향

```text
prepared 단일-asset CSV export 검증 / canonical mapping
  -> timestamped observation timeline + 첫 private/field source conformance
  -> RegisteredSource control plane / persistence / Sources UX
  -> Operations UI에서 관측 / data quality / PHM evidence 연결
  -> source lifecycle / freshness / prepared-file polling runtime
  -> first OPC UA one-shot read proof
  -> OPC UA registration contract / registry v4 persistence / Sources read + explicit registration UX
  -> OPC UA one-shot endpoint probe / bounded browse / mapping UX
  -> registered OPC UA one-shot read + receipt persistence + canonical observation projection + Operations manual run
  -> OPC UA runtime → latest connection-attempt evidence 기록
  -> Operations latest attempt evidence 표시 / source-health inspection projection 완료
  -> FILE/OPC UA caller-owned CLI polling
  -> bounded OPC UA DataChange subscription connector
  -> persistent session telemetry / reconnect runtime
  -> source에 맞는 diagnostics / prognostics 검증
  -> 실시간 분석과 유지보수 시스템 연계
```

현재 우선순위는 다양한 모델을 추가하는 것보다 실제 센서 데이터를 더 쉽게 연결하고,
현장 데이터에서 분석 결과가 어떻게 달라지는지 확인하는 것입니다. File/file-directory source의
등록 identity와 CSV mapping을 보존하는 최소 `RegisteredSource` / `FileSourceConfig` /
`SourceRepository` control-plane contract와 versioned local JSON persistence가 추가되었습니다.
현재 persistence는 single-writer local registry 범위이고 Operations의 Sources 화면에서 prepared
file/history source를 discover, preview, map, validate한 뒤 등록하고, 선택한 registered source를 현재
Observation/Timeline으로 다시 로드할 수 있습니다. Load 시 source bytes를 재검증하므로 registration 시점의
검증 결과를 현재 관측으로 캐시하지 않습니다. Registry v4는 FILE/OPC UA registration, lifecycle과 optional source-specific freshness policy를 함께 보존하고
기존 v1/v2/v3 prepared-file registry를 읽어 다음 write에서 v4로 승격합니다. Operations에서
Activate/Pause와 max observation age policy 설정/해제가 가능하고 ACTIVE source는 one-shot runtime cycle을
실행할 수 있지만 ACTIVE나 FRESH를 online/healthy/continuously-ingesting으로 해석하지 않습니다. Registered source의 on-demand load에는 `received_at`과
observed→received delivery lag evidence가 추가되었고, policy가 있으면 latest observation age를 별도로
평가해 FRESH/STALE을 표시합니다. Latest accepted receipt는 별도
`industrial-phm-source-runtime-v2` state에 영속되어 restart 후에도 monitoring read model이 복원됩니다. v1 receipt-only state도 읽을 수 있고 다음 write에서 v2로 승격됩니다. OPC UA one-shot runtime은 latest bounded connection-attempt evidence도 기록하고 Operations Sources에서 outcome/timing/detail을 확인할 수 있지만 current connection state로 해석하지 않습니다. Receipt/attempt **history**도 아직 없습니다. Current lifecycle, persisted latest receipt와
freshness policy를 묶은 source-health read model은 제공하지만 boolean healthy/unhealthy나 connection
success를 추론하지 않습니다. Operations UI의 runtime cycle은 explicit single iteration이고, CLI의
`operations poll-source`는 source type별 one-shot cycle을 일정 interval로 동기 반복합니다. OPC UA는 각 iteration마다 새 connect/read/disconnect를 수행하고 connection/session을 cycle 사이에 유지하지 않습니다. Polling은 failure/non-ACTIVE에서
즉시 멈추며 retry/backoff나 background daemon을 만들지 않습니다. Browser upload/file-picker, source
edit/delete도 아직 지원하지 않습니다. OPC UA는 one-shot protocol read, application-level
`OpcUaSourceConfig` / `SourceType.OPCUA` registration identity, local registry v4 round-trip과 Operations Sources
read surface까지 검증했습니다. Registry에 보존되는 endpoint는 anonymous/NoSecurity `opc.tcp`만 허용하고
endpoint userinfo credential은 거부합니다. Operations Add source에서는 endpoint, asset/measurement point,
browse 후보 또는 explicit `channel_id,node_id` mapping과 timeout을 등록할 수 있습니다. Connector API의 one-shot endpoint probe와 bounded browse는 지속 connection state를 만들지 않습니다. Application의 registered OPC UA one-shot runtime/receipt persistence는 Operations **Run active source once**에도 연결됩니다. OPC UA 성공은 latest receipt/freshness evidence를 갱신하고 one-shot snapshot을 `AssetObservationSummary`로 projection합니다. Projection은 `sample_count=1`, mapped channels와 asset/source identity를 보존하고 complete-channel SourceTimestamp watermark만 observation time으로 사용하며, sampling rate/file snapshot provenance는 만들지 않습니다. CLI polling도 OPC UA one-shot cycle을 반복할 수 있습니다. Connector에는 explicit NodeId를 대상으로 max-events/session-timeout/queue bound를 둔 bounded DataChange subscription 수집도 추가됐지만, 아직 registered-source application lifecycle/runtime persistence/Operations에 연결하지 않았고 auto-reconnect도 사용하지 않습니다. Persistent session telemetry와 continuous ingestion은 아직 지원하지 않습니다.

준비된 단일-asset CSV export는 Python 코드를 작성하지 않고도 CLI에서 먼저 검증할 수 있습니다.

```bash
uv run --locked industrial-phm data validate-csv \
  --source /path/to/pump.csv \
  --asset-id pump-01 \
  --channel vibration_x \
  --channel vibration_y \
  --sampling-rate-hz 12800
```

Timestamp column을 함께 사용하는 경우 `--timestamp-column`을 지정할 수 있고, declared sampling rate와
timestamp interval의 consistency를 확인하려면 `--sampling-rate-tolerance-ratio`를 명시합니다. 이 명령은
source structure/quality/provenance만 검증하며 모델 fitting이나 thresholding은 실행하지 않습니다.

현재 일반 field-input contract는 CSV export/snapshot에 한정됩니다. MIMII의 WAV 입력은 dataset-specific
audio adapter이며 generic field WAV adapter를 의미하지 않습니다. 실제 private source conformance, historian/API
연결과 field model execution은 실제 source requirement를 확인한 뒤 확장합니다.

최근 PHM 연구와 산업 적용 방향은
[PHM 연구·산업 동향](docs/research/phm-industry-direction.md)에 별도로 정리합니다.

## 더 자세히 보기

- [Analysis Explorer](apps/README.md) — 분석 화면과 실행 방법
- [아키텍처](docs/architecture/overview.md) — 전체 구성과 책임 분리
- [제품·UX 기준](docs/product/overview.md) — 분석 결과를 사용자에게 보여주는 방식
- [데이터 준비](data/README.md) — 데이터셋 준비와 검증
- [연구 문서](docs/research/README.md) — 실험 프로토콜, RUL 연구, 실행 기록
- [기여 방법](CONTRIBUTING.md) — 개발 환경, 코드 변경, 테스트 방법

자세한 변경 내용은 [변경 이력](CHANGELOG.md), 테스트 기준은 [테스트 정책](docs/testing-policy.md)을 참조합니다.

## 라이선스

[Apache License 2.0](LICENSE)을 사용합니다.
데이터셋의 원본 라이선스와 출처는 각 데이터 문서를 따릅니다.
