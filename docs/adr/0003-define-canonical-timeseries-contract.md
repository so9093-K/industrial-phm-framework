# ADR-0003: Domain-neutral canonical time-series contract 정의

- Status: Accepted
- Date: 2026-09-14

## Context

산업 설비 데이터는 센서 채널, sampling rate, label, degradation target과 파일 구조가 서로 다릅니다.
공통 PHM 코드가 원천 형식을 직접 해석하면 데이터셋이 추가될 때 조건 분기가 누적됩니다.

## Decision

Domain Adapter와 공통 PHM 계층 사이에 `CanonicalTimeSeries` 계약을 둡니다. 초기 계약은 자산 ID,
timestamp, channel, value, optional sampling rate, optional label/RUL 및 domain-neutral metadata를 표현합니다.

이 ADR이 고정하는 핵심 결정은 **dataset/source-specific representation과 공통 PHM core 사이에 명시적인 canonical
boundary를 둔다는 것**입니다. Pre-1.0 단계의 현재 field set 자체를 모든 산업 데이터에 대한 영구 universal schema로
고정하지 않습니다. 두 번째 dataset과 실제 field-data integration에서 의미 손실이나 반복 조건 분기가 확인될 때
공통으로 필요한 의미만 evidence에 따라 정제합니다. 현재 assumptions와 변경 기준은
[`../architecture/canonical-data-contract.md`](../architecture/canonical-data-contract.md)에 유지합니다.

계약은 특정 NumPy/Pandas 표현을 강제하지 않는 순수 Python 구조로 시작합니다. 실제 성능 요구가 확인되면
내부 tensor/array 표현은 후속 결정으로 최적화합니다.

## Alternatives Considered

- Pandas DataFrame을 공통 계약으로 사용: 편리하지만 schema와 의미가 암묵적이 되기 쉽습니다.
- NumPy ndarray만 전달: 빠르지만 channel/asset/provenance 의미를 별도 경로로 관리해야 합니다.
- 특정 산업 interoperability SDK object를 core contract로 사용: 외부 연동에는 유용하지만 core가 transport 또는
  vendor/standard implementation detail에 종속될 수 있으므로 현재 단계에서는 채택하지 않습니다.

## Consequences

- Adapter contract test로 새로운 도메인의 최소 호환성을 검증할 수 있습니다.
- XJTU-SY convention을 canonical field로 승격하기 전에 IMS와 이후 실제 field source에서 contract를 반증합니다.
- 초기 계약 변경은 pre-1.0 단계에서 가능하지만 CHANGELOG와 관련 ADR에 영향이 기록되어야 합니다.
