# Current Support Status

이 문서는 `industrial-phm-framework`의 **현재 구현·지원 범위**를 한 곳에서 확인하기 위한
authoritative status 문서입니다.

이 문서는 architecture나 roadmap이 아닙니다.

- 시스템 책임과 contract boundary는 [Architecture](architecture/overview.md)가 소유합니다.
- 구조 결정의 이유와 대안은 [ADR](adr/README.md)이 소유합니다.
- 실행 방법과 runtime path는 해당 subsystem README가 소유합니다.
- 변경 이력은 [CHANGELOG](../CHANGELOG.md)가 소유합니다.
- 계획된 작업, milestone, 일회성 migration 상태는 GitHub Issue/PR이 소유합니다.

README·Architecture·Product 문서는 아래 지원 표를 다시 복사하지 않고 이 문서를 참조합니다.
이 문서는 **지원 경계가 바뀔 때만** 갱신하며, 내부 refactor나 commit마다 현황을 추가하지 않습니다.

## 상태 정의

| 상태 | 의미 |
| --- | --- |
| **지원** | repository의 public/runtime 경로와 자동화된 검증이 존재함 |
| **조건부 지원** | 명시적 configuration 또는 제한된 contract 안에서 지원함 |
| **Research only** | 연구·평가 evidence 경로이며 operational capability로 주장하지 않음 |
| **미제공** | 현재 public/runtime 경로가 없음 |

## Operational data path

| 영역 | 상태 | 현재 경계 / 근거 |
| --- | --- | --- |
| FILE source 등록·검증·backfill | **지원** | prepared FILE source를 명시적 asset/channel/time mapping으로 검증하고 Asset History에 적재 |
| OPC UA one-shot / bounded subscription | **지원** | explicit NodeId mapping과 protocol quality/timestamp 보존 |
| OPC UA persistent collection | **지원** | 독립 collection service, reconnect, durable spool, telemetry, DuckLake writer, observation-window coordinator |
| Asset History | **지원** | FILE backfill과 OPC UA live observation을 DuckLake history에서 함께 조회 |
| Asset History manual small-file compaction | **조건부 지원** | explicit `maintenance history compact`만 지원. snapshot expiration/cleanup 없이 table별 merge-only compaction을 수행하고 old snapshot evidence/retry를 검증. 자동 scheduling은 미제공 |
| Asset History live retention | **조건부 지원** | explicit `maintenance history retain <workspace>`만 지원(기본 7일, `--dry-run`). OPC UA live 관측과 finalized window를 event time 기준으로 삭제하고 cutoff 이전 snapshot을 만료한 뒤 참조되지 않는 file을 제거. FILE history와 닫히지 않은 review의 관측 범위·window·snapshot은 보존. 분석 cursor가 지나지 않은 window는 삭제하지 않음. 삭제는 약 10만 행의 분 단위 slice, snapshot 만료는 2,000개 chunk 단위로 catalog lease를 나눠 잡고 마지막 flush로 catalog-inline 삭제분을 비움. slice 탐색·snapshot 목록·cleanup·flush의 lease는 상태 크기에 따라 길어짐. 다른 행과 섞인 file의 삭제분은 물리적으로 남음. 자동 scheduling·telemetry/catalog VACUUM은 미제공 ([ADR-0023](adr/0023-retain-live-evidence-for-a-bounded-period.md)) |
| 측정 의미(semantic binding) | **조건부 지원** | source가 명시적으로 제공한 versioned binding만 사용. channel 이름에서 물리 의미를 추론하지 않음 |
| Asset History latest/page/aggregation 의미 표시 | **지원** | FILE/OPC UA raw evidence에 고정된 의미 snapshot을 fail-closed로 표시 |
| Finalized observation window | **지원** | accepted event set과 rejection/watermark evidence를 SQLite WAL에 보존. continuous coordinator는 bounded durable-ingestion cursor로 새 event만 처리하고 cursor/watermark/active buffer를 finalized window와 같은 transaction에 checkpoint |
| Live 분석 runner | **지원** | collection service와 별도 process. capability/algorithm/policy별 durable cursor 이후의 finalized window만 bounded page로 처리하고 분석 결과/SQLite skip ledger를 restart-safe하게 저장 |

세부 live stack 실행은 [OPC UA local stack](../tools/opcua/README.md)을 따릅니다.

## Analysis and Operations

