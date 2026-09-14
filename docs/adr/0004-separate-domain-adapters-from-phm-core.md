# ADR-0004: Domain Adapter와 공통 PHM 책임 분리

- Status: Accepted
- Date: 2026-09-14

## Context

프로젝트는 여러 산업 설비 데이터로 확장할 수 있어야 하지만 하나의 범용 모델이 모든 설비를 처리한다고
가정하지 않습니다. 재사용해야 할 것은 데이터 계약, 평가 및 파이프라인 경계이며 모델은 도메인과 task에
따라 달라질 수 있습니다.

## Decision

데이터셋/설비별 parsing과 의미 변환은 `industrial_phm.adapters` 경계에 둡니다. Adapter는 공통 계약을
생산하고 downstream PHM component는 원천 데이터셋 이름이나 파일 구조를 알지 못합니다.

초기에는 adapter를 동일 package 안에 둡니다. 외부 plugin package와 entry-point discovery는 실제로
독립 배포 요구가 발생한 경우에만 도입합니다.

## Alternatives Considered

- 모델별로 직접 dataset loader 구현: 초기 구현은 빠르지만 loader/model/evaluation 결합도가 커집니다.
- 처음부터 plugin architecture: 확장성은 높지만 아직 검증되지 않은 extension point에 복잡성을 부과합니다.

## Consequences

- 두 번째 도메인 통합 시 core 수정량이 architecture 검증 지표 중 하나가 됩니다.
- 공통 계약으로 표현할 수 없는 도메인 의미가 발견되면 contract를 명시적으로 발전시켜야 합니다.
