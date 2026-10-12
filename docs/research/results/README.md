# Research Result Artifacts

이 디렉터리는 versioned research/evaluation evidence를 보관합니다.

Operations Web의 **기존 연구 결과**에서 이 디렉터리의 결과 목록을 찾고, 지원되는 schema의
평가·출처·적용 범위를 읽을 수 있습니다. 원본 데이터 없이 저장 결과를 조회하는 경로이며
현재 작업공간의 관측·AnalysisRun·사람 검토 기록에 합산하지 않습니다.
원본 데이터는 별도로 준비해야 하고, 결과 조회만으로 실험 재실행 가능성을 보장하지 않습니다.
상세 탐색은 기존 [Analysis Explorer](../../../apps/README.md#다른-저장-결과-열기)를 사용합니다.

Web에 포함되는 `src/industrial_phm/apps/web/research-results.json`은 canonical JSON에서
기존 experiment inspector로 생성한 읽기 전용 요약입니다. 직접 수정하지 않습니다.
결과를 변경하거나 추가하면 다음 명령으로 갱신합니다. 지원하지 않는 inspector schema는
원본 파일 진입점만 제공하고 평가 수치를 만들어내지 않습니다.

```bash
uv run --no-sync python -m tools.research_catalog
uv run --no-sync python -m tools.research_catalog --check
```

`tests/contract/test_research_web_catalog.py`가 원본 해시와 요약의 일치를 검증합니다.
wheel에도 이 요약이 포함되며, canonical JSON과 대형 raw prediction을 복제하지 않습니다.

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
