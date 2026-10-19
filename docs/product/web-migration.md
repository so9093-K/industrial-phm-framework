# Operations Web 전환과 검증 범위

2026-10-17 사용자의 `/web/` 전환·이전 화면 삭제 요청에 따른 변경입니다.
기본 화면은 Svelte 업무 UI 하나입니다. Python API·supervisor·저장소가 측정값과
분석·검토의 주인이라는 계약은 유지합니다. 빌드 산출물의 내부 디렉터리 이름
`web_next`는 주소가 아닙니다.

| 이전 업무 | 현재 위치 | 회귀 근거 |
| --- | --- | --- |
| 관측·설비·수신/모델 주의 항목·수집/분석 서비스 경고 | 관측 현황, 설비·신호 | monitor attention, controlled journey |
| CSV 파일 점검·업로드·이력·분석 | 운영 관리 › 데이터 연결 | connections, registration, 실제 supervisor 응답 유실/리로드 |
| 3상 역할·OPC UA 등록/탐색·수집 | 운영 관리 › 데이터 연결 | registration, 실제 OPC UA 프로세스 중단/재연결 |
| 격리 예시 시작·상태·복귀·종료 | 운영 관리 › 데이터 연결 | sample browser 실제 supervisor |
| 연결 모델·자동 분석·점수/입력 원본 | 설비 › 이상 징후 › 모델 점수 | model connect/evidence/score trend, 실제 자동 분석 runner |
| AI 없는 특징값 비교·구간 흐름·원본·지점 질문 | 모델 점수 › 선택 측정 | model explanation/comparison, API 범위/비교 계약 |
| 시계열/진동 탐색·A/B 비교·관계·주파수·3상 상태 | 설비 › 신호/변화 분석 | signal/compare/relation/spectrum/acquisition profile/electrical |
| 선택 신호 예측·기준 도달·세부 설정·과거 검증 | 설비 › 상태 전망 | projection/acquisition outlook, 실제 Prophet 설정·이전 주소 검증 |
| 저장된 분석·실행 불가·AI·사람 검토 | 분석 기록/정비 검토 | investigations/finding review/outlook capture/model explanation |
| 프로세스·조회 실패·권한 | 운영 관리 › 시스템 상태 | operations, controlled journey의 PID/UID/CSRF·독립 preview 경계 |

`/web-next/`는 query를 유지하는 308 이동입니다. 이전 `#anomaly`의
`phm_binding/position/compare`, `#forecast/#rul`의 신호·기간·기준·계산 설정,
`#signals`의 두 구간 조건은 현재 위치로 옮깁니다. 없는 모델/측정/예측 신호를
다른 결과로 대체하지 않습니다. 모델 측정 선택은 최근 64회 밖의 저장된 번호도
정확히 읽습니다. 직접 측정을 고르거나 질문하면 자동 추적을 멈추고 사용자가
다시 시작할 수 있습니다. 진동 시간 예측은 기록된 간격 또는 명시한 가정이
필요하며 실제 관측 시각을 만들어내지 않습니다.

이전 direct-DOM HTML/JS/CSS와 그 DOM에만 의존한 브라우저 테스트는 제거했습니다.
저장소·실제 프로세스·권한 검사는 보존하고 현재 UI 회귀로 옮겼습니다.
2026-10-19부터 일반 Source CI는 lock·Ruff·mypy·unit/contract 검사만 수행합니다.
기존 `web-next`·`forecast`·`supervised-browser` 복합 gate와 PR마다 실행하는 개별 브라우저/배포
수용 워크플로는 제거했습니다. 실제 Web 수용은 단일 CI의 주간·명시적 Product acceptance 실행이 소유합니다. 현재 Web 기능·read DTO·빌드/배포를 변경할 때는
Svelte/TypeScript 빌드와 관련 통합·Chromium·supervisor 또는 wheel 수용을
해당 변경에서 별도로 실행하고 결과·미실행 범위를 PR에 기록합니다.
이전 성공한 자동 수용 결과를 현재 변경의 자동 보증으로 승격하지 않습니다.

실제 기록 데이터 acceptance 도구는 현재 UI를 사용하도록 갱신했습니다. 과거
2026-10-13 캡처·지연·AI 응답·PASS는 당시 코드의 기록입니다. 현재 자동 회귀의
합격이 전체 기록 데이터/로컬 AI 재실행, 현장 모델 성능, 실제 운영자 사용성,
전면 영어·스크린리더 수용 시험을 뜻하지 않습니다. 이전 README 이미지는 보존된 참고 자료입니다.
현재 화면·합성 시나리오·체험 배포물은 [제품 체험](product-showcase.md)에서 별도로 재현합니다.
