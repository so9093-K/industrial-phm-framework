# Applications

현재 repository는 목적이 다른 두 interactive application을 분리합니다.

- `apps/operations.py` — asset 관측, data quality, PHM/maintenance capability 상태와 system health를 보는 Operations surface
- `apps/analysis_explorer.py` — experiment/analysis evidence와 pipeline을 검토하는 PHM Workbench surface

## PHM Operations

`apps/operations.py`는 운영 사용자가 **있어야 할 정보 구조를 처음부터 확인**할 수 있게 합니다. 현재 값이
없다는 이유로 Condition, Finding, RUL, Maintenance 또는 System Health 영역을 숨기지 않습니다. 대신
검증·연결 상태를 명시하고 값을 꾸며내지 않습니다.

```bash
uv run --locked --group research marimo run apps/operations.py
```

현재 local inspection 입력은 **prepared single-asset CSV snapshot** 또는 같은 asset/measurement point의
**timestamped CSV history directory**입니다. **Overview → Prepared source inspection**에서 single source path 또는
history directory, asset/source ID, optional measurement point, channel과 time mapping을 입력합니다. History
directory가 지정되면 single source보다 우선합니다. 이 입력은 Overview에서만 노출하고, 지속적으로 관리할
registered source의 설정·lifecycle·runtime action은 **Sources**가 소유합니다.

**Sources** 화면은 별도의 persistent source registry를 읽어 등록된 source의 identity와 type-specific configuration을 표시합니다. **Add source**의 type selector에서 FILE 또는 OPC UA를 선택할 수 있습니다. FILE은 file/history mode,
asset/measurement-point mapping, channels, timestamp/sampling policy와 registration time을 목록/상세로 표시합니다.
등록 record와 별도로 `REGISTERED / ACTIVE / PAUSED / ERROR` lifecycle state를 보존하고 Sources에서
Activate/Pause할 수 있습니다. ACTIVE는 one-shot source runtime이 소비할 수 있는 administrative
enablement이며, 그 자체로 connection/health/freshness/continuous ingestion을 주장하지 않습니다. 기본 registry 경로는
`artifacts/operations/source-registry.json`입니다. Latest accepted receipt는 별도 runtime-state 파일
`artifacts/operations/source-runtime.json`에 저장합니다. 두 경로 모두 환경변수로 바꿀 수 있습니다.

```bash
export INDUSTRIAL_PHM_OPERATIONS_SOURCE_REGISTRY="/path/to/source-registry.json"
export INDUSTRIAL_PHM_OPERATIONS_SOURCE_RUNTIME="/path/to/source-runtime.json"
uv run --locked --group research marimo run apps/operations.py
```

Sources 화면은 persistent registration/control-plane 흐름만 보여주고 Overview의 일회성 prepared-source
inspection 입력을 반복 노출하지 않습니다. **Add source**는 prepared CSV file/history-directory와
OPC UA registration을 지원합니다. OPC UA는 endpoint, source/asset/measurement-point identity와 timeout을 입력한 뒤 bounded Variable browse를 실행해 후보를 선택하거나, 한 줄당 `channel_id,node_id` mapping을 직접 입력해 registry v4에 저장합니다. Browse는 NodeId/browse/display path만 발견하고 value를 읽지 않으며, 선택한 후보는 BrowseName을 channel ID로 사용합니다. Application에는 ACTIVE registered OPC UA source를 한 번 읽고 latest receipt를 저장하는 async runtime cycle이 있으며 Operations의 **Run active source once**가 FILE/OPC UA를 type-specific dispatch합니다. Application에는 ACTIVE registered OPC UA source의 persisted endpoint/NodeId mapping으로 bounded DataChange session을 한 번 수집하는 API도 있습니다. 각 notification은 source/asset/measurement-point identity와 zero-based local collection order를 가진 registered DataChange event로 조회할 수 있습니다. 이 collection index는 OPC UA server sequence가 아니며 gap-free delivery evidence도 아닙니다. Bounded result는 configured/observed/missing channel coverage도 계산하지만, full channel coverage는 timestamp-aligned snapshot이나 analysis-ready observation/window를 의미하지 않습니다. Lifecycle-aware bounded subscription cycle은 latest connection-attempt evidence만 runtime-state v3에 `opcua-subscription` operation으로 기록하고 receipt/freshness는 만들지 않습니다. Operations Sources의 **Collect bounded subscription**은 ACTIVE OPC UA source에 이 bounded cycle을 실행하고 completion reason, notification count, channel coverage와 event-level value/status/timing을 현재 app session에서 보여줍니다. Notification persistence, complete observation/window projection, reconnect/continuous ingestion에는 아직 연결하지 않습니다. Multi-node `observed_at`은 모든 mapped node에 SourceTimestamp가 있을 때 earliest timestamp를 complete-channel watermark로 사용합니다. Explicit OPC UA data-contract/transport failure만 source-owned로 분류하고 runtime 부재나 unexpected internal failure는 platform-owned로 남깁니다. OPC UA 성공은 receipt/freshness state를 갱신하고 protocol snapshot을 canonical `AssetObservationSummary`로 projection합니다. One-shot iteration은 `sample_count=1`로 표현하고 mapped channel identity를 보존하며, 모든 mapped node에 SourceTimestamp가 있을 때만 conservative complete-channel watermark를 observed start/end로 사용합니다. Non-good OPC UA status는 `opcua-non-good-status` data-quality ERROR로 aggregate하고 sampling rate/file provenance는 추정하지 않습니다.
현재 **Add source** 등록 흐름은 다음 네 단계입니다.

