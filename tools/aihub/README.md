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

`AIHUB_APIKEY`는 다운로드 subprocess의 environment로만 전달합니다. command argument, preset,
inventory JSON 또는 local manifest에는 기록하지 않습니다. Process environment에 이미 설정된 값이 있으면
`.env`가 덮어쓰지 않습니다.

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

현재 bootstrap은 Training/raw의 보일러(`44033`, 59 MB 표시)와 압출기(`44035`, 97 MB 표시)를
선택합니다. AI-Hub file tree의 용량 표시는 반올림된 값이므로 plan의 합계는 근사치입니다.

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
현재 local bytes의 SHA-256을 `local-manifest.json`에 기록하고, 이후 실행은 그 local provenance와의
일치 여부를 검사합니다.

## Boundaries

- CI와 기본 pytest suite는 AI-Hub endpoint에 접속하거나 대용량 payload를 다운로드하지 않습니다.
- API key, `.env`, vendor archive, generated inventory/local manifest는 commit 대상이 아닙니다.
- preset은 acquisition selection metadata이며 아직 framework dataset registry의 canonical manifest가
  아닙니다.
- dataset-specific parsing, measurement semantics, Asset History integration은 별도 변경으로 다룹니다.
