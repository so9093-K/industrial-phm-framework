# Canonical Data Contract Boundary

상태: architecture working boundary / XJTU-SY + IMS + MIMII DUE conformance verified

이 문서는 `industrial-phm-framework`의 canonical data contract가 **무엇을 표준화하고 무엇을 표준화하지 않는지**,
현재 `CanonicalTimeSeries`가 가진 가정과 한계, XJTU-SY·IMS·MIMII DUE에서 검증한 범위, 실제 산업
데이터와 cross-domain source에서 확인할 항목을 정의합니다.

현재 contract는 XJTU-SY를 위해 고정된 schema가 아니며, 모든 산업 데이터를 하나의 universal schema로 미리
추상화하려는 시도도 아닙니다. XJTU-SY는 첫 번째 concrete conformance case이고, IMS와 이후 실제 비공개/현장
데이터를 통해 공통으로 필요한 의미만 canonical boundary에 남깁니다.

## 1. Boundary principles

### Canonical contract는 source format이 아니다

CSV directory, historian, SQL database, object storage, OPC UA server, vendor API 같은 원천 차이는 PHM core 밖의
acquisition/source-integration boundary가 흡수해야 합니다. PHM core가 source-specific protocol이나 directory
grammar를 직접 알지 않도록 유지합니다.

현재 구현 범위는 더 좁습니다. `DomainAdapter.iter_series()`는 `source: Path`를 받으므로 현재 production adapter는
**file-backed prepared local source**를 전제로 합니다. 따라서 framework가 historian/OPC UA/database를 직접
지원한다고 주장하지 않습니다. 첫 field integration에서는 우선 조직의 기존 권한과 ingestion 경계를 통해 허가된
snapshot/export를 준비하고 그 source를 adapter에 전달할 수 있습니다. 실제로 direct non-file source를 반복해서
지원해야 할 필요가 확인될 때만 source-handle 또는 ingestion interface 확장을 검토합니다.

### Canonical contract는 storage format이 아니다

순수 Python contract는 의미와 불변조건을 표현합니다. 향후 규모 때문에 NumPy, Arrow, Parquet, tensor 또는 외부
storage reference가 필요해지더라도 물리적 표현과 canonical semantics를 같은 것으로 취급하지 않습니다.

### Canonical contract는 experiment configuration이 아니다

train/validation/test assignment, feature selection, normal-reference rule, normalization, model parameter는
experiment protocol/configuration이 소유합니다. 데이터 contract에 XJTU의 `fold-1`, bearing split 또는 특정 모델
가정을 넣지 않습니다.

### 표준에 정렬하되 표준 구현에 종속되지 않는다

ISO 13374/OSA-CBM의 PHM 기능 경계, OGC SensorThings의 sensing semantics, Asset Administration Shell(AAS)의 asset 및
time-series semantics를 참고하지만 core object를 특정 AAS/OPC UA/SensorThings SDK object로 만들지 않습니다.
실제 interoperability requirement가 생기면 외부 표준과의 mapping/adapter를 edge에서 추가합니다.

## 2. Current `CanonicalTimeSeries`

현재 contract는 한 asset의 multivariate time-series segment를 다음 정보로 표현합니다.

- `asset_id`
- explicit `timestamps` 또는 regular `sampling_rate_hz`
- `channels`
- rectangular finite numeric sample-by-channel `values`
- optional sample-aligned `labels`
- optional sample-aligned `rul`
- domain-neutral primitive `metadata`

이 구조는 XJTU-SY의 한 vibration acquisition처럼 **동일 sample axis를 공유하는 여러 channel의 유한 segment**를
표현하는 데 충분합니다. 하지만 이 성공을 전체 산업 데이터에 대한 충분조건으로 해석하지 않습니다.

## 3. Current assumptions and known limitations

현재 contract와 adapter boundary가 암묵적으로 또는 명시적으로 가지는 가정은 다음과 같습니다.

