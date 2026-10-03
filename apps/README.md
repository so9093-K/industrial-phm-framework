# Applications

## Asset measurement history

Operations의 Assets는 같은 DuckLake에 있는 FILE backfill과 OPC UA 관측을 시간·채널별로 조회합니다.
`uv sync --locked --extra operations`로 Operations 실행 환경을 준비합니다. Analysis Explorer 개발 환경은 별도 `research` group을 사용합니다. AI-Hub를 처음 적재할 때는
[실행 안내](../tools/aihub/README.md#local-power-data-profiling-and-history)를 따릅니다.

Operations의 history catalog/data는 local workspace가 소유합니다. `operations init <root>`로 workspace를
만들고 `operations start <root>`로 collection/analysis/UI를 같은 root에 연결합니다. UI만 개발용으로 직접
실행할 때도 `INDUSTRIAL_PHM_OPERATIONS_WORKSPACE=<root>`를 지정합니다.

**Assets → Asset 선택 → Measurement History → 시간·측정 항목 선택 → 이력 조회 / 새로고침** 순서로
사용합니다. 시각 입력에는 UTC offset이 필요하고 종료는 미포함입니다. 최대 2,000개 관측을 표시하며 한도를
넘으면 범위를 줄이라는 안내를 보여줍니다. Source별 관측점, null의 시각 표시, 품질 문제·값 충돌과 provenance를
확인할 수 있습니다. 보간·집계·자동 건강 판정은 하지 않습니다. 예상 수집 주기가 없는 상태에서 공백을
자동으로 missing sample이라 부르지 않습니다.

Catalog에만 있는 설비도 목록에 표시합니다. 설비·채널 목록은 화면 초기화 시 읽고, 선택한 구간은 조회 버튼으로
다시 읽습니다. 신규 적재 후 **설비 이력 목록 새로고침**으로 목록을 갱신할 수 있습니다.
최근 범위는 조회 시점 기준으로 이동합니다. 15분은 최근 2,000개 원시 관측, 직접 지정은 첫 2,000개를
표시하며 요청 범위·실제 반환 범위·개수·잘림을 별도로 보여줍니다. 축은 요청 전체 범위로 유지합니다.
직접 지정 범위의 원시 관측이 2,000개를 넘으면 첫 2,000개 대신 전체 기간 200개 구간 집계로 전환합니다.
과거 적재 설비는 최근 범위 밖에 있으므로 이 경로로 긴 기간을 확인합니다. 표시 시각은 그래프와 같은 UTC입니다.
24시간은 200개 시간 구간, 7일은 100개 구간으로 전체 선택 기간을 집계합니다. source/측정점/매핑·의미
해석별로 분리하며 전체 반환 bucket은 최대 2,000개입니다. 초과 시 일부만 표시하지 않고 오류를 냅니다.
UI min/max/mean은 null·충돌·원천 non-good 값을 제외하며 제외 개수와 원본 관측 개수를 보존합니다.
동일값 중복도 개수에 포함하고 mean은 관측 개수 가중치입니다. 시간 가중 평균·에너지·source 평균 측정값이
아닙니다. 빈 시간 구간은 보간하지 않습니다. 해석 근거와 history snapshot ID를 집계 표에서 확인할 수 있습니다.

Source별 최신 저장값은 그래프 범위/한도와 별개로 조회합니다. `history_age_seconds`는 저장 관측의
나이이며 `event_time_state`는 recorded/future-timestamp/time-unavailable입니다. 과거 backfill/import/replay의
expected live freshness는 not-applicable입니다. LIVE 행의 freshness도 이 표에서 판정하지 않고
Sources의 기존 SourceFreshnessPolicy 및 receipt 화면으로 안내합니다. 설비 건강 판정이 아닙니다.
동일 최신 시각의 값이 충돌하면 대표값을 정상값처럼 표시하지 않습니다.
FILE source quality는 unknown이며 numeric/null availability와 분리합니다. OPC UA는 protocol Good/non-good을
보존합니다. Raw channel label은 canonical observed property로 승격하지 않고 미해석 상태를 표시합니다.

최신 저장 관측의 **최신 관측 출처·매핑 근거**에서 원본 파일·checksum, 시간대 가정,
설비 grouping 근거, 의미 해석 version과 단위 근거를 확인할 수 있습니다. 그래프 구간에
관측이 없어도 이 근거는 조회됩니다. 단위 정보가 없는 FILE/OPC UA 값은 `unknown`을 유지합니다.

독립 collector와 UI를 함께 실행하는 방법은 [로컬 OPC UA 스택](../tools/opcua/README.md)에 있습니다.
Local catalog 접근은 adapter가 connection 수명 동안 파일 잠금으로 조율하며 대기 한도 초과는 오류로
표시합니다. 하나의 control/spool 구성에는 하나의 collector를 사용합니다.

현재 repository는 목적이 다른 interactive application을 분리합니다.

- `src/industrial_phm/apps/operations.py` — wheel에 포함되는 canonical operational action/evidence workspace
- `apps/analysis_explorer.py` — repository research 환경에서 experiment/analysis evidence와 pipeline을 검토하는 PHM Workbench surface

### Operations

현재 기본 Operations는 `src/industrial_phm/apps/operations.py`입니다.
**Monitor / Assets / Investigations / Maintenance / System / Setup**이 실제 operational read model과
명시적 application action에 연결돼 있습니다. 메인 배경은 `#292827`입니다.

Investigations에서는 저장된 analysis evidence에 대해 사용자가 명시적으로 **Request review**를 누를 때만
human-review finding을 기록하고, Maintenance는 Open / Acknowledged / Closed 업무 queue로 이어 받아
note / acknowledge / close action을 기록합니다. 이 workflow는 fault/alarm/health/repair/CMMS 판단을
만들지 않습니다. Setup은 source 등록, Enable/Pause, OPC UA Start/Stop collection desired-state와
source별 데이터 경과 시간 정책을 소유합니다. One-shot runtime과 bounded subscription은 persistent
collection과 분리된 **Advanced diagnostics** action으로만 제공하며, 성공을 현재 connection health로
승격하지 않습니다. 등록된 FILE snapshot의 on-demand vibration feature 분석은 **Assets → Analysis**에서
실행하고 결과를 같은 evidence repository에 저장해 Assets와 Investigations에서 즉시 확인합니다.

**Assets**는 Monitor evidence와 DuckLake history asset의 합집합을 보여줍니다. Asset을 고르면
Overview / Signals / Analysis / Events / Maintenance로 같은 설비 문맥을 유지합니다. Signals는 기존
Asset History 의미를 그대로 사용해 15분 raw 관측(최대 최근 2,000개), 24시간·7일 전체 기간 UI 집계,
선택 channel의 latest stored value를 표시합니다. History-only asset은 live 상태를 추론하지 않으며,
history query 실패도 다른 Asset evidence 화면까지 막지 않습니다.

**Investigations**는 저장된 operational analysis를 최신순 queue로 보여주고 Review / Asset / Capability로
필터링합니다. Queue의 `Not requested / Open / Acknowledged / Closed`는 사람의 review workflow 상태이며
위험도나 고장 심각도가 아닙니다. 선택한 결과의 data quality와 capability-specific evidence를 오른쪽에서
검토하고, run/evidence/finding ID와 provenance는 detail/accordion으로 내려 progressive disclosure합니다.
Three-phase unbalance는 summary·trend·제외 사유·provenance를, FILE vibration feature는 exact snapshot
feature evidence를 표시합니다.

**Maintenance**는 review finding을 Status / Asset으로 필터링하고 selected review의 요청 시각, 현재 workflow
상태, note 수, append-only action timeline을 보여줍니다. Open은 note/acknowledge, Acknowledged는
note/close를 허용하며 Closed는 추가 event를 받지 않습니다. Maintenance에서 변경한 review state는 같은
V2 session의 Investigations에도 즉시 반영됩니다. Finding/run ID는 primary queue가 아니라 Review identity
detail에 둡니다.

**System**은 live acquisition / history storage / analysis service / current state read를 분리해서 보여줍니다.
Analysis runner는 persistent heartbeat와 최근 result/skip/failure가 있을 때만 runtime 상태를 표시합니다.
Operations application 자체의 process heartbeat는 아직 계측하지 않으므로 **Not instrumented**로 명시하고,
이번 refresh에서 state를 읽은 사실을 process health로 승격하지 않습니다. Source/session/history/spool 같은
관측 가능한 runtime fact는 primary System에 두고 repository path·state file 위치는 **Advanced diagnostics**로
내립니다. 읽기 실패는 현재 application state error로 별도 표시합니다.

**Setup**은 Data Sources / Signal Mapping / Measurement Semantics / Analysis Configuration으로 분리합니다.
Add Source는 **Source → Select signals → Define meaning → Review & save** 흐름을 사용합니다. FILE은 먼저
discovery로 공통 column을 확인하고 선택한 signal만 등록합니다. OPC UA는 bounded anonymous browse로
Variable identity를 찾고, 사용자가 선택한 NodeId만 explicit mapping으로 등록합니다. BrowseName·NodeId에서
물리 의미를 추론하지 않으며, measurement meaning은 channel별로 version과 interpretation evidence를
명시할 때만 `ChannelSemanticBinding`으로 저장합니다. 의미가 확정되지 않은 signal은 **Unresolved**로
남깁니다. 기존 registry contract는 등록된 source config의 in-place 수정 API를 제공하지 않으므로 이미
등록된 mapping/semantics는 read-only evidence로 보여줍니다. Enable/Pause는 administrative use state이고
Start/Stop collection은 collector에 대한 desired-state 요청일 뿐 connection/process running 증거가 아닙니다.
Analysis Configuration은 현재 안전하게 persist할 application contract가 없어 read-only ownership 안내만
제공합니다.

한 local Operations instance는 workspace root 하나로 지정할 수 있습니다.

```bash
industrial-phm operations init artifacts/live
industrial-phm operations start artifacts/live
```

`start`는 packaged Operations app을 collection/analysis와 같은 local supervisor 아래에서 loopback web app으로 실행합니다.
개발자가 UI만 별도로 확인할 때는 `operations` extra가 설치된 환경에서 packaged app path를 사용할 수 있습니다.

workspace를 지정하면 source/runtime/control/spool/telemetry/window/analysis/finding/review와
DuckLake catalog/data 경로를 같은 root에서 결정합니다. Packaged Operations app은 이 workspace root를
유일한 persistence composition input으로 사용하며 개별 state/history path 환경변수를 해석하지 않습니다.
Internal service/diagnostic CLI의 explicit path flag는 독립 process 검증을 위해 별도 경계로 유지합니다.

### 전력 품질 분석 · 3상 불평형

Asset Detail의 **전력 품질 분석 · 3상 불평형**에서 source와 구간을 고르고 **3상 불평형 분석 실행**을 누르면
[`three-phase-unbalance-v1`](../docs/architecture/phase-unbalance-capability.md)이 현재 history snapshot에서
실행됩니다. 결과는 전압(상전압 기준)·전류별 평가 시각 수, 제외 수, median/p95/max와 max 시각, 시간 구간별
median·max 그래프, 제외 사유, 입력·버전·설정 근거(snapshot ID, semantic version, 신호 기준)를 보여줍니다.
의미가 확정되지 않은 channel(예: metadata v1/v2 적재, semantics 예외 member, semantic binding이 없는
OPC UA source)과 정지 구간은 제외 사유로만 표시됩니다. 서술적 측정값이며 고장·건강·alarm 판정이 아닙니다.

결과는 workspace의 `phase-unbalance.sqlite`에 run마다 한 row로 저장되며(이전 결과를 다시 읽거나 다시 쓰지 않음)
**분석 기록**에서 이전 run을 다시 볼 수 있습니다.

별도 analysis runner process가 같은 파일에 기록한 결과는 Asset Detail이나
Investigation의 **Refresh analysis results**로 앱 재시작 없이 다시 읽습니다. 자동 polling은 하지 않으며 선택 중인
분석은 refresh 후에도 유지됩니다. 읽기에 실패하면 마지막 성공 읽기 결과를 그대로 두고 실패를 별도로 표시합니다.
Operations의 primary read는 누적 결과 전체를 매번 역직렬화하지 않고 최근 500개 3상 결과만 읽습니다.
다만 사람이 review를 요청한 과거 run은 500개 범위 밖이어도 analysis_run_id로 정확히 다시 읽어
Investigation/Maintenance evidence가 사라지지 않습니다. 이 제한은 표시/조회 경계이며 저장된 결과를 삭제하거나
retention하지 않습니다. 전체 저장 개수와 이번에 읽은 범위는 System → Advanced diagnostics에서 확인할 수 있습니다.
정상 product runtime에서는 supervisor가 analysis runner와 Operations UI process lifecycle을 함께 소유합니다. UI의 개별 action은 runner process를 직접 제어하지 않습니다. Asset Detail·Overview의 Analysis runs와 Investigation은 FILE 특징 분석과 3상 불평형을
함께 다룹니다. Investigation의 **검토할 분석**에서 결과를 고르면 capability별 근거가 보이고, **Create review
finding**으로 그 결과에 대한 사람의 검토 요청을 만들어 Maintenance Review로 이어갈 수 있습니다.

## Legacy Operations migration

Phase 9부터 packaged Operations application이 canonical Operations surface입니다. 이전 legacy Operations
application은 제거됐고, 필요한 기능은 Monitor / Assets / Investigations / Maintenance / System / Setup
문맥으로 이관됐습니다. One-shot source cycle과 bounded OPC UA subscription은 Setup의 **Advanced diagnostics**로,
FILE snapshot vibration feature analysis는 **Assets → Analysis**로 이동했습니다. Source별 데이터 경과
시간 정책도 Setup에서 저장·해제합니다.

Legacy 화면의 Overview / Sources / Investigation / Maintenance Review / Operational State IA는 더 이상
현재 사용 흐름이 아닙니다. 상세 runtime/contract 경계는 [현재 지원 상태](../docs/status.md)와
[아키텍처 문서](../docs/architecture/overview.md)를 기준으로 확인합니다.

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
- **검토 및 조치** — descriptive review interval이 있으면 사용자가 메모와 검토 완료 상태를 durable local review state에 저장. Operations Investigation에서도 같은 human-review evidence를 읽음
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

### 검토 및 조치

결과에 descriptive review threshold를 넘는 연속 구간이 있으면 **검토 및 조치** 화면에서 우선 확인 구간을 보고 메모를 남긴 뒤 **검토 완료로 표시**할 수 있습니다. acknowledgement는 analysis artifact의 exact SHA-256, asset, review policy와 함께 local JSON state에 저장되어 앱 재시작 후에도 복원됩니다. 기본 경로는 `artifacts/analysis/review-state.json`이며 `INDUSTRIAL_PHM_ANALYSIS_REVIEW_STATE`로 변경할 수 있습니다. 이 기록은 OperationalFinding, fault diagnosis, maintenance work order 또는 CMMS 기록을 생성하지 않으며, review interval이 없다는 사실도 설비 정상 판정으로 해석하지 않습니다.

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
