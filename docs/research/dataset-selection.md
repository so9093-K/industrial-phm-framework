# Dataset Selection and Acquisition Research

이 문서는 첫 실제 Domain Adapter와 이후 cross-dataset/cross-domain 검증에 사용할 공개 PHM 데이터셋 후보를 비교하고,
각 데이터셋의 획득 자동화 범위와 provenance 주의사항을 정리합니다.

조사 기준일: 2026-09-17

## 1. Selection Goals

첫 데이터셋은 최신 모델 성능 경쟁보다 다음 구조 가설을 검증하는 데 사용합니다.

1. 실제 산업 시계열이 현재 canonical contract로 자연스럽게 표현되는가?
2. dataset-specific parsing/semantics가 Domain Adapter 경계 안에 머무는가?
3. 자산·Run 단위 split과 독립 evaluation을 재현 가능하게 만들 수 있는가?
4. anomaly, health, prognostics 중 어떤 capability가 데이터에 의해 정당하게 지원되는가?

두 번째 dataset은 첫 dataset에서 암묵적으로 굳어진 data-contract 가정을 **모델 개발 전에** 반증하는 데 사용할 수
있습니다. 같은 bearing-vibration modality의 IMS를 이용해 source/acquisition semantics portability를 먼저 확인하고,
이후 MIMII DUE처럼 modality와 machine domain이 다른 dataset으로 cross-domain boundary를 검증합니다.

공개 benchmark만으로 실제 field-data readiness가 증명되는 것은 아닙니다. 첫 private/field source가 확보되면
access policy, asset/sensor identity, data quality, provenance, maintenance/configuration events와 external storage
boundary를 별도 conformance case로 검증합니다.

## 2. Candidate Summary

| Dataset | Modality / task | Research role | Acquisition | License / provenance note |
| --- | --- | --- | --- | --- |
| XJTU-SY | bearing vibration, complete run-to-failure | **Primary concrete case** | 공식 페이지가 여러 download mirror를 제공하므로 manual/semi-automated | 공식 GitHub README는 public use와 citation을 명시하지만 별도 software-style license/redistribution 조건은 확인 후 manifest에 기록 |
| IMS Bearings | bearing vibration/degradation | **Early canonical-contract cross-check** | NASA PCoE가 공식 ZIP endpoint 제공 | NASA Open Data Portal은 `other-license-specified`; repository citation과 donor acknowledgement 요구를 보존하고 source terms 확인 |
| MIMII DUE | industrial machine audio, normal/abnormal, source/target domain shift | **Cross-domain candidate** | Zenodo record/files API와 공개 checksum을 사용해 자동화 가능 | CC BY-NC-SA 4.0, Zenodo v1.01, DOI와 file checksum 보존 필요 |
| AI4I 2020 | synthetic tabular predictive maintenance | smoke/example only | UCI 공식 ZIP으로 자동화 용이 | CC BY 4.0, DOI 제공. 실제 PHM evidence의 primary 근거로 사용하지 않음 |

## 3. Primary Concrete Case: XJTU-SY

공식 XJTU-SY repository는 Xi'an Jiaotong University와 Changxing Sumyoung Technology의 accelerated
degradation experiment에서 수집한 15개 rolling-element bearing의 complete run-to-failure 데이터를 공개하고,
prognostics 연구에서 사용할 수 있다고 안내합니다. 공식 README에는 저자 웹사이트, Google Drive, Dropbox,
MediaFire, MEGA, Baidu Netdisk 등의 다운로드 경로와 원 논문 citation이 제공됩니다.

이 데이터셋을 첫 concrete case로 우선 검증하는 이유는 다음과 같습니다.

- 실제 vibration waveform과 asset lifecycle을 함께 다뤄 canonical contract의 granularity를 검증할 수 있음
- complete run-to-failure 특성 때문에 degradation/health/RUL 연구로 확장 가능
- 첫 baseline 이후 asset-held-out 평가를 설계하기 적합

