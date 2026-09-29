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

## Measurement dictionary

Raw ITEM_NAME은 channel identity입니다. 의미·단위는 provider 문서와 실제 데이터가 **둘 다** 뒷받침할 때만
`aihub-239-semantics-v1`(history metadata v3)에 기록합니다. 문서의 "평균"은 시간 평균이 아니라 **3상 평균**
(power는 실제로 3상 합)입니다. 1분 sample 안의 시간 집계 방식(순시값/구간 평균)은 문서에 유효·무효전력만
"순시값"으로 적혀 있고 나머지는 미확정입니다. Source timezone은 문서에 없어 계속 설정 가정입니다.

| Raw ITEM_NAME | Provider 문서 (§1.6.3) | 실제 데이터 검증 | semantics-v1 |
| --- | --- | --- | --- |
| R상무효전력 | kVar | √(P²+Q²) = V·I → **var** 스케일 (문서와 불일치) | unresolved |
| R상선간전압 | V (RS/ST/TS) | 선간/상 ≈ √3 | unresolved (R/S/T → pair 대응 미확정) |
| R상역률 | %, 진상/지상 부호 포함 | −1..1 **비율** (문서와 불일치) | unresolved |
| R상유효전력 | kW, 순시값 | P = V·I·PF → **W** 스케일 (문서와 불일치) | unresolved |
| R상전류 | A | √(P²+Q²) = V·I | **phase current, A** |
| R상전류고조파 | % THD | 독립 검증 없음 | unresolved |
| R상전압 | V (R/S/T상 전압) | 선간/상 ≈ √3 | **phase voltage, V** |
| R상전압고조파 | % THD | 독립 검증 없음 | unresolved |
| S상무효전력 | kVar | √(P²+Q²) = V·I → **var** 스케일 (문서와 불일치) | unresolved |
| S상선간전압 | V (RS/ST/TS) | 선간/상 ≈ √3 | unresolved (R/S/T → pair 대응 미확정) |
| S상역률 | %, 진상/지상 부호 포함 | −1..1 **비율** (문서와 불일치) | unresolved |
| S상유효전력 | kW, 순시값 | P = V·I·PF → **W** 스케일 (문서와 불일치) | unresolved |
| S상전류 | A | √(P²+Q²) = V·I | **phase current, A** |
| S상전류고조파 | % THD | 독립 검증 없음 | unresolved |
| S상전압 | V (R/S/T상 전압) | 선간/상 ≈ √3 | **phase voltage, V** |
| S상전압고조파 | % THD | 독립 검증 없음 | unresolved |
| T상무효전력 | kVar | √(P²+Q²) = V·I → **var** 스케일 (문서와 불일치) | unresolved |
| T상선간전압 | V (RS/ST/TS) | 선간/상 ≈ √3 | unresolved (R/S/T → pair 대응 미확정) |
| T상역률 | %, 진상/지상 부호 포함 | −1..1 **비율** (문서와 불일치) | unresolved |
| T상유효전력 | kW, 순시값 | P = V·I·PF → **W** 스케일 (문서와 불일치) | unresolved |
| T상전류 | A | √(P²+Q²) = V·I | **phase current, A** |
| T상전류고조파 | % THD | 독립 검증 없음 | unresolved |
| T상전압 | V (R/S/T상 전압) | 선간/상 ≈ √3 | **phase voltage, V** |
| T상전압고조파 | % THD | 독립 검증 없음 | unresolved |
| 누적전력량 | kWh, 3상 합 | 미검증 | unresolved |
| 무효전력평균 | kVar, 3상 평균 | = **sum**(R,S,T), var 스케일 (문서와 불일치) | unresolved |
| 상전압평균 | V, 3상 평균 | = mean(R,S,T 상전압) | **phase voltage, 3상 평균, V** |
| 선간전압평균 | V, 3상 평균 | = mean(3 선간), ≈ √3 × 상전압평균 | **line-to-line voltage, 3상 평균, V** |
| 역률평균 | %, 3상 평균 | |mean(R,S,T)|와 일치, 일부 member에서 부호 반대 | unresolved |
| 온도 | °C, 계측부하 온도 | 독립 검증 없음 | unresolved |
| 유효전력평균 | kW, 3상 평균 | = **sum**(R,S,T), W 스케일 (문서와 불일치) | unresolved |
| 전류고조파평균 | % THD, 3상 평균 | 대부분 mean(R,S,T)와 일치 | unresolved |
| 전류평균 | A, 3상 평균 | = mean(R,S,T 상전류) | **phase current, 3상 평균, A** |
| 전압고조파평균 | % THD, 3상 평균 | 대부분 mean(R,S,T)와 일치 | unresolved |
| 주파수 | Hz | 대부분 59.7–60.1 (60 Hz 계통) | **frequency, Hz** |

검증은 보일러 `SourceData_211/347/359`, 압출기 `SourceData_127/128`의 같은 timestamp record로 했습니다.
압출기 member는 대부분 timestamp에서 11개 집계 channel만 기록돼 상별 전력 관계는 보일러에서 확인했습니다.
Unresolved 항목은 문서 단위를 그대로 쓰지도, 관측 스케일로 조용히 바꾸지도 않습니다. 사용하려면 불일치를
설명하는 별도 근거와 versioned binding이 필요합니다.

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
- **Unresolved:** 물리 설비 identity, source timezone, 위 표의 unresolved 항목 단위, sample 내부 시간 집계.

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

