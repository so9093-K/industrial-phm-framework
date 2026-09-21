# XJTU-SY RUL v1 Held-out Benchmark Execution Runbook

상태: execution procedure frozen · 절차대로 1회 실행 완료 (§8)

이 runbook은 validation-selected temporal LSTM을 fold-1 held-out bearing에 적용하는 RUL v1 마지막 numerical
execution 절차를 고정합니다. Selection과 uncertainty decision은
[`xjtu-rul-v1-finalization.md`](xjtu-rul-v1-finalization.md)가 소유합니다.

## 1. Preconditions

Benchmark implementation이 merge된 clean `main` checkout에서만 실행합니다.

```bash
git status --short
git rev-parse HEAD
```

- tracked working tree가 clean이어야 합니다.
- exact 40-character revision을 기록합니다.
- prepared XJTU-SY source는 repository 밖 local data path를 사용합니다.
- benchmark 결과를 보기 전에 target/model/evaluation/lifecycle boundary를 변경하지 않습니다.

## 2. Source validation

```bash
uv run industrial-phm data validate xjtu-sy \
  --source data/interim/xjtu-sy/source
```

complete local source profile이 PASS하지 않으면 benchmark를 실행하지 않습니다.

`--source`는 environment-local prepared source root이며 operating-condition 디렉터리를 직접 포함하는 경로를
가리킵니다. 실제 경로는 환경마다 다르므로 위 예시 경로를 그대로 쓰지 말고 준비된 root를 지정합니다. 이
값은 protocol scope가 아니라 실행 환경 설정입니다.

## 3. Frozen scope

```text
fit:
  Bearing1_3 Bearing1_4 Bearing1_5
  Bearing2_3 Bearing2_4 Bearing2_5
  Bearing3_3 Bearing3_4 Bearing3_5

held-out benchmark:
  Bearing1_1 Bearing2_1 Bearing3_1

selected method:
  xjtu-sy-rul-lstm-fold-1-v1

target:
  N-k acquisition intervals
  no clipping
  no target normalization

sequence:
  length 8
  stride 1
  right-edge alignment

uncertainty:
  unsupported/not validated in RUL v1
```

Held-out bearing은 project history에서 기존 anomaly/robustness 연구에 노출된 적이 있으므로
`pristine external holdout`이나 `external validation`으로 표현하지 않습니다.

## 4. Independent deterministic executions

Canonical tracked result path에 바로 쓰지 않고 임시 output 두 개로 독립 실행합니다.

```bash
REVISION="$(git rev-parse HEAD)"

uv run industrial-phm experiment rul-benchmark xjtu-sy \
  --source data/interim/xjtu-sy/source \
  --output /tmp/xjtu-rul-benchmark-run-1.json \
  --code-revision "$REVISION"

uv run industrial-phm experiment rul-benchmark xjtu-sy \
  --source data/interim/xjtu-sy/source \
  --output /tmp/xjtu-rul-benchmark-run-2.json \
  --code-revision "$REVISION"
```

두 실행 사이에서 source, environment, revision, configuration을 변경하지 않습니다.

## 5. Reproducibility check

```bash
cmp /tmp/xjtu-rul-benchmark-run-1.json /tmp/xjtu-rul-benchmark-run-2.json

python - <<'PY'
from hashlib import sha256
from pathlib import Path

for path in (
    Path("/tmp/xjtu-rul-benchmark-run-1.json"),
    Path("/tmp/xjtu-rul-benchmark-run-2.json"),
):
    print(path, sha256(path.read_bytes()).hexdigest())
PY
```

Byte-identical하지 않으면 어떤 run도 authoritative evidence로 선택하지 않습니다. 원인을 조사하고 execution
contract 문제를 별도 변경으로 해결한 뒤, 새 clean revision에서 절차를 다시 시작합니다.

## 6. Evidence review

먼저 shared inspection read model로 schema/protocol drift를 검증합니다.

```bash
uv run industrial-phm experiment inspect /tmp/xjtu-rul-benchmark-run-1.json
uv run industrial-phm experiment inspect /tmp/xjtu-rul-benchmark-run-2.json
```

두 artifact 모두 같은 stage vocabulary와 benchmark scope를 통과해야 합니다.

Result에서 최소 다음을 확인합니다.

- `provenance.code_revision`이 execution revision과 정확히 일치
- evidence class = `protocol-frozen-retrospective-benchmark-evidence`
- benchmark population = `Bearing1_1 / Bearing2_1 / Bearing3_1`
- selected method = frozen temporal LSTM
- `operational_primary_method_id = null`
- acquisition 8..N right-edge prediction coverage
- bearing별 MAE / RMSE / signed error / normalized MAE
- equal-bearing aggregate
- early / middle / late lifecycle-position error와 각 prediction count
- prediction interval / uncertainty calibration이 unsupported
- validated physical failure threshold / field validation / maintenance recommendation이 unsupported

Lifecycle thirds는 complete recorded lifecycle 기준으로 고정된 evaluation-only diagnostic이며 sequence prefix 때문에
boundary를 다시 나누지 않습니다.

## 7. Promotion

두 output이 byte-identical이고 evidence review가 통과하면 run 1을 다음 canonical path로 승격합니다.

```text
docs/research/results/xjtu-sy-rul-lstm-fold-1-benchmark-v1.json
```

PR evidence note에는 다음을 기록합니다.

- execution revision
- prepared source validation 결과
- run 1 / run 2 SHA-256
- byte-identical 여부
- point metric summary
- lifecycle-position summary
- project-history limitation
- unsupported capability boundary

## 8. Executed run

이 절차는 revision `2ae41acc16c45bf922f3b6ad8a228103d16d0982`에서 한 번 실행됐습니다. 실행 기록과 숫자는
[`xjtu-rul-v1-finalization.md`](xjtu-rul-v1-finalization.md) §7에 있습니다.

## 9. No post-benchmark retuning

이 artifact를 본 뒤 같은 RUL v1에서 다음을 변경하지 않습니다.

- target definition/clipping
- train/test bearing assignment
- feature schema
- sequence length/alignment
- LSTM configuration
- lifecycle thirds boundary
- primary point metric
- selection rule
- uncertainty policy

추가 연구가 필요하면 v2 protocol/configuration으로 분리하고 이 benchmark를 새 unbiased evidence로 재사용하지
않습니다.
