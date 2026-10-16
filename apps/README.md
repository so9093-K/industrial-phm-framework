# Applications

이 디렉터리는 repository-local interactive application의 **실행·개발 진입점**을 설명합니다.

현재 지원 capability와 제한은 [프로젝트 상태](../docs/status.md), 제품 정보 구조와 UX 의미는
[제품·UX 기준](../docs/product/overview.md), runtime/data ownership은
[architecture 문서](../docs/architecture/overview.md)를 authoritative source로 사용합니다.
이 문서는 화면별 현재 기능 목록을 중복해서 유지하지 않습니다.

## Operations — supervised Web

현재 운영자 제품은 패키지 내 Web 자산(`src/industrial_phm/apps/web/`)과
Python API로 실행합니다. 운영용 marimo 애플리케이션 및 `--ui marimo`는 제거했습니다.
연구용 marimo 화면은 `notebooks/`와 선택 설치 `research` group에서 별도로 관리합니다.

```bash
make up
make status
make logs
make down
```

기본 작업공간은 `artifacts/operations`이며 `WORKSPACE=<path>`로 변경합니다.
`make up`은 collection/analysis/Web를 하나의 Supervisor로 시작하므로,
이미 동일 작업공간에 수동으로 실행한 수집기·분석기와 병행하지 마세요.

```bash
uv sync --locked --extra operations
uv run --no-sync industrial-phm operations up artifacts/live
# 정지된 workspace의 수집/분석 재시작이 필요하지 않은 독립 UI/API 진단:
uv run --no-sync python -m industrial_phm.runtime.operations_web_preview \
  artifacts/live --port 8765
```

마지막 UI-only 명령은 **독립 Web preview**이며 Supervisor의 수집/분석 lifecycle을
소유하지 않습니다. 같은 workspace의 supervised Web가 작동 중이면 협조적 writer lease가
preview 쓰기를 차단합니다. 무인증 네트워크·다중 사용자 서비스가 아닙니다.

빈 작업공간의 첫 화면은 `예시 데이터로 둘러보기`와 `파일에서 시작`·`설비 연결 (OPC UA)`을 보여줍니다.
예시는 별도 작업공간·포트의 합성 모터 신호이며 실제 작업공간에 소스나 측정값을 넣지 않습니다.
격리 예시 화면에는 합성·읽기 전용 표시와 실제 작업공간으로 돌아가는 링크가 있습니다. 동봉된 CSV 예시는
브라우저 미리보기 전용이며 실제 작업공간의 등록·저장이 차단됩니다. 연결 진행·예시 관리와 고급 등록은 보조 영역입니다.
`CSV 파일로 시작`은 20MiB 이하 UTF-8 CSV를 저장 전에 브라우저에서 읽어 시간·측정 컬럼 후보, 빈 값·숫자 아닌 값·
시간대 누락·시간 역순을 행 번호와 함께 보여주고 실제 값을 미리 그립니다. 이 미리보기는 검증이나 저장이 아니며,
서버 사전 점검을 통과한 뒤에만 기존 등록 → 활성화 → 검증 수신 → 이력 저장을 단계별 결과와 함께 실행합니다.
재시도는 같은 ID뿐 아니라 파일 해시·컬럼·설정의 동일성을 서버에서 확인합니다. 브라우저를 다시 열면 같은 파일을
선택해 입력을 복원하고 점검 후 이어갈 수 있습니다. 저장 작업은 Supervisor가 소유하며 상태 조회 실패·중단은 저장 실패로
단정하지 않습니다. 완료 후 같은 설비·파일 출처·신호·표시 범위로 모니터링을 엽니다. 7일보다 긴 파일은 마지막 7일을 표시합니다. 단위·3상 역할은 자동으로 정하지 않으며 근거가 필요한 3상 매핑은 고급 CSV 등록을 씁니다.

