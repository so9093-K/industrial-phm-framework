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
- **이상 변화 분석** — 진동·음향 센서 데이터에서 시간에 따른 이상 점수와 특징 변화를 분석합니다.
- **RUL 분석** — 베어링 수명 데이터를 이용해 잔여수명 모델을 비교하고 평가 결과를 기록합니다.
- **분석 결과 탐색** — Analysis Explorer에서 요약, 주요 관측값, 모델 결과, 실행 정보를 단계별로 확인합니다.
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
  -> operational observation read model + 첫 private/field source conformance
  -> Operations UI에서 관측 / data quality / PHM evidence 연결
  -> source에 맞는 diagnostics / prognostics 검증
  -> 실시간 분석과 유지보수 시스템 연계
```

현재 우선순위는 다양한 모델을 추가하는 것보다 실제 센서 데이터를 더 쉽게 연결하고,
현장 데이터에서 분석 결과가 어떻게 달라지는지 확인하는 것입니다.

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
