# Analysis Explorer

`apps/analysis_explorer.py`는 저장된 PHM 분석 결과를 화면에서 확인하고,
준비된 XJTU-SY 데이터로 새 분석을 실행하는 사용자용 애플리케이션입니다.

수치 계산은 앱에서 다시 구현하지 않고 `industrial_phm.analysis`의 기존 분석 경로를 사용합니다.

## 바로 실행하기

원본 데이터셋 없이도 저장소에 포함된 예제 결과를 바로 확인할 수 있습니다.

```bash
uv python install 3.14
uv run --locked --group research marimo run apps/analysis_explorer.py
```

기본 화면에서는 XJTU-SY LSTM 분석 결과가 열립니다.

- **분석 요약** — 시간에 따른 이상 점수 변화와 집중 확인 구간
- **이상 근거** — 점수가 높았던 관측값과 특징 잔차
- **RUL 분석** — 저장된 RUL 모델 비교 결과
- **AI 설명** — 현재 분석 결과를 바탕으로 한 선택 기능
- **새 분석 실행** — 준비된 XJTU-SY 데이터로 분석 실행
- **보고서 저장** — 선택한 설비의 Markdown 보고서 생성
- **상세 정보** — 모델, 데이터 범위, 실행 이력 등 개발자용 세부 정보

## 내 데이터로 분석하기

현재 앱에서 직접 실행하는 분석 경로는 준비된 XJTU-SY 데이터셋을 대상으로 합니다.
데이터 준비 방법은 [`data/README.md`](../data/README.md)의 XJTU-SY 절을 먼저 확인합니다.

실제 LSTM 분석에는 deep-learning 의존성이 필요합니다.

```bash
uv run --locked --group research --extra deep-learning \
  marimo run apps/analysis_explorer.py
```

앱의 **새 분석 실행**에서 준비된 데이터 폴더만 입력하면 됩니다.

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

AI 호출은 **AI 설명 생성** 버튼을 누를 때만 실행됩니다.

## 다른 저장 결과 열기

다른 분석 결과를 기본 화면에 열고 싶다면 환경변수로 artifact 경로를 지정합니다.

```bash
INDUSTRIAL_PHM_ANALYSIS_ARTIFACT=path/to/anomaly-result.json \
INDUSTRIAL_PHM_PROGNOSTICS_ARTIFACT=path/to/prognostics-result.json \
  uv run --locked --group research marimo run apps/analysis_explorer.py
```

서로 다른 분석 결과가 같은 화면에 표시될 수 있는지는 앱이 저장된 dataset/split/population 정보를 이용해 다시 확인합니다.

## 앱을 개발할 때

일반 사용자는 `marimo run`을 사용합니다.
앱 코드를 수정하거나 notebook cell을 편집할 때만 `marimo edit`을 사용합니다.

```bash
uv run --locked --group research marimo edit apps/analysis_explorer.py
```

모델·검증·artifact의 정확한 의미는 [연구 문서](../docs/research/README.md),
앱의 제품 정보 구조는 [제품·UX 기준](../docs/product/overview.md)을 참조합니다.
