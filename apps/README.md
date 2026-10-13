# Applications

이 디렉터리는 repository-local interactive application의 **실행·개발 진입점**을 설명합니다.

현재 지원 capability와 제한은 [프로젝트 상태](../docs/status.md), 제품 정보 구조와 UX 의미는
[제품·UX 기준](../docs/product/overview.md), runtime/data ownership은
[architecture 문서](../docs/architecture/overview.md)를 authoritative source로 사용합니다.
이 문서는 화면별 현재 기능 목록을 중복해서 유지하지 않습니다.

## Operations — supervised Web

현재 운영자 제품은 패키지 내 Web 자산(`src/industrial_phm/apps/web/`)과
Python API로 실행합니다. 운영용 marimo 애플리케이션 및 `--ui marimo`는 제거했습니다.
연구용 `apps/analysis_explorer.py`와 노트북의 marimo는 별개로 유지합니다.

```bash
make up
make status
make logs
make down
```

기본 작업공간은 `artifacts/operations`이며 `WORKSPACE=<path>`로 변경합니다.
`make up`은 collection/analysis/Web를 하나의 Supervisor로 시작하므로,
이미 동일 작업공간에 수동으로 실행한 수집기·분석기와 병행하지 마세요.

```bash
uv sync --locked --extra operations
uv run --no-sync industrial-phm operations up artifacts/live
# 정지된 workspace의 수집/분석 재시작이 필요하지 않은 독립 UI/API 진단:
uv run --no-sync python -m industrial_phm.runtime.operations_web_preview \
  artifacts/live --port 8765
```

마지막 UI-only 명령은 **독립 Web preview**이며 Supervisor의 수집/분석 lifecycle을
소유하지 않습니다. 같은 workspace의 supervised Web가 작동 중이면 협조적 writer lease가
preview 쓰기를 차단합니다. 무인증 네트워크·다중 사용자 서비스가 아닙니다.

빈 Web 작업공간에서 분리된 synthetic 샘플을 명시적으로 시작·중지할 수 있고,
FILE/OPC UA 소스별 등록·활성·수신 근거와 저장 이력, 분석 근거, Review를 조회할 수
있습니다. 전체 영어 UI·접근성과 모든 업무·오류 복구는 현재 수용 범위 밖이며
[현재 지원 상태](../docs/status.md)가 범위 기준입니다.
소스·설비·측정점·채널·분석/검토 ID와 UTC 의미는 화면에서 변경하지 않습니다.

개별 OPC UA replay와 fault/recovery 실험은 [도구 안내](../tools/opcua/README.md)를
따르며, 연구 화면은 아래 Analysis Explorer 실행 지침을 따릅니다.

### 기본 설비 모니터링

`/web/#monitor`는 관측 상태, 확인할 설비, 선택 설비의 실제 신호 순서로 표시합니다. 같은 설비의 분석 거부는
하나의 확인 항목으로 묶고, 기준 비교·새 입력 대기·원본 읽기 실패를 구별합니다. 이상 탐지 현재값·이전값·변화량·기준 비교는 신호와 함께 표시하며, 모델 설정과 입력 상세는 보조 영역에 둡니다.
선택한 XJTU 획득은 저장된 원본 RMS 크기와 직전 조회 기록 대비 증가·감소율, 최근 연속 기록을 보여줍니다.
앞선 비교 기록은 정상 기준이 아니며 기록 번호 공백은 현장 통신 중단의 근거가 아닙니다. 원본 파형과 전체 조회 범위도
선택할 수 있습니다. 공기압축기는 실제 전류·전압·주파수를 원래 단위로 보여줍니다.
상세 영역의 `이 시점의 추세·원본 입력 보기` 또는 `RUL·검토 상세`는 같은 바인딩과 저장된 시점을 열며,
주소의 `phm_binding`·`phm_position`은 재로딩 후에도 유지됩니다. 기준 초과는 고장 판정이 아닙니다.

기본 갱신은 3초마다 운영 요약 3개를 읽고, 선택한 입력이 바뀔 때만 원본 미리보기와 최대 64개 저장 결과를
추가로 읽습니다. 모델 100개까지의 요약 범위와 읽기 실패를 표시합니다. 원본 검증이 실패하면 파형과 크기 요약을
지우며, 이전 입력은 버튼을 명시적으로 누른 경우에만 구별해 표시합니다. 부하·불평형 변화 분석은 수동 실행입니다.

### 이상 탐지 · RUL 모니터링 (XJTU-SY 기록 재생)

