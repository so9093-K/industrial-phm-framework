# IMS Bearing Data Set Source Profile

상태: source registration / local archive validation pending

이 문서는 NASA Prognostics Center of Excellence(PCoE)가 배포하는 IMS Bearing Data Set을 두 번째
canonical-data conformance case로 사용할 때 **공식 출처에서 확인된 사실**과 **실제 archive에서 확인해야 할
사실**을 분리합니다.

이 단계에서는 IMS adapter compatibility를 주장하지 않습니다. 공식 archive가 registry에 등록되어 있다는 사실과
그 archive 내부 구조를 `DomainAdapter`가 실제로 지원한다는 주장은 별개입니다.

## 1. Official source and citation

NASA PCoE Prognostics Data Repository는 `Bearings` dataset을 University of Cincinnati의 Center for Intelligent
Maintenance Systems(IMS)가 제공한 bearing experiment data로 설명하고 공식 ZIP download를 제공합니다.

- project dataset ID: `ims-bearings`
- official repository: NASA Prognostics Center of Excellence Data Set Repository
- official archive: `https://phm-datasets.s3.amazonaws.com/NASA/4.+Bearings.zip`
- repository citation: J. Lee, H. Qiu, G. Yu, J. Lin, and Rexnord Technical Services (2007), IMS, University of
  Cincinnati, *Bearing Data Set*, NASA Prognostics Data Repository, NASA Ames Research Center
- NASA Open Data Portal entry: `https://data.nasa.gov/dataset/ims-bearings`
- NASA Open Data Portal license field: `other-license-specified`

NASA repository는 해당 repository에서 획득한 data를 사용하는 publication에서 repository와 data donor를 함께
acknowledge하도록 요청하고, 사용은 사용자 책임임을 안내합니다.

현재 manifest에는 upstream SHA-256이 없습니다. 따라서 `data fetch`가 archive를 성공적으로 내려받고 local hash를
계산하더라도 그 값만으로 upstream authenticity가 사전에 pin되었다고 주장하지 않습니다.

## 2. Why IMS is used now

IMS를 지금 사용하는 목적은 XJTU-SY 이후 곧바로 두 번째 모델 성능 benchmark를 만드는 것이 아닙니다.

```text
XJTU-SY
  ↓
current CanonicalTimeSeries assumptions
  ↓
IMS source inspection / minimal adapter
  ↓
contract incompatibility 확인
  ↓
필요한 경우에만 domain-neutral contract refinement
```

같은 bearing-vibration domain에서 source layout과 acquisition semantics가 달라져도 adapter/core boundary가 유지되는지
먼저 확인합니다. Isolation Forest, Health Indicator, RUL 같은 downstream 연구는 이 contract exercise와 분리합니다.

## 3. Facts not promoted to production invariants yet

IMS dataset에 대해 논문, tutorial, community repository에서 다음과 같은 설명이 널리 반복됩니다.

- 여러 bearing run/test가 존재한다.
- individual measurement file 이름이 acquisition time을 나타낸다.
- fixed-rate vibration snapshot이 반복 수집된다.
- test에 따라 channel configuration과 acquisition interval이 달라질 수 있다.

하지만 현재 project는 이러한 secondary-source 설명을 production validator의 authoritative profile로 사용하지
않습니다. 특히 archive directory nesting, test별 exact file count, channel count, sample count, acquisition interval은
source 설명 간 차이가 있으므로 **공식 archive를 local에서 직접 조사한 결과**를 기준으로 정합니다.

따라서 아직 다음 상수를 코드에 추가하지 않습니다.

```text
EXPECTED_TEST_FILE_COUNTS
EXPECTED_CHANNEL_COUNT
EXPECTED_ACQUISITION_PERIOD
EXPECTED_ARCHIVE_DIRECTORY_TREE
```

실제 source inspection으로 확인되지 않은 값은 compatibility claim이 아닙니다.

## 4. Local acquisition and inspection boundary

Manifest는 NASA PCoE의 공식 archive URL을 `url` provider로 등록합니다. 원본 archive는 수정하지 않고 local raw
workspace에 보존합니다.

