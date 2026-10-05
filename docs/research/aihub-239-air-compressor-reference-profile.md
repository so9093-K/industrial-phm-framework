# AI-Hub 239 air-compressor reference asset profile

상태: #403 reference asset 기준선

이 문서는 Operations vertical을 검증할 **하나의 한국 제조 reference asset**을 사람이 이해할 수 있는 형태로
고정합니다. Archive 전체의 schema·품질·relation 사실은 [source profile](aihub-239-source-profile.md)이
소유하고, 이 문서는 그중 대표 device와 구간, 사용자에게 설명하는 방식, 주장 경계만 소유합니다.

갱신 조건: 대표 device·구간·사용 channel·semantics version이 바뀔 때. 폐기 조건: 다른 reference asset으로
교체할 때(교체 이유를 Issue에 남기고 이 문서를 새 문서로 대체합니다).

## 1. 설비군과 선택 이유

**공기압축기**는 provider가 산업 대표 설비 10종 중 범용 설비 4종(펌프/일반모터, 공조설비, 공기압축기,
공작기계)으로 분류한 설비군입니다(구축 가이드라인 v1.5 §1.5.2, 전문가 검토로 선정).

보일러·압출기는 source profiling, semantics-v2, replay, fault harness 개발에 이미 사용했으므로, 개발에 쓰지
않은 설비군에서 현재 abstraction이 그대로 성립하는지 확인하기 위해 선택했습니다. 후보 비교(공기압축기 vs
펌프/일반모터)와 선정 근거는 #403 comment에 있습니다. 근거는 versioned tooling으로 재현 가능한 profile
결과와 설비군 자체의 설명 가능성입니다.

- 단일 설비 종류라 "공기압축기 → 3상 전원 부하 → R/S/T 전류 관측"으로 설명할 수 있습니다.
- 현재 vertical의 핵심 입력인 R/S/T 상전류 관계가 이 archive에서 안정적입니다. 전류평균 = mean(R,S,T)이
  99.7% 성립하고, 상전류를 unresolved로 두는 member 예외는 `SourceData_135` 하나입니다.
- Training/raw 72 device, 84,685,346 records로 데이터량이 충분합니다.

## 2. 사용자에게 설명하는 방식

설비 관리자·정비 엔지니어에게는 다음처럼 설명합니다.

> 공장의 압축공기를 만드는 공기압축기 한 대의 3상 전원 계측 기록입니다. 설비에 들어가는 R/S/T 세 상의
> 전류와 전압, 주파수를 1분마다 기록했습니다. 이 화면은 기록된 데이터를
> 재생(replay)한 것이며 현재 공장에서 실시간으로 들어오는 값이 아닙니다.

- 표시 이름(**설정값**): `공기압축기 · reference asset`. 보조 표기는 `AI-Hub 239 device 1338`입니다.
  Provider identity가 아니라 이 프로젝트가 정한 이름입니다.
- 제안 identifier(**설정값**, replay 연결 단계에서 확정): source `aihub239-replay-air-compressor-1338`,
  asset `aihub-air-compressor-1338`. 보일러 demo(`aihub-boiler-2297`)와 같은 규칙입니다.

## 3. 대표 device와 구간

| 항목 | 값 |
| --- | --- |
| Archive | Training/raw `3.공기압축기.zip` (filekey 44031, SHA-256 `ffde668b…3119`) |
| Member | `3.공기압축기/SourceData_16.json` |
| `DEVICE_ID` / `DEVICE_BD_ID` | 1338 / 1 |
| 데이터 기간 | 32일(local `2020-10-22 00:00:22`–`2020-11-22 23:59:35`), 43,135 timestamp, 1,509,725 records |
| 품질 | 35채널 완전 timestamp 100%, 60초 cadence 99.98%, null·중복·충돌 0 |
| semantics-v3 | member 예외 아님(모든 confirmed channel이 확정) |
| **Replay 구간** | local `2020-11-16 04:00:00`–`10:00:00`(종료 미포함), 360 timestamp, 모두 60초 간격 |

선정 기준은 semantics-v3 예외가 아닌 58개 member 중 다음 다섯 가지입니다.

1. 35채널 완전 timestamp 100%
2. 60초 cadence 99.9% 이상
3. null·중복·충돌 0
4. 정지 timestamp 비율 10–70%(정지와 운전이 모두 있음)
5. 기록 기간 20일 이상

다섯 조건을 모두 만족한 member는 `SourceData_16` 하나였습니다. 중복·충돌을 1–2건까지 허용하면
`SourceData_465`(device 5049), `17`(1337), `78`(1307)이 다음 후보입니다. 정지 판정은 relation profile의
low-signal(전류 < 1 A) 집계를 사용합니다.

Replay 구간에는 다음이 순서대로 들어 있습니다.

