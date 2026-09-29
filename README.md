# industrial-phm-framework

**산업 설비의 상태와 변화를 지속적으로 파악하고, 분석 근거를 바탕으로 운영자와 정비 담당자가
더 나은 운영·정비 판단을 내릴 수 있도록 지원하는 시스템**입니다.

센서 데이터의 품질과 출처를 확인하고, 이상·열화·RUL 등 PHM 분석 결과와 근거를 만들며,
그 결과를 사람이 검토해 운영·정비 판단으로 이어갈 수 있는 흐름을 다룹니다.

데이터·출처 보존, 분석 재현성과 수집 신뢰성은 이 목적을 뒷받침하는 시스템 요구사항입니다.

공개 데이터셋과 연구 모델은 프레임워크를 개발하고 검증하는 데 사용합니다.

> 버전: pre-alpha `0.0.1`

## 전체 구조

![설비 관측에서 사람의 운영·정비 판단까지 이어지는 시스템 아키텍처](assets/system-architecture.png)

설비 데이터는 원본 근거를 보존한 채 설비 이력(Asset History)으로 모이고, 분석은 이력에서 명시적으로
만든 입력으로 실행되어 근거(evidence)를 남깁니다. 사람은 Operations에서 근거를 조사·검토해 운영·정비를
판단합니다. 공개 데이터셋의 label 같은 provider annotation은 연구 평가에만 쓰며 production 분석의 입력이
아닙니다.

현재 구현 범위: FILE·OPC UA 수집과 Asset History, 설비별 이력·품질·출처 조회, 근거가 확인된 측정 의미
(semantic binding), FILE snapshot 특징 분석과 과거 Asset History 기반
[3상 불평형 분석](docs/architecture/phase-unbalance-capability.md), finalized live window의 accept event로
같은 분석을 실행하는 별도 runner([ADR-0008](docs/adr/0008-analyze-finalized-window-accepted-events.md))와
명시적 시간 정렬 정책([ADR-0009](docs/adr/0009-temporal-alignment-policy.md)), 분석 결과에 대한
Investigation·사람의 review finding·maintenance review입니다. Live 분석 결과의 Operations 화면, validated
진단·alarm·operational RUL·자동 정비 권고는 아직 제공하지 않습니다.

수집 runtime, 저장소, 분석 경계의 상세 구조는 [아키텍처 문서](docs/architecture/overview.md)에서 확인할 수 있습니다.

## 애플리케이션

### Operations

현장 데이터와 PHM 결과를 다루는 운영 UI입니다.

- **Sources** — FILE/OPC UA 데이터 연결과 관측
- **Assets** — 설비별 측정 이력·관측점 추세·품질과 출처 확인
- **Investigation** — 분석 결과와 evidence 검토
- **Maintenance Review** — review finding의 확인·메모·acknowledge·close
- **Operational State** — 기록된 운영 상태와 evidence 확인

외부 데이터가 없어도 bundled demo source로 같은 흐름을 확인할 수 있습니다.

### Analysis Explorer

PHM 분석 결과를 상세하게 검토하는 UI입니다.

- anomaly/RUL evidence
- feature/model 결과
- 주요 관측 구간
- 분석 provenance와 review

애플리케이션의 로컬 개발·실행 방법은 [Applications 문서](apps/README.md),
개발 환경 구성은 [기여 방법](CONTRIBUTING.md)에 정리되어 있습니다.

## 데이터

XJTU-SY, IMS Bearings, MIMII DUE 등의 공개 데이터는 분석 방법과 evidence를 개발·검증하는 데 사용합니다.
데이터 준비와 출처는 [데이터 안내](data/README.md), 연구 프로토콜은 [연구 문서](docs/research/README.md)에 정리되어 있습니다.

## 문서

다음 개발은 실제 설비 이력 확인 → 지속적인 상태·변화 관찰 → 분석 근거와 운영·정비 검토 연결 순으로
진행합니다. AI-Hub 보일러·압출기의 첫 historical slice는
[실행 안내](tools/aihub/README.md#local-power-data-profiling-and-history)와
[검증된 데이터 범위](docs/research/aihub-239-source-profile.md)를 참고하세요.

- [Applications](apps/README.md) — Analysis Explorer와 Operations 사용 방법
- [측정 의미·집계·확장 계획](docs/architecture/measurement-history-evolution.md) — 현재 계약과 후속 단계
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
