# Research Result Artifacts

이 디렉터리는 versioned research/evaluation evidence를 보관합니다.

연구 평가 결과는 운영 Web에서 보여주지 않습니다. 이 디렉터리의 JSON과 기존
[Analysis Explorer](../../../apps/README.md#다른-저장-결과-열기)로 확인합니다. 원본 데이터는 별도로 준비해야 하며,
결과 파일만으로 실험 재실행 가능성을 보장하지 않습니다.

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


AI-Hub 전기 다변량 후보의 [평가 v2](aihub-239-electrical-anomaly-evaluation-v2.json)는 **FAIL**입니다.
설비·유형별 주입 사례와 학습 불가/위치 부족도 보존하며, 원본을 바꾸지 않은 경보 비율은 실제 이상이
섞일 수 있어 오경보율로 부르지 않습니다. 기능 재생 검증을 모델 성능 합격으로 승격하지 않습니다.
