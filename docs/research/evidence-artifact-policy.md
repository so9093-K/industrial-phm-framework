# Evidence Artifact Storage and Review Policy

상태: P2 evidence-operations policy

이 문서는 numerical evidence artifact가 커질수록 Git diff 자체가 리뷰 인터페이스가 되기 어려운 문제를 다룹니다.
목표는 canonical machine evidence를 버리지 않으면서, 사람이 검토하는 경로를 deterministic summary/report와
명확히 분리하는 것입니다.

## 1. Artifact roles

### Canonical machine evidence

Numerical source of truth입니다.

- versioned schema ID
- exact code revision/protocol/configuration provenance
- evaluation population과 capability boundary
- 필요한 경우 prediction-level observations
- deterministic serialization
- 기존 artifact를 결과에 맞춰 조용히 덮어쓰지 않음

UI, GenAI, report는 canonical artifact를 다시 계산하지 않고 validated read model을 통해 소비합니다.

### Human-review representation

Canonical evidence를 사람이 빠르게 검토하기 위한 representation입니다.

예:

- `industrial-phm experiment inspect`
- `industrial-phm analysis report`
- PR description의 bounded metric table
- deterministic Markdown/text summary

이 representation은 canonical numerical source of truth가 아닙니다. Summary와 canonical artifact가 충돌하면
artifact/schema validation이 우선하며 summary를 수정합니다.

## 2. Repository storage policy

현재 repository에는 prediction-level JSON이 이미 MB 단위로 존재합니다. 따라서 다음 정책을 적용합니다.

| Serialized artifact size | 기본 정책 |
| --- | --- |
| < 1 MiB | deterministic하고 review value가 있으면 Git tracking 허용 |
| 1–5 MiB | canonical evidence로 필요할 때 Git tracking 허용. PR에는 반드시 deterministic human-review summary와 checksum을 함께 기록 |
| > 5 MiB | Git tracking을 기본값으로 하지 않음. 별도 artifact storage/LFS 계층 필요성을 먼저 검토하고 repository에는 manifest/checksum/summary를 남기는 방향을 우선 |
| 반복적으로 수십 MiB 이상 | DVC/MLflow/object storage 등 전용 evidence storage를 별도 ADR로 결정하기 전에는 확장하지 않음 |

크기 기준은 architecture trigger이지 자동 삭제 규칙이 아닙니다. 규제/감사/재현성 때문에 canonical payload 자체를
Git에 둘 이유가 있으면 PR에서 명시적으로 근거를 남깁니다.

## 3. Large artifact PR requirements

1 MiB 이상의 canonical result를 추가하거나 교체하는 PR은 최소 다음을 기록합니다.

- schema ID
- evidence class
- execution code revision
- source scope / excluded scope
- deterministic rerun 여부
- SHA-256
- serialized byte size
- 주요 aggregate metric
- per-asset 또는 per-stratum bounded summary
- capability available / unsupported boundary
- artifact가 development / benchmark / external / field 중 어떤 evidence인지
- 결과를 본 뒤 protocol/configuration을 변경했는지 여부

Prediction-level JSON 전체를 PR description에 복사하지 않습니다.

## 4. Deterministic review path

리뷰어는 다음 순서를 기본으로 사용합니다.

```text
canonical artifact
  -> schema validation / ExperimentInspection
  -> deterministic bounded summary/report
  -> 필요할 때만 raw prediction-level payload drill-down
```

Review summary는 timestamp, random ordering, environment-dependent absolute path 등 입력 evidence와 무관한
비결정적 값을 넣지 않습니다.

## 5. Checksums

Clean execution에서 생성한 authoritative numerical artifact에는 PR evidence note에서 SHA-256을 기록합니다.
동일 revision/configuration에서 reproducibility를 주장하는 경우 최소 두 독립 실행 output이 byte-identical인지
확인하고 checksum을 비교합니다.

Artifact 내부에 self-checksum을 넣어 serialization을 순환 의존시키지는 않습니다. Checksum은 execution/review
metadata가 소유합니다.

## 6. Prediction-level retention

Prediction-level rows는 다음 중 하나를 만족할 때 canonical artifact에 유지할 수 있습니다.

- read model/UI가 recorded prediction identity를 그대로 제시해야 함
- evaluation 재검증에 source-aligned prediction이 필요함
- clipping/negative prediction 같은 중요한 semantic evidence가 row-level에서만 확인됨
- future audit에서 aggregate metric의 provenance 확인이 필요함

반대로 aggregate 결과와 동일 정보를 중복하는 대규모 intermediate array는 canonical result에 넣지 않습니다.

## 7. Source data와 evidence 구분

Raw/manual dataset은 이 repository에 재배포하지 않습니다. Evidence artifact는 source data 자체가 아니라 project가
생성한 result이며, dataset license/provenance 경계를 계속 따릅니다.

현재 artifact provenance가 exact local source byte hash를 항상 기록하는 것은 아닙니다. 따라서
`verified_source_acquisition_count`와 dataset/split scope가 같다는 이유만으로 동일 source bytes라고 주장하지
않습니다.

## 8. Schema/read-model maintainability decision

현재 `result_inspection.py`는 여러 result schema를 하나의 public inspection entry point로 지원합니다. P2에서
재측정한 결과 schema-specific inspector와 parsing/validation helper가 충분히 커졌지만, 공통 numerical
`PHMResult`를 도입할 근거는 없습니다.

따라서 현재 결정은 다음과 같습니다.

- public `inspect_experiment_result(path)` entry point는 유지
- schema-specific parsing/validation semantics는 각 schema가 계속 소유
- 공통화는 mapping/text/number/revision validation과 capability/provenance stage 같은 실제 반복에 한정
- 새로운 universal result object, registry framework, plugin system은 만들지 않음
- 파일 크기/변경 충돌이 계속 증가하면 다음 refactor는 **schema-specific inspector module 분리**이지 semantic
  unification이 아님

즉 P2의 목표는 abstraction 수를 늘리는 것이 아니라 canonical evidence와 presentation/read-model 책임을 더
명확하게 만드는 것입니다.

## 9. Current application of this policy

현재 대형 canonical evidence 예시는 XJTU LSTM development result, XJTU three-model RUL validation result,
MIMII external score result입니다. 이들은 prediction/score-level identity를 보존하기 때문에 canonical payload를
유지하되, 일상 리뷰는 inspection/report와 PR summary를 사용합니다.

향후 RUL held-out benchmark numerical artifact도 같은 정책을 적용합니다.
