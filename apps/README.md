# Applications

이 디렉터리는 repository-local interactive application의 **실행·개발 진입점**을 설명합니다.

현재 지원 capability와 제한은 [프로젝트 상태](../docs/status.md), 제품 정보 구조와 UX 의미는
[제품·UX 기준](../docs/product/overview.md), runtime/data ownership은
[architecture 문서](../docs/architecture/overview.md)를 authoritative source로 사용합니다.
이 문서는 화면별 현재 기능 목록을 중복해서 유지하지 않습니다.

## Operations

wheel에 포함되는 canonical operational application은
`src/industrial_phm/apps/operations.py`입니다.

정상 local lifecycle은 저장소 root의 한 front door를 사용합니다.

```bash
make up
make status
make logs
make down
```

기본 workspace는 `artifacts/operations`입니다. 다른 root는 같은 값을 모든 runtime component에
공유하도록 `WORKSPACE=<path>`로 지정합니다.

```bash
make up WORKSPACE=artifacts/site-a
```

빈 workspace의 `make up`은 first-run 화면에서 synthetic sample과 실제 데이터 연결을 선택하게 합니다.
sample은 real workspace와 분리된 demo workspace에서 기존 synthetic product demo를 실행합니다.
`make demo`는 first-run UI를 거치지 않고 같은 demo를 직접 실행하는 개발·진단 shortcut입니다.

현재 Operations가 지원하는 Monitor / Assets / Investigations / Maintenance / System / Setup의
정확한 범위는 [docs/status.md](../docs/status.md)를 참조합니다. Live observation과
observation/interpretation 경계는 [docs/product/overview.md](../docs/product/overview.md)가 소유합니다.

### Display locale

Operations는 `ko-KR`과 `en-US` locale resource를 사용합니다. 앱 상단의 language selector에서
전환할 수 있으며, 초기값은 `INDUSTRIAL_PHM_LOCALE`을 먼저 보고 그다음 `LC_ALL`,
`LC_MESSAGES`, `LANG`을 해석합니다. 지원하지 않는 값은 `en-US`로 fallback합니다. 현재
localized coverage는 first-run, top-level navigation, Monitor와 주요 workspace의
status/label/action/help/error/empty-state 및 주요 table/section label까지 적용합니다. 한국어
typography와 error/content 구조, browser acceptance의 완료 범위는
[현재 지원 상태](../docs/status.md)의 경계를 따릅니다.

Locale은 presentation concern입니다. `source_id`, `asset_id`, `measurement_point_id`,
`channel_id`, `capability_id`, `analysis_run_id`, `evidence_id`, `finding_id`와 저장된 UTC
timestamp는 번역하거나 locale별로 다시 기록하지 않습니다.

### Direct CLI / development

`Makefile`은 runtime을 직접 구현하지 않고 canonical CLI에 위임합니다. service-manager 통합,
자동화 또는 UI-only 개발처럼 lower-level 제어가 필요한 경우에만 직접 실행합니다.

```bash
uv sync --locked --extra operations
uv run --no-sync industrial-phm operations init artifacts/live
uv run --no-sync industrial-phm operations start artifacts/live
```

UI만 개발용으로 실행할 때도 동일한 workspace root를 사용합니다.

```bash
export INDUSTRIAL_PHM_OPERATIONS_WORKSPACE=artifacts/live
uv run --no-sync marimo run src/industrial_phm/apps/operations.py
```

source/runtime/control/spool/telemetry/window/analysis/review/history path는
`OperationsWorkspace`가 workspace root 아래에서 결정합니다. Packaged Operations app은 개별
persistence path 환경변수를 조합하지 않습니다.

OPC UA simulator, recorded replay, independent collector와 fault/recovery 검증 절차는
[OPC UA tools](../tools/opcua/README.md)를 참조합니다. AI-Hub raw data 준비와 profiling은
[AI-Hub tools](../tools/aihub/README.md)를 참조합니다.

## Application roles

- `src/industrial_phm/apps/operations.py` — operational observation/evidence/human-review workspace
- `apps/analysis_explorer.py` — research environment에서 experiment/analysis evidence를 검토하는 PHM Workbench surface

Operations와 Analysis Explorer는 서로의 persistence/runtime ownership을 대신하지 않습니다.

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