빈 Web 작업공간에서 분리된 synthetic 샘플을 명시적으로 시작·중지할 수 있고,
FILE/OPC UA 소스별 등록·활성·수신 근거와 저장 이력, 분석 근거, Review를 조회할 수
있습니다. 전체 영어 UI·접근성과 모든 업무·오류 복구는 현재 수용 범위 밖이며
[현재 지원 상태](../docs/status.md)가 범위 기준입니다.
소스·설비·측정점·채널·분석/검토 ID는 화면에서 변경하지 않습니다. API 시각은 UTC 순간이며 한국어 Web은
KST(UTC+9)로 표시하고, 원본 측정·수신·이력 저장·분석 완료·조회 시각을 서로 다른 이름으로 구분합니다.

개별 OPC UA replay와 fault/recovery 실험은 [도구 안내](../tools/opcua/README.md)를
따르며, 연구 화면은 아래 Analysis Explorer 실행 지침을 따릅니다.

### 화면 구조

주요 메뉴는 `설비 모니터링`과 `데이터 연결`입니다. 설비 모니터링에서 설비를 고르면 같은 설비로 `개요`·`신호 탐색`·
`이상 탐지`·`상태 전망`·`분석 기록` 탭을 오갑니다(주소의 `monitor_asset`). 분석 결과의 확인·메모는 분석 기록 탭에서 남기고,
로컬 서비스 진단은 보조 링크 `시스템 상태`에 있습니다. 연구 평가 결과는 운영 Web이 아니라 Analysis Explorer에서 봅니다.

### 기본 설비 모니터링

`/web/#monitor`는 관측 상태, 확인할 설비, 선택 설비의 실제 신호 순서로 표시합니다. 같은 설비의 분석 거부는
하나의 확인 항목으로 묶고, 기준 비교·새 입력 대기·원본 읽기 실패를 구별합니다. 이상 탐지 현재값·이전값·변화량·기준 비교는 신호와 함께 표시하며, 모델 설정과 입력 상세는 보조 영역에 둡니다.
선택한 XJTU 진동 측정은 저장된 원본 RMS 크기와 직전 조회 기록 대비 증가·감소율, 최근 연속 기록을 보여줍니다.
앞선 비교 기록은 정상 기준이 아니며 기록 번호 공백은 현장 통신 중단의 근거가 아닙니다. 원본 파형과 전체 조회 범위도
선택할 수 있습니다. 공기압축기는 실제 전류·전압·주파수를 원래 단위로 보여줍니다.
상세 영역의 `이 시점의 추세·원본 입력 보기`는 같은 바인딩과 저장된 시점을 열며,
주소의 `phm_binding`·`phm_position`은 재로딩 후에도 유지됩니다. 기준 초과는 고장 판정이 아닙니다.

PHM 모델이 연결되지 않은 설비도 목록에 나타나며, 저장된 측정 이력(Asset History)의 실제 값·원본 측정 시각·
원본 품질과 구간 평균·최소·최대 추세를 모델과 무관하게 보여줍니다. 값이 없는 구간은 연결하지 않고 출처·측정점은
합치지 않습니다. 모델이 연결된 설비는 기존 분석 입력 화면이 기본이며 `저장된 측정 이력 (모델 무관)`을 측정 소스로
선택할 수 있습니다. PHM 조회가 실패해도 측정 신호는 계속 표시하고 분석 값만 숨깁니다.
저장 이력 추세는 요청마다 운영 스냅샷을 다시 읽어 요약보다 비용이 크므로 3초마다
읽지 않습니다. 설비·신호·구간을 바꾸거나, 해당 설비의 이력 커밋·기록 종료 시각이 바뀌거나, 30초가 지났을 때만
다시 읽으며 실패하면 이전 값을 지웁니다.

기본 갱신은 3초마다 운영 요약 3개를 읽고, 선택한 입력이 바뀔 때만 원본 미리보기와 최대 64개 저장 결과를
추가로 읽습니다. 모델 100개까지의 요약 범위와 읽기 실패를 표시합니다. 원본 검증이 실패하면 파형과 크기 요약을
지우며, 이전 입력은 버튼을 명시적으로 누른 경우에만 구별해 표시합니다. 부하·불평형 변화 분석은 수동 실행입니다.

