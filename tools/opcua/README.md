# OPC UA 실제 기록 재생 및 수집 점검

이 경로는 **로컬에 준비한 산업 계측 기록**을 OPC UA로 재생·수집하고 이력·복구를 확인하기 위한 도구입니다. 합성 제품 시연 서버 `tools.opcua.demo`와 `make demo`는 제거했습니다.

## 실제 AI-Hub 239 기록

[데이터 준비](../../data/README.md)에 따라 보일러·압출기·공기압축기 아카이브를 내려받아 로컬에 준비합니다. 제공 데이터의 시각·장비 ID·채널·단위 근거를 해석한 뒤 다음 도구로 기록을 재생할 수 있습니다.

- `tools/opcua/aihub_replay.py`: 기록 기반 OPC UA 이벤트 재생
- `tools/opcua/presets/`: AI-Hub 보일러·공기압축기 설정
- `tools/opcua/fault_harness.py`: 재연결·중지·backlog 등 장애 시나리오의 선택적 진단
- `tools/opcua/replay_audit.py`: 기록 재생 근거 확인

빠르게 보일러 실측 기록과 Operations를 함께 실행하려면 프로젝트 루트에서 `uv sync --locked --extra operations --extra aihub` 후 `uv run industrial-phm demo aihub-boiler`를 사용합니다. 로컬 원본 경로와 옵션은 `industrial-phm demo aihub-boiler --help` 및 [Operations 사용법](../../apps/README.md)을 참고하세요.

## 실행 및 해석 주의

재생 데이터는 실제로 측정된 **과거 기록**입니다. OPC UA 엔드포인트로 다시 전송했다고 현재 현장 수집이나 실제 고장 진단이 검증된 것은 아닙니다. 측정 시각과 재생·수신 시각, 측정점 의미, 결측 및 품질을 구분해야 합니다.

실제 데이터가 없는 환경에서 실행을 성공시켜 보이기 위해 합성 관측값으로 대체하지 않습니다. 장애 테스트용 최소 인공 입력과 실제 제품 분석 근거를 혼동하지 않습니다.

운영 Web과 기록 저장의 책임 경계는 [아키텍처](../../docs/architecture/overview.md), 실제 지원 범위는 [상태 문서](../../docs/status.md)를 참고하세요.
