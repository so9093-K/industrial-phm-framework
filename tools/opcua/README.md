# OPC UA 실제 계측 기록 재생

이 도구는 로컬에 준비한 AI-Hub 239 **실측 기록**을 OPC UA DataChange로 재생하고, 수신·원본 근거를 확인합니다. 합성 제품 시연 서버와 대형 자동 장애 수용 harness는 배포하지 않습니다.

## 보일러 실측 기록으로 시작

[AI-Hub 데이터 준비](../../data/README.md)에 따라 원본 아카이브를 로컬에 내려받습니다. 원본 위치가 기본값이라면 다음과 같이 시작합니다.

```bash
uv sync --locked --extra operations --extra aihub
uv run --no-sync industrial-phm demo aihub-boiler
```

원본 위치나 실행 옵션은 `industrial-phm demo aihub-boiler --help`를 확인합니다. 이 명령은 실제 기록을 재생하는 진입점입니다. **현장 수집·현장 고장 판정이 검증됐다는 뜻은 아닙니다.**

## 기존 작업공간에서 별도 OPC UA 서버 실행

기록의 원본 시각·품질·채널을 확인해야 하거나 replay 서버와 수집기를 독립적으로 실행할 때는 아래 개발용 명령을 사용합니다.

```bash
uv sync --locked --extra history --extra opcua --extra aihub --group research
uv run --no-sync python -m tools.opcua.aihub_replay prepare \
  --root artifacts/aihub-replay \
  --endpoint opc.tcp://127.0.0.1:4850/aihub-replay/ \
  --archive data/raw/aihub/239/archives/training/raw/5.보일러.zip \
  --member "5.보일러/SourceData_211.json" \
  --binding tools/opcua/presets/aihub-boiler-2297-replay.json \
  --start 2020-11-14T06:00:00 --end 2020-11-14T12:30:00
uv run --no-sync python -m tools.opcua.aihub_replay server \
  --root artifacts/aihub-replay --speed 60 --loop
```

`prepare`와 `server`는 같은 작업공간을 사용합니다. 수집기 또는 Operations를 연결할 때도 **동일한 workspace 경로**를 지정하세요. 압축기 실측 기록은 `tools/opcua/presets/aihub-air-compressor-1338-replay.json`과 [참조 프로필](../../docs/research/aihub-239-air-compressor-reference-profile.md)을 참고합니다.

- `tools/opcua/aihub_replay.py`: 실제 기록 기반 OPC UA 재생, 재생 시각·원본 digest 보존
- `tools/opcua/replay_audit.py`: replay ledger와 저장된 수신 이벤트의 누락·중복·품질 대조
- `tools/opcua/presets/`: 실제 보일러·공기압축기 선택 정보

OPC UA DataChange는 값 또는 품질이 달라질 때만 관측됩니다. 재생 시각과 원본 측정 시각을 구별하고, 측정량 의미가 확인되지 않은 채널에 단위·물리 의미를 임의 부여하지 마세요.

정상 사용자 CSV·OPC UA 연결은 [Operations 사용법](../../apps/README.md), 장비·수집 경계는 [아키텍처](../../docs/architecture/overview.md), 실제 지원 범위는 [현재 상태](../../docs/status.md)를 참고하세요.