```text
Source
  -> Discover & Preview
  -> Mapping
  -> Validate & Register
```

현재 Source 단계는 browser upload가 아니라 실행 중인 Operations가 접근 가능한 **CSV file 또는 history-directory
path**를 받습니다. Discover는 각 CSV header를 읽어 모든 파일에 공통인 column, file count, total bytes,
header variant 수와 representative preview를 보여줍니다. Mapping 뒤 Validate & Register는 별도의 UI 검증기를
만들지 않고 기존 `CsvSensorLayout` / field observation / timeline validation을 그대로 실행한 뒤에만
`JsonSourceRepository`에 저장합니다. Path/mode/delimiter를 discovery 이후 바꾸면 stale discovery로 처리해
재-discover를 요구합니다.

등록 이후에는 Sources의 **Load registered source**로 선택된 source를 별도 path/mapping 재입력 없이
Observation surface에 연결할 수 있습니다. 이 동작은 registration 결과를 캐시하지 않고 등록된 config로
현재 file/history bytes를 다시 읽고 기존 CSV/timeline validation을 재실행합니다. Source가 삭제되거나
내용이 invalid하게 바뀌면 현재 load가 fail-closed되고 이전 관측값을 새 source 결과처럼 유지하지 않습니다.
이는 on-demand observation load이며 continuous ingestion이나 source health monitoring이 아닙니다.

Registry v4는 FILE/OPC UA registration, lifecycle과 optional source-specific freshness policy를 함께 저장합니다.
기존 v1/v2/v3 prepared-file registry는 backward-compatible하게 읽고 다음 write에서 v4로 승격됩니다. 사용자 UI는
Activate/Pause와 freshness policy save/clear를 제공하고 ERROR는 향후 runtime이 실패 evidence와 함께 기록할
상태입니다.

### Source lifecycle

Source lifecycle은 connection-health model과 분리합니다.

```text
REGISTERED -> ACTIVE <-> PAUSED
                 |
                 v
               ERROR
                 |
                 +----> ACTIVE / PAUSED
```

등록 직후 상태는 `REGISTERED`입니다. `ACTIVE`는 source runtime이 소비하도록 enable된 administrative
intent이고, `PAUSED`는 runtime consumption을 중지하려는 intent입니다. Sources의 **Run active source once**는
ACTIVE 상태만 실제로 소비합니다. FILE validation/I/O failure와 OPC UA explicit data-contract failure처럼
현재 source 입력/config를 그대로 다시 실행해도 성공할 수 없는 source failure는 ACTIVE → ERROR로 전이하고
concrete detail을 보존합니다. OPC UA transport `OSError`는 source-owned failed attempt로 기록하지만
administrative ACTIVE intent는 유지합니다. OPC UA optional runtime 부재, caller-contract/internal error,
runtime-state persistence 같은 platform-owned failure도 cycle을 FAILED로 표시하되 lifecycle은 ACTIVE를
유지합니다. ERROR는 사용자가 Activate로 명시적으로 복구한 뒤 다시 실행할 수 있습니다. Connection,
freshness, retry/buffer telemetry를 lifecycle state 자체에서 추론하지는 않습니다.