새 적재는 metadata v3입니다. 위 표에서 확인된 항목만 `aihub-239-semantics-v1`의 의미·단위·근거를 갖고
나머지는 `observed_property=None`, 단위 unknown입니다. v2는 모든 항목이 미확정인 이전 형식이며, v1의
property_name은 legacy label로 표시합니다. 이미 적재된 v1/v2 JSON은 재작성하지 않습니다.
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

**Provider label method (documented).** 구축활용가이드 §2.4와 기술문서에 따르면 label은 1분 원시 데이터를
1시간 구간으로 나눠 크라우드 워커가 labeling tool에서 구간을 선택해 붙이고 전문 인력이 검수했습니다.

- 기동패턴: 설비별 실측값으로 정한 전류·전력 "정격"의 80% 이상 Loading, 10–80% Unloading, 10% 이하 Stop.
  Transient·glitch는 사람의 판단으로 앞뒤 상태에 붙입니다.
- SOH: 역률 80% 이상·전압고조파 3% 이하 정상, 60–80%·3–5% 주의, 60% 이하·5% 이상 경고. 한전 전력품질
  기준에 따른 **전력 품질 등급**이며 설비 열화나 고장 상태를 직접 판정한 것이 아닙니다.
- 검수 목표는 "사용패턴 분석 정확도 95%", "고장진단 정확도 90–95%"로 적혀 있지만 산출 방법은 없습니다.

Label별 BASE_ITEM 값 범위가 크게 겹치는 관측(예: 보일러 211 `Stop` 구간의 전류평균 최대 640)은 순간값
threshold가 아니라 1시간 구간 단위의 사람 판단이라는 문서 설명과 일치합니다. SOH 경고 비율이 역률평균
series에서 매우 높은 점(보일러 약 86%)은 데이터의 역률 부호·스케일 불일치와 함께 해석이 필요하며 운영상
경고 빈도로 해석하지 않습니다.

**Provider annotation boundary.** AI-Hub label은 research path의 provider annotation입니다.

```text
ProviderAnnotation
  source           = AI-Hub dataset 239 labeling archive (sha256 above)
  annotation type  = 기동패턴 / SOH, with its BASE_ITEM
  value            = Stop, Loading, Unloading / 정상, 주의, 경고
  interval         = source-local TIMESTAMP span of consecutive equal labels
  provenance       = archive, member, device identifiers, guideline v1.5 §2.4 method
```

- Production path(OPC UA/FILE → Raw Evidence → Asset History → Analysis → Evidence → Finding → Review)의
  입력이 아닙니다. 실제 설비에는 이런 label이 없으며 모든 production capability는 label 없이 동작해야 합니다.
- `AssetHealth`, `OperatingState`, `OperationalFinding`, maintenance decision이나 verified ground truth로
  승격하지 않습니다. Provider annotation ≠ live sensor state ≠ asset health ≠ maintenance ground truth입니다.
- 쓰임은 research evaluation입니다: label 없이 만든 분석 결과를 provider annotation과 비교할 때, 비교
  대상이 provider annotation(1시간 구간 사람 labeling)이었다고 명시합니다.
- Label ZIP은 raw measurement의 대체 source가 아닙니다. Raw evidence는 raw archive에서만 적재합니다.

**Metadata is not unit evidence.** `facility_volt=380`인 여러 설비의 선간전압평균이 약 225로 관측됩니다
(예: 5764, 7303, 7300). 정격 metadata가 측정점 전압과 일치한다고 가정하지 않습니다. `facility_capacity`의
단위도 공식 문서에는 kW로 설명되지만 유효전력평균 값(최대 약 2.6×10^5)과 같은 scale이 아닙니다.

## Provider documentation

AI-Hub 로그인으로 받은 문서 두 개를 근거로 사용합니다(local `data/raw/aihub/239/docs/`, Git 제외).

| 문서 | SHA-256 |
| --- | --- |
| 전력 설비 에너지 품질 AI데이터 구축·활용 가이드라인 v1.5 (2021-03-23, 33쪽) | `dfad9cd6d9451f571048813ae394923faec165519cc6eab84babee9c2f66560a` |
| 테크니컬 리포트: 전력 설비 에너지 품질 (18쪽) | `6577c2f682ef44e932b1fa7d182dca9181d9f668bfb7b2af4e197547f3867b44` |

문서로 확인된 사실: 계측기는 Mobile Energy Meter, 수집 주기 1분, 설비당 약 1개월, 35개 항목의 단위 표
(§1.6.3), 설비 key는 `DEVICE_ID`+`DEVICE_BD_ID`, `facility_capacity`는 kW 정격, 전력량·유효전력·역률
정밀도 목표 1.0%(IEC 61850 기준으로 기재). 계측기 모델, timezone, 원시 데이터 자동 필터링 규칙은 없습니다.