| Local time | 관측 |
| --- | --- |
| 04:00–05:54 | 운전. 전류평균이 약 70 A와 약 40 A 두 수준을 오갑니다 |
| 05:54 | 상전류가 0이 됩니다(정지) |
| 05:54–08:34 | 정지. 상전압 약 222 V와 주파수 약 59.86 Hz는 계속 기록됩니다 |
| 08:34 | 상전류가 다시 나타납니다(재기동) |
| 08:34–10:00 | 운전 |

구간 안에서 운전 200개, 정지 160개 timestamp입니다. 운전 중 3상 전류 불평형은 구간 선정을 위한 탐색
계산으로 median 4.6%, p95 6.8%였습니다. 이 값은 Operations E2E에서 3상 불평형 capability 결과로 다시
확인합니다.

Device 1338은 32일 동안 평일에는 연속 운전하고 주말에는 정지하는 주간 패턴을 보입니다. 또
`2020-10-31 07:59:22`부터 `2020-11-02 09:05:06`까지 약 49시간 기록이 없습니다. 이 공백은 이후 gap 표시
검증에 쓸 수 있지만 첫 replay 구간에는 넣지 않았습니다. Validation/raw의 같은 device(`SourceData_16`)는
`2020-11-23`–`2020-11-26`으로 이어지는 기간입니다.

## 4. 사용 channel과 semantics

| Channel | semantics-v3 | 이 reference에서의 용도 |
| --- | --- | --- |
| R/S/T상전류, 전류평균 | phase current, A (확정) | 운전/정지, 3상 전류 불평형 |
| R/S/T상전압, 상전압평균 | phase voltage, V (확정) | 전원 상태, 3상 전압 불평형 |
| 선간전압평균 | line-to-line voltage, V (확정, 이 member는 예외 아님) | 보조 표시 |
| 주파수 | frequency, Hz (확정) | 계통 상태 |
| 전력·역률·전력량·고조파·온도 | unresolved | raw 값만 표시하고 의미·단위는 주장하지 않음 |

## 5. Provider가 말하는 것 / raw가 보여주는 것 / 우리가 설정한 것

**Provider 문서** (구축 가이드라인 v1.5, 기술 리포트):

- 공기압축기는 범용 설비 4종 중 하나이며, 계획 구축 설비 수는 120대입니다.
- Mobile Energy Meter를 크라우드 소싱 방식으로 설치해 1분 주기로 수집했습니다.
- 라벨은 두 종류입니다. 에너지 사용패턴(Loading/Unloading/Stop, 전류평균·유효전력평균 기준)과
  설비 SOH(정상/주의/경고, 역률평균·전압/전류고조파평균 기준)입니다.
- 설비 정보와 업체 정보 metadata는 별도 데이터로 구축됐습니다.

**Raw data** (이 archive에서 관측):

- Training/raw에는 72 device가 있습니다. Root에는 `DEVICE_ID`, `DEVICE_BD_ID`만 있고 설비 정보
  metadata는 없습니다.
- 운전 중 전류가 두 수준을 오가고 정지 중에도 전압이 기록되며, 평일 운전·주말 정지 패턴이 보입니다.

**우리가 설정한 것**:

- 표시 이름, source/asset identifier, replay 구간.
- Timezone `Asia/Seoul`(normalization 가정이며 source fact가 아님).
- Replay publish interval, OPC UA DataChange cadence, deadband는 reference configuration이며 dataset
  timing이 아닙니다.

## 6. 주장할 수 있는 것 / 주장하면 안 되는 것

**주장할 수 있는 것**

- "AI-Hub 239 공기압축기 device 1338의 기록된 전력 데이터를 재생한 것"
- 선택 구간의 상전류·상전압·주파수 값과 그 semantics-v3 의미·단위
- 상전류가 0인 구간과 0이 아닌 구간이 있다는 관측
- 3상 전류·전압 불평형 계산 결과와 그 계산 근거

**주장하면 안 되는 것**

- Device 1338이 특정 물리 설비라는 것. Physical asset identity는 unresolved입니다.
- Source timezone. 설정 가정입니다.
- 전류 수준이 load/unload **제어 상태**라는 것. 두 수준은 관측이지만 raw만으로 압축기의 제어 상태를
  확정하지 않습니다. Provider의 Loading/Unloading/Stop 라벨도 설비별 실측 기준의 annotation입니다.
- 전류 불평형 = 설비 고장 또는 열화
- Provider SOH 등급(정상/주의/경고) = 정비 경보
- Replay = 현재 공장의 실시간 센서
- 데이터 수신 = 설비 정상. 정지 중에도 전압은 기록됩니다.
- 이 설비의 정비 이력, 고장, 수명(RUL)

## 7. 이후 단계에서 확인할 것

- Operations는 asset 표시 이름 개념 없이 `asset_id`를 그대로 보여줍니다. 기본 화면이 기술 ID로 시작하는지는
  #403의 UX gap 단계에서 이 asset으로 확인합니다.
- 정지 중 전압은 계속 들어오고 상전류만 0이 되는 구간에서 Monitor/Signals가 "수신 중"과 "운전 중"을 혼동하지
  않는지 확인합니다.