| 영역 | 현재 가정 | 이후 확인할 질문 |
| --- | --- | --- |
| source | `DomainAdapter`는 prepared local `Path`를 입력으로 받음 | historian/DB/API를 직접 읽어야 하는 반복 요구가 생기면 source interface를 분리할 것인가 |
| asset | segment마다 하나의 `asset_id` | site/line/component/sensor hierarchy가 별도로 필요한가 |
| time | segment 안에서 하나의 sample axis를 공유 | lifecycle time과 acquisition 내부 sample time을 분리해야 하는가 |
| sampling | explicit timestamps 또는 하나의 regular sampling rate | channel별/asynchronous sampling을 어떻게 표현할 것인가 |
| variables | channel은 고유한 문자열 이름 | unit, observed property, sensor, orientation/location이 first-class여야 하는가 |
| payload | rectangular in-memory finite numeric matrix | large payload/external storage reference가 필요한가 |
| labels | 존재하면 raw sample과 1:1 정렬 | event/run/interval 수준 annotation을 분리해야 하는가 |
| RUL | 존재하면 raw sample과 1:1 정렬 | acquisition/lifecycle target 및 censoring을 별도로 표현해야 하는가 |
| context | primitive `metadata`로 확장 | speed/load/environment 같은 operating context에 typed semantics가 필요한가 |
| quality | structural validity 중심 | bad/uncertain/missing/interpolated/calculated quality를 표현해야 하는가 |
| provenance | adapter metadata에 필요한 값을 둘 수 있음 | sensor/config/calibration/source/processing lineage를 더 명시해야 하는가 |
| events | 별도 event model 없음 | maintenance/failure/alarm/config-change event가 필요한가 |

이 목록은 즉시 새 class를 만들기 위한 backlog가 아닙니다. 두 번째 실제 dataset 또는 field-data integration에서
어떤 가정이 실제로 깨지는지 확인하기 위한 audit checklist입니다.

## 4. Multi-scale time을 특히 주의한다

XJTU-SY에는 적어도 두 시간축이 있습니다.

```text
bearing lifecycle
acquisition 1 -------- acquisition 2 -------- acquisition 3

within one acquisition
sample 1 ------------------------------- sample 32768
```

현재 `CanonicalTimeSeries`는 acquisition 내부 waveform segment를 잘 표현하지만 acquisition이 lifecycle에서 언제
발생했는지와 waveform 내부 sample time을 하나의 의미로 합치지 않습니다. IMS나 실제 historian data를 붙일 때
segment/acquisition time과 sample time의 관계가 반복적으로 필요해진다면 그때 명시적 contract 확장을 검토합니다.

Known final run length로 계산한 normalized lifecycle fraction은 retrospective analysis용이며 online input 또는
canonical physical time으로 취급하지 않습니다.

## 5. Standards concept mapping

아래 mapping은 개념 정렬을 위한 참고이며 implementation conformance 주장이 아닙니다.

| 프로젝트에서 다루는 의미 | 관련 표준 개념 | 적용 원칙 |
| --- | --- | --- |
| PHM processing stages | ISO 13374 / MIMOSA OSA-CBM | acquisition, data manipulation, state detection, health assessment, prognostics 책임을 분리하는 참고 경계 |
| physical asset | AAS Asset / OGC SensorThings Thing | 내부 `asset_id`를 특정 외부 object type에 결합하지 않음 |
| sensor/variable semantics | SensorThings Sensor / ObservedProperty / Datastream | 단순 channel 이름이 부족하다는 실제 evidence가 생길 때 unit/property/sensor semantics 검토 |
| observation/time-series data | SensorThings Observation / AAS Time Series Data | measurement semantics와 storage/API 표현을 분리 |
| segment and external data | AAS Time Series Data Segment 계열 | large/remote data는 core object에 무조건 복사하지 않고 source reference 가능성을 유지 |
| communication/presentation | ISO 13374-3/-4 | core numerical contract와 transport/presentation contract를 분리 |
| OT security boundary | NIST SP 800-82 Rev.3 | credentials, authorization, network policy를 canonical data payload에 넣지 않음 |

참고 표준/사양:

- ISO 13374-1:2003, *Condition monitoring and diagnostics of machines — Data processing, communication and
  presentation — Part 1: General guidelines* (2025 재확인).
- MIMOSA OSA-CBM, *Open System Architecture for Condition-Based Maintenance*.
- IDTA 02008, *Time Series Data*, version 1.1.
- OGC SensorThings API Part 1: Sensing 1.1.
- NIST SP 800-82 Rev.3, *Guide to Operational Technology (OT) Security*.

## 6. Real industrial data readiness

공개 benchmark 외 실제 비공개/현장 데이터에서는 다음 요구를 별도 축으로 검토합니다.

### External sources and storage

원본 데이터를 repository의 `data/raw/`로 복사하는 것을 production architecture의 전제로 하지 않습니다.
`data/`는 연구용 local workspace일 뿐 production data lake가 아닙니다.

다만 **현재 구현은 Path-backed adapter만 지원**합니다. 따라서 현장 source가 historian, database, object storage,
OPC UA 또는 vendor API에 남아 있는 경우 첫 integration은 다음 두 형태 중 실제 요구가 작은 쪽을 사용합니다.