```bash
uv run industrial-phm data fetch ims-bearings
uv run industrial-phm data verify ims-bearings
```

현재 upstream checksum이 manifest에 pin되어 있지 않으므로 `verify`의 의미는 XJTU-SY와 마찬가지로 제한해서
해석해야 합니다. Local archive size/hash를 provenance로 기록할 수는 있지만 공식 upstream hash와의 일치를
증명하지는 않습니다.

Archive를 실제로 준비한 뒤 다음을 먼저 조사합니다.

1. top-level 및 nested directory inventory
2. run/test 식별 방법
3. acquisition filename과 timestamp semantics
4. 각 run의 file count 및 실제 interval distribution
5. text file delimiter/header 여부
6. waveform sample count
7. channel count와 channel-to-bearing mapping
8. sampling rate를 official documentation과 local content 중 어디에서 authoritative하게 얻을 수 있는지
9. malformed/extra/non-data file 처리
10. source file provenance를 canonical metadata에 보존하는 방법

이 관찰을 `IMS source profile`의 verified section으로 승격한 뒤에만 production adapter validator를 작성합니다.

## 5. Canonical contract questions

IMS source는 다음 질문으로 현재 `CanonicalTimeSeries`를 반증합니다.

### Asset identity

각 file의 channel이 어떤 bearing/measurement point를 의미하는지 source-specific mapping이 필요할 수 있습니다.
Directory/test naming 자체를 canonical asset model로 승격하지 않습니다.

### Acquisition time and sample time

Filename timestamp가 acquisition lifecycle time을 나타내고 file 내부 row position이 waveform sample time을 나타낸다면
두 시간 의미를 명확히 구분해야 합니다. 현재 XJTU adapter처럼 단순 acquisition index/고정 period metadata만으로
충분한지 확인합니다.

### Channel semantics

Test마다 sensor/channel configuration이 다르다면 단순 channel 문자열 이름으로 downstream 공통 처리가 충분한지
확인합니다. Unit, sensor, measurement point 같은 의미가 공통 로직에서 반복적으로 필요할 때만 canonical extension을
검토합니다.

### Provenance

Canonical record에서 최소한 dataset ID, source file, run/test identity, acquisition timestamp를 잃지 않아야 합니다.
이 값 중 source-specific naming은 metadata/adapter에 남길 수 있으며 공통 contract field로 올리는 것은 반복 사용이
확인된 뒤 결정합니다.

## 6. Adapter implementation gate

`ImsBearingAdapter` 또는 IMS-specific production validator는 다음 조건 이후에 구현합니다.

- official archive 또는 그 원형을 보존한 local source를 실제로 확인했다.
- synthetic fixture가 실제 source의 delimiter, width, timestamp/file naming semantics를 반영한다.
- adapter가 source-specific directory/test convention을 core contract에 누출하지 않는다.
- XJTU-SY의 sampling/acquisition convention을 IMS에 억지로 적용하지 않는다.
- compatibility test와 문서가 실제로 검증한 범위를 과장하지 않는다.

이 gate는 구현을 늦추기 위한 절차가 아니라 **compatibility is earned through validation**이라는 project 원칙을
두 번째 dataset에서도 지키기 위한 것입니다.

## 7. Field-data relevance

IMS는 여전히 공개 benchmark이며 실제 plant historian이나 private OT source를 대신하지 않습니다. 다만 XJTU와 다른
source convention을 조기에 경험함으로써 `CanonicalTimeSeries`가 특정 benchmark directory와 lifecycle convention에
고정되는 것을 막는 역할을 합니다.

이후 첫 private/field source에서는 별도로 access policy, asset/sensor identity, data quality, calibration/configuration
history, maintenance event, censoring 및 external storage boundary를 검증합니다.

## Sources

- NASA Prognostics Center of Excellence Data Set Repository:
  `https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/`
- NASA Open Data Portal, IMS Bearings: `https://data.nasa.gov/dataset/ims-bearings`
