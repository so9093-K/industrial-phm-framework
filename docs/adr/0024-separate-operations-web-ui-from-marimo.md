# 0024. Separate the Operations web product from marimo

Status: Accepted

Supersedes: ADR-0014의 **UI 구현 프레임워크 및 `marimo run` launch 결정만** 대체.
ADR-0014의 local supervisor ownership, loopback-only reference boundary, 단일 workspace,
readiness 및 failure semantics는 계속 유효하다.

## Context

Operations의 정상 사용자 화면은 설비 담당자가 관측값과 변화, 데이터 품질, 분석 근거 및
사람의 검토 기록을 읽고 필요한 작업을 실행하는 제품이다. 연구 notebook을 편집하거나
분석 알고리즘을 UI 프로세스에서 다시 실행하는 환경이 아니다.

현재 packaged Operations UI는 `src/industrial_phm/apps/operations.py`의 marimo
reactive-cell 애플리케이션이다. Monitor는 다시 anywidget JavaScript/CSS를 사용하며
공통 shell은 marimo theme/layout을 별도로 보정한다. 기존 Chromium acceptance는
`ko-KR`/`en-US` × 1024/1440px의 여정과 접근성 이름 fallback을 보호하지만,
marimo 0.24.2의 표시 label과 native input 간 `for`/`id` 연결은 지원하지 않는다.
브라우저 acceptance 통과가 사용자 중심 정보 구조·한국어 문장 품질·접근성 전체
수용을 뜻하지는 않는다.

ADR-0018/0019/0020은 이미 read-side snapshot, write-side actions, workspace-first
composition을 marimo 셀 밖으로 옮겼다. 따라서 사용자 화면을 교체하기 위해
collection/analysis process와 SQLite/DuckLake history, source/review repositories를
재구현할 필요는 없다. ADR-0013/0014의 process lifecycle과 local deployment
계약은 보존한다.

## Decision

### 1. Operations와 Research를 다른 UI 책임으로 둔다

- Operations의 목표 인터페이스는 독립된 **일반 웹 클라이언트 + Python Operations
  HTTP API**이다. 화면 구성·interaction state·locale·접근성·차트를 marimo
  reactive-cell graph에 종속시키지 않는다.
- 연구 notebook과 `apps/analysis_explorer.py`의 marimo는 research dependency로
  남긴다. 연구용 결과 평가 및 재현성 흐름을 Operations 웹 UI에 이식하지 않는다.
