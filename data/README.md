# Local Data Workspace

`data/`는 연구와 개발 중 사용하는 **로컬 데이터 작업 공간**입니다. 원본 데이터셋과 파생 데이터는 Git에
commit하지 않으며, repository clone만으로 함께 배포되지 않습니다.

## 디렉터리 역할

```text
data/
├── raw/        # 원 출처에서 받은 원본. 내용 수정 금지
├── interim/    # 압축 해제·파싱 등 재생성 가능한 중간 결과
└── processed/  # 재현 가능한 preprocessing/feature 결과
```

`.gitignore`는 `data/raw/`, `data/interim/`, `data/processed/`를 제외합니다. dataset source/version/license의
Source of Truth는 `src/industrial_phm/data/manifests/`에 유지합니다.

## Local source inspection

`industrial-phm data inspect`는 dataset-specific parsing 전에 local source의 **구조적 inventory**를 요약합니다.
일반 file, directory와 ZIP archive에 대해 file count, source size, path depth, extension 분포를 보고합니다.

```bash
uv run industrial-phm data inspect <dataset-id> --source <local-path>
```

`--details`는 제한된 top-level entry와 대표 상대경로를 추가합니다. ZIP inventory는 archive metadata에서
member count와 uncompressed payload size를 계산합니다.

```bash
uv run industrial-phm data inspect <dataset-id> \
  --source <local-path> \
  --details
```

Dataset-specific validator가 file semantics, channel mapping, sampling/time contract와 Adapter compatibility를 소유합니다.
Private/field source의 path에 asset/site 정보가 포함된 경우 `--details` 출력에도 해당 조직의 공유 정책을
적용합니다.

## IMS Bearings

IMS Bearings manifest는 NASA PCoE 공식 ZIP endpoint를 사용합니다. `fetch`는 원본 archive를 raw
workspace에 보존하고 `verify`는 local SHA-256 provenance를 출력합니다.

```bash
uv run industrial-phm data fetch ims-bearings
uv run industrial-phm data verify ims-bearings
```

원본 ZIP inventory는 다음 명령으로 확인합니다.

```bash
uv run industrial-phm data inspect ims-bearings \
  --source data/raw/ims-bearings/ims-bearing-data-set.zip \
  --details
```

Archive layout은 ZIP → 7z → RAR 3개입니다. `bsdtar`로 각 계층을 별도 directory에 해제해 raw
archive와 prepared source의 provenance를 분리합니다.

```bash
mkdir -p data/interim/ims-bearings/nasa-archive
bsdtar -xf data/raw/ims-bearings/ims-bearing-data-set.zip \
  -C data/interim/ims-bearings/nasa-archive

mkdir -p data/interim/ims-bearings/ims-package
bsdtar -xf "data/interim/ims-bearings/nasa-archive/4. Bearings/IMS.7z" \
  -C data/interim/ims-bearings/ims-package

mkdir -p data/interim/ims-bearings/source
bsdtar -xf data/interim/ims-bearings/ims-package/1st_test.rar \
  -C data/interim/ims-bearings/source
bsdtar -xf data/interim/ims-bearings/ims-package/2nd_test.rar \
  -C data/interim/ims-bearings/source
bsdtar -xf data/interim/ims-bearings/ims-package/3rd_test.rar \
  -C data/interim/ims-bearings/source
```

준비 결과는 `1st_test/`, `2nd_test/`, `4th_test/txt/`를 갖는 source root입니다. Dataset-specific
validator는 이 root를 입력으로 받습니다.

```bash
uv run industrial-phm data validate ims-bearings \
  --source data/interim/ims-bearings/source
```

기본 sampled mode는 각 test의 first/middle/last waveform과 전체 filename/timestamp profile을 검사합니다.
`--full`은 9,464개 waveform 전체를 검사합니다. Set 3 결과는 README scope 4,448개와 archive
extension 1,876개를 분리해 보고합니다. 정확한 profile과 canonical mapping은
[`../docs/research/ims-source-profile.md`](../docs/research/ims-source-profile.md)에서 관리합니다.

## MIMII DUE

MIMII DUE는 `manual` provider로 등록되어 있으며 원본 archive와 추출본을 repository에 재배포하지 않습니다.
현재 prepared source root는 다음 구조를 전제로 합니다.