| 영역 | 상태 | 현재 경계 / 근거 |
| --- | --- | --- |
| Registered FILE snapshot vibration feature AnalysisRun | **지원** | operational AnalysisRun/evidence 경로 |
| 3상 불평형 · historical Asset History | **지원** | fixed history snapshot + explicit/semantic-role channel selection |
| 3상 불평형 · finalized live window | **지원** | ADR-0008에 따라 window가 accept한 event set만 사용 |
| Temporal alignment `strict-v1` | **지원** | 같은 timestamp의 세 상만 계산 |
| Temporal alignment `bounded-previous-v1` | **조건부 지원** | explicit max age와 근거가 필요. causal event-transition reconstruction이며 synchronized acquisition cycle을 주장하지 않음 |
| window 시작 전 carry-in state | **미제공** | finalized window 밖의 이전 값을 analysis input으로 재조회하지 않음 |
| Operations source control/monitor | **지원** | desired collection request, collector-service heartbeat, OPC UA session, live receive silence, spool/history evidence를 서로 다른 사실로 표시 |
| 설비 전기 상태·변화 분석 | **조건부 지원** | 한 asset/source/측정 지점의 확인된 3상 V/A 이력을 기준 구간과 비교. 관측 평균 전류, 1A 이상 통전 시간의 관측 추정, 전압/전류 불평형 및 기존 Isolation Forest의 기준 패턴 이탈 점수·시각을 표시. 기준만 학습·99% 점수 분위수 비교선을 계산하며 분석 구간은 학습에 사용하지 않음. 1/6/24h와 명시적인 앞선 기준 기간, 같은 snapshot·측정 의미, 기간별 3,600시각·22,000행 안에서 지원. 의미 미확정·혼합·결측·충돌·저전류·기준 부족은 미평가로 표시. 점수는 고장 확률·진단·경보·정비 권고·RUL이 아님. 탐색형 읽기 분석이며 자동 재학습 운영 모델의 배포·승인 기능이 아님 |
| Operations Monitor / Signals / attention | **조건부 지원** | 현재 wheel 내 `/web/`의 source·asset ID와 저장된 신호 이력, 최신 측정값·품질·시간·출처, 최대 6개 채널의 저장된 전체 기록(기본, 첫 측정~마지막 측정)·최근 15m/1h/24h/7d 조회, 등록 시 선언한 신호 이름·단위로 표시(값이 없으면 채널 ID), 단위가 붙은 세로축. 진동 측정만 있는 설비는 측정별 진동 특징 추이(`/api/v1/acquisition/trend`)와 저장된 AnalysisRun/Review 증거를 제공합니다. 기본 Monitor는 3초마다 운영 수신·PHM 요약을 자동 조회하며, 설비별 확인 항목과 선택 설비의 검증된 원본 신호를 먼저 표시합니다. 저장 이력이 있으면 모델 연결 여부와 무관하게 이를 기본으로 관측하며, PHM 입력은 별도 선택입니다. 수집 상태와 분석 상태, FILE의 검증 수신과 OPC UA 연속 수신을 구분합니다. XJTU는 최대 64개 저장 입력 RMS의 크기·직전 조회 기록 대비 증가·감소율·최근 연속 구간, 공기압축기는 원본 V/A/Hz를 표시합니다. 기록 번호 공백은 수신 중단이나 정상 기준이 아닙니다. 모델·검토 상세 링크는 정확한 모델과 시점을 유지합니다. 변화 분석·System 등 보조 화면은 명시적 조회입니다. live subscription이나 설비 안전 판정이 아닙니다. 빈 bucket은 0으로 연결하지 않으며, attention은 확인한 운영 상태 근거를 표시합니다. **구형 marimo의 별도 신호 검색/hover·cursor·Investigation drill-down 전체 UI를 현재 Web에 구현한 것으로 주장하지 않습니다.** 구형 화면과의 전체 업무 동등성은 현재 지원 범위 밖 |
| Operations Asset History | **지원** | 최신값·raw page·UI aggregation·quality·provenance 조회 |
| Operations의 3상 불평형 결과 조회 | **조건부 지원** | runner와 Operations가 같은 phase-unbalance result repository path를 사용해야 함. 기본 Monitor의 운영 요약은 자동 조회하며, 개별 결과·원본 신호는 명시적 조회로 확인 |
| Operations 분석 시도/skip 이유 조회 | **조건부 지원** | Operations가 runner와 같은 finalized-window SQLite와 analysis-ledger SQLite를 읽을 때 Asset별 Analyzed/Skipped 시도와 exact skip reason을 표시 |
| Live runner process lifecycle | **지원** | `operations start <root>`의 supervisor가 collection과 별도 analysis runner process를 함께 소유. analysis health는 runner-owned heartbeat가 authoritative |
| Investigation / human Review / Maintenance | **조건부 지원** | 기본 Svelte Web의 `/web/?page=investigations`는 저장된 분석·실행 불가 결과와 검토 요청을 표시합니다. `/web/?page=maintenance`는 검토 작업함에서 분석·모델 결과·요청된 전망의 근거를 연결하고 note/acknowledge/close 및 상태별 조회를 제공합니다. 검토 종료는 정비 완료나 설비 건강 판정이 아닙니다. 과거 marimo/direct-DOM 화면은 제거됐고, 연구/라이브러리용 pure projection 보존을 구형 운영 UI 지원으로 해석하지 않습니다 |
| PHM 모델 패키지 · 설비별 순서 step 분석 | **조건부 지원** | [ADR-0025](adr/0025-run-versioned-model-packages-over-ordered-asset-steps.md). 데이터 전용 패키지(내용 해시 ID, 적재 시 payload SHA-256·probe 재검증, pickle 없음)를 `operations phm bind` 또는 Web 이상 탐지 탭의 `연결`(입력 형식이 맞는 스트림만 제시, 운영 실행 중에만)로 명시한 (source, asset) 스트림에만 실행. step 결과·skip 이유·설비별 상태·검토 구간·cursor를 step 단위 트랜잭션으로 저장해 재시작 후 이어감. step 종류는 **acquisition snapshot**(파형 파일+SHA-256)과 확인된 3상 전기 **finalized observation window**를 지원. window binding은 source/asset/측정점을 명시하며 300초 윈도우의 같은 시각 R/S/T A·V와 Hz만 사용. PHM SQLite v1→v2는 replay/측정점 필드만 추가하고 기존 cursor·상태를 보존하며 구형 runner로의 schema 역변환은 제공하지 않음. 자동 재학습·모델 승인 workflow는 미제공. 잔여수명(RUL) 작업은 [ADR-0026](adr/0026-retire-remaining-life-estimation.md)으로 폐기했고, 기존 작업공간의 RUL 패키지·바인딩은 지우지 않되 실행·표시하지 않음 |
| AI-Hub 239 전기 다변량 이상 탐지 | **조건부 지원** | 설비별 Training/raw 앞 70%만 fit한 고정 PCA/IForest 패키지를 `package-aihub`로 생성하고 finalized window에서 반복 추론. 동일값의 새 timestamp와 원래 기록 시각을 보존하는 OPC UA 재생, 공통 시간축 7개 원본 신호·첫 유효 값 대비 변화율·PCA 특징별 잔차 기여·자동 갱신을 Web에서 확인. 사전 정한 결함 주입 평가 v2([결과](research/results/aihub-239-electrical-anomaly-evaluation-v2.json))는 기준(주입 유형별 탐지율 90% 이상, 보류 기간 경보 비율 2% 이하)에 못 미쳤습니다(탐지율 20.83~88.10%, 경보 비율 3.828%). 이 결과는 모델 개선의 참고 기록이며, 모델 실행·화면 표시를 막는 조건이 아님 |
| XJTU-SY 기록 재생 이상 점수 | **조건부 지원** | fold-1 연구 설정(Isolation Forest finalized)을 train 베어링으로 다시 학습한 패키지를 `operations phm package-xjtu`로 생성하고 `replay-xjtu`로 학습에 쓰지 않은 베어링의 획득을 순서대로 공급. [운영 추론 수용 프로토콜](research/operational-inference-acceptance-protocol.md) §2.2 판정: **PASS**(2026-10-12, 커밋 `344193d`): IForest held-out 3개 베어링의 Spearman ρ·late-vs-middle이 저장된 연구 결과와 차이 0, 순차 출력 = 일괄 출력(차이 0). 기록 데이터 시간 압축 재생이며 현장 설비 수신이 아님. 이상 점수 임계값은 train reference 점수 99.5% 분위수, 점수는 고장 확률이 아님. LSTM AE는 동일 연구 설정의 train-only 가중치를 JSON 수치 배열로 저장·재적재하며 8개 과거 획득 버퍼를 같은 트랜잭션으로 보존. [프로토콜 §5](research/operational-inference-acceptance-protocol.md) v3 판정 PASS(같은 실행 환경의 연구 재실행과 획득별 일치 AE ≤ 7.4e-7, 순차 = 일괄). 잔여수명(RUL) 패키지는 폐기([ADR-0026](adr/0026-retire-remaining-life-estimation.md)) |
| 이상 탐지 Web 화면 | **조건부 지원** | 기본 `/web/`의 설비별 ‘이상 징후’(`/web/?page=assets&tab=anomaly&method=model`)에서 연결된 모델의 저장된 점수·기준 초과·분석 실패/대기와 입력 측정 근거를 조회하고, 선택한 측정의 원본 파형·비교·AI 해설/사람 검토를 이어서 확인합니다. 같은 측정 흐름에 모델이 둘 이상이면 각 점수를 그 모델의 기준으로 나눈 값을 한 그래프에 겹쳐 그리고, 모델을 바꿔도 보던 측정을 유지합니다. 기준 초과 구간 안의 측정은 그 구간 직전 측정과 기본 비교합니다. 모델 이름은 방법(LSTM 오토인코더·Isolation Forest·PCA 잔차)으로 표시하고 레시피·패키지 ID는 기술 상세에 둡니다. `industrial-phm demo xjtu`는 로컬 XJTU-SY 원본에서 두 모델을 준비·연결하고 학습에 쓰지 않은 베어링을 재생한 뒤 Web을 엽니다. 브라우저는 새 모델 점수나 상태 판정을 만들지 않습니다 |
| 설비별 PHM 기본 Monitor | **조건부 지원** | 3초 자동 조회에서 모델 입력·마지막 성공 분석·최근 준비/거부/실행 불가를 구분. 원래 기록 시각과 저장·처리 시각, 기록 재생 여부, 기준 초과와 검토 상태를 설비별로 표시. 주의 항목에서 신호 변화는 정확한 모델·시점으로, 수신 문제는 해당 연결 진단으로, 분석 거부·대기는 입력·모델 처리 상태로, 진행 중 검토는 해당 분석의 사람 검토로 이동. 페이지 비활성·숨김 시 polling을 멈추고 복귀하면 재조회. 1회당 HTTP 조회 3개이며 PHM 요약은 최대 100개 바인딩·초과 범위를 표시. 이력 전체 조회·모델 계산·AI 호출을 기본 갱신에 포함하지 않음. 현장 경보·건강도나 무제한 설비 규모 보증이 아님 |
| PHM 신호 비교·AI 질문 · 사람 검토 | **조건부 지원** | 이상 탐지의 선택 결과와 같은 모델의 이전 분석(최근 128개와 첫 분석 선택지)을 비교. 기본 값·측정 특징 비교표는 AI 없이 펼쳐볼 수 있고 작은 화면에서는 특징별 값·변화로 묶어 표시. 읽기 전용에서는 상단에서 측정값 비교로, 질문 권한이 확인되면 질문으로 이동하며 두 시점·구간(5개 이상 분석)·선택 지점에 맞는 질문을 추천. 운영 실행 중 Web에서 최대 600자 질문(추천 질문 포함)을 저장 결과에 고정해 요청하고, 같은 비교의 이어지는 질문은 앞선 질문·답 최대 3개를 함께 전달. AI 입력에는 실제 특징 변화(최대 64개), 검증된 원본 통계(최대 16채널·파형 20만 샘플/16 MB), 같은 설비·소스·측정점·원본 입력의 관련 모델(최대 8개)을 포함. 선택 구간의 흐름(순위 상관)·수준 변화는 최대 512개 내외의 고른 표본으로 요약하고 근사 범위를 표시. 인접한 분석 결과 간 최대 변화와 꾸준한 방향 여부는 전체 구간에서 따로 계산해 표와 AI 입력에 포함하고, 추세 표현은 흐름이 한 방향인 항목에만 허용. 고장 원인 추정은 제공하지 않음. 원본 확인 시 선택 특징명과 선언된 채널 의미에 따른 관련 파형을 유지·강조하고, 작은 화면의 구간 흐름은 항목별 카드로 표시. 기본 `http://127.0.0.1:9400/v1`의 `local-main`(Responses, 실패 시 Chat Completions), 원격은 명시 허용한 https만. 답변은 JSON 스키마로 받아 언급한 특징·방향이 저장된 비교와 맞는지 코드가 확인하고, 수치는 화면이 저장값으로 표시. 숫자·판정·인과·추세·기준 비교·주 결과 방향·기여도 표현을 검사하고 문제가 있으면 이유와 함께 1회 재작성, 남은 문장은 빼고 저장된 비교로 채움(별도 검토 호출은 재작성 계기로만 사용). 임의 문장의 의미를 모두 검증하지는 않음. 답변은 모델 출력을 수정하지 않고 별도 저장하며 분석 진행을 기다리게 하지 않음. 사람 검토 요청·확인·종료는 기존 finding/review 기록을 사용. AI의 답변 품질·사용성 합격은 별도 평가 대상 |
| Operations asset 표시 이름 | **조건부 지원** | source 등록이 선언한 optional `asset_display_name`을 같은 asset의 선언이 모두 일치할 때만 label로 사용. 없거나 불일치하면 `asset_id`(불일치는 System 표시). `asset_id`는 identity·provenance로 유지 |

