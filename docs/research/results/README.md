# Research Result Artifacts

이 디렉터리는 versioned research/evaluation evidence를 보관합니다.

Raw dataset 저장소가 아니며, 각 JSON은 schema/provenance/capability boundary가 검증된 canonical machine
evidence입니다. 큰 prediction-level artifact는 Git diff 전체를 사람용 리뷰 인터페이스로 사용하지 않습니다.

리뷰 순서:

```text
canonical JSON
  -> industrial-phm experiment inspect <artifact>
  -> 필요하면 industrial-phm analysis report ...
  -> raw prediction/score rows drill-down
```

1 MiB 이상 artifact를 추가하는 PR은 serialized size, SHA-256, deterministic rerun 여부, aggregate/per-asset
summary와 capability boundary를 PR evidence note에 기록합니다.

상세 정책: [Evidence Artifact Storage and Review Policy](../evidence-artifact-policy.md)
