# Dataset Selection and Acquisition Research

이 문서는 첫 실제 Domain Adapter와 이후 cross-domain 검증에 사용할 공개 PHM 데이터셋 후보를 비교하고,
각 데이터셋의 획득 자동화 범위와 provenance 주의사항을 정리합니다.

조사 기준일: 2026-09-16

## 1. Selection Goals

첫 데이터셋은 최신 모델 성능 경쟁보다 다음 구조 가설을 검증하는 데 사용합니다.

1. 실제 산업 시계열이 현재 canonical contract로 자연스럽게 표현되는가?
2. dataset-specific parsing/semantics가 Domain Adapter 경계 안에 머무는가?
3. 자산·Run 단위 split과 독립 evaluation을 재현 가능하게 만들 수 있는가?
4. anomaly, health, prognostics 중 어떤 capability가 데이터에 의해 정당하게 지원되는가?

두 번째 데이터셋은 modality와 domain condition을 바꿔 adapter/core 분리가 실제로 재사용되는지 검증합니다.

## 2. Candidate Summary

| Dataset | Modality / task | Research role | Acquisition | License / provenance note |
| --- | --- | --- | --- | --- |
| XJTU-SY | bearing vibration, complete run-to-failure | **Primary candidate** | 공식 페이지가 여러 download mirror를 제공하므로 초기에는 manual/semi-automated | 공식 GitHub README는 public use와 citation을 명시하지만 별도 software-style license/redistribution 조건은 확인 후 manifest에 기록 |
| IMS Bearings | bearing vibration/degradation | Primary cross-check candidate | NASA Open Data에 ZIP resource가 있어 자동화 가능성이 높음 | NASA catalog가 public dataset으로 제공하며 license link를 government works로 연결 |
| MIMII DUE | industrial machine audio, normal/abnormal, source/target domain shift | **Secondary domain candidate** | Zenodo record/files API와 공개 checksum을 사용해 자동화 가능 | CC BY-NC-SA 4.0, Zenodo v1.01, DOI와 file checksum 보존 필요 |
| AI4I 2020 | synthetic tabular predictive maintenance | smoke/example only | UCI 공식 `ucimlrepo` 또는 공개 CSV로 자동화 용이 | CC BY 4.0, DOI 제공. 실제 PHM evidence의 primary 근거로 사용하지 않음 |
| DCASE 2026 Task 2 | dual-microphone industrial audio, normal-only training, domain shift/noise | modern stretch benchmark | challenge dataset policy에 맞춘 별도 acquisition 필요 | 2026 challenge rules/data revision을 dataset version과 함께 고정해야 함 |

## 3. Primary Candidate: XJTU-SY

공식 XJTU-SY repository는 Xi'an Jiaotong University와 Changxing Sumyoung Technology의 accelerated
degradation experiment에서 수집한 15개 rolling-element bearing의 complete run-to-failure 데이터를 공개하고,
prognostics 연구에서 사용할 수 있다고 안내합니다. 공식 README에는 저자 웹사이트, Google Drive, Dropbox,
MediaFire, MEGA, Baidu Netdisk 등의 다운로드 경로와 원 논문 citation이 제공됩니다.

이 데이터셋을 primary로 우선 검증하는 이유는 다음과 같습니다.

- 실제 vibration waveform과 asset lifecycle을 함께 다뤄 canonical contract의 granularity를 검증할 수 있음
- complete run-to-failure 특성 때문에 degradation/health/RUL 연구로 확장 가능
- 첫 baseline 이후 asset-held-out 평가를 설계하기 적합

### Acquisition policy

초기 implementation은 무리하게 특정 cloud mirror를 scrape하지 않습니다.

```text
manifest
  ↓
manual / verified source selection
  ↓
local raw dataset
  ↓
data verify
  ↓
Domain Adapter
```

공식 source가 안정적인 machine-readable download endpoint와 명확한 redistribution 조건을 제공하는지 추가 확인한
뒤 자동 fetch provider를 별도 도입합니다. repository가 제3자 mirror 역할을 하거나 원본 데이터를 재배포하지
않도록 합니다.

### Required provenance

- official repository / author page
- citation DOI: `10.1109/TR.2018.2882682`
- acquired mirror/source
- acquisition date
- raw file inventory와 가능한 checksum
- operating condition / asset/run mapping
- 원 출처에서 확인한 reuse/redistribution condition

## 4. Bearing Cross-check: IMS Bearings

NASA Open Data의 IMS Bearings entry는 University of Cincinnati Center for Intelligent Maintenance Systems가
제공한 bearing experiment dataset을 public resource로 노출하고 `IMS.zip` resource를 제공합니다.

XJTU-SY 하나에만 맞춘 preprocessing/adapter 가정을 발견하기 위한 보조 bearing dataset으로 가치가 있습니다.
다만 첫 번째 구현부터 두 bearing dataset을 동시에 지원하려고 추상화를 확대하지 않습니다. XJTU-SY adapter와
baseline이 안정된 뒤 같은 modality 안에서 portability를 점검할 때 사용합니다.

## 5. Secondary Domain: MIMII DUE

