# ADR-0005: 정규 샘플링 신호의 implicit sample time 허용

- Status: Accepted
- Date: 2026-09-16

## Context

XJTU-SY 실데이터를 확인한 결과, acquisition CSV 하나는 25.6 kHz로 수집한 32,768개의 2축 vibration sample을
포함하지만 CSV 자체에는 sample별 absolute timestamp column이 없습니다. 반면 bearing lifecycle은 `1.csv`부터
`N.csv`까지의 acquisition ordinal과 1분 sampling period로 표현됩니다.

기존 `CanonicalTimeSeries` v0.1은 모든 sample에 `datetime` timestamp를 요구했습니다. 이 구조를 그대로 적용하면
XJTU-SY waveform에 존재하지 않는 absolute time을 임의로 만들어야 하고, acquisition마다 32,768개의 Python
`datetime` object를 생성해야 합니다. 또한 waveform sample time과 bearing lifecycle time을 같은 축처럼 오해할
위험이 있습니다.

## Decision

`CanonicalTimeSeries.timestamps`는 regular sampling segment에서 `sampling_rate_hz`가 제공되는 경우 `None`을
허용합니다.

- explicit timestamp가 존재하는 데이터는 기존처럼 sample별 timestamp를 제공합니다.
- timestamp가 없고 regular sampling rate가 알려진 데이터는 sample position `i`와 `sampling_rate_hz`로
  segment-local offset `i / sampling_rate_hz`를 해석합니다.
- `timestamps`와 `sampling_rate_hz`가 모두 없는 series는 유효하지 않습니다.
- 이 결정은 absolute segment start time을 새로 정의하지 않습니다.
- asset lifecycle의 acquisition ordinal/period는 waveform sample timestamp와 별개이며 Adapter metadata에 보존합니다.
- 현재 sample-aligned `labels`와 `rul` 의미는 유지합니다. XJTU-SY Adapter는 lifecycle-level target을 waveform
  sample마다 반복하지 않고 둘 다 비워 둡니다.

## Alternatives Considered

- 임의 epoch에서 시작하는 `datetime`을 생성: contract type은 유지되지만 존재하지 않는 absolute time 의미를
  만들기 때문에 기각합니다.
- acquisition 전체를 하나의 거대한 sample sequence로 연결: acquisition boundary와 lifecycle granularity를 잃고
  RUL/condition 의미가 waveform sample에 잘못 투영될 수 있어 기각합니다.
- 즉시 `SignalSegment` / `LifecycleObservation` 같은 새 public contract를 추가: 두 번째 domain의 evidence 없이
  abstraction을 먼저 고정하게 되므로 보류합니다.

## Consequences

- regular high-frequency waveform을 false timestamp 없이 표현할 수 있습니다.
- acquisition 단위 lazy Adapter가 불필요한 timestamp object를 생성하지 않습니다.
- downstream component는 `timestamps is None`인 경우 `sampling_rate_hz` 기반 time offset을 처리해야 합니다.
- irregularly sampled data는 계속 explicit timestamp가 필요합니다.
- lifecycle-level RUL/health contract는 실제 모델·두 번째 domain evidence가 확보된 뒤 별도 ADR로 발전시킵니다.