```text
existing authorized export/snapshot
        ↓
prepared local source
        ↓
DomainAdapter(Path)
```

또는 direct online integration이 실제로 필요하고 반복된다면:

```text
external system
        ↓
source-specific ingestion/client boundary
        ↓
canonical processing boundary
```

후자의 공통 interface는 첫 현장 source 전에 추측해서 만들지 않습니다. Credential/network/access policy와 raw data
storage는 조직의 운영 시스템이 계속 소유할 수 있어야 합니다.

### Identity and operating context

현장에서는 asset, component, sensor, measurement point, site/line identity와 speed/load/environment 같은 context가
모델 해석과 재현성에 영향을 줄 수 있습니다. XJTU directory name을 일반 identity model로 승격하지 않고 실제
source에서 어떤 identity가 안정적으로 제공되는지 먼저 확인합니다.

### Data quality and provenance

shape/finite validation만으로 충분하지 않을 수 있습니다. Missing, bad, uncertain, interpolated, calculated 값과
sensor replacement, calibration, gain/sampling configuration 변경이 PHM signal 변화와 혼동될 수 있으므로 실제
source에서 제공하는 quality/provenance를 잃지 않는 것을 우선합니다.

### Events, maintenance, and censoring

실제 fleet에서는 failure보다 preventive maintenance나 observation 종료가 먼저 일어날 수 있습니다. Maintenance,
failure, alarm, configuration-change event와 right-censored lifecycle을 raw waveform sample label 하나로 강제로
표현하지 않습니다.

Dataset-neutral `RulTargetSeries`는 exact target이 어떤 endpoint 의미를 사용하는지
`RulEndpointKind`로 기록합니다. 현재 XJTU-SY target은 `observed-record-end`이며 마지막 기록점을 confirmed
physical failure로 승격하지 않습니다. `right-censored` lifecycle은 실제 remaining life가 관측되지 않았으므로
현재 exact `RulTargetSeries`로 만들 수 없습니다. 향후 censored prognostics가 필요하면 survival/censor-aware
target/evaluator를 별도 contract로 추가합니다.

### Security and governance

Credential, certificate, token, database password, 개인/계약상 민감 정보는 dataset manifest, experiment config,
Notebook 또는 canonical payload의 source of truth가 아닙니다. Runtime secret/access-control 및 조직의 OT/IT 보안
정책이 소유합니다. Framework는 해당 정책을 우회하지 않고 이미 허가된 source를 읽는 경계를 제공해야 합니다.

### Offline and online reuse

현재 구현은 offline batch research가 중심이지만 reusable processing logic은 batch runner, future stream consumer,
API 또는 edge process에서 호출할 수 있는 deterministic unit으로 유지합니다. Streaming infrastructure를 실제
requirement 없이 미리 도입하지 않습니다.

## 7. Validation sequence

Canonical contract를 한 dataset에서 완성한 뒤 일반화한다고 가정하지 않습니다. 다음 순서로 실제 반례를 찾습니다.

### Case A — XJTU-SY conformance

첫 conformance case로 fixed-rate multichannel vibration acquisition, operating-condition metadata, bearing-run
lifecycle을 `CanonicalTimeSeries`와 XJTU-SY Adapter로 검증했습니다.

### Case B — IMS conformance

IMS의 timestamp filename, test별 channel configuration, irregular acquisition interval, nested archive provenance를
`ImsBearingAdapter`로 표현했습니다. Asset identity, acquisition/lifecycle time, channel semantics, source
provenance는 현재 contract와 metadata boundary에서 보존되었으며 현재 core contract를 유지합니다.
이 결과는 bearing-vibration modality 내의 두 source에 대한 conformance evidence입니다.

### Case C — first private/field source

실제 비공개 산업 데이터가 확보되면 benchmark와 별도로 field-data conformance case로 사용합니다. 현재 Path-backed
boundary로 authorized export/snapshot을 충분히 다룰 수 있는지 먼저 확인하고, direct historian/DB/API integration이
실제 requirement라면 그때 source boundary를 확장합니다. Access policy, quality flags, asset/sensor identity,
maintenance/configuration history를 우선 검토합니다. 원본 데이터를 공개하거나 repository에 복사하지 않아도
contract/adapter test를 수행할 수 있어야 합니다.