### 상태 전망

`상태 전망` 탭에서 저장된 측정 이력이나 분석된 진동 측정별 특징을 고르고 관리 기준·종료 기준을 입력합니다.
최근 변화와 이상 탐지 근거, 조건별 기준 도달 여유를 살핀 뒤 같은 화면의 미래 예측 그래프에서 흐름을 확인합니다.
상세 설정에서는 추세 민감도·학습 범위·추가 측정 횟수와 측정 간격 가정을 바꿀 수 있습니다.

운영 실행 중에는 `현재 전망을 검토 대상으로 저장`으로 계산을 보존하고, 사람의 검토 메모·확인·완료를 남기거나
새 관측과 비교합니다. AI 질문은 선택적으로 연결합니다. 종료 기준까지의 조건부 여유와 물리적 고장 시각은 다릅니다.
계산 조건·근거 링크·검토·재관측의 의미는 [상태 전망 가이드](../docs/product/condition-and-rul-outlook.md)를 따릅니다.

### 이상 탐지 모니터링 (XJTU-SY 기록 재생)

**이상 탐지** 화면은 작업공간에 연결된 모델 패키지의 저장된 step 결과를 3초마다
변경분으로 읽습니다. 이상 탐지 상세는 선택 기록의 점수·앞선 분석 대비 변화량과 같은 범위의 신호 크기를
나란히 표시하고, 해당 기록의 원본 신호를 바로 아래에 둡니다. 기본 범위는 선택 시점의 연속 기록이며 전체 기록도
선택할 수 있습니다. 그래프 또는 키보드로 기록을 선택하면 요약·원본·주소가 함께 바뀌고, 새 입력이 도착해도
선택 기록을 유지합니다. `최신 기록으로`는 최근 결과를 따라가는 모드로 돌아갑니다. 모델·입력 특징과 검토 구간은
보조 영역에서 확인합니다.

모델을 연결하는 순서는 다음과 같습니다(준비된 XJTU-SY 원본은
[데이터 안내](../data/README.md#xjtu-sy)를 따릅니다).

```bash
make up                                   # 첫 터미널: 수집·분석·Web Supervisor
# 다른 터미널
SRC=data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets
uv run --no-sync industrial-phm operations phm package-xjtu artifacts/operations --source "$SRC"
uv run --no-sync industrial-phm operations phm bind artifacts/operations \
  --package <이상 점수 package ID> --source-id xjtu-sy-replay --asset-id Bearing1_1
uv run --no-sync industrial-phm operations phm replay-xjtu artifacts/operations \
  --source "$SRC" --bearing Bearing1_1 --interval-seconds 1
```

- `package-xjtu`는 fold-1 연구 설정을 train 베어링으로 다시 학습해 `models/`에 불변 패키지로 씁니다
  (약 3–4분). 깨끗한 Git checkout이 아니면 `--code-revision`을 지정합니다.
- 재생은 기록 데이터를 시간 압축해 공급하는 것이며 화면에 "기록 데이터 재생"으로 표시됩니다. 재생 대상은
  모델 학습에 쓰지 않은 베어링(`Bearing1_1/2_1/3_1`, `Bearing1_2/2_2/3_2`)을 사용합니다.
- 분석 runner는 0.5초마다 새 step을 처리하고, 화면은 최신 수신·최신 분석 시각과 분석 대기 수를 함께 보여줍니다.
- 이상 점수는 고장 확률·진단이 아닙니다. 판정 기준과
  검증 결과는 [운영 추론 수용 프로토콜](../docs/research/operational-inference-acceptance-protocol.md)을 따릅니다.

## 연구 도구

저장된 연구 결과 탐색은 [notebooks의 Analysis Explorer](../notebooks/saved-analysis-explorer.md)에서 별도로 실행합니다. 운영 제품의 모델 연결·수신·설비 관측 경로와 분리합니다.
