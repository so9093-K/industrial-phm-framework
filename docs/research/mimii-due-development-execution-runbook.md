# MIMII DUE Development Evidence Execution Runbook

상태: authoritative development execution procedure

이 문서는 이미 고정된
[`mimii-due-experiment-protocol.md`](mimii-due-experiment-protocol.md)을 실제 local MIMII DUE prepared source에
적용해 version-controlled numerical evidence를 생성할 때 따르는 실행 절차입니다.

이 문서는 protocol을 바꾸지 않습니다. Representation, preprocessing, model, scoring, evaluation과 capability
의미는 protocol과 packaged experiment configuration이 소유합니다.

목표는 다음 네 가지입니다.

1. 실행 source가 검증된 MIMII DUE v1.01 prepared profile과 일치하는지 다시 확인
2. authoritative output이 clean Git revision과 packaged dataset record provenance를 보존하는지 확인
3. 같은 revision/configuration/source에서 두 번 실행해 byte-identical deterministic result를 확인
4. inspection을 통과한 artifact만 repository evidence로 승격

## 1. 실행 전 조건

다음 조건이 모두 충족되어야 합니다.

- 현재 checkout은 numerical evidence에 사용할 정확한 commit입니다.
- tracked working tree가 clean입니다.
- local MIMII DUE prepared source가 repository 밖 또는 gitignored data workspace에 존재합니다.
- source root는 dataset-specific validator와 Adapter가 소비하는 prepared source root입니다.
- numerical result를 보기 전에 protocol/configuration 변경이 모두 merge되어 있습니다.
- sections 03–05 evaluation test/ground truth는 이 development execution에 사용하지 않습니다.

현재 Git revision을 고정합니다.

```bash
REV="$(git rev-parse HEAD)"
printf '%s\n' "$REV"
git status --porcelain --untracked-files=no
```

두 번째 명령의 출력은 비어 있어야 합니다.

`experiment mimii-development` CLI도 실행 직전에 declared `--code-revision`과 current `HEAD`가 일치하고
tracked working tree가 clean인지 다시 검증합니다.

## 2. Local source 위치 고정

예시는 repository-local gitignored prepared source를 사용합니다.

```bash
SOURCE="data/interim/mimii-due/source"
test -d "$SOURCE"
```

다른 local 위치를 사용해도 되지만, 두 deterministic run에서 같은 source root를 사용해야 합니다.

## 3. Full source validation

Authoritative execution 전에 sampled validation이 아니라 모든 WAV header를 확인합니다.

```bash
uv run industrial-phm data validate mimii-due \
  --source "$SOURCE" \
  --full
```

통과 기준:

- profile compatibility = PASS
- visible clip population이 verified profile과 일치
- 36,433 WAV clips
- mono
- signed 16-bit PCM
- 16,000 Hz
- 160,000 frames / 10 seconds

이 단계는 raw archive checksum을 새로 계산했다고 주장하지 않습니다. Zenodo record/version/license와 archive-level
verification evidence는 [`mimii-due-source-profile.md`](mimii-due-source-profile.md)가 소유합니다.

## 4. 두 개의 독립 output 경로 준비

첫 결과를 바로 `docs/research/results/`에 쓰지 않습니다.

```bash
RUN1="/tmp/mimii-due-development-run-1.json"
RUN2="/tmp/mimii-due-development-run-2.json"

rm -f "$RUN1" "$RUN2"
```

이렇게 하면 첫 실행 결과를 본 뒤 tracked artifact를 수정하면서 두 번째 실행 의미를 오염시키는 것을 피할 수
있습니다.

## 5. 첫 development execution

```bash
uv run industrial-phm experiment mimii-development mimii-due \
  --source "$SOURCE" \
  --output "$RUN1" \
  --code-revision "$REV"
```

CLI가 최소 다음 boundary를 출력해야 합니다.

- 5 machine types × 3 sections
- source_test + target_test scoring
- labels = evaluator edge only
- sections 03–05 excluded
- threshold/calibration = none
- clean tracked checkout revision verification
- 15 section models

첫 실행 후 numerical 값만 보고 protocol, representation, model parameter 또는 evaluator를 수정하지 않습니다.

## 6. 두 번째 deterministic execution

같은 checkout, source, configuration과 command로 두 번째 output을 생성합니다.

```bash
uv run industrial-phm experiment mimii-development mimii-due \
  --source "$SOURCE" \
  --output "$RUN2" \
  --code-revision "$REV"
```

