# IMS Bearing Data Set Source Profile

상태: official archive profile verified / minimal Adapter implemented

이 문서는 NASA Prognostics Center of Excellence(PCoE)가 배포하는 IMS Bearing Data Set의 source
profile, validation contract, canonical mapping을 기록합니다. IMS는 XJTU-SY에 이은 두 번째
`CanonicalTimeSeries` conformance case입니다.

## 1. Source record

- project dataset ID: `ims-bearings`
- official repository: NASA Prognostics Center of Excellence Data Set Repository
- official archive: `https://phm-datasets.s3.amazonaws.com/NASA/4.+Bearings.zip`
- repository citation: J. Lee, H. Qiu, G. Yu, J. Lin, and Rexnord Technical Services (2007), IMS,
  University of Cincinnati, *Bearing Data Set*, NASA Prognostics Data Repository, NASA Ames Research Center
- NASA Open Data Portal entry: `https://data.nasa.gov/dataset/ims-bearings`
- NASA Open Data Portal license field: `other-license-specified`

2026-09-17에 framework `data fetch`로 획득한 local artifact의 provenance는 다음과 같습니다.

- archive: `ims-bearing-data-set.zip`
- size: `1,075,597,174` bytes
- local SHA-256: `21001ac266c465f5d345ec42d7b508c6a6328487fd9d4d7774422dd5ea10ad83`
- checksum policy: local SHA-256 provenance

Manifest에 publisher-provided SHA-256을 추가하면 `verify`가 pinned checksum comparison을 적용합니다.

## 2. Archive layout

공식 ZIP은 waveform을 nested 7z/RAR archive로 배포합니다.

```text
ims-bearing-data-set.zip
└── 4. Bearings/
    └── IMS.7z                         1,075,320,408 bytes
        ├── 1st_test.rar                 366,567,310 bytes
        ├── 2nd_test.rar                  85,581,092 bytes
        ├── 3rd_test.rar                 609,047,134 bytes
        └── Readme Document for IMS Bearing Data.pdf
```

RAR extraction 결과는 다음 prepared-source profile을 갖습니다.

| RAR member | Extracted path | Waveform files | Payload bytes |
| --- | --- | ---: | ---: |
| `1st_test.rar` | `1st_test/` | 2,156 | 2,477,767,237 |
| `2nd_test.rar` | `2nd_test/` | 984 | 544,618,480 |
| `3rd_test.rar` | `4th_test/txt/` | 6,324 | 3,502,648,779 |
| total |  | 9,464 | 6,525,034,496 |

`3rd_test.rar`의 extracted directory는 archive에 기록된 `4th_test/txt/`입니다. Adapter는 이
source path를 stable test ID `set-3`으로 mapping합니다.

## 3. Measurement profile

공식 README는 four-bearing test rig, 2,000 RPM, 6,000 lb radial load, 20 kHz sampling rate, acquisition당
20,480 points를 기록합니다. Set 1은 bearing당 x/y accelerometer를 배치해 8 channels을 갖고,
Set 2와 Set 3은 bearing당 1개 accelerometer를 배치해 4 channels을 갖습니다.

Waveform은 headerless numeric ASCII입니다. Filename은 `%Y.%m.%d.%H.%M.%S` local-clock acquisition
timestamp를 표현합니다.

| Set | Source path | Archive range | Files | Channels | Interval profile |
| --- | --- | --- | ---: | ---: | --- |
| Set 1 | `1st_test/` | 2003-10-22 12:06:24 — 2003-11-25 23:39:56 | 2,156 | 8 | 600 s 1,962회, 300 s 145회, restart/gap interval |
| Set 2 | `2nd_test/` | 2004-02-12 10:32:39 — 2004-02-19 06:22:39 | 984 | 4 | 600 s 983회 |
| Set 3 | `4th_test/txt/` | 2004-03-04 09:27:46 — 2004-04-18 02:42:55 | 6,324 | 4 | 600 s 6,315회, 8개 gap interval |

README의 Set 3 scope는 4,448개 file과 `2004-04-04 19:01:57` 종료 시각입니다. Archive의 첫
4,448개 file은 이 범위와 일치하며, 이후 1,876개 file은 `archive-extension` scope를 구성합니다.
Sampled validation에서 두 scope의 waveform은 20,480 × 4 shape로 일치했습니다.

## 4. Validation contract

`data inspect` owns archive/directory inventory. `data validate ims-bearings` owns prepared-source profile and
waveform compatibility.

```bash
uv run industrial-phm data validate ims-bearings \
  --source data/interim/ims-bearings/source
```

Validator는 다음 invariant를 검사합니다.

- `1st_test/`, `2nd_test/`, `4th_test/txt/` source directory mapping
- test별 acquisition count·first timestamp·last timestamp
- filename timestamp parseability와 uniqueness
- acquisition당 20,480 rows
- Set 1의 8-column waveform과 Set 2/3의 4-column waveform
- numeric ASCII payload

Sampled mode는 각 set의 first/middle/last waveform 9개를 parse하고 전체 filename profile을 검사합니다.
`--full`은 9,464개 waveform 전체에 같은 payload validation을 적용합니다. 2026-09-17 sampled
validation은 profile compatibility와 waveform compatibility 모두 `PASS`를 반환했습니다.

## 5. Canonical mapping

`ImsBearingAdapter`는 acquisition file 하나를 bearing별 `CanonicalTimeSeries` 네 개로 분리합니다.

| Source | Canonical asset | Channels |
| --- | --- | --- |
| Set 1 channel pairs | `set-1-bearing-{1..4}` | `x_axis_vibration`, `y_axis_vibration` |
| Set 2 channels | `set-2-bearing-{1..4}` | `vibration` |
| Set 3 channels | `set-3-bearing-{1..4}` | `vibration` |

Canonical metadata는 다음 source provenance와 operating context를 보존합니다.

- `dataset_id`, `test_id`, `bearing_number`, `acquisition_index`
- `acquisition_timestamp`, `acquisition_time_basis=filename-local-clock`
- `archive_scope=readme-documented|archive-extension`
- `source_archive_member`, `source_file`
- `rotational_speed_rpm=2000`, `radial_load_lb=6000`

Within-acquisition sample time은 `sampling_rate_hz=20000`으로 표현하고 acquisition lifecycle time은 metadata의
filename timestamp와 index로 표현합니다. Source directory naming과 channel-to-bearing mapping은 Adapter 책임입니다.

## 6. Contract review and experiment decisions

현재 `CanonicalTimeSeries` 계약은 IMS waveform을 변환하는 데 충분합니다. Acquisition timestamp와
source scope는 metadata에서 보존되며, sampling rate와 channel sequence는 typed canonical field를 사용합니다.

다음 결정은 model experiment protocol에서 고정합니다.

1. Set 3 `readme-documented` 4,448개와 `archive-extension` 1,876개의 experiment scope
2. Set 2/3 single-channel sensor orientation의 analysis label
3. Full payload validation의 release/scheduled workflow 배치
4. Acquisition timestamp timezone을 제공하는 authoritative source가 확보될 경우 time-basis refinement

## Sources

- NASA Prognostics Center of Excellence Data Set Repository:
  `https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/`
- NASA Open Data Portal, IMS Bearings: `https://data.nasa.gov/dataset/ims-bearings`
