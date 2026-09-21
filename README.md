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

- **센서 데이터 준비** — XJTU-SY, IMS Bearings, MIMII DUE 등의 데이터 구조와 기본 품질을 확인하고 분석 가능한 형태로 변환합니다.
- **이상 변화 분석** — 진동·음향 센서 데이터에서 시간에 따른 이상 점수와 특징 변화를 분석합니다.
- **RUL 분석** — 베어링 수명 데이터를 이용해 잔여수명 모델을 비교하고 평가 결과를 기록합니다.
- **분석 결과 탐색** — Analysis Explorer에서 요약, 주요 관측값, 모델 결과, 실행 정보를 단계별로 확인합니다.
- **보고서 생성** — 분석 결과를 같은 수치와 내용으로 재현 가능한 Markdown 보고서로 저장합니다.
- **생성형 AI 설명** — 계산이 끝난 분석 결과를 바탕으로 요약과 질의응답을 제공합니다.

현재 구현된 분석 화면과 실행 방법은 [Analysis Explorer 안내](apps/README.md)에 정리되어 있습니다.

## 빠르게 시작하기

검증된 개발 환경은 CPython `3.14.x`와 저장소의 `uv.lock`입니다.

### 1. 환경 준비

```bash
uv python install 3.14
uv sync --locked
uv run --locked industrial-phm doctor
```

### 2. 기존 분석 결과 확인

원본 데이터셋을 내려받지 않아도 저장소에 기록된 분석 결과를 확인할 수 있습니다.

```bash
uv run --locked industrial-phm experiment inspect \
  docs/research/results/xjtu-sy-iforest-fold-1-holdout-v1.json

uv run --locked industrial-phm experiment inspect \
  docs/research/results/xjtu-sy-rul-lstm-fold-1-benchmark-v1.json
```

### 3. 분석 화면 열기

```bash
uv sync --locked --group research
uv run --locked --group research marimo edit apps/analysis_explorer.py
```

생성형 AI 설명 기능을 사용할 때는 `OPENAI_API_KEY`와 `INDUSTRIAL_PHM_GENAI_MODEL`을 실행 환경에 설정합니다.

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
일반 CSV/WAV 센서 입력
  -> 현장·비공개 데이터 연결
  -> 고장 진단과 RUL 불확실성 검증
  -> 실시간 분석과 유지보수 시스템 연계
```

현재 우선순위는 다양한 모델을 추가하는 것보다 실제 센서 데이터를 더 쉽게 연결하고,
현장 데이터에서 분석 결과가 어떻게 달라지는지 확인하는 것입니다.

최근 PHM 연구와 산업 적용 방향은
[PHM 연구·산업 동향](docs/research/phm-industry-direction.md)에 별도로 정리합니다.

## 더 자세히 보기

- [Analysis Explorer](apps/README.md) — 분석 화면과 실행 방법
- [아키텍처](docs/architecture/overview.md) — 전체 구성과 책임 분리
- [제품·UX 기준](docs/product/overview.md) — 분석 결과를 사용자에게 보여주는 방식
- [데이터 준비](data/README.md) — 데이터셋 준비와 검증
- [연구 문서](docs/research/README.md) — 실험 프로토콜, RUL 연구, 실행 기록
- [기여 방법](CONTRIBUTING.md) — 개발 환경, 코드 변경, 테스트 방법

변경 이력은 [CHANGELOG](CHANGELOG.md), 테스트 기준은 [Testing Policy](docs/testing-policy.md)를 참조합니다.

## 라이선스

[Apache License 2.0](LICENSE)을 사용합니다.
데이터셋의 원본 라이선스와 출처는 각 데이터 문서를 따릅니다.
