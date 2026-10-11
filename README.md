# industrial-phm-framework

**산업 설비의 상태와 변화를 지속적으로 파악하고, 분석 근거를 바탕으로 운영자와 정비 담당자가
더 나은 운영·정비 판단을 내릴 수 있도록 지원하는 시스템**입니다.

센서 데이터의 품질과 출처를 확인하고, 이상·열화·RUL 등 PHM 분석 결과와 근거를 만들며,
그 결과를 사람이 검토해 운영·정비 판단으로 이어갈 수 있는 흐름을 다룹니다.

데이터·출처 보존, 분석 재현성과 수집 신뢰성은 이 목적을 뒷받침하는 시스템 요구사항입니다.

공개 데이터셋과 연구 모델은 프레임워크를 개발하고 검증하는 데 사용합니다.

## 빠른 시작

정상적인 repository-local 진입점은 root `Makefile`입니다. 사용자는 내부 process나
`marimo` 실행 경로를 조합하지 않고 같은 front door에서 local Operations lifecycle을 다룹니다.

필요한 외부 도구는 `make`와 `uv`입니다.

```bash
make up
```

`make up`은 Python 3.14와 locked Operations 환경을 준비한 뒤 기본 workspace
`artifacts/operations`를 열고 collection + analysis + Operations UI를 하나의 foreground
supervisor로 실행합니다. 새 workspace는 자동으로 준비하고, 유효한 기존 workspace는 그대로 다시 엽니다.
현재 config가 생기기 전 Operations가 만든 것으로 식별 가능한 workspace는 기존 state를 보존한 채
현재 기본 runtime policy를 기록한 config를 추가해 재개합니다. Operations와 관계없는 파일이 섞인 directory는 자동으로
채택하지 않고 아무것도 변경하지 않은 채 다른 workspace를 선택하도록 안내합니다.

터미널에 출력되는 `operations_url`(`http://127.0.0.1:<port>/web/`)을 브라우저에서 엽니다.
현재 UI는 **로컬 단일 사용자 supervised Web 파일럿**입니다. 데이터 수신·저장 이력·분석 근거·사람 검토·일부 System 조회를 지원하지만 Investigation·Maintenance·System 전체 업무, 영어 조작 UI·스크린리더의 완전한 수용은 아직 진행 중입니다(#488, #489). 설비 고장·안전·물리적 정비 완료를 판정하지 않습니다.
빈 작업공간의 Web 파일럿은 FILE CSV 또는 로컬 OPC UA 소스 등록을 안내합니다. 소스 등록·ACTIVE·검증 수신·DuckLake 이력 저장·분석 근거는 별개의 사실이므로 각 단계의 근거를 확인해야 합니다.
기본 Web 첫 실행의 **격리 synthetic 샘플 시작·종료** 버튼으로 기존 synthetic OPC UA 데모를 실제 workspace와 분리된 로컬 작업공간·포트에서 실행할 수 있습니다. 샘플은 **별도의 기존 데모 앱 창**에서 열리며, 종료해도 전용 샘플 폴더를 자동 삭제하지 않습니다. 신규 Web에서 미지원인 업무는 구현된 것처럼 안내하지 않습니다. 지원 범위를 [현재 상태](docs/status.md)에서 확인하세요. 기존 소스가 있는 workspace는 Web에서 저장된 관측/검토 근거를 조회할 수 있습니다.

```bash
make status
make logs
make down
```

다른 workspace를 사용하려면 모든 lifecycle target에 같은 값을 전달합니다.

```bash
make up WORKSPACE=/var/lib/industrial-phm/plant-a
make status WORKSPACE=/var/lib/industrial-phm/plant-a
make down WORKSPACE=/var/lib/industrial-phm/plant-a
```

외부 데이터가 없어 실행 흐름을 확인할 때는 별도 synthetic workspace를 쓰는 `make demo`를 활용할 수 있습니다.
기본 Web은 사용자가 **격리 샘플 시작**을 명시적으로 누를 때만 데모 프로세스를 생성하며, 자동으로 시작하지 않습니다.

직접 CLI, UI-only 실행, replay, backup/restore, deployment, 연구 앱 실행은
[Applications 문서](apps/README.md)와 각 개발·운영 문서에서 다룹니다.

## 전체 구조

![설비 관측에서 사람의 운영·정비 판단까지 이어지는 시스템 아키텍처](assets/system-architecture.svg)

설비 데이터는 원본 근거를 보존한 채 설비 이력(Asset History)으로 모이고, 분석은 이력에서 명시적으로
만든 입력으로 실행되어 근거(evidence)를 남깁니다. 사람은 Operations에서 근거를 조사·검토해 운영·정비를
판단합니다. 공개 데이터셋의 label 같은 provider annotation은 연구 평가에만 쓰며 production 분석의 입력이
아닙니다.

구체적인 구현 지원 여부와 명시적 미지원 경계는 [현재 지원 상태](docs/status.md)를 기준으로 확인합니다.
README는 제품 목적과 주요 진입점을 설명하며 capability matrix나 roadmap을 중복 기록하지 않습니다.
수집 runtime, 저장소, 분석 책임의 상세 구조는 [아키텍처 문서](docs/architecture/overview.md)에서 확인할 수 있습니다.

## 애플리케이션

### Operations (supervised Web)

운영자 화면은 wheel에 포함된 `industrial_phm/apps/web/`의 HTML·JavaScript·CSS와
로컬 Python API로 구성됩니다. `make up` 및 `operations up/start`가 기본적으로
수집·분석·Web를 하나의 Supervisor로 실행합니다. 연구용 marimo는 운영 제품에 필요하지 않습니다.

- **Monitor / Assets / Signals**: 설비별 관측·저장 이력과 출처·품질·시각, 확인이 필요한 운영 상태
- **Connect**: FILE CSV와 제한된 로컬 익명 OPC UA 소스 등록·수신/제어 증거
- **Evidence / Review**: 저장된 AnalysisRun·Evidence 및 사람이 기록한 요청·확인·종료
- **System**: 로컬 프로세스 상태와 저장소 조회 오류의 제한된 진단

소스 등록, 수신, DuckLake 적재, 분석과 사람 검토는 서로 다른 증거입니다. 현재 Web은
한국어 중심 파일럿이며 전체 영어/접근성 및 일부 복구·업무 경로는 별도 개선 중입니다.
실제 API·업무 지원 범위는 [지원 상태](docs/status.md)를 따릅니다.

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

AI-Hub 보일러·압출기의 historical data 실행 예시는
[실행 안내](tools/aihub/README.md#local-power-data-profiling-and-history)와
[검증된 데이터 범위](docs/research/aihub-239-source-profile.md)를 참고하세요.

- [현재 지원 상태](docs/status.md) — 구현된 operational/research 지원 범위와 명시적 미지원 경계
- [Applications](apps/README.md) — Analysis Explorer와 Operations 사용 방법
- [측정 이력 의미·집계·scale 경계](docs/architecture/measurement-history-evolution.md) — semantic/display/storage 계약과 측정 근거
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
