# 0025. Run versioned PHM model packages over ordered per-asset analysis steps

Status: Accepted

## Context

수집·저장 경로(OPC UA/FILE → spool → DuckLake Asset History → finalized window)는 restart-safe하게
동작하지만, 저장된 관측이 PHM 모델의 반복 추론으로 이어지지 않습니다.

- Live window runner는 3상 불평형 capability 하나로 고정되어 있습니다. 결과는 window 하나만으로
  계산되며, window 사이에 이어지는 분석 상태가 없습니다(`docs/status.md`의 carry-in 미제공).
- 연구 모델(Isolation Forest, Ridge RUL, LSTM)은 실험 실행 중에만 메모리에 존재합니다. 학습된 모델과
  전처리 상태를 저장·재적재하는 형식이 없어서 운영 경로가 같은 모델을 다시 쓸 수 없습니다.
- 이상 구간(연속된 점수의 연결), RUL 시퀀스 입력(과거 획득 버퍼), 추정 궤적은 모두 **설비별 상태가 단계를
  넘어 이어져야** 계산됩니다.
- 고주파 진동 파형(XJTU-SY: 획득당 32,768 × 2 samples)은 스칼라 관측 행을 저장하는 Asset History나
  OPC UA DataChange window에 맞지 않습니다.
- 연구 결과 뷰(`AnalysisView`)는 dataset/split/fold를 필수로 갖는 retrospective evidence 표현이라 운영 결과
  계약으로 쓸 수 없습니다.

## Decision

### 1. Model package

학습이 끝난 모델은 **불변·데이터 전용 model package**로 저장합니다.

- 위치: `<workspace>/models/<package_id>/`. `package.json` manifest와 payload 파일(`*.json`, `*.npz`,
  `*.pt`)로 구성합니다.
- Manifest는 다음을 소유합니다: recipe ID(연구 manifest의 experiment ID 또는 운영 recipe ID), task
  (`anomaly-score` / `rul-estimate`), **입력 규격**(step 종류, 채널 이름·순서, 샘플링, feature set ID와
  feature 이름), 상태 규격(시퀀스 길이 등), **출력 규격**(점수 방향·임계값, RUL 단위·종료점 의미), 학습
  범위(dataset, 학습 asset·기간, partition), 검증 근거(연구 결과 artifact와 SHA-256, asset별 오차), 적용
  범위(학습 운전 조건), runtime 버전, payload SHA-256, **probe**(고정 입력과 기대 출력).
- `package_id = <recipe_id>-<manifest canonical JSON SHA-256 앞 12자>`입니다. 내용이 바뀌면 다른 패키지입니다.
- 적재 시 payload SHA-256을 확인하고 probe 입력을 다시 추론해 기대 출력과 비교합니다. 다르면 적재하지 않습니다
  (fail closed). 따라서 "재시작 후 같은 입력이면 같은 추론"이 적재할 때마다 검증됩니다.
- pickle을 쓰지 않습니다. 배열은 `numpy.load(allow_pickle=False)`, torch 가중치는 `weights_only=True`로만
  읽습니다. 선형 모델·스케일러·PCA는 계수 배열로 복원합니다. scikit-learn Isolation Forest는 공개된 계수 형식이
  없으므로 **저장한 fit 행과 seed로 결정적으로 다시 fit**한 뒤 probe로 동일성을 확인합니다. runtime 버전이 달라
  probe가 맞지 않으면 패키지는 적재되지 않고 그 이유가 skip으로 남습니다.
- 패키지 생성은 명시적 개발자/운영자 행위입니다(`industrial-phm model build ...`). 운영 runtime이 자동으로
  재학습하지 않습니다.

### 2. Ordered analysis steps

분석은 **(source, asset)별로 순서가 있는 step**을 소비합니다. step 종류는 두 가지입니다.

| step | authoritative input | 순서 키 | 시간 |
| --- | --- | --- | --- |
| observation window | ADR-0008의 finalized window accepted events | `(window_end, window_id)` | window의 event 시각 구간 |
| acquisition snapshot | 원본 파형 파일 참조 + SHA-256 + 채널·샘플링·획득 순번 | 획득 순번 | source가 제공한 경우에만 event 시각, 없으면 순번과 선언된 획득 주기 |

Acquisition snapshot은 raw waveform을 Asset History 행으로 펼치지 않습니다. 원본 파일은 해시로 고정한 file
evidence이고, 획득별 특징은 분석 입력 projection(ADR-0007)이므로 분석 결과에 기록합니다. 원본에 없는 절대 시각을
만들지 않습니다.