Registry는 기존 `industrial-phm-source-registry-v1`과 v2를 읽을 수 있습니다. v1 source는 implicit
`REGISTERED`로 해석하고 v2의 explicit lifecycle은 그대로 유지합니다. 신규 등록, lifecycle 변경 또는
freshness policy write가 발생하면 `industrial-phm-source-registry-v4`로 저장됩니다. 기존 v1/v2/v3 file registry는 읽을 수 있고 다음 write에서 v4로 승격됩니다.

### Runtime execution cycle

**Run active source once**는 scheduler가 아니라 한 번의 명시적 runtime iteration입니다. UI action은 선택된 source type에 따라 FILE current-byte validation 또는 OPC UA one-shot connect/read/disconnect를 실행합니다.

```text
REGISTERED / PAUSED / ERROR
  -> SKIPPED

ACTIVE FILE
  -> registered source current bytes 재검증

ACTIVE OPC UA
  -> one-shot connect/read/disconnect

Both
  -> SourceReceiptEvidence 생성
  -> latest runtime receipt persistence
  -> success: ACTIVE 유지
  -> source config/data-contract failure: ERROR + failure detail
  -> OPC UA transport failure: FAILED/SOURCE + ACTIVE 유지
  -> platform-owned failure: FAILED/PLATFORM + ACTIVE 유지
```

Manual **Load registered source**는 lifecycle과 무관한 inspection 경로로 계속 남습니다. 반면 runtime cycle은
ACTIVE lifecycle을 반드시 요구합니다. FILE validation/I/O 또는 OPC UA data-contract failure처럼 operator가
source/configuration을 확인해야 하는 source failure는 lifecycle ERROR로 기록합니다. OPC UA transport
`OSError`는 failure scope를 SOURCE로 유지하면서 lifecycle은 ACTIVE로 보존합니다. runtime
unavailable/caller-contract/internal/runtime-state persistence 같은 platform-owned failure도 cycle 자체는
FAILED지만 source lifecycle은 ACTIVE를 유지합니다. 이미 validation된 observation을 runtime success로
승격하지 않는 경계는 그대로 유지합니다.
Operations UI는 사용자가 버튼으로 한 iteration을 실행하는 구조를 유지합니다. 별도 CLI
`industrial-phm operations poll-source`는 registered source type에 따라 FILE 또는 OPC UA one-shot runtime cycle을 synchronous caller-owned loop로 반복하며,
background daemon, retry/backoff, buffering, connector session은 아직 구현하지 않습니다.

### Registered-source polling runtime

CLI에서는 ACTIVE registered FILE 또는 OPC UA source를 명시적 interval로 반복 실행할 수 있습니다.

```bash
uv run --locked industrial-phm operations poll-source \
  --registry artifacts/operations/source-registry.json \
  --runtime-state artifacts/operations/source-runtime.json \
  --source-id pump-source \
  --interval-seconds 5
```

`SourcePollingPolicy`는 positive finite interval과 optional positive `max_cycles`를 소유합니다. Polling은
registered source type에 따라 FILE one-shot validation cycle 또는 OPC UA fresh connect/read/disconnect cycle을
반복하고 success 사이에서만 sleep합니다. REGISTERED/PAUSED/ERROR로 SKIPPED되거나 SOURCE/PLATFORM failure가
발생하면 즉시 종료합니다. Platform failure를 자동 재시도하지 않는 이유는 retry/backoff policy가 아직 구현되지
않았기 때문입니다. `--max-cycles`를 생략한 CLI는 현재 process가 Ctrl+C를 받을 때까지 반복할 수 있지만 별도
service/background task를 만들지는 않습니다.

### Source health assessment

Sources의 health 표시는 단일 **healthy/unhealthy** verdict가 아니라 현재 확보한 evidence를 분리한 read
model입니다.

```text
SourceHealthAssessment
  ├ lifecycle
  ├ connection = NOT_INSTRUMENTED
  ├ data flow
  │    ├ INACTIVE
  │    ├ SOURCE_ERROR
  │    ├ NO_RECEIPT
  │    ├ FRESHNESS_NOT_CONFIGURED
  │    ├ FRESH
  │    ├ STALE
  │    └ TIMING_UNAVAILABLE
  ├ latest observed_at / received_at
  └ freshness assessment?
```