Zenodo의 MIMII DUE v1.01은 fan, gearbox, pump, slide rail, valve의 normal/abnormal operating sound를 포함하고,
source/target domain이 서로 다른 운전·환경 조건을 갖도록 구성되어 있습니다.

이 데이터셋은 두 번째 domain에 적합합니다.

- vibration에서 audio로 modality가 변경됨
- 여러 machine type을 포함함
- source/target domain shift가 명시적임
- anomaly detection이 중심 task라 첫 bearing domain과 다른 capability 조합을 검증할 수 있음

Zenodo record는 전체 약 9.4 GB의 파일, 개별 파일 size와 MD5 checksum을 공개하고 있습니다. 따라서
machine-readable record/file metadata를 이용해 `fetch → cache → verify` 흐름을 구현하기 좋은 대상입니다.

### License boundary

MIMII DUE는 CC BY-NC-SA 4.0입니다. Apache-2.0인 framework source repository가 dataset 자체를 재배포하거나
동일 라이선스로 오해하게 해서는 안 됩니다. repository에는 manifest와 acquisition logic만 두고 원본 데이터는
local/cache에 유지합니다.

## 6. Smoke Dataset: AI4I 2020

UCI AI4I 2020 Predictive Maintenance Dataset은 10,000-row synthetic dataset이며 UCI가 CC BY 4.0, DOI
`10.24432/C5HS5C`, `ai4i2020.csv`와 `ucimlrepo` import 방법을 제공합니다.

실제 vibration/audio PHM 연구 결과의 근거로 사용하지는 않지만 다음에는 유용합니다.

- dataset registry/fetch/verify CLI의 작은 end-to-end smoke example
- CI에서 대형 외부 데이터 없이 acquisition behavior를 설명하는 example
- tabular domain을 향후 지원할지 판단하기 위한 작은 fixture source

실제 CI가 매번 원격 UCI 서비스를 호출하도록 만들지는 않습니다. remote acquisition 자체의 test는 별도
integration/smoke workflow로 분리합니다.

## 7. 2026 Research Direction: DCASE Task 2

DCASE 2026 Task 2는 noise-aware unsupervised anomalous sound detection을 다루며, normal-only training,
domain shift, noisy factory condition과 near/far 두 microphone의 synchronized recording을 핵심 조건으로 둡니다.

2026 제출 시스템들에서는 frozen/pretrained audio embedding과 k-NN/Mahalanobis 계열 anomaly scoring,
noise-aware multi-channel processing 등이 반복적으로 나타납니다. 따라서 MIMII DUE 기반 second-domain 실험이
안정된 뒤 현대적 audio baseline의 stretch benchmark로 연결하기 좋습니다.

DCASE 데이터는 challenge 중 file revision이 발생할 수 있으므로 dataset name만 기록해서는 부족합니다.
acquisition manifest에 challenge year, task, machine subset, published revision/file name과 hash를 고정해야 합니다.

## 8. Initial Decision

현재 단계의 기본 연구 순서는 다음으로 정합니다.

```text
Primary architecture validation
XJTU-SY bearing vibration
        ↓
Isolation Forest / independent evaluation
        ↓
LSTM-AE / health / supported prognostics
        ↓
Secondary-domain validation
MIMII DUE industrial audio
        ↓
Optional modern benchmark
DCASE 2026 Task 2
```

AI4I는 framework의 연구 결론을 만드는 dataset이 아니라 acquisition/CLI/example 같은 작은 workflow를 검증하는
보조 데이터로만 취급합니다. IMS는 XJTU-SY 이후 같은 bearing modality에서 portability를 확인하는 cross-check
후보입니다.

## 9. Acquisition Implementation Order

1. dataset manifest schema를 최소 필드로 정의
2. local/manual provider를 먼저 구현해 XJTU-SY를 provenance와 함께 등록
3. common file inventory/checksum validator 구현
4. Zenodo provider로 MIMII DUE metadata/fetch automation 검증
5. 필요하면 작은 HTTP/UCI provider 추가
6. provider별 network smoke check는 PR unit suite와 분리

Domain Adapter는 acquisition provider를 알지 않습니다. Adapter에는 검증된 local source path만 전달합니다.

## Sources

- XJTU-SY official repository: https://github.com/WangBiaoXJTU/xjtu-sy-bearing-datasets
- XJTU-SY reference DOI: https://doi.org/10.1109/TR.2018.2882682
- NASA IMS Bearings: https://data.nasa.gov/dataset/ims-bearings
- MIMII DUE Zenodo record: https://zenodo.org/records/4740355
- MIMII DUE DOI: https://doi.org/10.5281/zenodo.4740355
- UCI AI4I 2020: https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset
- UCI AI4I DOI: https://doi.org/10.24432/C5HS5C
- DCASE 2026 Task 2: https://dcase.community/challenge2026/task-first-shot-unsupervised-anomalous-sound-detection-for-machine-condition-monitoring
- DCASE 2026 Task 2 results: https://dcase.community/challenge2026/task-first-shot-unsupervised-anomalous-sound-detection-for-machine-condition-monitoring-results
