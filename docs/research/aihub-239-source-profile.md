# AI-Hub 239 source profile

## Scope and evidence

Training/raw 보일러(filekey 44033)와 압출기(44035) ZIP의 모든 JSON을 local streaming profiler로
조사했습니다. 결과는 아래 SHA-256의 local bytes에 한정되며 publisher checksum이나 전체 데이터셋의
보장을 뜻하지 않습니다. 재현 방법은 [tooling README](../../tools/aihub/README.md)에 있습니다.

| Archive | JSON | Records | Null | Extra duplicate records | Conflicting timestamp/channel groups |
| --- | ---: | ---: | ---: | ---: | ---: |
| 보일러 | 14 | 13,274,603 | 105 | 13 | 6 |
| 압출기 | 15 | 17,649,075 | 11,891 | 9 | 5 |

중복 통계는 member 내부 timestamp/channel 기준입니다. null과 숫자는 다른 값으로 계산하고, 같은 값의
반복도 삭제하지 않습니다. 서로 다른 member/device의 같은 시각은 충돌로 합치지 않습니다.

- 보일러 SHA-256: `87ad1f77172f549c5aa5f78a857ddd8b02cb010a08af67ea64a3cf4c5a824023`
- 압출기 SHA-256: `7fd3a50f1222a695fc440ef2d4e8f2b431dd419b2249b60a6bc0ab34d5472a17`

## Observed source contract

- Root: `DEVICE_ID`, `DEVICE_BD_ID`, `data` array. Record: `ITEM_NAME`, `ITEM_VALUE`, `TIMESTAMP`.
- 모든 조사 member에서 동일한 35개 이름이 관측됐으며 값에는 숫자와 null이 있습니다.
- Timestamp는 offset 없는 `YYYY-MM-DD HH:MM:SS`입니다. 주로 60초와 다른 간격이 함께 관측됩니다.
- 한 시각에 35개가 모두 있는 경우 외에 11개/24개로 나뉜 경우도 있습니다. 이를 자동 정렬하거나
  오류로 판정하지 않습니다. Sampling cadence와 aggregation window는 별개입니다.
- 압출기에서는 한 timestamp에 19개 또는 27개 channel만 관측된 경우도 있습니다.
- 파일 suffix는 device ID가 아닙니다. `SourceData_391.json`의 `DEVICE_ID`는 7303입니다.

## Measurement dictionary baseline

아래 이름은 observed raw identity입니다. 현재 canonical mapping, 단위, aggregation window와
measurement method는 미확정입니다. UI는 raw name과 `unit: unknown`을 표시합니다. 이름에 평균이
있어도 temporal average를 뜻한다고 가정하지 않습니다.

| Raw ITEM_NAME | Canonical mapping | Unit |
| --- | --- | --- |
| R상무효전력 | unresolved | unknown |
| R상선간전압 | unresolved | unknown |
| R상역률 | unresolved | unknown |
| R상유효전력 | unresolved | unknown |
| R상전류 | unresolved | unknown |
| R상전류고조파 | unresolved | unknown |
| R상전압 | unresolved | unknown |
| R상전압고조파 | unresolved | unknown |
| S상무효전력 | unresolved | unknown |
| S상선간전압 | unresolved | unknown |
| S상역률 | unresolved | unknown |
| S상유효전력 | unresolved | unknown |
| S상전류 | unresolved | unknown |
| S상전류고조파 | unresolved | unknown |
| S상전압 | unresolved | unknown |
| S상전압고조파 | unresolved | unknown |
| T상무효전력 | unresolved | unknown |
| T상선간전압 | unresolved | unknown |
| T상역률 | unresolved | unknown |
| T상유효전력 | unresolved | unknown |
| T상전류 | unresolved | unknown |
| T상전류고조파 | unresolved | unknown |
| T상전압 | unresolved | unknown |
| T상전압고조파 | unresolved | unknown |
| 누적전력량 | unresolved | unknown |
| 무효전력평균 | unresolved | unknown |
| 상전압평균 | unresolved | unknown |
| 선간전압평균 | unresolved | unknown |
| 역률평균 | unresolved | unknown |
| 온도 | unresolved | unknown |
| 유효전력평균 | unresolved | unknown |
| 전류고조파평균 | unresolved | unknown |
| 전류평균 | unresolved | unknown |
| 전압고조파평균 | unresolved | unknown |
| 주파수 | unresolved | unknown |