**이상 탐지**와 **RUL 모니터링** 화면은 작업공간에 연결된 모델 패키지의 저장된 step 결과를 3초마다
변경분으로 읽습니다. 이상 탐지 상세는 선택 기록의 점수·앞선 분석 대비 변화량과 같은 범위의 신호 크기를
나란히 표시하고, 해당 기록의 원본 신호를 바로 아래에 둡니다. 기본 범위는 선택 시점의 연속 기록이며 전체 기록도
선택할 수 있습니다. 그래프 또는 키보드로 기록을 선택하면 요약·원본·주소가 함께 바뀌고, 새 입력이 도착해도
선택 기록을 유지합니다. `최신 기록으로`는 최근 결과를 따라가는 모드로 돌아갑니다. 모델·입력 특징과 검토 구간은
보조 영역에서 확인합니다. RUL의 요약과 검토도 선택 시점을 따릅니다.

모델을 연결하는 순서는 다음과 같습니다(준비된 XJTU-SY 원본은
[데이터 안내](../data/README.md#xjtu-sy)를 따릅니다).

```bash
make up                                   # 첫 터미널: 수집·분석·Web Supervisor
# 다른 터미널
SRC=data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets
uv run --no-sync industrial-phm operations phm package-xjtu artifacts/operations --source "$SRC"
uv run --no-sync industrial-phm operations phm bind artifacts/operations \
  --package <이상 점수 package ID> --source-id xjtu-sy-replay --asset-id Bearing1_1
uv run --no-sync industrial-phm operations phm bind artifacts/operations \
  --package <RUL package ID> --source-id xjtu-sy-replay --asset-id Bearing1_1
uv run --no-sync industrial-phm operations phm replay-xjtu artifacts/operations \
  --source "$SRC" --bearing Bearing1_1 --interval-seconds 1
```

- `package-xjtu`는 fold-1 연구 설정을 train 베어링으로 다시 학습해 `models/`에 불변 패키지로 씁니다
  (약 3–4분). 깨끗한 Git checkout이 아니면 `--code-revision`을 지정합니다.
- 재생은 기록 데이터를 시간 압축해 공급하는 것이며 화면에 "기록 데이터 재생"으로 표시됩니다. 재생 대상은
  모델 학습에 쓰지 않은 베어링(`Bearing1_1/2_1/3_1`, `Bearing1_2/2_2/3_2`)을 사용합니다.
- 분석 runner는 0.5초마다 새 step을 처리하고, 화면은 최신 수신·최신 분석 시각과 분석 대기 수를 함께 보여줍니다.
- 이상 점수는 고장 확률·진단이 아니며, RUL은 데이터셋의 마지막 기록 획득까지의 획득 간격입니다. 판정 기준과
  검증 결과는 [운영 추론 수용 프로토콜](../docs/research/operational-inference-acceptance-protocol.md)을 따릅니다.

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


### AI-Hub 전기 다변량 모델 개발 경로

공기압축기 후보의 운영 승격 [평가 v2](../docs/research/results/aihub-239-electrical-anomaly-evaluation-v2.json)는
**FAIL**입니다. 다음 경로는 원본 신호와 모델 출력을 탐색하는 개발 기능이며 합격한 현장 경보·진단이 아닙니다.
AI-Hub에는 수명 종료 사건이 없어 RUL을 생성하지 않습니다.

```bash
uv sync --locked --extra operations --extra aihub
uv run --no-sync python -m tools.opcua.aihub_replay prepare \
  --root artifacts/aihub-phm --endpoint opc.tcp://127.0.0.1:48555/phm/ \
  --archive data/raw/aihub/239/archives/training/raw/3.공기압축기.zip \
  --member 3.공기압축기/SourceData_16.json \
  --binding tools/opcua/presets/aihub-air-compressor-1338-replay.json \
  --start 2020-11-13T09:35:00 --end 2020-11-13T10:09:00
# 개발 replay가 만든 sources/control을 보존하며 작업공간 형식만 초기화합니다.
uv run --no-sync python - <<'PY'
from pathlib import Path
from industrial_phm.runtime.operations_workspace import OperationsWorkspace, initialize_operations_workspace
initialize_operations_workspace(OperationsWorkspace(Path("artifacts/aihub-phm")), allow_recognized_legacy=True)
PY
uv run --no-sync industrial-phm operations phm package-aihub artifacts/aihub-phm \
  --archive data/raw/aihub/239/archives/training/raw/3.공기압축기.zip \
  --member 3.공기압축기/SourceData_16.json --candidate pca-residual
```

시작 전에 `artifacts/aihub-phm/config.toml`의 `[collection] window_duration_seconds = 300.0`을
설정합니다. 다른 윈도우 길이는 이 모델의 입력이 아니므로 이유를 남기고 분석하지 않습니다.
출력된 package ID를 사용해 명시적으로 연결합니다. 측정점이 있는 다른 소스라면 `--measurement-point-id`도
정확히 지정하며, 생략하면 측정점이 없는 스트림만 선택합니다.

```bash
uv run --no-sync industrial-phm operations phm bind artifacts/aihub-phm \
  --package <package-id> --source-id aihub239-replay-air-compressor-1338 \
  --asset-id aihub-air-compressor-1338 --recorded-replay
uv run --no-sync industrial-phm internal request-collection \
  --workspace artifacts/aihub-phm --source-id aihub239-replay-air-compressor-1338 --state running
uv run --no-sync industrial-phm operations start artifacts/aihub-phm
# 다른 터미널: 속도는 전송에만 적용하고 원래 기록 시각·60초 cadence는 보존합니다.
uv run --no-sync python -m tools.opcua.aihub_replay server \
  --root artifacts/aihub-phm --speed 60 --recorded-timestamps
```

`/web/#anomaly`에서 입력 특징과 점수·검토 구간을 같은 축으로 탐색하고, 시점을 선택해 7개 원본 신호와
품질·PCA 잔차 기여를 확인합니다. 변화율은 선택 윈도우의 첫 유효 관측 대비 화면 비교값으로,
모델 정규화나 고장 원인 판정이 아닙니다. 최근 입력이 조건을 충족하지 않으면 이전 분석과 구분해 표시합니다.


### LSTM 이상 탐지 · RUL 연결

같은 준비된 XJTU-SY 데이터로 LSTM AE와 LSTM RUL을 패키징할 수 있습니다.
학습은 기존 frozen 연구 설정과 train 베어링만 사용하며, 실행 시 다시 학습하지 않고 저장 가중치를 적재합니다.

```bash
uv sync --locked --extra operations --extra deep-learning
uv run --no-sync industrial-phm operations phm package-xjtu-lstm artifacts/live \
  --source data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets
```

출력된 두 package ID를 `operations phm bind`로 기존 `xjtu-sy-replay`와 선택한 베어링에 각각 연결한 뒤
동일한 `replay-xjtu` 명령을 사용합니다. 두 화면의 설비·모델 목록에서 모델을 선택합니다.
처음 7개 획득은 과거 8개 입력을 모으는 준비 구간이며 결과로 채우지 않습니다. 버퍼는 결과와 함께 저장해
재시작 후 이어지고, 누락·입력 불일치·운전 조건 변경은 시퀀스 준비를 다시 시작합니다.
RUL의 참고 MAE는 기존 연구 결과이며 새 가중치의 성능 인증이 아닙니다. 같은 가중치의 계산 재현성과
제품 동작을 모델 성능 개선과 분리합니다.

### AI 설명과 사람 검토 (local-main)

이상 탐지·RUL 화면에서 선택한 저장 결과마다 **AI 설명 생성**과 **검토 요청 → 검토 확인 → 검토 종료**를
기록할 수 있습니다. 쓰기는 감독 실행(`make up`) 화면에서만 가능합니다.

```bash
# 기본값: 로컬 OpenAI 호환 서버의 local-main (Responses API, 없으면 Chat Completions)
export INDUSTRIAL_PHM_GENAI_BASE_URL="http://127.0.0.1:9400/v1"
export INDUSTRIAL_PHM_GENAI_MODEL="local-main"
# 선택: INDUSTRIAL_PHM_GENAI_API_KEY, 원격(https) 주소는 INDUSTRIAL_PHM_GENAI_ALLOW_REMOTE=1일 때만
```

- AI에는 저장된 결과와 함께 **코드가 확정한 의미 문장**(점수·종료점·검증 근거·적용 범위)을 전달하고,
  수치를 다시 계산하거나 고장 확률·진단·신뢰구간을 만들지 않도록 지시합니다.
- 생성된 설명의 숫자를 저장된 근거와 대조해, 근거에 없는 수치가 있으면 경고와 함께 표시합니다.
- 설명은 분석 결과와 별도 저장소(`phm-explanations.sqlite`)에 저장되며 모델 출력을 바꾸지 않습니다.
  AI 서버가 응답하지 않아도 분석 조회와 직접 검토는 계속됩니다. 검토 종료는 정비 완료가 아닙니다.
- `INDUSTRIAL_PHM_GENAI_MODEL`은 연구 Analysis Explorer의 OpenAI 설명과 같은 변수명을 씁니다.