현재 FILE/OPC UA one-shot runtime은 persistent connector session telemetry를 기록하지 않으므로 read가 성공했거나 receipt가 fresh해도
connection을 connected/healthy로 승격하지 않습니다. ACTIVE인데 아직 receipt가 없으면 NO_RECEIPT,
source lifecycle ERROR면 SOURCE_ERROR, policy와 timing evidence가 있으면 freshness-derived data-flow state를
표시합니다. PAUSED/ERROR에서 다시 ACTIVE로 전환한 경우 current lifecycle change보다 오래된 persisted
receipt는 새 activation의 성공 evidence로 재사용하지 않고 NO_RECEIPT로 남깁니다. 이는 source monitoring
read model이며 asset health나 PHM finding과도 별개입니다.

### Receipt timing

Registered source의 **Load registered source**가 성공하면 `SourceReceiptEvidence`를 만들고
`JsonSourceRuntimeRepository`에 source별 latest receipt를 기록합니다. `received_at`은 source bytes가 기존
CSV/timeline validation을 통과한 뒤 application boundary에서 수락된 시각입니다. Latest source timestamp는
`observed_at`으로 유지하며 두 시간이 모두 timezone-aware일 때 signed observed→received lag를 계산합니다.
앱 재시작 시 runtime repository의 latest receipt를 복원해 Sources monitoring에 다시 사용합니다.

Prepared file은 원래 sensor transport arrival을 보존하지 않으므로 이 `received_at`을 과거의 실제 네트워크
도착 시각으로 해석하지 않습니다. Source timestamp가 naive이거나 없으면 delivery lag를 `Unavailable`로
남깁니다.

### Freshness policy

Sources에서 source별 **Max observation age (seconds)** 정책을 설정할 수 있습니다. Freshness는 delivery lag가
아니라 평가 시점 기준 latest observation age로 계산합니다.

```text
delivery lag     = received_at - observed_at
observation age  = assessed_at - observed_at

observation age <= configured max age  -> FRESH
observation age >  configured max age  -> STALE
missing/naive/future observed_at        -> UNAVAILABLE
no source policy                        -> NOT_CONFIGURED
```

Freshness는 timing-policy assessment일 뿐 connection/asset health 의미가 아닙니다. Latest receipt는
runtime state에 영속되지만 전체 receipt history나 background polling을 의미하지 않습니다. Freshness는
복원된 latest receipt와 현재 assessment time에서 다시 계산하므로 derived assessment 자체는 저장하지 않습니다.


### Runtime evidence state

Source registration/lifecycle/freshness policy는 control-plane registry가 소유하고, latest accepted receipt는
별도의 runtime repository가 소유합니다.

```text
source-registry.json
  registration / mapping / lifecycle / freshness policy

source-runtime.json
  latest SourceReceiptEvidence per source

# 반드시 source-registry.json과 다른 파일 경로여야 함
```

Runtime state writer는 `industrial-phm-source-runtime-v3`를 사용합니다. 기존 v1 receipt-only와 v2 operation-less state는 읽을 수 있고 다음 write에서 v3로 승격됩니다. v2 attempt는 작업 종류를 추정하지 않고 `legacy-unspecified`로 보존합니다. Registry와 runtime-state 경로가 같은
파일로 resolve되면 runtime write가 control-plane state를 덮어쓸 수 있으므로 startup과 write 모두
fail-closed로 차단합니다. Source ID별 latest receipt와 latest bounded connection-attempt evidence를 각각 deterministic하게 저장합니다. Receipt는 `received_at`, attempt는 `completed_at`이 과거로 되돌아가는 write를 거부합니다. Same received_at의 동일 evidence는
idempotent하게 허용하지만 같은 시각에 다른 evidence가 들어오면 충돌로 거부합니다. JSON write는 registry와
같이 same-directory temporary file + flush/fsync + `os.replace`를 사용합니다.

Latest connection-attempt evidence는 historical bounded-attempt fact일 뿐 current connection status가 아닙니다. Operations Sources는 selected source의 latest attempt operation, outcome, attempted/connected/completed timing과 failure detail을 별도 evidence block으로 표시합니다. 현재 runtime state는 retries, buffering, sequence counters, ingestion throughput, receipt/attempt
history를 저장하지 않습니다. 즉 restart-safe monitoring seed이지 continuous ingestion runtime 자체는 아닙니다.