- 새 클라이언트는 기존 화면을 픽셀 단위로 복제하지 않는다. 제품의
  [Operations observation loop](../product/overview.md#1-사용자-역할)와
  [PHM Operations workflow contract](../product/overview.md#8-phm-operations-workflow-contract)를
  우선한다. 화면 명칭과 한국어 copy는 product/terminology owner에서 검토하고
  기술 식별자를 표시 문자열로 재사용하지 않는다.
- 프런트엔드 프레임워크·차트 라이브러리의 정확한 선택은 접근성, 대량 시계열 성능,
  local static packaging을 확인하는 첫 구현 PR에서 결정한다. 본 ADR은
  React 등의 구체적인 라이브러리 버전을 고정하지 않는다.

### 2. API는 기존 runtime facade를 소비하며 데이터 소유자가 아니다

- API의 read boundary는 `load_operations_app_context()` /
  `OperationsAppSnapshot` 및 기존 bounded history read model을 활용한다.
  브라우저에서 DuckLake/SQLite/JSON 파일 또는 collector의 내부 프로토콜에 직접
  접근하지 않는다. 서버에서 쓰기 가능한 영속적 UI cache를 새로운
  source of truth로 만들지 않는다.
- API response는 versioned, browser-safe DTO로 노출한다. explicit asset/source/
  measurement-point/channel identity, event/source/receive timestamp, timezone/UTC
  semantics, unit, original quality, provenance, snapshot assessment time,
  missing/unavailable/failed-to-load를 손실 없이 구분한다. Python 객체의
  임의 자동 직렬화나 내부 filesystem path 노출을 public contract로 만들지 않는다.
- History/Signal API는 bounded range, limit 및 cursor/page 경계를 가진다.
  server-side downsampling은 기존 bucket/evidence 의미를 보존하고, 브라우저가
  누락 구간을 연속 관측처럼 그리거나 측정 의미가 다른 신호를 임의 합산하지 않는다.
  별도 계약 없이 자동 polling을 추가하거나 마지막 관측 시각을 현재 시각으로
  승격하지 않는다.
- Write/API command는 `OperationsAppActions`에서 제공하는 등록·diagnostic·
  수집 요청·freshness policy·FILE 분석·finding/review action을 기존 application
  validation을 통해 실행한다. 검증되지 않은 직접 repository mutation 경로를
  추가하지 않는다. 입력 오류, 이미 존재하는 resource, conflict, 일시적 failure의
  계약을 정하고, 요청 수락과 실제 receipt/history evidence를 분리한다.
- Live-analysis runner 및 collection service는 기존 독립 child process에 남는다.
  UI나 HTTP request handler가 분석 실행 루프·OPC UA subscription·history writer
  lifecycle을 소유하지 않는다.

### 3. 단일 사용자 로컬 제품의 보안 경계를 유지한다

- 기준 설치 모델은 `127.0.0.1`의 한 origin에서 packaged static UI와 API를
  제공하는 local node이다. `0.0.0.0`/public host·공유 workstation·원격
  운영자 접근은 이 결정으로 지원하지 않는다.
- 새 JSON API가 생기므로 marimo `--no-token`을 보안 모델로 재사용하지 않는다.
  변경 요청에는 명시적 same-origin/Host/Origin 검증 및 CSRF·세션 정책을 수립하고,
  다른 사이트의 local API 사용, 임의 CORS 허용, 민감한 파일 경로 접근을 차단한다.
  loopback binding만으로 접근 통제의 충분성을 주장하지 않는다.
- 사용자 입력 endpoint/path는 명시적 validation/allowlist 경계와 bounded
  diagnostic policy를 거친다. URL을 서버가 무제한 조회하는 generic proxy나
  저장소 임의 파일 읽기 API를 제공하지 않는다. 자격 증명이나 sensitive raw
  payload는 telemetry, browser response, build artifact에 넣지 않는다.
- HTTPS/authentication/TLS 및 shared-host threat model은 별도 배포 결정으로
  검토하기 전까지 미지원이다.

### 4. 기존 local Operations lifecycle과 패키징 계약을 보존한다

- `make up`, `operations up/start/stop/status/logs` 및
  `validate deployment`의 public 동작을 유지한다.
- `OperationsRuntimePlan`의 collection → analysis → UI child 순서,
  하나의 workspace root/config, component별 log, supervisor lock, child
  failure 시 coordinated stop, graceful shutdown, 독립 telemetry ownership을
  보존한다. UI가 ready인지의 판단에는 실제 loopback listener 응답과
  process identity가 모두 필요하며 collection/analysis heartbeat와 혼동하지 않는다.
- production UI는 빌드된 정적 asset을 설치 가능한 Python wheel에서 제공한다.
  개발 시 Node 기반 빌드 도구를 사용하더라도 설치된 product를 실행할 때
  Node 개발 서버나 repository checkout을 요구하지 않는다. asset missing,
  UI readiness, wheel contents 및 CLI smoke는 배포 계약 테스트가 소유한다.
- `operations` optional dependency의 marimo/anywidget 제거는 기존 앱 사용을
  마친 최종 전환 이후 수행한다. research group의 marimo는 제거하지 않는다.

### 5. 증거 기반으로 교체하고 한 번에 cutover하지 않는다

- 기존 marimo UI를 전환 검증의 reference로 보존한 채, 먼저 read-only API 및
  observation→asset/signal 상세의 수직 경로를 구축한다. 검증 전에 하나의
  workspace에 legacy UI와 신규 UI의 **동시 쓰기**를 활성화하지 않는다.
  병렬 관찰이 필요할 때는 read-only 또는 격리된 fixture workspace를 사용한다.
- 이후 source registration/first-run, operations control, investigation,
  maintenance review, system diagnostics를 각 독립된 사용자 여정으로 옮긴다.
  동작·권한·의미 보존이 확인되기 전 기존 UI를 기본 진입점에서 제거하지 않는다.
- First-run의 isolated synthetic demo launch/stop, real workspace 비오염,
  configured resume, accepted receipt 확인 전 Monitor navigation 제한, 오류 복구,
  typed attention drill-down 및 review evidence 왕복은 전환 수용 계약이다.
- 기본 UI 진입점 변경과 old-marimo UI/dependency cleanup은 별도의
  리뷰 가능한 변경으로 제출한다. 배포 전환 시점의 롤백은 이전 정상 package 및
  변경하지 않은 workspace 저장 형식으로 수행한다. 영속 상태/schema를 바꾸는
  migration은 이 UI 교체 범위에 포함하지 않는다.

### 6. 제품 의미와 UX를 함께 보호한다

- 한국어 `ko-KR`을 사용자 문장·레이블·행동·오류·빈 상태 설계의 기준으로
  검토하고 영어 `en-US`를 별도로 자연스럽게 작성한다. stable page/domain ID는
  번역하지 않으며 `docs/terminology.md`가 기술 의미를 소유한다.
- 데이터 수신, source 연결, 저장, runner 상태, 원본 data quality,
  분석 결과, 설비 condition은 별도 사실이다. UI는 미확인·수신 중단·품질 문제를
  고장/안전 판정, verified fault diagnosis, alarm, operational RUL로 격상하지 않는다.
  AI나 자동 정비 권고를 이미 지원하는 것으로 표현하지 않는다.
- 네이티브 label/control 연결, 키보드 Tab/Enter/Space, 가시적 focus,
  읽을 수 있는 error/empty-state 및 locale별 layout을 새 웹 제품의
  기본 설계 계약으로 둔다. WCAG 2.2 AA는 검토 목표이며 자동 테스트만으로
  적합성을 주장하지 않는다.

### 7. CI 검증과 수용 범위를 새 코드 경로까지 확장한다

- Python의 Ruff/format/mypy/pytest와 runtime contracts는 유지한다.
  새 Web UI에는 JS/TS lint/format/typecheck, component behavior test,
  production build, packaged asset test를 추가한다. **경로 분류 CI에서
  새 frontend 디렉터리를 반드시 선택**하게 하며, required validation이
  skipped job을 성공 실행으로 오해하게 하지 않는다.
- Python API는 versioned response와 action validation, input bounds,
  same-origin security, error/recovery 및 invalid-data evidence contract를
  통합/계약 테스트로 보호한다.
- 실서비스와 통합된 Playwright는 `ko-KR`/`en-US` × 1024/1440px을
  최소 regression matrix로 유지하고, 실제 keyboard focus, native labels,
  browser history, refresh, sample/real, source receipt gate, configured restart,
  asset/signal/history, investigation/review, 1024px overflow를 검증한다.
  보조공학 실제 검증과 더 좁은 화면·zoom은 별도 acceptance 결과로 명시한다.
- 기존 marimo structural check는 old UI가 남아 있는 동안 유지한다.
  cutover 완료 시 Operations에만 적용되는 검사·테스트를 교체하고,
  연구 노트북/Analysis Explorer의 marimo 검증은 지속한다.

## Alternatives considered

- **marimo CSS/anywidget만 계속 확장**: 기존 구현을 보존하지만 screen/form/locale/
  accessibility framework workaround와 대형 reactive cell을 계속 늘리는 비용을
  감수해야 하므로 장기 사용자 제품 경계로 채택하지 않는다.
- **Python runtime과 데이터 계약을 웹 기술로 함께 재작성**: 검증된 수집·분석/
  provenance/recovery 계약을 재구현하고 새 실패 모드를 도입하므로 채택하지 않는다.
- **UI를 한 번에 교체한 뒤 테스트 복구**: package/front-door/readiness/first-run/
  review 결함을 발견하기 어렵고 사용자 비교 근거를 잃으므로 채택하지 않는다.
- **별도 개발 서버를 production UI로 실행**: single-command wheel/local supervisor
  계약을 위반하므로 채택하지 않는다.

## Consequences

Operations의 목표 클라이언트는 marimo에 의존하지 않으며, Python domain/runtime이
data/evidence/action source of truth를 유지한다. API transport, static asset
packaging, browser security 및 별도의 JS/TS 검증을 운영해야 하는 비용은 증가한다.

**이 ADR은 target architecture를 결정하며 현재 구현 상태의 변경을 선언하지 않는다.**
현재 기본 Operations UI는 전환이 완료되기 전까지 여전히 marimo이다.
현재 지원 범위는 `docs/status.md`가 소유하며, 순차 구현·일회성 acceptance
evidence·migration 작업 목록은 GitHub Issue/PR이 소유한다.