두 실행 사이에 tracked file을 수정하면 CLI revision guard가 두 번째 실행을 차단해야 합니다.

## 7. Byte-for-byte reproducibility 확인

Deterministic JSON writer를 사용하므로 두 output은 byte-identical이어야 합니다.

```bash
cmp "$RUN1" "$RUN2"
```

`cmp`가 non-zero를 반환하면 authoritative evidence로 승격하지 않습니다.

SHA-256도 기록합니다.

```bash
uv run python - "$RUN1" "$RUN2" <<'PY'
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

for value in sys.argv[1:]:
    path = Path(value)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"{digest}  {path}")
PY
```

두 digest가 같아야 합니다.

## 8. Result inspection

두 output이 동일한 뒤 첫 artifact를 공통 inspection reader로 검증합니다.

```bash
uv run industrial-phm experiment inspect "$RUN1"
```

최소 확인 항목:

### Source

- Dataset = mimii-due
- Dataset version = zenodo-v1.01
- Source provider = manual
- Source URL = Zenodo record 4740355
- Citation DOI = 10.5281/zenodo.4740355
- Verified source profile = 36,433 WAV clips
- Source group = dev
- Sections = 00, 01, 02

### Population / Model

- Section models = 15
- model unit = machine-type-x-section
- complete section train population만 preprocessing/reference/model fit에 사용
- target-domain normal train은 section당 3 clips
- score semantics = higher-is-more-anomalous

### Evaluation

- 30 machine × section × domain strata
- ROC AUC
- standardized pAUC, max FPR = 0.1
- source/target/overall harmonic summaries
- MIMII domain-shift summary
- DCASE official score = false
- selection or threshold calibration = none

### Capability

Available capability와 unsupported capability가 protocol과 일치해야 합니다.

특히 다음을 결과에서 생성하거나 추론하지 않습니다.

- thresholded normal/fault state
- fault diagnosis
- Health Indicator
- RUL
- maintenance priority/recommendation

## 9. Repository evidence로 승격

두 output이 byte-identical이고 inspection이 통과한 뒤에만 authoritative path로 복사합니다.

```bash
ARTIFACT="docs/research/results/mimii-due-iforest-domain-shift-development-v1.json"
cp "$RUN1" "$ARTIFACT"

uv run industrial-phm experiment inspect "$ARTIFACT"
git diff -- "$ARTIFACT"
```

Artifact 내부 `provenance.code_revision`은 `$REV`와 일치해야 합니다.

Artifact 내부 `source_scope.dataset_record`는 packaged `mimii-due` manifest와 일치해야 합니다.

## 10. Evidence note에 기록할 항목

Artifact를 commit하는 PR에는 최소 다음을 기록합니다.

- execution Git revision
- prepared source validation PASS
- full source validation 사용 여부
- run 1 SHA-256
- run 2 SHA-256
- byte-identical 여부
- result artifact path
- inspection PASS
- source-domain AUC/pAUC harmonic summary
- target-domain AUC/pAUC harmonic summary
- overall AUC/pAUC harmonic summary
- mimii_domain_shift_summary
- DCASE official score가 아님
- unsupported capability
- development evidence이며 sections 03–05 external evaluation이 아니라는 점

숫자를 보고 해석을 추가할 수는 있지만, protocol에서 지원하지 않는 diagnosis/health/RUL claim으로 승격하지 않습니다.

## 11. Reproducibility 실패 시

두 output이 다르면 먼저 다음을 조사합니다.

1. Git revision이 실제로 동일했는가
2. tracked working tree가 두 실행 모두 clean이었는가
3. 같은 prepared source root를 사용했는가
4. packaged lock/environment가 동일했는가
5. source files가 실행 사이에 변경되지 않았는가
6. nondeterministic ordering 또는 model randomness가 새로 유입됐는가

이 경우 두 결과 중 하나를 임의로 authoritative artifact로 선택하지 않습니다.

원인을 수정하는 변경은 별도 PR과 CI를 거친 뒤 새 clean `main` revision에서 두 실행을 처음부터 다시 수행합니다.

## 12. Development review 이후

Authoritative development artifact가 기록된 뒤 다음 decision만 가능합니다.

### Freeze

V1 configuration을 변경하지 않고 sections 03–05 external evaluation으로 이동합니다.

### Explicit v2

Development evidence에서 configuration 변경 필요가 확인되면 새 protocol/configuration version을 먼저 작성합니다.

V1 development artifact는 삭제하지 않으며 v2의 fresh/unbiased evidence라고 재해석하지 않습니다.
