# Prepared FILE Source Conformance Runbook

상태: prepared export/snapshot baseline · authorized organization-provided source 확보 시 실행

이 runbook은 조직이 허가한 **단일 asset CSV export/snapshot** 또는 같은 asset/measurement point의
**timestamped segment history**를 현재 canonical/application boundary에 연결할 수 있는지 검증하는 절차입니다.
Raw source를 repository에 복사하지 않고도 source identity, time basis, data quality, observation ordering과
feature projection compatibility를 확인하는 것이 목적입니다.

이 절차는 operational model validation, live inference, maintenance recommendation 또는 historian integration을
승인하는 절차가 아닙니다.

## 1. Preconditions

- source 접근 권한이 조직 정책에 따라 승인되어 있어야 합니다.
- credential, token, certificate, database password는 repository/document/result artifact에 기록하지 않습니다.
- raw CSV는 repository 밖의 local/authorized path에 둡니다.
- 한 CSV 파일은 한 asset의 한 segment를 나타내야 합니다.
- 여러 segment를 observation history로 묶을 때는 모두 같은 asset/measurement point 의미를 가져야 합니다.
- History ordering에는 explicit timestamp가 필요하며 filename 순서를 시간 의미로 사용하지 않습니다.
- 사용할 sensor column과 timestamp 또는 regular sampling rate를 source owner와 확인합니다.
- source owner가 제공한 quality flag, maintenance/configuration event, calibration 의미가 있으면 별도로 기록해
  현재 CSV baseline이 이를 보존할 수 있는지 검토합니다.

다음 중 하나라도 불명확하면 모델 실행으로 넘어가지 않습니다.

- asset identity
- sensor/channel meaning과 unit
- timestamp timezone 또는 sampling rate
- observation 시작/종료 의미
- failure/maintenance/censoring 의미가 필요한 prognostics use case

## 2. Local source validation

Regular sampling export 예시:

```bash
uv run --locked industrial-phm data validate-csv \
  --source /authorized/path/pump.csv \
  --asset-id pump-01 \
  --channel vibration_x \
  --channel vibration_y \
  --sampling-rate-hz 12800
```

Explicit timestamp와 declared rate를 함께 검증해야 하면 tolerance를 **명시적으로** 지정합니다.

```bash
uv run --locked industrial-phm data validate-csv \
  --source /authorized/path/pump.csv \
  --asset-id pump-01 \
  --channel vibration_x \
  --timestamp-column timestamp \
  --sampling-rate-hz 100 \
  --sampling-rate-tolerance-ratio 0.02 \
  --minimum-sample-count 100
```

Framework가 임의 tolerance를 정하거나 resampling하지 않습니다.

여러 prepared segment를 Operations observation history로 확인할 때는 각 파일을 같은 mapping으로 검증하고,
history directory를 지정합니다.

```bash
export INDUSTRIAL_PHM_OPERATIONS_HISTORY_DIRECTORY=/authorized/path/pump-history
export INDUSTRIAL_PHM_OPERATIONS_ASSET_ID=pump-01
export INDUSTRIAL_PHM_OPERATIONS_SOURCE_ID=file-export:pump-01
export INDUSTRIAL_PHM_OPERATIONS_MEASUREMENT_POINT_ID=drive-end-bearing
export INDUSTRIAL_PHM_OPERATIONS_CHANNELS=vibration_x,vibration_y
export INDUSTRIAL_PHM_OPERATIONS_TIMESTAMP_COLUMN=timestamp

uv run --locked --group research marimo run src/industrial_phm/apps/operations.py
```

각 CSV는 독립 source snapshot으로 SHA-256/byte size를 보존합니다. Application timeline은 recorded timestamp로
segment를 정렬하며 overlap/reverse segment를 차단합니다. Timeline ordering은 source observation history일
뿐 fault progression 또는 PHM trend를 뜻하지 않습니다.

## 3. PASS / WARN / failure interpretation

### PASS

최소 다음을 확인합니다.

- required channel과 time basis가 존재
- missing/non-numeric/non-finite sensor value 없음
- explicit timestamp가 strictly increasing
- source SHA-256과 byte size가 출력됨
- declared validation policy가 출력됨
- quality state = `PASS`

PASS는 **source structure가 현재 adapter contract를 통과했다는 뜻**입니다. Sensor가 건강하거나 model에
적합하다는 뜻이 아닙니다.

### WARN

`irregular-sampling` 또는 `sampling-rate-mismatch` warning은 source를 자동 수정하지 않습니다.