```text
data/interim/mimii-due/source/
├── dev/{fan,gearbox,pump,slider,valve}/
│   ├── train/
│   ├── source_test/
│   └── target_test/
└── eval/{fan,gearbox,pump,slider,valve}/
    └── train/
```

Dataset-specific validator는 모든 visible file의 directory/filename grammar와 clip population을 확인하고,
기본 sampled mode에서는 관찰된 group/machine/domain/split/label stratum별 대표 WAV header를 검사합니다.

```bash
uv run industrial-phm data validate mimii-due \
  --source data/interim/mimii-due/source
```

모든 36,433개 WAV header를 확인해야 할 때만 `--full`을 사용합니다. 이 검증은 waveform payload를
정규화하거나 audio feature를 계산하지 않으며, 16-bit PCM / mono / 16 kHz / 160,000 frames라는 source
compatibility만 확인합니다.

```bash
uv run industrial-phm data validate mimii-due \
  --source data/interim/mimii-due/source \
  --full
```

정확한 record, license, checksum, clip count, filename attribute와 canonical mapping 쟁점은
[`../docs/research/mimii-due-source-profile.md`](../docs/research/mimii-due-source-profile.md)가 소유합니다.

## XJTU-SY

XJTU-SY 공식 repository는 여러 cloud mirror를 제공합니다. Framework의 manifest는 현재 `manual` provider를
유지하므로 package import나 `data fetch`가 임의로 이 데이터를 다운로드하지 않습니다.

### 1. 원본 배포물 획득

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

다운로드가 중간에 실패하면 같은 `--continue` 명령을 다시 실행합니다. 원본 inventory는 다음 명령으로
확인합니다.

```bash
uv run industrial-phm data inspect xjtu-sy --source data/raw/xjtu-sy
```

`data inspect`는 local file inventory만 확인하며 배포물의 완전성이나 upstream authenticity를 보증하지 않습니다.

### 2. signal archive 압축 해제

공식 Google Drive 배포물의 signal data는 multipart RAR archive입니다. `part01`부터 마지막 part까지 같은
directory에 보존하고 **첫 번째 part를 시작점으로 한 번만** 압축 해제합니다. 원본 archive는 `data/raw/`에
그대로 두고 결과는 `data/interim/`에 둡니다.

macOS에서 `unar`를 사용하는 예시는 다음과 같습니다.

```bash
brew install unar
mkdir -p data/interim/xjtu-sy
unar \
  -o data/interim/xjtu-sy \
  data/raw/xjtu-sy/Data/XJTU-SY_Bearing_Datasets.part01.rar
```

다른 환경에서는 multipart RAR를 지원하는 동등한 도구를 사용할 수 있습니다. Adapter가 읽는 준비된 root는
다음 경로입니다.

```text
data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets
```

### 3. Adapter 호환성 자동 검증

초기 조사에서 사람이 직접 수행했던 directory count, acquisition filename continuity, CSV schema/sample count,
Adapter smoke check는 이제 dataset-specific validator로 반복 실행합니다.

```bash
uv run industrial-phm data validate xjtu-sy \
  --source data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets
```

기본 검증은 모든 condition/run의 directory와 acquisition sequence를 확인한 뒤 각 run의 first/middle/last
waveform을 실제 Adapter 경로로 파싱합니다. 현재 관찰된 완전한 source profile인 3 operating conditions,
15 bearing runs, 9,216 acquisitions와도 비교합니다.

모든 9,216 acquisition CSV의 waveform content를 실제로 파싱해야 할 때만 명시적으로 full mode를 사용합니다.

```bash
uv run industrial-phm data validate xjtu-sy \
  --source data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets \
  --full
```

`data validate`는 **source/profile 및 Adapter 호환성 검사**입니다. XJTU-SY manifest에는 pinned upstream
checksum이 없으므로 이 명령이 성공해도 upstream authenticity를 검증했다고 주장하지 않습니다. Google Drive
mirror의 접근 정책이나 내용이 바뀌면 공식 repository가 안내하는 다른 mirror를 사용하고 획득 출처를 연구
기록에 남깁니다.
