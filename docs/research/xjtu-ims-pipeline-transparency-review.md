# XJTU / IMS Developer Pipeline Transparency Review

상태: XJTU finalized fold-1 holdout와 IMS fixed cross-test evidence 검토 및 inspection 구현 완료

이 문서는 두 numerical experiment의 성능을 합산하거나 순위를 비교하지 않습니다. 목적은 이미 실행된 두 경로를
같은 developer pipeline stage로 읽었을 때 공통 contract와 dataset-specific 의미가 명확하게 구분되는지 확인하고,
schema별 inspection UX가 제공해야 할 정보를 식별하고 구현 경계를 고정하는 것입니다.

검토한 authoritative result는 다음과 같습니다.

- [XJTU fold-1 one-shot holdout](results/xjtu-sy-iforest-fold-1-holdout-v1.json)
- [IMS Set 2 → Set 3 one-time cross-test](results/ims-bearings-iforest-single-channel-cross-test-v1.json)

XJTU cross-fold robustness result는 finalized configuration의 post-holdout 분석이며 이 일대일 비교의 evaluation
scope에는 포함하지 않습니다. 각 result의 numerical interpretation은 dataset별 protocol이 계속 소유합니다.

## Pipeline lineage comparison

| Pipeline stage | XJTU-SY finalized fold-1 | IMS single-channel cross-test | 공통 계약 | Dataset-specific 의미 |
| --- | --- | --- | --- | --- |
| Source | 수동 준비한 complete XJTU-SY profile, 15 bearing run / 9,216 acquisitions | 검증된 IMS profile, Set 2 complete archive와 Set 3 README-documented scope | source validation과 provenance | source layout, authenticity/checksum 수준, 포함·제외 scope |
| Experiment split | fold-1 train 9 / holdout test 3 bearing runs | Set 2 전체 train / Set 3 README scope evaluation | versioned `split_id`, partition isolation | bearing-run rotating holdout와 test-level cross-test |
| Canonicalization | acquisition CSV 하나를 bearing 하나의 H/V 2-channel series로 변환 | acquisition file 하나를 bearing별 `vibration` single-channel series 4개로 변환 | `CanonicalTimeSeries`, asset/acquisition identity | channel schema와 source acquisition → canonical observation cardinality |
| Feature | `vibration-statistical-v1`, H/V에서 16 features | 같은 formula, single channel에서 8 features | stateless feature formula와 ordered schema | channel-derived feature names와 width |
| Preprocessing | complete train 3,246 observations에서 identity state fit | complete Set 2 3,936 observations에서 identity state fit | train-fitted `PreprocessingState` | fit population과 partition semantics |
| Reference | train bearing별 retrospective early third, 1,084 observations | complete Set 2 all-train, 3,936 observations | reference provenance와 eligibility count | lifecycle-aware early-third와 complete-distribution rarity reference |
| Sampling | acquisition-uniform, reference 1,084 → fit 1,084 | acquisition-uniform, reference 3,936 → fit 3,936 | `ModelFitInput` population counts | reference selection이 만든 실제 fit population |
| Model fit | Isolation Forest, 16 inputs, seed 42 | Isolation Forest, 8 inputs, seed 42 | model family, parameter validation, deterministic seed | input width |
| Scoring | unseen holdout bearing 3개, 3,152 observations | Set 3 bearing 4개, 17,792 observations | `ModelScoringInput`, `AnomalyScores`, higher-is-more-anomalous | holdout bearing lifecycle과 shared test-stage scope |
| Evaluation | bearing별 acquisition-order Spearman ρ와 lifecycle late-vs-middle rank probability, 3-bearing equal mean | bearing별 같은 rank math를 test-stage thirds에 적용, 4-bearing equal mean | Spearman과 rank-probability 계산 | lifecycle-third와 shared test-stage-third의 해석 |
| Result | `xjtu-fold-1-holdout-result-v1` | `ims-single-channel-cross-test-result-v1` | identity, population, evaluation, code/config provenance concepts | schema layout과 interpretation |
| Capability | anomaly scoring과 descriptive temporal evidence | anomaly scoring과 descriptive temporal evidence | 수치 score와 capability boundary | unsupported capability를 artifact에 노출하는 정도 |

이 비교에서 재사용이 실제로 확인된 범위는 canonical time series, feature formula, train-only preprocessing,
model-fit/scoring input, Isolation Forest, anomaly-score 방향과 rank statistic 계산입니다. Split, reference,
evaluation scope와 result interpretation은 서로 다른 source 의미를 보존하므로 dataset-specific boundary에 남아야
합니다.

## Population flow

```text
XJTU
  source train acquisitions       3,246
    -> preprocessing fit          3,246
    -> reference eligible         1,084
    -> model fit                  1,084

  holdout source observations     3,152
    -> model scoring              3,152

IMS
  Set 2 source files                984
    -> bearing observations       3,936
    -> preprocessing fit          3,936
    -> reference eligible         3,936
    -> model fit                  3,936

  Set 3 source files              4,448
    -> bearing observations      17,792
    -> model scoring             17,792
```