XJTU-SY는 canonical schema의 정의가 아니라 첫 conformance case입니다. XJTU directory grammar, 60-second acquisition
period, H/V channel naming 또는 bearing-run split을 모든 산업 source의 공통 의미로 승격하지 않습니다.

### Acquisition policy

초기 implementation은 무리하게 특정 cloud mirror를 scrape하지 않습니다.

```text
manifest
  ↓
manual / verified source selection
  ↓
local raw dataset
  ↓
data inspect / dataset-specific validation
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

## 4. Early Contract Cross-check: IMS Bearings

NASA Prognostics Center of Excellence Data Set Repository는 University of Cincinnati Center for Intelligent
Maintenance Systems가 제공한 bearing experiment dataset을 `Bearings`로 배포하고 공식 ZIP endpoint를 제공합니다.
NASA Open Data Portal에도 `IMS Bearings` dataset이 등록되어 있으며 현재 license field는
`other-license-specified`입니다.

IMS의 첫 역할은 XJTU-SY 다음의 **모델 성능 benchmark가 아니라 canonical-data contract cross-check**입니다.
XJTU feature/model 연구를 계속 쌓기 전에 source layout, acquisition time, channel mapping과 provenance가 달라졌을 때
현재 Adapter → `CanonicalTimeSeries` 경계가 자연스럽게 유지되는지 확인합니다.

```text
XJTU-SY concrete case
        ↓
current canonical assumptions
        ↓
IMS source inspection + minimal adapter exercise
        ↓
observed incompatibilities
        ↓
minimal domain-neutral refinement, if justified
        ↓
XJTU modeling / later IMS model portability
```

### Verified source/adapter boundary

실제 NASA archive를 획득해 nested archive와 prepared source를 조사했고, 현재 production validator와
`ImsBearingAdapter`가 구현되어 있습니다. Prepared source는 3개 test와 총 9,464개 acquisition의
filename/time/channel profile을 검사하며, sampled mode는 test별 first/middle/last waveform 총 9개를 실제로
parse합니다. 정확한 archive layout, Set 3 README 범위와 archive extension, canonical mapping은
[`ims-source-profile.md`](ims-source-profile.md)가 소유합니다.

이 검증은 관찰한 NASA 배포 archive와 Adapter의 **source/profile compatibility**를 확인한 것입니다. Publisher가
SHA-256을 제공하지 않았으므로 local digest를 upstream authenticity 증명으로 표현하지 않습니다. IMS의 다음
역할은 별도 parser를 더 만드는 것이 아니라 XJTU에서 만든 model/preprocessing/evaluation interface가 같은
bearing-vibration domain의 두 번째 source에서도 유지되는지 확인하는 것입니다.

### Acquisition/provenance policy

- official NASA PCoE archive URL을 manifest의 source로 사용
- framework-managed raw archive는 수정하지 않음
- upstream SHA-256이 공식 manifest에 pin되어 있지 않으므로 local digest를 upstream authenticity 증명으로 표현하지 않음
- NASA repository citation과 data donor acknowledgement 요구를 연구 기록에 유지
- NASA Open Data Portal의 `other-license-specified` 표기를 명시하고 실제 사용/재배포 조건을 별도로 확인

## 5. Cross-domain Candidate: MIMII DUE

Zenodo의 MIMII DUE v1.01은 fan, gearbox, pump, slide rail, valve의 normal/abnormal operating sound를 포함하고,
source/target domain이 서로 다른 운전·환경 조건을 갖도록 구성되어 있습니다.

이 데이터셋은 cross-domain 검증에 적합합니다.

- vibration에서 audio로 modality가 변경됨
- 여러 machine type을 포함함
- source/target domain shift가 명시적임
- anomaly detection이 중심 task라 첫 bearing domain과 다른 capability 조합을 검증할 수 있음

Zenodo record는 file size와 MD5 checksum을 공개합니다. 따라서 machine-readable record/file metadata를 이용해
`fetch → cache → verify` 흐름을 구현하기 좋은 대상입니다.

### License boundary

MIMII DUE는 CC BY-NC-SA 4.0입니다. Apache-2.0인 framework source repository가 dataset 자체를 재배포하거나
동일 라이선스로 오해하게 해서는 안 됩니다. repository에는 manifest와 acquisition logic만 두고 원본 데이터는
local/cache에 유지합니다.

## 6. Smoke Dataset: AI4I 2020

UCI AI4I 2020 Predictive Maintenance Dataset은 10,000-row synthetic dataset이며 UCI가 CC BY 4.0, DOI
`10.24432/C5HS5C`와 공식 ZIP을 제공합니다.

실제 vibration/audio PHM 연구 결과의 근거로 사용하지는 않지만 다음에는 유용합니다.

- dataset registry/fetch/verify CLI의 작은 end-to-end smoke example
- CI에서 대형 외부 데이터 없이 acquisition behavior를 설명하는 example
- tabular domain을 향후 지원할지 판단하기 위한 작은 fixture source

실제 CI가 매번 원격 UCI 서비스를 호출하도록 만들지는 않습니다. remote acquisition 자체의 test는 별도
integration/smoke workflow로 분리합니다.

## 7. Dataset and Evidence Validation Order

Dataset별 검증 책임은 다음 순서로 확장합니다. Project-level current status의 Source of Truth는 root README이며,
이 문서는 dataset 선택과 evidence validation의 현재 순서만 요약합니다.

```text
XJTU-SY model lifecycle baseline + IMS model-pipeline portability
        ↓
