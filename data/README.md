# Local Data Workspace

`data/`는 연구와 개발 중 사용하는 **로컬 데이터 작업 공간**입니다. 원본 데이터셋과 파생 데이터는 Git에
commit하지 않으며, repository clone만으로 함께 배포되지 않습니다.

## 디렉터리 역할

```text
data/
├── raw/        # 원 출처에서 받은 원본. 내용 수정 금지
├── interim/    # 파싱·변환 중간 결과
└── processed/  # 재현 가능한 preprocessing/feature 결과
```

`.gitignore`는 `data/raw/`, `data/interim/`, `data/processed/`를 제외합니다. dataset source/version/license의
Source of Truth는 `src/industrial_phm/data/manifests/`에 유지합니다.

## XJTU-SY

기본 local source는 다음 경로를 권장합니다.

```text
data/raw/xjtu-sy/
```

XJTU-SY 공식 repository는 여러 cloud mirror를 제공합니다. Framework의 manifest는 현재 `manual` provider를
유지하므로 package import나 `data fetch`가 임의로 이 데이터를 다운로드하지 않습니다.

공식 README에 게시된 Google Drive mirror는 `gdown`을 이용해 **로컬에서 반자동으로** 받을 수 있습니다. 이
명령은 framework-managed fetch가 아니며, upstream checksum/authenticity를 검증하지 않습니다.

먼저 folder listing이 가능한지 확인합니다.

```bash
uvx --from gdown==6.2.0 gdown \
  --folder 1_ycmG46PARiykt82ShfnFfyQsaXv3_VK \
  --json
```

그다음 프로젝트 내부 raw workspace로 다운로드합니다.

```bash
mkdir -p data/raw/xjtu-sy
uvx --from gdown==6.2.0 gdown \
  --folder 1_ycmG46PARiykt82ShfnFfyQsaXv3_VK \
  --continue \
  -O data/raw/xjtu-sy
```

다운로드 후 framework가 관측한 local inventory를 확인합니다.

```bash
uv run industrial-phm data inspect xjtu-sy --source data/raw/xjtu-sy
```

`data inspect`가 성공하더라도 이는 local file inventory 확인일 뿐 upstream authenticity 검증은 아닙니다.
Google Drive mirror의 접근 정책이나 내용이 바뀌면 XJTU-SY 공식 repository가 안내하는 다른 mirror를 사용하고
획득 출처를 연구 기록에 남깁니다.