이 integration을 준비하기 위한 첫 구현으로 `CsvSensorAdapter`는 **한 CSV 파일을 한 asset의 한 canonical
segment로 읽는 명시적 export/snapshot 경계**를 제공합니다. 사용자가 channel column과 timestamp 또는 regular
sampling rate를 직접 선언하며, missing/non-numeric/non-finite 값과 non-increasing timestamp는 fail-fast로
거부합니다. Explicit timestamp 간격이 일정하지 않으면 값을 재격자화하지 않고 `irregular-sampling` warning을
남깁니다. Timestamp와 declared sampling rate를 함께 제공하는 경우에는 사용자가
`sampling_rate_tolerance_ratio`를 명시했을 때만 두 time source의 consistency를 검사하고, 허용 편차를 넘으면
`sampling-rate-mismatch` warning을 남깁니다. Framework가 임의 tolerance로 sampling metadata를 수정하거나
resampling하지 않습니다. 원본 file SHA-256과 byte size는 source provenance로 보존합니다. Adapter가 canonical
segment를 만들 때 validation에서 관찰한 quality state/issue code와 sampling interval 최대 편차뿐 아니라
CSV delimiter, minimum sample count와 명시된 sampling-rate tolerance도 primitive metadata로 보존합니다. 따라서
feature projection 이후에도 어떤 parsing/validation policy에서 PASS/WARN이 결정됐는지 추적할 수 있습니다.
CSV content는
하나의 byte snapshot으로 읽고, 바로 그 bytes에서 UTF-8 text parsing과 SHA-256/byte-size provenance를 함께
만듭니다. 따라서 adapter 실행 중 파일이 교체되더라도 parsed values와 기록된 digest가 서로 다른 file state를
가리키지 않습니다.

이 CSV adapter는 실제 private/field source conformance를 완료했다는 주장이 아닙니다. Historian/DB/OPC UA
connector, maintenance event, sensor calibration, vendor quality flag semantics는 첫 실제 source가 요구할 때
검토합니다.

### Case D — MIMII DUE cross-domain conformance

MIMII DUE의 16 kHz mono 16-bit PCM machine audio를 세 번째 source이자 첫 cross-domain case로 검증했습니다.
한 WAV clip은 `timestamps=None`, `sampling_rate_hz=16000`, `channels=("pcm_amplitude",)`인
`CanonicalTimeSeries` 하나로 표현합니다.

Clip-level normal/anomaly label, source/target domain, section, split과 원문 operating attribute는 sample-aligned
`labels`로 투영하지 않고 metadata에 보존합니다. PCM signed 16-bit sample은 Adapter에서 `[-1, 1]` 같은
학습용 normalization을 수행하지 않고 같은 amplitude scale의 numeric value로 옮깁니다.

`asset_id`는 source가 안정적으로 제공하는 machine type과 section을 조합해 `fan/section-00` 같은 source
identity로 사용합니다. Section을 machine serial number, physical lifecycle 또는 run-to-failure asset으로
확대 해석하지 않습니다. Filename의 `NNNN`도 source file number로만 보존하며 acquisition/lifecycle order를
생성하지 않습니다.

이 conformance에서 audio modality를 표현하기 위한 새 canonical public field는 필요하지 않았습니다. 따라서
현재 core contract를 유지합니다.

## 8. Rules for changing the canonical contract

Canonical contract 확장은 다음 조건을 우선합니다.

1. 두 번째 실제 source 또는 field source에서 현재 contract로 의미 손실 없이 표현하기 어렵다.
2. 해당 의미를 adapter metadata에만 두면 공통 PHM 로직에서 반복 parsing/조건 분기가 발생한다.
3. 추가 필드/타입이 특정 dataset 이름이나 directory convention이 아니라 domain-neutral 의미를 가진다.
4. 기존 dataset adapter와 contract test를 함께 재검증할 수 있다.
5. pre-1.0 public-contract 변경은 CHANGELOG와 필요한 ADR에 기록한다.

Source interface 확장도 같은 원칙을 따릅니다. 한 field source가 API라는 이유만으로 generic connector framework를
만들지 않고, prepared `Path` boundary로 해결할 수 없는 반복 요구가 확인될 때만 별도 source abstraction을 둡니다.

반대로 "산업에서는 언젠가 필요할 것 같다"는 이유만으로 AssetGraph, SensorRegistry, EventStore, QualityFramework,
streaming abstraction을 미리 만들지 않습니다.

## 9. Next review boundary

XJTU-SY, IMS와 MIMII DUE conformance 결과는 현재 `CanonicalTimeSeries` boundary를 유지할 근거를 제공합니다.
이후 model experiment 순서는 이 문서가 소유하지 않습니다. 다음 canonical 재검토는 first private/field source에서
quality, asset/sensor identity, maintenance/event/censoring 또는 external-source boundary처럼 현재 metadata와
Path-backed Adapter로 의미 손실 없이 표현하기 어려운 실제 요구가 확인될 때 수행합니다.
