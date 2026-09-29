# Architecture Decision Records

ADR은 장기적으로 코드 구조, 호환성 또는 운영 방식에 영향을 주는 결정을 기록합니다.
단순 구현 세부사항이나 일시적인 작업 계획은 ADR 대상이 아닙니다.

## Status

- `Proposed`: 논의 중
- `Accepted`: 현재 유효한 결정
- `Deprecated`: 더 이상 권장하지 않지만 대체 결정이 명확하지 않음
- `Superseded`: 후속 ADR에 의해 대체됨

Accepted ADR의 과거 내용을 현재 설계에 맞추기 위해 다시 쓰지 않습니다. 결정이 바뀌면 새로운 ADR을
작성하고 `Superseded by ADR-XXXX` 관계를 남깁니다.

## Index

- [ADR-0001: Use src layout](0001-use-src-layout.md)
- [ADR-0002: Use uv for project management](0002-use-uv-for-project-management.md)
- [ADR-0003: Define canonical time-series contract](0003-define-canonical-timeseries-contract.md)
- [ADR-0004: Separate domain adapters from PHM core](0004-separate-domain-adapters-from-phm-core.md)
- [ADR-0005: Allow implicit time for regularly sampled signals](0005-allow-implicit-regular-sample-time.md)
- [ADR-0006: Use PyTorch for the CPU reference deep-learning runtime](0006-use-pytorch-cpu-reference-runtime.md)
- [ADR-0007: Preserve raw measurements before analysis projection](0007-preserve-raw-measurements-before-analysis-projection.md)
