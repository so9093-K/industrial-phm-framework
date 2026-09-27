# industrial-phm-framework

산업 설비 데이터를 **PHM 분석 결과와 유지보수 판단으로 연결하는 Python 기반 PHM 프레임워크**입니다.

센서 데이터를 받아 품질과 출처를 확인하고, 이상·열화·RUL 등 PHM 분석 결과와 근거를 만들며,
사용자가 그 결과를 검토해 운영·정비 판단으로 이어갈 수 있는 흐름을 만드는 것이 목표입니다.

공개 데이터셋과 연구 모델은 이 흐름을 개발하고 검증하기 위한 수단으로 사용합니다.

> 현재 버전: pre-alpha `0.0.1`

## 전체 구조

![산업 설비 데이터부터 분석 결과까지 이어지는 시스템 구조](assets/system-architecture.png)

센서 데이터는 데이터셋별 변환 단계를 거쳐 공통 분석 흐름으로 들어갑니다.
분석 결과는 파일로 기록되고, 같은 결과를 Analysis Explorer·보고서·생성형 AI 설명에서 함께 사용합니다.

자세한 설계는 [아키텍처 문서](docs/architecture/overview.md)에서 확인할 수 있습니다.

## 현재 할 수 있는 것

- **Analysis Explorer** — anomaly/RUL 연구 결과, 주요 관측값, feature/model evidence와 실행 정보를 검토합니다.
- **Operations** — FILE/OPC UA source를 등록하고 관측·데이터 품질을 확인합니다. 등록된 FILE snapshot은 on-demand 분석을 실행해 결과 evidence를 만들고, review finding과 Maintenance Review로 이어갈 수 있습니다.
- **OPC UA** — source 등록, bounded browse, one-shot read와 bounded subscription collection을 지원합니다.
- **보고서와 설명** — 저장된 분석 결과를 Markdown 보고서와 생성형 AI 설명에 재사용할 수 있습니다.

연구 결과와 운영 결과는 구분합니다. Research anomaly/RUL evidence를 Operations의 operational 상태나 RUL로 자동 승격하지 않습니다.

## 실행

Git, [uv](https://docs.astral.sh/uv/), 저장소 접근 권한이 필요합니다.

```bash
git clone https://github.com/so9093-K/industrial-phm-framework.git
cd industrial-phm-framework
uv python install 3.14
```

### Analysis Explorer

```bash
uv run --locked --group research marimo run apps/analysis_explorer.py
```

저장소에 포함된 분석 결과를 바로 열어 anomaly/RUL evidence와 분석 과정을 확인할 수 있습니다.

### Operations

```bash
uv run --locked --group research marimo run apps/operations.py
```

외부 데이터가 없어도 Overview에서 **Prepare bundled demo source**를 실행한 뒤 다음 흐름을 확인할 수 있습니다.

```text
Sources
  → Analyze FILE snapshot
  → Investigation
  → Create review finding
  → Maintenance Review
```

실제 source를 사용할 때는 **Sources**에서 FILE snapshot/history-directory 또는 OPC UA source를 등록합니다.

자세한 source 등록, OPC UA, polling, data-quality 의미론과 환경변수는
[Applications 문서](apps/README.md)에 정리되어 있습니다.

## 현재 범위

현재 Operations에서 연결된 흐름:

```text
Source
  → Observation / Data Quality
  → Analysis
  → Result Evidence
  → Review Finding
  → Maintenance Review
```

현재 지원하지 않는 범위:

- automatic condition/fault/alert 판정
- operational RUL
- inspection/work-order/CMMS 실행
- persistent OPC UA session과 continuous ingestion
- reconnect/backoff/buffering 기반의 장기 실행 runtime

지원하지 않는 기능을 추정하거나 빈 상태로 꾸며서 표시하지 않는 것을 원칙으로 합니다.

## 연구·검증 데이터

XJTU-SY, IMS Bearings, MIMII DUE 등의 공개 데이터는 분석 방법과 evidence를 개발·검증하는 데 사용합니다.
데이터 준비 방법과 출처는 [데이터 안내](data/README.md),
선정 배경과 연구 프로토콜은 [연구 문서](docs/research/README.md)를 참조합니다.

## 문서

- [Applications](apps/README.md) — Analysis Explorer와 Operations 사용 방법
- [아키텍처](docs/architecture/overview.md) — 구성 요소와 책임 경계
- [제품·UX 기준](docs/product/overview.md) — 사용자 흐름과 제품 의미
- [데이터 준비](data/README.md) — 데이터셋과 입력 검증
- [연구 문서](docs/research/README.md) — 실험 프로토콜과 연구 evidence
- [테스트 정책](docs/testing-policy.md) — 검증 기준
- [기여 방법](CONTRIBUTING.md) — 개발 환경과 변경 절차
- [변경 이력](CHANGELOG.md) — 변경 내용

## 라이선스

[Apache License 2.0](LICENSE)을 사용합니다.
데이터셋의 원본 라이선스와 출처는 각 데이터 문서를 따릅니다.
