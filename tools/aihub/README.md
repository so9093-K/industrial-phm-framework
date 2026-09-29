# AI-Hub acquisition tooling

이 디렉터리는 AI-Hub 공개 데이터의 **개발/연구용 local acquisition**을 재현하기 위한 tooling입니다.
`src/industrial_phm`의 runtime capability가 아니며 framework code는 이 디렉터리를 import하지 않습니다.

현재 preset은 dataset `239`의 실제 `aihubshell` file inventory를 기준으로 한 최소 bootstrap selection만
소유합니다. 실제 원본 ZIP, API key, local manifest는 repository에 commit하지 않습니다.

## Local configuration

Repository root의 `.env.example`을 `.env`로 복사하고 필요한 값을 채웁니다.

```bash
cp .env.example .env
```

```text
AIHUB_APIKEY=<local key>
AIHUBSHELL_PATH=/home/user/aihubshell
INDUSTRIAL_PHM_DATA_DIR=/home/user/industrial-phm-data
```

`AIHUB_APIKEY`는 process environment 또는 `.env`에서 읽습니다. AI-Hub 공식 `aihubshell`의 download mode가
`-aihubapikey` argument를 요구하므로 다운로드 subprocess에는 해당 argument로 전달합니다. Tool 자체는 key를
출력하거나 preset, inventory JSON, local manifest에 기록하지 않으며 child environment에는 key를 중복 전달하지
않습니다. Process environment에 이미 설정된 값이 있으면 `.env`가 덮어쓰지 않습니다.

공식 shell 계약상 다운로드 실행 중에는 운영체제의 process argument 조회에서 key가 보일 수 있으므로 공유
host에서는 process visibility 정책을 함께 확인합니다.

`AIHUBSHELL_PATH`가 비어 있으면 `PATH`, 그다음 `~/aihubshell` 순서로 실행 파일을 찾습니다. Tool이
실행 파일을 자동 설치하거나 repository에 복사하지는 않습니다.

`INDUSTRIAL_PHM_DATA_DIR`는 기존 project data-root 환경변수를 재사용합니다. 지정하지 않으면
`data/raw`를 사용합니다.

## Commands

Remote inventory를 갱신합니다. 이 명령은 vendor file tree를 조회하지만 dataset payload를 다운로드하지
않습니다.

```bash
uv run python -m tools.aihub.cli inventory 239
```

현재 bootstrap selection과 예상 용량을 network I/O 없이 확인합니다.

```bash
uv run python -m tools.aihub.cli plan 239 --preset bootstrap
```

현재 preset은 `boiler`(Training/raw 보일러 `44033`), `extruder`(Training/raw 압출기 `44035`),
`bootstrap`(두 archive 모두)을 제공합니다. AI-Hub file tree의 용량 표시는 반올림된 값이므로 plan의
합계는 근사치입니다.

명시적으로 다운로드합니다.

```bash
uv run python -m tools.aihub.cli download 239 --preset bootstrap
```

원본 ZIP은 다음과 같이 보존합니다.

```text
$INDUSTRIAL_PHM_DATA_DIR/
└── aihub/
    └── 239/
        ├── archives/
        │   └── training/
        │       └── raw/
        │           ├── 5.보일러.zip
        │           └── 7.압출기.zip
        ├── inventory/
        │   ├── file-tree.txt
        │   └── inventory.json
        └── local-manifest.json
```

Tool은 vendor ZIP을 자동으로 풀지 않습니다. `aihubshell`이 내부 transport TAR/part를 처리한 뒤 남긴
선택 ZIP만 normalized archive 위치로 옮깁니다.

이미 local archive가 있는 경우 먼저 expected archive 경로로 옮긴 뒤 local SHA-256 provenance를
명시적으로 기록할 수 있습니다.

```bash
uv run python -m tools.aihub.cli verify 239 --preset bootstrap
```

Publisher checksum이 preset에 없으므로 `verify`는 upstream authenticity를 주장하지 않습니다. 최초 실행은
현재 local bytes의 SHA-256을 `local-manifest.json`에 기록하고, 이후 실행은 그 local provenance와의 일치
여부를 검사합니다. 이미 보일러만 받아 둔 경우에는 `--preset boiler`처럼 개별 preset으로 먼저 등록할 수
있습니다.

## Boundaries

- CI와 기본 pytest suite는 AI-Hub endpoint에 접속하거나 대용량 payload를 다운로드하지 않습니다.
- API key, `.env`, vendor archive, generated inventory/local manifest는 commit 대상이 아닙니다.
- preset은 acquisition selection metadata이며 아직 framework dataset registry의 canonical manifest가
  아닙니다.