IMS의 `984 → 3,936`, `4,448 → 17,792` 변환은 한 source file의 네 bearing channel을 bearing별 canonical
observation으로 분리한 결과입니다. 단순 count만 나열하면 데이터 누락이나 중복처럼 보일 수 있으므로 inspection
UX는 source unit과 canonical/model observation unit을 함께 표시해야 합니다.

## 현재 artifact만으로 확인하기 어려운 정보

두 result JSON과 연결된 config/protocol을 대조하면 다음 비대칭이 확인됩니다.

| 정보 | XJTU holdout result | IMS cross-test result | Inspection 요구 |
| --- | --- | --- | --- |
| Exact feature names/count | result에 없음, finalized config 조회 필요 | result에 포함 | effective schema를 config/result에서 해석해 동일 형식으로 표시 |
| Model parameters와 score 방향 | result에 없음, config/model contract 조회 필요 | result에 포함 | effective model configuration과 score semantics 표시 |
| Source inclusion/exclusion | source total과 holdout bearing은 있음 | train/evaluation/excluded scope가 구조화됨 | selected scope와 excluded scope 표시 |
| Scoring population total | bearing count를 합산해야 함 | 명시적 population flow에 포함 | source/reference/fit/scoring count를 한 흐름으로 표시 |
| Canonical channel/cardinality | 두 result 모두 직접 설명하지 않음 | 두 result 모두 직접 설명하지 않음 | source unit → canonical observation 변환과 channel schema 표시 |
| Capability scope | interpretation 문장에서 추론해야 함 | available/unsupported 목록이 구조화됨 | available, unsupported, consumed를 명시적으로 표시 |
| One-time scope 상태 | protocol을 읽어야 `consumed` 의미 확인 가능 | artifact에 one-time 의미가 있으나 상태 vocabulary는 없음 | evaluation scope를 `consumed`로 표시 |
| Code revision assurance | 선언된 revision만 기록 | 선언된 revision만 기록 | 우선 `declared code revision`으로 표시하고 checkout 대조 여부를 별도 상태로 구분 |

Artifact만 단독으로 읽으면 IMS의 canonicalization cardinality와 channel lineage, XJTU의 effective config와
capability를 확인하기 어렵습니다. `experiment inspect`가 result와 packaged Source of Truth를 조합해 이 정보를
같은 stage 순서로 표시합니다.

이 결론은 기존 authoritative evidence artifact를 새 schema로 다시 쓰라는 의미가 아닙니다. 이미 기록된 result는
당시 실행의 authoritative evidence로 유지하고, inspection layer가 result schema와 packaged config/contract에서
필요한 사실을 읽어 같은 표시 순서로 조합하는 편이 provenance를 보존합니다.

## 구현된 inspection UX

`industrial-phm experiment inspect <result.json>`은 다음 read-only summary 계약을 구현합니다.

1. `xjtu-fold-1-holdout-result-v1`, `ims-single-channel-cross-test-result-v1`과
   `xjtu-lstm-development-result-v1`을 각각 명시적으로 식별합니다.
2. schema별 reader가 기존 result와 packaged config를 검증하고 immutable `ExperimentInspection` read model을
   생성합니다.
3. 출력 순서는 `Source → Canonical → Feature → Preprocessing → Reference → Sequence Construction → Population →
   Model → Scoring → Evaluation → Capability → Provenance`로 고정합니다.
4. Acquisition-level model의 Sequence Construction은 `not applicable`로 표시하고 LSTM은 실제 acquisition→window
   population 전환을 표시합니다.
5. source acquisition, canonical/model observation과 sequence window 단위를 분리해 표시합니다.
6. XJTU와 IMS numerical metric을 하나의 성능값으로 합산하거나 공통 pass/fail 판정으로 바꾸지 않습니다.
7. holdout/cross-test scope는 `consumed`, 지원하지 않는 PHM 기능은 `unsupported`로 표시합니다.
8. artifact의 code revision은 선언 provenance로 표시하고, 실행 checkout과 자동 대조한 기록이 없으면 attested로
   표현하지 않습니다.

세 schema는 각각 작은 reader가 소유하며 text rendering은 read model과 분리합니다. 기존 version-controlled result
artifact는 authoritative evidence로 유지합니다. Reader가 공유하는 stage vocabulary보다 result JSON layout을
일찍 통합하지 않습니다.

```bash
uv run industrial-phm experiment inspect \
  docs/research/results/xjtu-sy-iforest-fold-1-holdout-v1.json

uv run industrial-phm experiment inspect \
  docs/research/results/ims-bearings-iforest-single-channel-cross-test-v1.json

uv run industrial-phm experiment inspect \
  docs/research/results/xjtu-sy-lstm-autoencoder-fold-1-development-v1.json
```