한 CSV는 계속 한 canonical segment입니다. 여러 파일을 하나의 waveform으로 합치지 않고 각각
`AssetObservationSummary`로 검증한 뒤, explicit recorded timestamp가 있는 segment만
`AssetObservationTimeline` application read model로 묶습니다. Timeline은 filename이나 directory iteration
순서가 아니라 recorded observation time으로 정렬하며 overlap/reverse segment를 차단합니다. UI는
`CsvSensorValidationReport`를 직접 해석하지 않습니다.

현재 primary navigation:

- **Overview** — 현재 observation과 data quality, 아직 연결되지 않은 operational PHM 상태를 한눈에 확인
- **Sources** — FILE/OPC UA 등록, lifecycle, one-shot runtime, bounded OPC UA collection, receipt/freshness/attempt evidence
- **Investigation** — observation timeline과 향후 AnalysisRun/Finding/Prognostics 결과가 연결될 조사 surface
- **Data Quality** — source mapping, exact snapshot provenance, validation policy와 quality evidence

기존 **Assets / Asset / Maintenance / System Health** view 코드는 삭제하지 않았지만, 실제 data/action이 연결되기 전에는 완성된 제품 기능처럼 primary navigation에 노출하지 않습니다. 현재 제품 milestone은 `Source → Analyze → Results → Finding → Maintenance review`이며, 다음 작업은 registered source/observation에서 실제 `AnalysisRun`과 capability-specific result를 만드는 operational producer를 연결하는 것입니다.

Observation timeline도 PHM trend가 아닙니다. 시간순 source segment 목록은 실제 관측 이력일 뿐 anomaly,
condition, health 또는 RUL 의미를 만들지 않습니다. Research benchmark의 anomaly/RUL도 operational state로
복사하지 않습니다.

운영 분석 결과를 받을 application contract는 `AnalysisRun`과 `OperationalFinding`으로 분리되어 있습니다.
`AnalysisRun`은 execution/provenance envelope만 소유하고, `OperationalFinding`은 capability,
finding-semantics, opaque state와 evidence reference만 소유합니다. Generic finding에 score, threshold,
severity, RUL 또는 maintenance priority를 넣지 않습니다. 현재 Operations에는 이 contract의 producer가 아직
연결되지 않았으므로 Investigation과 System Health에서 `Not connected`/`Unavailable`로 표시합니다.

## Analysis Explorer

apps/analysis_explorer.py는 저장된 PHM experiment/analysis evidence를 화면에서 검토하고,
준비된 XJTU-SY 데이터로 새 분석을 실행하는 **PHM Workbench 성격의 interactive application**입니다.
운영 asset의 현재 관측 상태나 maintenance workflow를 소유하는 Operations dashboard는 아닙니다.

수치 계산은 앱에서 다시 구현하지 않고 industrial_phm.analysis의 기존 분석 경로를 사용합니다.
Operations surface는 experiment artifact를 직접 소비하지 않고 별도의 application/operational read model을
통해 구축합니다.

## 바로 실행하기

원본 데이터셋 없이도 저장소에 포함된 예제 결과를 바로 확인할 수 있습니다.

```bash
uv python install 3.14
uv run --locked --group research marimo run apps/analysis_explorer.py
```

기본 화면에서는 XJTU-SY LSTM 분석 결과가 열립니다.

- **결과 요약** — 집중 확인 구간과 가장 높은 구간을 먼저 보고 시간에 따른 점수 변화를 확인
- **근거 확인** — 점수가 높았던 관측값, 특징 잔차와 해당 결과에 대한 선택적 AI 설명
- **RUL 분석** — 저장된 RUL 모델 비교 결과와 해당 결과에 대한 선택적 AI 설명
- **새 분석 실행** — 준비된 XJTU-SY 데이터로 분석 실행
- **보고서 저장** — 선택한 설비의 Markdown 보고서 생성
- **상세 정보** — 검토 기준값, Spearman rho, 모델, 데이터 범위와 실행 이력

## 내 데이터로 분석하기

현재 앱에서 직접 실행하는 분석 경로는 준비된 XJTU-SY 데이터셋을 대상으로 합니다.
데이터 준비 방법은 [`data/README.md`](../data/README.md)의 XJTU-SY 절을 먼저 확인합니다.