기록 데이터 재생으로 공급된 step은 재생임을 step 자체에 기록하고 결과와 화면까지 전달합니다.

### 3. Explicit binding

어떤 패키지를 어떤 설비에 실행할지는 **명시적 binding**(binding ID, package ID, source ID, asset ID)으로 정합니다.
채널 이름·데이터셋 이름으로 모델을 추측해 연결하지 않습니다. binding 생성 시와 매 step마다 입력 규격 적합성을
검사하고, 맞지 않으면 구체적인 이유와 함께 skip으로 기록합니다.

### 4. One transaction per step

binding별 PHM 분석 상태는 하나의 SQLite 저장소(`<workspace>/phm-analysis.sqlite`)가 소유합니다. step 하나의
처리는 한 트랜잭션에서 다음을 함께 커밋합니다.

- step 결과(분석) 또는 skip과 이유
- binding 상태(시퀀스 버퍼, 진행 중인 검토 구간, 연속 초과 횟수)
- 검토 구간 행의 생성·확장·종료
- binding cursor
- 변경 순번(change sequence)

(binding ID, step key)는 유일합니다. 재시작 후 같은 step을 다시 처리해도 결과가 중복되지 않고, 상태는 마지막
커밋된 step 뒤에서 이어집니다. 상태가 있는 분석은 순서를 바꿔 처리하지 않습니다. 이미 지난 순번의 step이
늦게 도착하면 결과를 바꾸지 않고 `late-step` skip으로 남깁니다.

### 5. Task-specific results

| task | step 결과 | 구간·궤적 |
| --- | --- | --- |
| anomaly-score | 점수, 패키지 임계값, 초과 여부, 모델이 제공하는 경우에만 feature별 기여 | 검토 구간: 시작·끝 step, 시각, 최대 점수, step 수, open/closed |
| rul-estimate | 추정값, 단위, 종료점 의미, 적용 범위 안/밖 | 추정 궤적 = step 결과의 순서열, 이전 추정과의 차이 |

모든 결과는 analysis run ID, step 입력 참조(window ID 또는 snapshot SHA-256), package ID, event 시각(있을 때),
처리 시각, 재생 여부를 가집니다. 모델이 변수별 근거를 제공하지 않으면 화면이 기여도를 만들지 않습니다.

### 6. Read API and refresh

PHM 화면 API는 `phm-analysis.sqlite`를 직접 읽고, 응답마다 최신 step의 event 시각·처리 시각과 change sequence를
반환합니다. Web은 `since=<change sequence>` 변경분 조회(polling)로 갱신합니다. Push 전송(SSE 등)은 이 계약 위에
나중에 추가할 수 있습니다. 변경분은 commit sequence 순으로 최대 5,000개씩 반환하며, 응답의
`change_seq`는 반환한 마지막 결과까지만 전진합니다. `has_more`이면 이어서 조회하고, 이력 크기나 늦은
step의 position 때문에 아직 읽지 않은 결과를 건너뛰지 않습니다.

### 7. Runner ownership

기존 analysis runner process가 binding loop를 함께 실행합니다. binding 하나의 실패(패키지 적재 실패, 입력
부적합)는 그 binding의 skip/오류로 남고 다른 binding과 3상 불평형 처리를 막지 않습니다.

## Consequences

- 연구 결과를 운영 기능으로 쓰려면 패키지를 만들고 binding을 명시해야 합니다. 검증 범위·오차·적용 범위가
  패키지와 함께 이동하므로 "research only" 경계를 넘을 때도 근거가 사라지지 않습니다.
- Isolation Forest 패키지는 fit 행을 포함하므로 학습 데이터 일부(특징 벡터)가 workspace에 남습니다. 원본
  파형·관측값은 포함하지 않습니다.
- runtime 버전이 바뀌면 probe 불일치로 패키지가 적재되지 않을 수 있습니다. 조용히 다른 모델로 계속 추론하는 것보다
  멈추고 이유를 표시하는 쪽을 택합니다.
- `phm-analysis.sqlite`는 workspace state이므로 backup/restore 단위에 포함합니다. 보존 기간 정책은 별도
  결정입니다.
- 3상 불평형은 기존 저장소와 계약을 유지합니다. window 하나로 계산되는 상태 없는 capability이기 때문입니다.