- dataset-specific parsing, measurement semantics, Asset History integration은 별도 변경으로 다룹니다.

## Local power-data profiling and history

Acquisition은 위 CLI가 담당하고, 아래 명령은 이미 받은 ZIP만 읽습니다. 실행 환경은 다음으로 준비합니다.

```bash
uv sync --locked --extra aihub --extra history --group research
uv run --no-sync python -m tools.aihub.profile \
  data/raw/aihub/239/archives/training/raw/5.보일러.zip \
  --output artifacts/aihub-239/boiler-profile.json
uv run --no-sync python -m tools.aihub.profile \
  data/raw/aihub/239/archives/training/raw/7.압출기.zip \
  --output artifacts/aihub-239/extruder-profile.json
```

Profiler는 ZIP/member를 stream하고 임시 SQLite에서 중복·cadence를 계산하므로 전체 JSON을 메모리에
올리지 않습니다. 상세 결과는 `artifacts/`에 두고 검증된 사실과 조사 범위만
[source profile](../../docs/research/aihub-239-source-profile.md)에 남깁니다.

이력 적재에는 명시적 binding JSON이 필요합니다. 다음은 **개발용 예시**이며 물리 설비 identity와
source timezone을 확인했다는 주장이 아닙니다. 실제 적용에는 확인된 근거 또는 사용자가 선택한 가정을
기록합니다. `.env`나 API key는 이 파일에 넣지 않습니다.

```json
{
  "source_id": "aihub239-boiler",
  "asset_id": "research-boiler-2297",
  "device_id": "2297",
  "device_board_id": "1",
  "timezone": "Asia/Seoul",
  "identity_evidence": "Explicit development grouping; physical asset identity unverified",
  "timezone_evidence": "Explicit normalization assumption; source timezone unverified",
  "version": "research-v1"
}
```

이를 `artifacts/aihub-239/boiler-binding.json`에 저장한 뒤 작은 구간을 적재합니다. 선택 시각은
offset 없는 **원본 local time**이고 종료 시각은 미포함입니다.

```bash
uv run --no-sync python -m tools.aihub.history \
  data/raw/aihub/239/archives/training/raw/5.보일러.zip \
  --member '5.보일러/SourceData_211.json' \
  --binding artifacts/aihub-239/boiler-binding.json \
  --start 2020-11-13T00:00:00 --end 2020-11-13T01:00:00 \
  --ducklake-catalog artifacts/operations/history/catalog.sqlite \
  --ducklake-data artifacts/operations/history/data
uv run --no-sync marimo run apps/operations.py
```

Operations의 **Assets → Asset → Measurement History → 이력 조회**에서 추세와 provenance를 확인합니다.
압출기는 별도 source/asset binding(device 2223/board 1), member `7.압출기/SourceData_127.json`,
local range `2020-11-01T00:00:00`–`2020-11-01T01:00:00`으로 같은 경로를 사용할 수 있습니다.

Importer는 2,000개 단위 commit을 사용합니다. 동일 입력/설정의 재실행은 기존 commit을 복구하지만,
다른 범위나 변경된 binding이 기존 raw identity와 겹치면 명시적으로 실패합니다. 오류 이전 batch는
보존되므로 같은 명령으로 재실행합니다. 이 명령은 CSV Source 등록이나 collector start를 수행하지 않습니다.

## Observed macOS vendor-shell issue

공식 `aihubshell` v0.6의 `escaped_prefix=$(printf '%q' "$prefix")`가 macOS 기본 Bash에서 한글
filename을 shell-quoted 문자열로 바꿔 `find -name`이 part 파일을 찾지 못하는 문제를 재현했습니다.
빈 ZIP이 만들어지면 tooling의 ZIP 검증에서 실패하며 manifest에 성공으로 기록하지 않습니다.

이번 local execution은 외부 vendor script 원본을 보관하고 해당 assignment를
`escaped_prefix="$prefix"`로 바꾼 local copy를 사용했습니다. Repo tooling은 vendor script를 자동으로
patch하지 않습니다. 선택한 두 archive에서 검증한 우회이며 임의 filename/다른 OS의 지원 보장이 아닙니다.
공식 원본과 설치 안내: [AI-Hub Shell](https://www.aihub.or.kr/devsport/apishell/list.do).

New imports use metadata schema `aihub-239-history-v2`: raw ITEM_NAME remains channel identity and
`observed_property` is null until evidenced. Existing v1 rows are read without rewriting their JSON;
the old `property_name` is shown only as a legacy source label. To resume an exact pre-v2 selection,
use `--metadata-schema v1` with its original binding/range/batch size. Retrying it as v2 fails on immutable
batch/row evidence rather than silently rewriting interpretation. Use v2 for new selections.