## Documented / configured / unresolved

[공식 dataset 239 설명](https://www.aihub.or.kr/aihubdata/data/view.do?dataSetSn=239)의 데이터 구조를
추가 확인했습니다. `DEVICE_ID`와 `DEVICE_BD_ID`는 센서 식별자로 설명되며, 설비명·종류·정격정보는
별도 metadata 항목입니다. 따라서 센서 ID를 바로 물리 asset ID로 승격하지 않습니다.
계약전력과 설비 정격전력의 kW 표기는 metadata의 단위이며 `ITEM_VALUE` 전체의 단위 근거가 아닙니다.
공개 구조 설명에는 TIMESTAMP 형식이 있지만 UTC offset/timezone 규정은 확인하지 못했습니다.

- **Documented selection:** `tools/aihub/presets/dataset-239.json`이 filekey/설비군/split을 소유합니다.
- **Observed:** 위 archive 범위에 대한 schema/count/null/duplicate/cadence 조사 결과입니다.
- **Configured:** 소구간 실행의 asset ID는 개발용 grouping이며 `Asia/Seoul`은 명시적인 normalization
  가정입니다. 두 값 모두 binding의 evidence/version과 함께 저장하고 검증된 source fact로 취급하지 않습니다.
- **Unresolved:** 물리 설비 identity, source timezone, 단위, 평균의 계산 범위, provider label 해석.

다른 archive/version을 조사하면 그 scope와 근거를 추가합니다. 두 설비군에서 확인한 공통점만으로
전체 데이터셋의 불변 schema를 선언하지 않습니다. 상세 실행 결과와 원본은 Git에 넣지 않습니다.

## Actual historical slice

보일러 `SourceData_211.json`(device 2297/board 1)의 2020-11-13 00:00–01:00과 압출기
`SourceData_127.json`(device 2223/board 1)의 2020-11-01 00:00–01:00 local time을 개발용 binding으로
같은 DuckLake에 적재했습니다. 각각 2,100개 관측과 35개 channel이며 정렬·보간·deduplication하지 않습니다.
이는 measurement-history 동작 검증이지 PHM 정확성이나 실제 설비 상태 검증이 아닙니다.

추가로 보일러 `SourceData_543.json`의 2021-02-01 07:05:14 주변 null 구간과
`SourceData_359.json`의 2021-02-01 00:00:01 누적전력량 충돌 구간을 원본 그대로 적재해
품질 표시를 검증했습니다. 각각 별도의 명시적 개발용 설비 grouping을 사용합니다.

## Interpretation and quality boundary

새 metadata v2는 `observed_property=None`으로 canonical 해석 미확정을 표현합니다. 원본 ITEM_NAME은
channel label입니다. v1의 property_name은 legacy label로 표시하며 기존 JSON을 재작성하지 않습니다.
FILE의 source quality는 unknown입니다. 숫자 존재/present와 null은 별도 availability이며 protocol Good이 아닙니다.
기존 history `status_good` 저장 필드는 FILE에서 availability를 담는 호환 필드로 유지하되,
공통 read model의 `source_quality`와 UI는 이를 source Good 판정에 사용하지 않습니다.

## Labeling data profile

Training/label 보일러(filekey 44023)와 압출기(44025) ZIP의 모든 JSON을 `tools/aihub/label_profile.py`로
streaming 조사했습니다. 상세 결과는 `artifacts/aihub-239/*-label-profile.json`(Git 제외)에 있습니다.

| Archive | JSON | Records | SHA-256 |
| --- | ---: | ---: | --- |
| 보일러 label | 70 | 66,372,401 | `453d94dad934c20414d4465894d9031d1d29ef8672c48641d7861a4f6f912931` |
| 압출기 label | 75 | 88,245,330 | `b5492c2ee3c707afc5fa01364b2e5cb88de0702bed8ac45120be4b22c96444da` |

**Observed structure.** 각 member는 `SVC_NAME`과 `BASE_ITEM` 하나를 가지며 raw와 같은 35개 item record에
`LABEL_NAME`을 붙입니다. 설비마다 5개 label series가 있습니다.

| SVC_NAME | BASE_ITEM | LABEL_NAME |
| --- | --- | --- |
| 기동패턴 | 전류평균, 유효전력평균 | Stop, Loading, Unloading |
| SOH | 역률평균, 전류고조파평균, 전압고조파평균 | 정상, 주의, 경고 |

한 timestamp 안의 record는 모두 같은 label입니다. Label은 median 수십~수백 timestamp 동안 유지되는 구간으로
관측됩니다. Header에는 익명화된 회사 정보, 계약전력, `facility_name`, `facility_type_name`,
`facility_vendor`, `facility_year`, `facility_capacity`, `facility_volt`가 있습니다. 마스킹된 `KEPCO_INFO`는
profile에 기록하지 않습니다.

**Correspondence with raw.** Label `DEVICE_ID` 집합(보일러 14, 압출기 13)과 설비별 시간 범위는 raw와
일치합니다. Label record 수는 raw에서 member 내부 중복 extra record(대부분 1건)를 뺀 수와 같습니다. 보일러는
raw null(device 5702의 105건)도 없고, 압출기는 null을 유지합니다(2323의 11,856건, 2325의 35건). 보일러
device 7247의 label series 하나는 1,007,976건으로 다른 series보다 24건 적습니다. Record 단위 일치는 아직
검증하지 않았습니다(count·범위·device 기준 대응).

**Provider label method is unresolved.** 같은 설비 안에서 label별 BASE_ITEM 값 범위가 크게 겹칩니다. 예를 들어
보일러 211의 `Stop` 구간에도 전류평균이 최대 640까지 관측되고, SOH `정상`과 `경고`가 모두 역률 0..1 범위를
가집니다. 따라서 label은 해당 순간값의 단순 threshold로 보이지 않지만 산정 방법·기간·기준은 문서로
확인하지 못했습니다. SOH 경고 비율이 역률평균 series에서 매우 높은 점(보일러 약 86%)도 운영상 경고
빈도로 해석하지 않습니다.

**Provider annotation boundary.** AI-Hub label은 research path의 provider annotation입니다.

```text
ProviderAnnotation
  source           = AI-Hub dataset 239 labeling archive (sha256 above)
  annotation type  = 기동패턴 / SOH, with its BASE_ITEM
  value            = Stop, Loading, Unloading / 정상, 주의, 경고
  interval         = source-local TIMESTAMP span of consecutive equal labels
  provenance       = archive, member, device identifiers, provider method: unresolved
```

- Production path(OPC UA/FILE → Raw Evidence → Asset History → Analysis → Evidence → Finding → Review)의
  입력이 아닙니다. 실제 설비에는 이런 label이 없으며 모든 production capability는 label 없이 동작해야 합니다.
- `AssetHealth`, `OperatingState`, `OperationalFinding`, maintenance decision이나 verified ground truth로
  승격하지 않습니다. Provider annotation ≠ live sensor state ≠ asset health ≠ maintenance ground truth입니다.
- 쓰임은 research evaluation입니다: label 없이 만든 분석 결과를 provider annotation과 비교할 때, 비교
  대상이 provider annotation(방법 미확정)이었다고 명시합니다.
- Label ZIP은 raw measurement의 대체 source가 아닙니다. Raw evidence는 raw archive에서만 적재합니다.

**Metadata is not unit evidence.** `facility_volt=380`인 여러 설비의 선간전압평균이 약 225로 관측됩니다
(예: 5764, 7303, 7300). 정격 metadata가 측정점 전압과 일치한다고 가정하지 않습니다. `facility_capacity`의
단위도 공식 문서에는 kW로 설명되지만 유효전력평균 값(최대 약 2.6×10^5)과 같은 scale이 아닙니다.

**Empirical consistency (not a unit declaration).** 아래는 값 범위가 물리적 관계와 일치한다는 관측이며
source unit 문서가 아닙니다. Canonical mapping과 unit은 계속 `unresolved`입니다.

- 주파수: 대부분 59.7–60.1 (60 Hz 계통과 일치)
- 선간전압평균 / 상전압평균 ≈ 1.73 (삼상 √3 관계와 일치)
- 역률 계열: −1..1 (비율 scale과 일치, 백분율 아님)
- 유효전력평균: 정격 capacity와 scale이 달라 W/kW/scale factor를 판단할 수 없음

이 관측을 semantic binding으로 승격하려면 provider 문서 또는 계측기 사양 같은 독립 근거, 그리고
evidence level을 구분하는 versioned binding이 필요합니다.
