# industrial-phm-framework

**산업 설비의 상태와 변화를 지속적으로 파악하고, 분석 근거를 바탕으로 운영자와 정비 담당자가
더 나은 운영·정비 판단을 내릴 수 있도록 지원하는 시스템**입니다.

센서 데이터의 품질과 출처를 확인하고, 이상·열화·RUL 등 PHM 분석 결과와 근거를 만들며,
그 결과를 사람이 검토해 운영·정비 판단으로 이어갈 수 있는 흐름을 다룹니다.

데이터·출처 보존, 분석 재현성과 수집 신뢰성은 이 목적을 뒷받침하는 시스템 요구사항입니다.

공개 데이터셋과 연구 모델은 프레임워크를 개발하고 검증하는 데 사용합니다.

## 전체 구조

![설비 관측에서 사람의 운영·정비 판단까지 이어지는 시스템 아키텍처](assets/system-architecture.png)

설비 데이터는 원본 근거를 보존한 채 설비 이력(Asset History)으로 모이고, 분석은 이력에서 명시적으로
만든 입력으로 실행되어 근거(evidence)를 남깁니다. 사람은 Operations에서 근거를 조사·검토해 운영·정비를
판단합니다. 공개 데이터셋의 label 같은 provider annotation은 연구 평가에만 쓰며 production 분석의 입력이
아닙니다.

구체적인 구현 지원 여부와 명시적 미지원 경계는 [현재 지원 상태](docs/status.md)를 기준으로 확인합니다.
README는 제품 목적과 주요 진입점을 설명하며 capability matrix나 roadmap을 중복 기록하지 않습니다.
수집 runtime, 저장소, 분석 책임의 상세 구조는 [아키텍처 문서](docs/architecture/overview.md)에서 확인할 수 있습니다.

## 애플리케이션

### Operations

설비 관측 데이터와 PHM 근거를 다루는 운영 UI입니다. Canonical application은 wheel에 포함되는
`industrial_phm.apps.operations`이며, UI runtime dependency는 `operations` extra가 소유합니다.

- **Monitor** — 수집·저장·분석·검토 흐름과 지금 확인할 항목
- **Assets** — 설비별 현재 데이터, Signals, Analysis, Events, Maintenance
- **Investigations** — 저장된 분석 evidence와 사람의 review 요청
- **Maintenance** — Open / Acknowledged / Closed review 업무
- **System** — 수집·저장·분석 runtime과 state-read 상태
- **Setup** — FILE/OPC UA 연결, signal mapping, measurement meaning과 collection intent

설정과 진단 정보는 primary 운영 흐름에서 분리하고, NodeId·state path 같은 세부 정보는 필요한
경우에만 Setup/System의 advanced 영역에서 확인합니다.

외부 데이터 없이 전체 local node를 먼저 확인하려면 `operations` extra 설치 후 synthetic demo 하나로
OPC UA simulator, collection, analysis, Operations UI를 함께 실행할 수 있습니다.

```bash
industrial-phm demo synthetic
```

기본 workspace는 `artifacts/demo-synthetic`이며 synthetic 3상 값은 물리 설비에서 측정된 값이나 고장 진단이 아닙니다.
명령은 loopback OPC UA source를 자동 등록·활성화하고 collection을 시작합니다. 종료는 Ctrl-C를 사용합니다.

이미 로컬에 AI-Hub 239 보일러 raw archive가 있으면, 검증에 사용한 device 2297의 기록 구간을 같은
Operations runtime 위에서 replay할 수 있습니다. AI-Hub parser는 normal Operations dependency가 아니므로
`operations`와 `aihub` extras를 함께 설치합니다.

```bash
uv sync --locked --extra operations --extra aihub
uv run --no-sync industrial-phm demo aihub-boiler
```

기본 preset은 `5.보일러.zip`의 `5.보일러/SourceData_211.json`, 2020-11-14 06:00–12:30 local,
60× replay를 사용합니다. 기본 archive 경로가 다르면 `--archive`만 지정하면 됩니다. recorded provider
data를 replay하는 개발·검증 경로이며 대상 운영 OPC UA source validation이나 fault diagnosis를 주장하지 않습니다.

대상 운영 source를 연결할 새 local Operations workspace는 다음처럼 초기화합니다.

```bash
industrial-phm operations init ./plant-a
```

초기화한 workspace의 collection + analysis + Operations UI는 한 foreground supervisor로 실행합니다.

```bash
industrial-phm operations start ./plant-a
```

`start`는 workspace `config.toml`의 runtime policy를 사용하고, Ctrl-C 시 child process를 함께
graceful shutdown합니다. 다른 shell이나 service manager에서 명시적으로 종료하려면:

```bash
industrial-phm operations stop ./plant-a
```

`stop`은 이전에 기록된 PID만 보고 signal을 보내지 않고, 해당 workspace의 supervisor lock이 실제로
점유 중인 경우에만 live supervisor에 종료를 요청합니다. Local runtime의 process identity와
collection/analysis heartbeat 상태는 다음처럼 확인합니다.

```bash
industrial-phm operations status ./plant-a
```

`status`는 supervisor PID, collection/analysis heartbeat와 UI loopback listener readiness를 서로 다른 evidence로 표시합니다. 조회 성공 + 전체 runtime
ready는 exit 0, 조회는 성공했지만 아직 ready하지 않으면 exit 2, workspace/state read 오류는 exit 1입니다.
component 로그는 내부 파일 경로를 직접 찾지 않고 `industrial-phm operations logs ./plant-a`로 확인합니다.

중요한 local workspace는 runtime을 중지한 뒤 하나의 recovery unit으로 backup할 수 있습니다.

```bash
industrial-phm operations stop ./plant-a
industrial-phm maintenance backup ./plant-a ./backups/plant-a-2026-10-02
industrial-phm maintenance restore ./backups/plant-a-2026-10-02 ./plant-a-restored
```

backup은 config와 durable source/control/spool/window/analysis/history evidence를 포함하고 로그, supervisor
PID/lock, rebuildable history accelerator는 제외합니다. restore는 checksum을 검증한 뒤 **새 workspace root**에만
복원하며 기존 root를 덮어쓰지 않습니다.

이 local UI는 `127.0.0.1` 전용이며 marimo token auth를 사용하지 않습니다. shared/public host 노출은 이
명령의 지원 범위가 아니며 별도 deployment/auth 경계가 필요합니다.

장시간 host 운영 전에는 실제 service account로 deployment preflight를 실행합니다.

```bash
industrial-phm validate deployment /var/lib/industrial-phm/plant-a
```

reference systemd unit과 restart/permission 경계는
[Local Operations deployment](docs/architecture/operations-deployment.md)에 정리되어 있습니다. node-level
restart는 application 내부 무한 loop가 아니라 외부 service manager가 소유합니다.

정상 node lifecycle은 `operations`, 복구·history 작업은 `maintenance`, 배포 사전검증은
`validate`, supervisor가 호출하는 service/source plumbing은 `internal` namespace가 소유합니다. 이동 전
`operations backup/preflight/run-*` spelling은 더 이상 rewrite하지 않으며 canonical namespace만 지원합니다.

현재 지원되는 실행 경계는 [지원 상태](docs/status.md)를 기준으로 확인합니다.

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
