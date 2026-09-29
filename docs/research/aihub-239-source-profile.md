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