3상 불평형의 계산·eligibility·alignment 계약은
[capability 문서](architecture/phase-unbalance-capability.md), live input 결정은
[ADR-0008](adr/0008-analyze-finalized-window-accepted-events.md), temporal alignment는
[ADR-0009](adr/0009-temporal-alignment-policy.md)을 따릅니다.

## Research / operational boundary

| 영역 | 상태 | 현재 경계 |
| --- | --- | --- |
| XJTU/IMS/MIMII anomaly experiment evidence | **Research only** | Analysis Explorer에서 연구 결과·pipeline·provenance 검토. XJTU RUL 실험 코드는 폐기했고 결과 문서(`docs/research/results`)만 기록으로 보존 |
| provider label을 production 분석 입력으로 사용 | **미제공** | label은 research evaluation에만 사용 |
| validated fault diagnosis | **미제공** | 관측·분석 evidence를 진단으로 자동 승격하지 않음 |
| operational alarm / fleet risk scoring | **미제공** | source 상태나 analysis output을 alarm/risk verdict로 자동 승격하지 않음 |
| RUL 모델 (Ridge·LSTM) | **폐기** | [ADR-0026](adr/0026-retire-remaining-life-estimation.md). 학습된 RUL 모델과 별도 RUL 화면은 없음. 잔여수명은 아래 `상태·잔여수명 전망`이 사용자가 정한 종료 기준까지의 거리로 계산([ADR-0027](adr/0027-condition-and-remaining-life-outlook-from-stored-analyses.md)) |
| 자동 정비 권고·설비 제어 실행 | **미제공** | 사람의 review/승인을 대체하지 않음 |