## LSTM Autoencoder cross-schema 확인

LSTM result reader는 `Preprocessing`과 `Model Fit` 사이의 `Sequence Construction`에서 input acquisition 수, window
length/stride, asset·partition boundary, generated window 수, dropped prefix와 window-to-acquisition lineage를
표시합니다. XJTU/IMS Isolation Forest reader는 같은 stage를 생략하지 않고 acquisition-level feature observation을
직접 소비한다는 이유와 함께 `not applicable`로 표시합니다.

Developer Workbench는 세 schema의 Overview와 Lineage를 이 공통 stage 순서로 표시합니다. Detailed Evidence는 XJTU
LSTM artifact가 보존한 acquisition-aligned trajectory와 feature residual에만 `available`이며, 해당 raw evidence를
기록하지 않은 Isolation Forest result에서는 `not recorded`입니다. 이 차이는 model capability나 result JSON layout을
하나로 합치는 근거가 아닙니다. LSTM의 구체적인 scope와 sequence population은
[`xjtu-lstm-autoencoder-protocol.md`](xjtu-lstm-autoencoder-protocol.md)가 소유합니다.

## 최소 승격 범위 검토

XJTU Isolation Forest holdout, IMS Isolation Forest cross-test, XJTU LSTM development 세 result reader가 같은
`ExperimentInspection` stage vocabulary를 실제로 사용하게 된 시점에, 반복되는 책임 중 무엇을 공통 contract로
올릴지 검토했습니다.

### 비교

| 책임 | XJTU IF | IMS IF | XJTU LSTM | 판단 |
| --- | --- | --- | --- | --- |
| 12-stage 순서 | 같음 | 같음 | 같음 | 이미 `ExperimentInspection`이 소유 |
| Provenance stage 구성 | 같음 | 같음 | 같음 + `Evidence class` | module 내부 helper로 추출 |
| Capability stage 구성 | 같음 | 같음 | 같음 | module 내부 helper로 추출 |
| `capability_scope` 검증 | artifact에 없음, 상수 사용 | 같음 | 같음 (available 기대값만 다름) | module 내부 helper로 추출 |
| Sequence Construction | `not applicable` | `not applicable` | window 실제 evidence | 기존 helper 유지 |
| Source / Canonical cardinality | acquisition → bearing | acquisition → bearing 4 | acquisition → bearing | schema별 유지 |
| Reference 의미 | early third | all train | early third | schema별 유지 |
| Evaluation segmentation | lifecycle third | test stage | lifecycle third + residual | schema별 유지 |
| Scoring 의미 | IF anomaly score | IF anomaly score | reconstruction error | schema별 유지 |
| 저장 JSON shape | 고유 | 고유 | 고유 | 통합하지 않음 |

### 결정

- **새 public type을 만들지 않습니다.** 공개 contract는 계속 `ExperimentInspection` / `InspectionStage` /
  `InspectionFact` 세 read model입니다. 세 reader에서 반복된 것은 presentation 단계의 stage 구성과
  capability 검증이며, 저장 schema가 같다는 근거는 아닙니다.
- **실제로 세 번 반복된 코드만 같은 module의 private helper로 옮겼습니다.** Provenance stage, Capability
  stage, `capability_scope` 검증입니다. 세 committed artifact의 rendered inspection text가 변경 전과
  바이트 단위로 같음을 확인했습니다.
- **Result JSON serialization은 통합하지 않습니다.** 각 schema reader가 자기 schema를 검증하고 공통 read
  model만 생성합니다.
- **Stage status는 계속 문서화된 vocabulary로 둡니다.** [`../product/overview.md`](../product/overview.md)가
  pipeline stage 상태, evidence availability, capability를 별개 vocabulary로 소유합니다. 이를 enum 같은 typed
  public contract로 올리는 것은 네 번째 result schema가 같은 vocabulary를 필요로 하는지 확인한 뒤 판단합니다.
- **Operational inference output과 experiment evidence는 분리합니다.** `ExperimentInspection`은 이미 기록된
  experiment evidence를 읽는 read model이며 inference 결과 contract가 아닙니다.

`GenericPipeline`, universal result schema, `PHMResult`, model registry는 이 검토 범위에서 근거가 확인되지
않아 계속 보류합니다.

### 재검토 조건 갱신 (2026-09-21)

MIMII development, MIMII external, XJTU RUL three-model reader가 추가되어 현재 지원 schema는 여섯 개입니다.
RUL reader는 anomaly 계열과 달리 target definition, 세 method 비교, common support 같은 prognostics 고유
의미를 담지만 같은 12-stage vocabulary와 `ExperimentInspection`만으로 표현됐고 새 public type이 필요하지
않았습니다. 따라서 stage status를 typed contract로 올리는 판단은 계속 보류하고, 여섯 reader의 반복 책임
재측정은 별도 작업으로 둡니다.
