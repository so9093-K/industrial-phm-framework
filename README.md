# industrial-phm-framework

**산업 설비의 상태와 변화를 지속적으로 파악하고, 분석 근거를 바탕으로 운영자와 정비 담당자가
더 나은 운영·정비 판단을 내릴 수 있도록 지원하는 시스템**입니다.

센서 데이터의 품질과 출처를 확인하고, 이상·열화·RUL 등 PHM 분석 결과와 근거를 만들며,
그 결과를 사람이 검토해 운영·정비 판단으로 이어갈 수 있는 흐름을 다룹니다.

데이터·출처 보존, 분석 재현성과 수집 신뢰성은 이 목적을 뒷받침하는 시스템 요구사항입니다.

공개 데이터셋과 연구 모델은 프레임워크를 개발하고 검증하는 데 사용합니다.

> 버전: pre-alpha `0.0.1`

## 전체 구조

```mermaid
flowchart LR
    FILE[FILE 원본·명시적 매핑] --> HISTORY[DuckLake Asset History]
    OPC[OPC UA] --> COLLECTOR[독립 수집 서비스]
    COLLECTOR --> SPOOL[Durable spool]
    SPOOL --> HISTORY
    SPOOL --> WINDOW[관측 Window]
    HISTORY --> ASSET[Operations Asset Detail<br/>최신 관측·이력·품질·출처]
    FILE --> ANALYSIS[FILE snapshot 특징 분석]
    ANALYSIS --> EVIDENCE[Analysis Evidence]
    EVIDENCE --> INVESTIGATION[Investigation]
    INVESTIGATION --> FINDING[사람의 Review Finding]
    FINDING --> REVIEW[Maintenance Review<br/>확인·메모·종료 기록]
    DATA[공개 데이터·연구 프로토콜] --> RESEARCH[모델 학습·평가]
    RESEARCH --> ARTIFACT[연구 Artifact]
    ARTIFACT --> EXPLORER[Analysis Explorer]
    WINDOW -. 후속 연결 .-> EVIDENCE
```

FILE과 OPC UA 관측은 원본 근거를 보존하며 설비 이력으로 모입니다. 독립 수집 서비스가 spool과
history 기록을 담당하고, Operations는 설비별 최신 관측·추세·품질·출처 및 사람의 검토 이력을 보여줍니다.
로컬 SQLite DuckLake 접근은 협조하는 프로세스끼리 직렬화합니다.

현재 운영 분석은 명시적인 timestamp를 가진 FILE snapshot 특징 추출입니다. Live Window에서
Analysis Evidence까지의 점선은 후속 연결이며, validated 진단·alarm·operational RUL·자동 정비 권고는
현재 capability가 아닙니다. 연구 모델 결과는 별도의 artifact와 Analysis Explorer에서 검토합니다.

자세한 설계는 [아키텍처 문서](docs/architecture/overview.md)에서 확인할 수 있습니다.

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