XJTU LSTM numerical evidence + LSTM-centric Developer Workbench
        ↓
XJTU / IMS / model-family cross-schema evidence review
        ↓
MIMII DUE cross-domain validation
        ↓
event/onset/censoring 근거가 확보된 경우에만 Health Indicator / RUL 범위 재검토
```

MIMII DUE에서는 source, license, checksum, audio-specific Adapter와 canonical data boundary를 먼저 검증합니다.
Experiment protocol과 evaluation definition은 그 다음에 고정하며 model implementation을 선행하지 않습니다.
Health Indicator와 RUL은 complete run-to-failure라는 dataset 설명만으로 정당화하지 않고 defensible event/onset,
censoring, lifecycle target, uncertainty와 independent evaluation 근거가 생긴 뒤 별도 연구 범위로 검토합니다.

AI4I는 framework의 연구 결론을 만드는 dataset이 아니라 acquisition/CLI/example 같은 작은 workflow를 검증하는
보조 데이터로만 취급합니다.

첫 private/field source는 availability에 따라 이 순서 중간에 별도 conformance case로 들어올 수 있습니다. 공개
benchmark를 모두 끝내야만 실제 source를 검토할 수 있다는 의미가 아닙니다.

Dataset acquisition의 현재 command와 준비 절차는 `data/README.md`, source/version/license/hash는 packaged dataset
manifest가 소유합니다. Domain Adapter는 검증된 local source를 받으며 acquisition provider를 알지 않습니다.
Historian, database 또는 API source가 prepared `Path` boundary로 반복해서 해결되지 않을 때 source interface를
재검토합니다.

## Sources

- XJTU-SY official repository: https://github.com/WangBiaoXJTU/xjtu-sy-bearing-datasets
- XJTU-SY reference DOI: https://doi.org/10.1109/TR.2018.2882682
- NASA PCoE Data Set Repository: https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/
- NASA IMS Bearings: https://data.nasa.gov/dataset/ims-bearings
- MIMII DUE Zenodo record: https://zenodo.org/records/4740355
- MIMII DUE DOI: https://doi.org/10.5281/zenodo.4740355
- UCI AI4I 2020: https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset
- UCI AI4I DOI: https://doi.org/10.24432/C5HS5C
