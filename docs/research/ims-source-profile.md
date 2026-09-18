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

Set 3를 사용하는 모든 IMS model experiment configuration은 source scope를 `readme-documented` 또는
`readme-documented+archive-extension`으로 명시합니다. 첫 model experiment의 scope와 나머지 결정은
IMS experiment protocol에서 고정합니다.

1. Set 2/3 single-channel sensor orientation의 analysis label
2. Full payload validation의 release/scheduled workflow 배치
3. Acquisition timestamp timezone을 제공하는 authoritative source가 확보될 경우 time-basis refinement

## 7. Cross-dataset portability 관찰 (2026-09-18)

XJTU-SY 첫 baseline이 한 사이클(development → diagnosis → reference decision → finalized configuration →
one-shot holdout → post-holdout robustness)을 마친 시점에, 기존에 검증한 IMS local-source profile과
Adapter canonical mapping을 기준으로 같은 feature interface가 IMS canonical representation에서도 유지되는지
확인했습니다. 목적은 IMS에서 비슷한 수치를 얻는 것이 아니라 **어떤 계층이 dataset-neutral하게
유지되고 어떤 가정이 XJTU edge에 남아야 하는지**를 구분하는 것입니다.

### 그대로 재사용되는 계층

`ImsBearingAdapter -> CanonicalTimeSeries -> vibration-statistical-v1` 경로는 수정 없이 동작합니다. IMS
acquisition에서 추출한 feature vector의 `feature_set_id`는 XJTU와 같은 `vibration-statistical-v1`이고,
`dataset_id`와 `acquisition_index` metadata도 보존됩니다. Feature formula가 한 acquisition만 입력으로 받는
stateless transformation이므로 dataset 경계를 넘습니다.

### Dataset마다 달라지는 것

Feature **이름**은 channel 이름에서 파생되므로 dataset과 test set에 따라 달라집니다.

| Source | Channels per bearing | Feature 수 |
| --- | ---: | ---: |
| XJTU-SY | 2 (`Horizontal_*`, `Vertical_*`) | 16 |
| IMS set-1 | 2 (`x_axis_vibration`, `y_axis_vibration`) | 16 |
| IMS set-2 / set-3 | 1 (`vibration`) | 8 |

따라서 `feature_set_id`는 공유되지만 `selected_features`는 dataset-specific입니다. 현재 channel-derived
feature schema에서는 IMS 안에서도 set-1과 set-2/3가 동일한 `selected_features` configuration을 그대로
공유할 수 없습니다.

### XJTU edge에 남아야 하는 가정

현재 experiment 계층(`industrial_phm.experiments.xjtu_*`)은 IMS에 그대로 적용되지 않습니다. 이는 결함이
아니라 경계가 의도대로 서 있다는 뜻이며, IMS experiment protocol이 아래 항목을 스스로 결정해야 합니다.

- **Split unit**: XJTU는 bearing run 하나가 독립적인 run-to-failure trajectory입니다. IMS는 한 test에서
  4개 bearing이 같은 shaft에서 동시에 기록되므로 acquisition timeline을 공유합니다. 같은 test의 bearing을
  서로 다른 partition에 두는 것은 XJTU의 bearing-run 규칙과 같은 의미의 분리가 아닙니다. 게다가 독립적인
  test는 3개뿐이라 XJTU의 5-fold rotating holdout을 그대로 옮길 수 없습니다.
- **`operating_condition`**: IMS canonical metadata에는 이 key가 없습니다. 대신
  `rotational_speed_rpm=2000`, `radial_load_lb=6000`이 보존되며 세 test가 모두 같은 조건입니다. XJTU
  evaluation/characterization이 `operating_condition`을 요구하므로, IMS protocol은 이 값을 metadata로
  기록할지 아니면 condition 축 없이 정의할지를 정해야 합니다.
- **Lifecycle segment 의미**: XJTU의 retrospective thirds와 `train-bearing-early-third-v1` reference는 각
  bearing이 자신의 run-to-failure lifecycle을 갖는다는 전제 위에 있습니다. IMS는 test 단위로 종료되고 어떤
  bearing이 고장에 이르렀는지는 source README가 설명하지만 이 repository는 아직 이를 검증된 profile이나
  acquisition-level label로 승격하지 않았습니다.
- **Acquisition completeness**: XJTU는 bearing별 `1..N` 연속성을 검증합니다. IMS는 test별 acquisition 수가
  고정이고 4개 bearing이 그 수를 공유하며, set-1과 set-3에는 restart/gap interval이 있습니다.
- **Set 3 scope**: `readme-documented`(4,448)와 `archive-extension` 포함(6,324) 중 하나를 configuration이
  명시해야 합니다.

이 관찰들은 IMS experiment protocol의 입력이며, 이 문서가 그 결정을 대신 고정하지 않습니다. Feature 계층이
dataset-neutral하게 유지된다는 사실 자체는 contract 테스트가 두 domain의 channel 구성으로 고정합니다.

## Sources

- NASA Prognostics Center of Excellence Data Set Repository:
  `https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/`
- NASA Open Data Portal, IMS Bearings: `https://data.nasa.gov/dataset/ims-bearings`