- original timestamp를 보존합니다.
- warning code와 observed deviation을 provenance로 유지합니다.
- source owner와 export/sampling metadata를 확인합니다.
- downstream algorithm이 regular sampling을 요구하면 그 요구를 별도 protocol에서 명시합니다.

### Failure

다음은 현재 baseline에서 blocking입니다.

- required column 누락
- missing/non-numeric/non-finite value
- duplicate/non-increasing timestamp
- mixed timezone awareness
- minimum sample count 미달
- invalid layout/time basis

Blocking source를 자동 보간·삭제·정렬해 통과시키지 않습니다.

## 4. Source identity evidence

검증 결과에서 최소 다음을 실행 기록에 보존합니다.

- source filename 또는 조직 내 비민감 source identifier
- SHA-256
- byte size
- asset id
- channel mapping
- timestamp column 또는 sampling rate
- minimum sample count
- sampling-rate tolerance가 있으면 그 값
- quality state / issue codes

Absolute local path, credential 또는 민감한 source content는 tracked evidence에 복사하지 않습니다.

CSV adapter는 하나의 byte snapshot에서 parsing, SHA-256과 byte size를 함께 계산합니다. 따라서 처리된 values와
기록된 digest는 같은 source snapshot을 가리킵니다.

## 5. Canonical / feature compatibility

현재 executable contract는 `tests/contract/test_field_csv_feature_path.py`와
`tests/integration/test_field_csv_observation.py`에서 다음 경로를 검증합니다.

```text
prepared FILE CSV
  -> CsvSensorAdapter
  -> CanonicalTimeSeries
  -> vibration-statistical-v1 feature projection
  -> source/quality/policy provenance preserved

timestamped prepared CSV segments
  -> per-segment validation / AssetObservationSummary
  -> recorded-time ordering
  -> AssetObservationTimeline
  -> latest observation + segment evidence in Operations
```

organization-provided source에서 이 경로를 사용할 때 dataset-specific split, reference population, threshold 또는 fault label을
임의로 만들지 않습니다.

## 6. Additional semantics review

첫 organization-provided source에서는 CSV 구조 검증과 별개로 다음을 확인합니다.

| 질문 | 현재 baseline에서의 처리 |
| --- | --- |
| vendor quality flag가 있는가? | 별도 semantics 검토 필요 |
| sensor replacement/calibration 이력이 있는가? | maintenance/configuration event 검토 필요 |
| 한 파일에 여러 asset이 섞이는가? | 현재 single-asset adapter 범위 밖 |
| direct historian/API access가 필수인가? | Path export로 반복 해결 불가할 때 source abstraction 재검토 |
| lifecycle 종료가 failure인가? | confirmed failure / observed end / right-censored를 구분 |
| right-censored RUL ground truth가 필요한가? | 현재 exact RUL target 범위 밖 |
| source-specific diagnosis label이 있는가? | evidence/protocol 없이 canonical label로 승격하지 않음 |

## 7. Stop conditions for new contract work

다음 요구가 구체적인 source에서 확인되면 현재 metadata/CSV adapter에 억지로 넣지 않고 별도 contract 변경으로
분리합니다.

- repeated multi-asset source ingestion
- vendor-specific quality state가 여러 pipeline 단계에서 공통 판단에 필요
- maintenance/configuration/calibration event가 analysis semantics에 직접 영향
- right-censored prognostics training/evaluation
- direct historian/DB/API access가 prepared export로 반복 해결되지 않음
- streaming ordering, watermark, late-arrival semantics가 실제 requirement가 됨

이 경우 먼저 concrete source example과 실패하는 conformance test를 확보하고 generic abstraction은 그 다음에
설계합니다.

## 8. Conformance completion criteria

첫 organization-provided prepared FILE source conformance는 다음이 모두 충족될 때 완료로 기록합니다.

1. authorized source가 repository 밖에서 validation됨
2. exact source byte identity가 기록됨
3. asset/channel/time mapping이 source owner 의미와 일치
4. blocking quality issue가 없음
5. warning이 있으면 의미와 처리 정책이 명시됨
6. canonical/feature projection에서 provenance가 보존됨
7. lifecycle/failure/censoring을 source owner가 확인한 의미보다 강하게 해석하지 않음
8. 현재 contract로 표현하지 못한 실제 요구가 있으면 별도 issue/PR boundary로 분리됨

이 완료 조건은 model accuracy, operational threshold, maintenance action validation을 포함하지 않습니다. 해당
capability는 source-specific evidence가 생긴 뒤 별도 protocol로 검증합니다.
