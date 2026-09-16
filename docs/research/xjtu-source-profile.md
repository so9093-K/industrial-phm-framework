# XJTU-SY Local Source Profile

조사일: 2026-09-16

이 문서는 공식 XJTU-SY Google Drive mirror에서 로컬로 획득하고 압축 해제한 실제 데이터 구조를 관찰한 결과를
기록합니다. Notebook 출력 자체가 Source of Truth가 되지 않도록, Adapter와 canonical contract에 영향을 주는
확인 사실만 research 기록으로 승격합니다.

## Acquisition provenance

- registered dataset: `xjtu-sy`
- official repository: https://github.com/WangBiaoXJTU/xjtu-sy-bearing-datasets
- official author page: https://biaowang.tech/xjtu-sy-bearing-datasets/
- acquired mirror: official Google Drive folder linked by the project
- local raw inventory after completed download: 18 files / 4,481,668,866 bytes
- signal data archive: `XJTU-SY_Bearing_Datasets.part01.rar` through `part06.rar`
- extracted working root: `data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets`

Local inventory and extraction success do not prove upstream authenticity. The framework continues to treat XJTU-SY as a
manual source and does not claim a pinned upstream checksum.

## Observed directory structure

The extracted signal dataset contains three operating-condition directories and five bearing runs per condition.

```text
XJTU-SY_Bearing_Datasets/
├── 35Hz12kN/
│   ├── Bearing1_1/
│   ├── Bearing1_2/
│   ├── Bearing1_3/
│   ├── Bearing1_4/
│   └── Bearing1_5/
├── 37.5Hz11kN/
│   └── Bearing2_1 ... Bearing2_5/
└── 40Hz10kN/
    └── Bearing3_1 ... Bearing3_5/
```

Observed acquisition counts:

| Operating condition | Bearing | CSV acquisitions |
| --- | --- | ---: |
| 35Hz12kN | Bearing1_1 | 123 |
| 35Hz12kN | Bearing1_2 | 161 |
| 35Hz12kN | Bearing1_3 | 158 |
| 35Hz12kN | Bearing1_4 | 122 |
| 35Hz12kN | Bearing1_5 | 52 |
| 37.5Hz11kN | Bearing2_1 | 491 |
| 37.5Hz11kN | Bearing2_2 | 161 |
| 37.5Hz11kN | Bearing2_3 | 533 |
| 37.5Hz11kN | Bearing2_4 | 42 |
| 37.5Hz11kN | Bearing2_5 | 339 |
| 40Hz10kN | Bearing3_1 | 2,538 |
| 40Hz10kN | Bearing3_2 | 2,496 |
| 40Hz10kN | Bearing3_3 | 371 |
| 40Hz10kN | Bearing3_4 | 1,515 |
| 40Hz10kN | Bearing3_5 | 114 |
| **Total** | **15 runs** | **9,216** |

All 15 bearing directories were checked for acquisition filename continuity. Every run used numeric filenames from `1.csv`
through `N.csv` without gaps, so the numeric filename is a stable lifecycle acquisition ordinal for the observed source.

## Observed CSV schema

A representative file contains one header row followed by 32,768 waveform rows:

```text
Horizontal_vibration_signals,Vertical_vibration_signals
0.3225922957062721,0.5557417869567871
...
```

For each of the 15 bearing runs, the first, middle and final acquisition were inspected: 45 files total. All sampled files had:

- 32,768 waveform samples
- 2 columns
- header `Horizontal_vibration_signals,Vertical_vibration_signals`

The official author page states a 25.6 kHz sampling frequency, 32,768 points / 1.28 s per acquisition and a 1 minute
sampling period. The production Adapter validates each CSV as it is read rather than assuming the 45-file sample check proves
all 9,216 files are intact.

## Time-axis consequence

The real source exposes two different time/granularity axes:

```text
bearing lifecycle
  acquisition 1
  acquisition 2
  ...
  acquisition N

one acquisition
  waveform sample 0
  waveform sample 1
  ...
  waveform sample 32767
```

CSV rows contain vibration values only; they do not contain absolute sample timestamps. Fabricating 32,768 `datetime`
objects for every acquisition would create false absolute time semantics and unnecessary memory cost. A regular waveform segment
therefore needs to be representable by sample position plus `sampling_rate_hz`, while the acquisition ordinal remains separate
lifecycle metadata.

The current XJTU Adapter does **not** project lifecycle RUL, fault type or condition labels onto every waveform sample. `labels`
and `rul` remain absent until an experiment protocol defines a defensible target at the correct granularity.

## Adapter boundary

The minimal Adapter responsibility is:

```text
extracted XJTU source
  -> operating condition
  -> bearing/run
  -> numeric acquisition order
  -> CSV schema/value validation
  -> one CanonicalTimeSeries per acquisition
```

The Adapter does not perform feature engineering, train/test splitting, anomaly labeling, RUL derivation or model evaluation.
Those responsibilities remain downstream and require a separate experiment protocol.