실제 LSTM 분석에는 deep-learning 의존성이 필요합니다.

```bash
uv run --locked --group research --extra deep-learning \
  marimo run apps/analysis_explorer.py
```

앱의 **새 분석 실행**에서 데이터 폴더와 결과 위치를 입력한 뒤,
먼저 **데이터 확인 및 실행 계획 만들기**를 누릅니다. 이 단계에서는 representative acquisition으로
source profile과 population을 확인하고 실제 LSTM fit/scoring은 시작하지 않습니다.

계획에 차단 항목이 없고 입력이 변경되지 않은 경우에만 **분석 실행**으로 실제 분석을 시작합니다.
데이터 폴더나 결과 위치를 계획 확인 뒤 변경하면 기존 계획은 오래된 것으로 표시되며 다시 확인해야 합니다.

예시:

```text
data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets
```

결과 파일은 기본적으로 다음 위치에 저장됩니다.

```text
artifacts/analysis/xjtu-lstm-analysis.json
```

Git revision은 현재 clean checkout의 HEAD를 자동으로 기록합니다.
tracked file에 로컬 변경이 있으면 versioned 분석 결과 생성을 중단하고 먼저 commit 또는 revert하도록 안내합니다.

필요한 경우 환경변수로 기본 경로를 바꿀 수 있습니다.

```bash
export INDUSTRIAL_PHM_XJTU_SOURCE="data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets"
export INDUSTRIAL_PHM_ANALYSIS_OUTPUT="artifacts/analysis/xjtu-lstm-analysis.json"

uv run --locked --group research --extra deep-learning \
  marimo run apps/analysis_explorer.py
```

분석이 성공하면 새 결과가 현재 Explorer에 바로 반영됩니다.
실패하면 기존에 열려 있던 결과는 그대로 유지됩니다.

## 보고서 저장

Explorer의 **보고서 저장** 화면에서 현재 선택한 설비의 분석 결과를 Markdown으로 저장할 수 있습니다.

기본 위치:

```text
artifacts/reports/<asset-id>.md
```

CLI가 필요한 경우 기존 `analysis report` 명령도 사용할 수 있습니다.

## 생성형 AI 설명

AI 설명은 선택 기능입니다. 사용할 때만 실행 환경에 API key와 model을 설정합니다.

```bash
export OPENAI_API_KEY="..."
export INDUSTRIAL_PHM_GENAI_MODEL="<enabled-model-id>"

uv run --locked --group research marimo run apps/analysis_explorer.py
```

AI 설명은 독립 화면이 아니라 **근거 확인** 또는 **RUL 분석** 문맥에서 사용합니다.
AI 호출은 **AI 설명 생성** 버튼을 누를 때만 실행됩니다.

## 다른 저장 결과 열기

다른 분석 결과를 기본 화면에 열고 싶다면 환경변수로 artifact 경로를 지정합니다.

```bash
INDUSTRIAL_PHM_ANALYSIS_ARTIFACT=path/to/anomaly-result.json \
INDUSTRIAL_PHM_PROGNOSTICS_ARTIFACT=path/to/prognostics-result.json \
  uv run --locked --group research marimo run apps/analysis_explorer.py
```

서로 다른 분석 결과가 같은 화면에 표시될 수 있는지는 앱이 저장된 dataset/split/population 정보를 이용해 다시 확인합니다.

상세 `AnalysisView` projector가 있는 artifact는 기존 결과 요약/근거/RUL 화면으로 엽니다.
IMS cross-test, MIMII DUE development처럼 artifact inspection은 가능하지만 상세 trajectory projector가 없는
schema는 **inspection-only** 화면으로 열어 pipeline stage, capability, provenance를 확인할 수 있습니다.
이 경우 artifact에 기록되지 않은 observation-level score trajectory나 RUL evidence를 앱이 재구성하지 않습니다.

## 앱을 개발할 때

일반 사용자는 `marimo run`을 사용합니다.
앱 코드를 수정하거나 notebook cell을 편집할 때만 `marimo edit`을 사용합니다.

```bash
uv run --locked --group research marimo edit apps/analysis_explorer.py
```

모델·검증·artifact의 정확한 의미는 [연구 문서](../docs/research/README.md),
앱의 제품 정보 구조는 [제품·UX 기준](../docs/product/overview.md)을 참조합니다.