## Validation and deployment boundary

| 영역 | 상태 | 현재 경계 |
| --- | --- | --- |
| synthetic OPC UA loopback E2E | **지원** | 실제 asyncua server와 별도 collector process를 사용하는 contract test |
| one-command synthetic Operations demo | **지원** | `industrial-phm demo synthetic`이 전용 workspace에 synthetic 3상 OPC UA source를 등록하고 simulator + collection + analysis + packaged UI를 한 foreground lifecycle로 실행. 물리 설비 측정/고장 진단 evidence가 아님 |
| supervised Web first-run synthetic sample lifecycle | **조건부 지원** | 운영 실행 중 Web의 `격리 샘플 시작/종료/상태 확인`은 Supervisor PID-bound IPC를 통하며, 별도 sibling workspace·동적 loopback 포트의 실제 `/web/` 화면으로 열립니다. #512에서 삭제된 marimo 때문에 skip되던 Chromium 테스트를 복구했고 [PR CI #38141702708](https://github.com/so9093-K/industrial-phm-framework/actions/runs/38141702708)에서 실제 21 passed / 0 skipped(해당 Browser step)와 격리·새 탭·리로드·중지를 확인했습니다. standalone preview는 샘플 process 명령 403. 테스트 완료가 전체 guided Setup/Investigation/System 동등성을 뜻하지 않습니다 |
| AI-Hub boiler recorded replay demo | **조건부 지원** | local AI-Hub 239 boiler archive + `aihub` extra가 있을 때 `industrial-phm demo aihub-boiler`가 검증된 device 2297/member/time-range preset을 replay server + normal Operations runtime으로 실행. recorded provider data replay이며 live endpoint 동작 검증이나 설비 진단이 아님 |
| AI-Hub 239 공기압축기 recorded replay Operations E2E | **조건부 지원 / 역사적 근거** | 로컬 AI-Hub 239 공기압축기 아카이브와 전용 binding을 사용한 1338 replay→collection→history→finalized window→3상 불평형은 별도 recorded-run evidence가 존재합니다. 이전 marimo UI의 Monitor/Investigation/Maintenance 전체 화면 실측을 현재 Web의 동등성 PASS로 승계하지 않습니다. 현재 supervised Web의 Evidence→Review 및 오류/복구 지원은 아래 Web 수용 범위를 따릅니다. 현장 OPC UA 접속·실설비 고장 진단·자동 정비 권고가 아닙니다 |
| Operations Web browser acceptance | **조건부 지원** | 기본 Web의 저장된 관측·FILE/OPC UA 등록·분석·Review·Supervisor 재시작 사용자 여정을 Chromium으로 검증. 예전 marimo Monitor에서 측정한 6개 fault UI 상태의 과거 증거는 현재 Web에 승계하지 않음. `tools/opcua/fault_harness.py --browser`는 실제 Web의 source/attention 근거를 검사하도록 개정했지만 동일 AI-Hub 기록 재실행 결과가 없으면 신규 full gate를 통과했다고 주장하지 않음. 실제 현장 설비 검증은 별개 |
| PHM 기록 재생 제품 인수 (XJTU-SY · AI-Hub 239) | **조건부 지원** | 원본 기록 재생을 감독형 노드의 공급/OPC UA 수신 → 추론·저장 → 이상 탐지 → 실제 `local-main` 설명 → 사람 검토 → 재시작으로 검증. UX 개편 후 1440/1024/390px ko-KR Chromium에서 입력 거부·LSTM 준비·최신 SKIPPED·조회 실패의 이전 결과 구분, R/S/T 동단위 비교와 원본 입력 연결, 키보드 포커스·가로 넘침, AI 요청 실패 중 직접 검토를 확인([실행·화면](research/results/phm-product-acceptance-2026-10-13/README.md)). 기록 재생의 기능·화면 검증이며 모델 성능 합격·현장 설비·다른 브라우저·스크린리더 인증이 아님. 기본 CI에는 포함하지 않음 |
| clean-workspace Operations product acceptance | **지원** | 외부 데이터 없이 fresh synthetic workspace에서 실제 Web 포함 demo process → runtime ready → finalized window/analysis evidence → stop → 같은 workspace restart/state 보존을 합성 수용 테스트로 검증 (기본 CI에는 포함하지 않음) |
| AI-Hub replay repeatable fault gate | **조건부 지원** | `tools/opcua/fault_harness.py`는 stall·kill/restart·overflow·spool backlog N회 주입, missing-phase evidence, live receive→pause→reconnect→recover/history continuity, 정확한 AnalysisRun/Evidence 기반 review 기록을 판정. `--browser`는 현재 Web source/attention 근거를 확인하나 변경 후 전체 기록 데이터 실측 재실행이 필요. 과거 marimo 결과를 현재 Web 성공으로 간주하지 않음 |
| Local Operations workspace 초기화 | **지원** | `industrial-phm operations init <root>`가 versioned `config.toml`과 managed data/log directory를 만들고 기존 유효 workspace에는 idempotent하게 동작. config 없는 비어 있지 않은 directory는 자동 채택하지 않음 |
| Local Operations runtime status | **지원** | `industrial-phm operations status <root>`가 supervisor process identity, collection/analysis heartbeat, UI loopback listener readiness를 분리해 표시. PID 존재만으로 component health/readiness를 추정하지 않음 |
| 통합 local Operations lifecycle | **지원** | `operations start <root>`가 workspace config에서 collection → analysis → packaged UI launch plan을 만들고 한 foreground supervisor로 실행. Ctrl-C 또는 `operations stop <root>`은 child를 역순으로 graceful shutdown하며, 터미널의 Ctrl-C·창 닫기(SIGHUP)가 child에 먼저 닿아도 정상 중지로 기록. 실행 중인 supervisor가 없으면 stop은 마지막 상태를 알리고 성공으로 끝나며, supervisor가 사라진 뒤 남은 component는 명령줄의 역할·작업공간(프로세스 cwd 기준 경로)과 stdout 로그가 모두 일치하는 프로세스만 pidfd로 신호를 보내 stop·up에서 정리. up은 Web 포트를 다른 프로세스가 쓰면 시작 전에 알림. stop은 persisted PID만 믿지 않고 workspace supervisor lock owner PID까지 검증 후 signal 요청 |
| Web CSV 분석 전 점검 pilot | **조건부 지원** | 운영 실행 중 Web에서 20MiB 이하 PC 업로드(임시 stage) 또는 작업공간 내 CSV 상대 경로의 실제 어댑터 검증을 재사용해 행/채널/시각/원본 SHA·이력 시간대·3상 입력 준비와 구체적 수정 안내를 표시. 사전 점검은 source/receipt/DuckLake/AnalysisRun을 생성하지 않으며 현장 단위·배선 의미의 진위를 증명하지 않음 |
| Web source mutation pilot (운영 실행 중) | **조건부 지원** | Linux 단일 로컬 작업공간에서 기본 `operations start <root>` / `make up`의 `web-controlled` 모드에서 supervisor-owned Unix IPC/PID/UID/token과 기존 action facade로 source 등록·수집/검증 명령을 실행. single writer는 supervisor가 보유하고 운영 중 별도로 띄운 조회 전용 Web의 충돌 POST는 409. `FILE` first-run→ACTIVE→accepted receipt→명시적 DuckLake backfill→별도로 사용자가 실행해 **신규 저장한 FILE 통계 특징 AnalysisRun/Evidence** 또는 사용자 선언 V/A·R/S/T·단위 근거를 원본 행에 보존한 FILE 이력의 **3상 불평형 AnalysisRun/Evidence**→사람 검토 request/note/ack/close→Supervisor 재시작 후 복원은 실제 1024/1440px ko-KR Chromium에서 검증. 과거 wheel-only·stopped-workspace backup/new-root restore·특정 이전 green wheel rollback(#474~#475)과 참조 systemd 서비스 restart/failure(#476)를 해당 시점에 실측. 현재 기본 CI가 배포·롤백 호환성을 지속 보증한다는 뜻은 아님. **전체 Web 업무/영어/접근성 동등성은 현재 지원하지 않음**. crash 후 durable exactly-once·임의 버전/schema rollback은 보장하지 않음. 기본 `make up`은 로컬 파일럿이며 구형 `--ui marimo`·`--ui web-preview` 모드는 제거됨. Web은 하나이고 `/api/v1/session`의 `mode`(operations·view-only·example)와 `can_change`로 변경 가능 여부를 알리며, 화면은 운영이 실행 중이 아닐 때만 한 번 안내함. 전면 영어·실제 운영자 사용성 검증은 미완료 |
| Web evidence-linked human review API pilot | **조건부 지원** | `POST /api/v1/reviews/request`는 저장된 3상 분석 또는 FILE 통계 특징의 `analysis_run_id`와 정확한 `evidence_id`를 확인해 검토 요청을 기록. `POST /api/v1/reviews/action`은 기존 finding의 note/acknowledge/close만 영속 기록하며 **검토 종료는 물리 정비 완료·설비 건강·진단이 아님**. Supervisor-owned Web IPC/HTTP CSRF와 1024/1440px Chromium Review·재시작 영속 수용(#471~#477), 운영자 화면 상태 해석 안내(#482)까지 Chromium으로 검증했습니다. FILE 특징 결과는 운영 실행 중 Web `POST /api/v1/analysis/file`로 명시적 실행한 소스 CSV 스냅샷에서만 신규 생성하며 원본 SHA-256·특징값을 표시. 기존 3상 분석 엔진과 별개이고, backfill은 자동 분석이 아님. `POST /api/v1/analysis/phase-file`은 등록 시 명시한 상·V/A·근거가 DuckLake 원본 행에 보존돼 있고 파일 SHA-256이 일치하는 FILE만 분석. 무바인딩/이력 누락/변조 원본은 거부하며 3상 불평형률 역시 고장 판정·경보가 아님. 통계 특징도 단위 확인·고장 진단이나 건강 판정이 아님 |
| Web 모델 연결 | **조건부 지원** | 준비된 패키지만 선택 설비의 선언 입력과 대조해 기존 CLI 바인딩을 생성. 연결·입력 대기·runner 결과를 구분하며 모델 업로드·학습·성능 보증은 포함하지 않음 |
| Web 화면 구조 | **지원** | 기본 `/web/`의 업무 메뉴는 **관측 현황·설비·신호·분석 기록·정비 검토·운영 관리** 5개. 선택 설비의 탭은 **상태 요약·이상 징후·신호·변화 분석·상태 전망**이며 `monitor_asset`으로 설비 문맥을 유지. 운영 관리 안에 데이터 연결·시스템 상태가 있고, 정비 검토는 분석 기록과 분리해 사람의 확인·종료를 소유(Web에서 새 메모 입력은 받지 않고, 이전에 남긴 메모는 기록에 표시). 기존 `?view=`·`#review`·`#research`·`#rul`·`/web-next/` 주소는 현재 업무 화면으로 이동하며 북마크의 유효 분석 선택 조건을 보존. 연구 평가 결과는 운영 Web에 없고 `docs/research/results/`에 보존 |
| 신호 탐색 · 구간 비교 | **지원** | 선택 설비의 두 구간을 저장된 원본 관측값으로 비교. 측정 이력은 DuckLake에서 source·측정점·채널·해석별로 개수·사용 가능·값 없음·원본 품질 문제·같은 시각 충돌, 최소·최대·평균·표준편차·5/25/50/75/95% 분위수, 사용 가능 시각 간격의 중앙값·가장 긴 공백·중앙값 3배 초과 공백 수, 같은 값이 이어진 최대 기록, 두 구간 공통 경계의 20칸 히스토그램, 다른 구간 5–95% 범위 밖 값 수를 계산(구간당 최대 31일, 채널 최대 6개). 진동 획득은 저장된 획득별 특징과 전달된 획득 번호로 같은 항목과 빠진 번호·분석되지 않은 획득을 계산. 두 항목 관계는 같은 출처·측정점·시각(진동은 같은 획득)의 관측만 짝지어 구간별 짝 수·Pearson·평균 순위 Spearman과 표본 산점도(최대 1,500점)를 제공. 진동 주파수는 구간별 최대 8개 획득의 SHA-256 확인 원본 파형으로 Welch PSD(Hann, 50% 겹침, 4,096점) 평균과 16개 대역의 B/A dB 변화를 제공하며 고장 주파수를 지정하지 않음. 자동 원인 진단은 이 화면에 없음 |
| 분석 바로가기 | **지원** | 설비 개요와 CSV 저장 직후에 측정 신호·구간 비교·신호 관계·주파수 성분·상태 전망·이상 탐지·AI 질문을 근거와 함께 열기/모델 연결/대기로 표시하고, 할 수 없는 항목은 이유와 함께 한 줄로 모음. 서버가 저장된 이력·획득·설치 패키지의 입력 조건·연결된 모델 결과·Web 권한으로 판단(`GET /api/v1/explore/capabilities`). 분석·모델은 실행하지 않음 |
| 상태·잔여수명 전망 | **지원** | `상태 전망` 탭(`#forecast`)의 첫 내용. 선택 신호의 열화 지표(기록 처음 30% 대비 최근 수준 변화, 최근·그 전 변화 속도의 Theil–Sen 기울기, 변동폭 비율, 중앙값 ± MAD 변동폭 3.5배 초기 비교 범위에서 이후 관측의 80% 이상이 이탈하기 시작한 지점), 연결된 이상 탐지 모델의 최근 점수·처음 기준 초과·검토 구간, 사용자가 입력한 관리 기준·종료 기준(상한/하한)까지 남은 시간·획득 수를 표시. 종료 기준까지의 거리를 잔여수명으로 부름. 같은 기준까지의 여유를 현재 설정·최근 구간만 학습(중복되면 생략)·추세 변화에 민감·최근 변화 속도 유지 최대 네 가지로 비교하고, 계산 근거(측정값 식별, 구간, 예측 설정·시작값, 계산 범위)와 신호 탐색·이상 탐지 링크를 둠. 여유는 학습 기록 길이의 절반 앞까지만 계산. 진동 특징 전망은 저장된 측정·예측·예측 범위·기준을 측정 순서 축의 한 그래프로 보여 주고, 기록되거나 가정한 측정 간격이 있으면 남은 측정 수를 시간으로도 표시. 일반 조회는 요청 시 계산하며 자동 저장하지 않음(`GET /api/v1/outlook`, [ADR-0027](adr/0027-condition-and-remaining-life-outlook-from-stored-analyses.md)). 미래 예측 API와 계산에 사용한 측정 시계열의 내용 기반 `measurement_version`을 비교해 같은 투영의 결과만 함께 표시([ADR-0028](adr/0028-bind-forecast-and-outlook-to-one-measurement-projection.md)) |
| 상태 전망 근거 보존·사람 검토·재관측 비교 | **조건부 지원** | `상태 전망`에서 명시적으로 확정한 전망만 운영 supervisor가 같은 관측·분석 버전과 설정으로 재계산한 뒤 불변 근거로 저장(`outlook-captures.sqlite`). 같은 캡처에 담당자 확인·검토 종료를 기록하며 AnalysisRun finding 검토와 동일한 상태 전이를 공유하되 다른 분석 근거를 빌리지 않음. 저장 당시 계산·관측 범위·설정을 재열람하고 동일 설비·출처·측정점·축·설정의 나중 관측과만 비교. 최근 20건씩 이전 검토 기록 조회, 읽기 전용 열람, 중단 작업공간 백업·복원 지원. **원본 측정 자체의 장기 스냅샷 보존·검토 중 원본 삭제 방지는 제공하지 않음**. 당시 계산·사람 검토는 유지하며 현재 원본의 일치·변경·출처 불일치·조회 불가를 구별. 고장 진단·안전 승인·정비 완료가 아님([ADR-0029](adr/0029-axis-aware-reviewed-outlook-and-reobservation.md)) |
| 상태 전망 AI 브리핑 | **조건부 지원** | 운영 실행 중 Web에서 상태 전망을 근거로 질문(`POST /api/v1/outlook/briefings/request`). 운영 프로세스가 전망을 다시 계산해 화면과 같은 표기의 사실 목록만 설정된 모델(기본 `local-main`)에 보내고, 답의 숫자(사실에 있는 것만)·판정·원인 추정·정비 지시·수명 표현(종료 기준과 함께만)·도달 여부를 대조. 실패하면 한 번 다시 쓰고, 남은 실패 문장은 빼거나 계산된 요약으로 대체. 답은 선택 조건과 측정·분석 근거의 `data_version`별로 `outlook-briefings.sqlite`에 저장. 모델 결과가 없는 설비도 질문 가능. 모델 문장 품질은 검사 범위 안에서만 보장 |
| 미래 예측 | **지원** | 선택 설비의 저장된 측정 이력(한 출처·측정점·해석, 최대 1,000개 시간 구간 평균)이나 분석된 진동 획득 특징(기록된 획득 간격 기준)을 Prophet 1.5로 이어 그려 1시간·24시간·7일·30일 뒤 예측과 80% 범위, 모델이 읽은 흐름을 표시. 예측 기간의 2배 이상·20개 이상 기록일 때만 계산. 하루·일주일 반복 패턴은 기록이 2일·14일 이상일 때만 사용. 관리 기준 입력 시 예상 도달·빠른 도달 시점. 최근 구간(예측 기간 또는 기록의 25%)을 가리고 예측한 평균 오차·범위 적중률을 마지막 값 유지와 비교해 표시. 요청 시 계산하며 저장하지 않음(`GET /api/v1/forecast`). 상태 전망 탭에서 상태·잔여 여유 아래의 그래프로 표시 |
| 미래 예측·상태 전망 확장 | **지원** | 기존 1h/24h/7d/30d 예측을 유지하면서 Prophet 추세 민감도·변화점 범위·최근 학습 수·계절성 사용 여부를 요청 시 조절. 진동 획득은 획득 개수 예측과 원본/가정 획득 간격 구분, 기본 차트의 변화 중심 Y축, 상세 과거 검증(선택적으로 3개 기준 시점), 직전 설정과 예측선 비교를 제공. EDA·모델 없는 이상 탐지에서 선택 신호의 상태 전망으로 연결. 기준까지의 여유는 위 `상태·잔여수명 전망`이 계산. [콘텐츠·설정 계약](product/forecast-flexibility-and-condition-outlook.md) |
| 평소 범위를 벗어난 구간 (모델 없이) | **지원** | 이상 탐지 탭. 저장된 측정 이력이 있는 설비에서 고른 신호(최대 6개, 한 출처·측정점·해석, 최대 1,000개 시간 구간 평균)를 기록의 처음 30%·50%·전체와 비교해 기준 중앙값에서 MAD 기반 변동 폭의 3.5배 이상 벗어난 시점과 이어진 구간을 표시(`GET /api/v1/explore/anomaly`). 구간마다 기준 구간과의 구간 비교로 이동. 학습된 모델이나 고장 판정이 아니며, 기준 구간은 비교의 출발점일 뿐 정상 상태로 검증된 구간이 아님 |
| 기록 시각 기준 Web 이력 조회 | **조건부 지원** | bounded history API의 `anchor=latest`는 선택한 신호의 마지막 저장 관측으로 기간을 정하며 `anchor=now`는 조회 평가 시각을 사용. 실제 event time은 변경하지 않음. 파일의 저장된 상·단위·해석 근거를 표시하고 조회 오류를 빈 상태로 대체하지 않음 |
| 독립 Web UI 화면·접근성 범위 | **조건부 지원** | ko-KR 단일 로컬 Web pilot의 Monitor/Signal 이력, source FILE/제한된 OPC UA 제어, AnalysisRun/Review, System **읽기 근거의 일부**를 실제 브라우저·프로세스 경로로 검증(#453~#483). Web의 `html lang=ko`는 고정되어 있고 전체 `en-US` 리소스/동작, 모든 화면의 keyboard/스크린리더 접근성, Investigation/Maintenance/System 완전 업무 동등성은 **현재 미제공**. Web 기본 선택은 책임자 로컬 파일럿 범위이며 기존 marimo 수용 결과를 Web에 자동 적용하지 않음 |
| Operations Web 업무 화면 (`/web/`) | **조건부 지원** | Svelte·TypeScript 번들이 기본 화면이며 기존 direct-DOM 자산은 제거했습니다. `/web-next/`와 이전 hash 주소·모델 측정 북마크는 같은 origin의 업무 화면으로 이어집니다. 관측 현황·설비별 신호/변화/전망·분석 기록·정비 검토·운영 관리, CSV 업로드/3상 역할·OPC UA 탐색/수집·모델 연결·격리 예시를 기존 supervisor/API 계약으로 제공합니다. 모델 결과는 자동 갱신과 측정 고정, 원본·AI 없는 측정/구간 비교·지점 지정 질문을 지원합니다. 예측 설정·과거 시점 검증·해설/검토는 같은 데이터·설정 근거에 연결됩니다. CSV 응답 유실·리로드, 실제 수집 중단/재연결, supervisor 재시작 후 검토 보존을 Linux Chromium으로 검사합니다. 표준 sdist/wheel 빌드는 잠금된 프런트엔드 빌드가 필수(Node.js >=22.12·npm), 설치된 wheel 실행은 Node 없이 가능합니다. [전환과 검증 범위](product/web-migration.md), [ADR-0030](adr/0030-svelte-typescript-operations-web.md). 자동 회귀는 실제 운영자 사용성·전면 영어/스크린리더·AI 품질·현장 모델 성능 합격을 뜻하지 않습니다 |
| 안내형 제품 체험 | **조건부 지원** | `make showcase`로 현재 Svelte UI의 관측·신호·기준 이탈 분석·기간 비교·추세 예측·조건부 RUL·저장된 검토를 둘러봅니다. 합성 CSV와 실제 앱 결과를 정적 배포물로 제공하며 API 서버가 필요 없습니다. 준비한 전체 조건만 읽고 미제공 조건·쓰기는 거부합니다. 입력 해시·최신 화면 6장·GIF·WebM·재생성/브라우저 검증을 제공합니다. 공개 사이트는 아직 배포하지 않았으며 학습 모델·현장 성능·AI 품질을 증명하는 체험은 아닙니다. [데이터와 검증 범위](product/product-showcase.md) |
| 로컬 Operations 컨테이너 | **조건부 지원** | macOS Docker Desktop의 `make up/status/logs/down`, Linux의 명시적 `make container-up/status/logs/down`으로 Linux supervisor·수집·분석·Web·DuckLake를 실행합니다. 이미지 빌드 때 잠금된 Web·Python 의존성을 포함하며 런타임과 호스트에 Node가 필요 없습니다. localhost 2718/2719만 공개하고 Host/Origin/CSRF·PID/UID broker를 유지합니다. 영속 볼륨의 CSV·분석·검토 보존과 격리 예시를 실제 브라우저로 검사합니다. 호스트 작업공간·모델·외부 OPC UA·AI 서버 연결은 자동 이전/제공하지 않습니다. [실행·보관·검증 범위](architecture/operations-container.md) |
| Local Operations logs | **지원** | `operations logs <root>`가 collection/analysis/ui의 workspace-owned log를 component별 최대 10,000줄 bounded tail로 표시. 내부 log path를 정상 사용자가 직접 지정하지 않음 |
| stopped workspace backup/restore | **지원** | `maintenance backup <workspace> <backup>`이 stopped local node의 durable workspace state/history를 manifest+SHA-256으로 capture. SQLite는 backup API 사용. logs/supervisor identity/locks/rebuildable batch index는 제외. `maintenance restore <backup> <new-root>`는 검증 후 새 root에 atomic restore하며 기존 workspace는 덮어쓰지 않음 |
| deployment preflight / systemd reference | **지원** | `validate deployment <absolute-root>`가 실제 service user 기준 runtime dependency, config/plan, workspace access, supervisor/history lock, UI port를 검증. reference unit은 foreground `operations start`, `Restart=on-failure`, `KillMode=mixed`, bounded restart/stop policy를 사용 |
| installable Operations application | **지원** | 기본 `make up`/`operations up/start`는 wheel 내 **supervised Web**를 실행하며 `operations` extra는 history/OPC UA·예측(Prophet)·LSTM 실행(torch CPU) 런타임을 포함. 운영용 marimo·anywidget 및 `--ui marimo` 실행은 제거. 연구용 marimo/Matplotlib과 Analysis Explorer는 `notebooks/`·`research` group에서 별도로 관리·설치. Web는 loopback `127.0.0.1` 로컬 단일 사용자 파일럿이며 원격 인증/TLS·다중 사용자 운영은 미지원 |
| operational CLI taxonomy | **지원** | normal node lifecycle=`operations`, recovery/history=`maintenance`, deployment gates=`validate`, service/source plumbing=`internal`. 이동 전 `operations` spelling은 더 이상 rewrite하지 않음 |
| local multi-process coordination | **조건부 지원** | SQLite WAL과 local file lock 기반. 같은 state/catalog에 대한 협조 프로세스 전제 |
| HA / distributed coordination / leader election | **미제공** | local-first runtime 경계 |
| OPC UA username/password/certificate/security-policy configuration | **미제공** | 현재 connector는 anonymous local/dev 경계를 사용 |
| MQTT connector | **미제공** | 현재 operational protocol slice는 FILE과 OPC UA |

지원 여부를 새 문서에 추가하기 전에 production code, contract test 또는 subsystem 실행 경로가 실제로
존재하는지 확인합니다. 계획만 있는 항목은 이 표에 “예정”으로 넣지 않고 Issue/PR에서 관리합니다.
