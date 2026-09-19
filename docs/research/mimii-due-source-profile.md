# MIMII DUE Source Profile

상태: official record verified / local inventory observed / source validator 구현 / Adapter 미구현

이 문서는 MIMII DUE의 source record, license boundary, 실제 local inventory와 canonical mapping 쟁점을 기록합니다.
MIMII DUE는 XJTU-SY와 IMS에 이은 세 번째 source이며, bearing-vibration 범위를 벗어나는 첫 cross-domain case
(machine audio)입니다. [`../architecture/canonical-data-contract.md`](../architecture/canonical-data-contract.md)의
Case D에 해당합니다.

이 문서는 experiment protocol이나 evaluation 정의를 고정하지 않습니다.

## 1. Source record

Zenodo REST API(`https://zenodo.org/api/records/4740355`)로 2026-09-19에 확인했습니다.

- project dataset ID: `mimii-due`
- title: MIMII DUE: Sound Dataset for Malfunctioning Industrial Machine Investigation and Inspection with
  Domain Shifts due to Changes in Operational and Environmental Conditions
- Zenodo record: `4740355`, DOI `10.5281/zenodo.4740355`
- version: `1.01` (`versions/latest`가 같은 record를 가리킴)
- publication date: 2021-05-05
- license: `cc-by-nc-sa-4.0`, access: open

### License boundary

MIMII DUE는 CC BY-NC-SA 4.0입니다. Apache-2.0인 이 repository는 dataset을 재배포하지 않습니다. Repository에는
manifest, profile, Adapter/validator 같은 코드만 두고 원본 archive와 추출본은 gitignored `data/raw/`,
`data/interim/`에만 둡니다. 파생 artifact를 repository에 기록할 때도 원본 waveform이나 그 재구성이 가능한 양의
sample을 포함하지 않습니다.

## 2. Record files

Record는 10개 ZIP을 제공하며 합계 9,428,046,039 bytes입니다. Zenodo는 파일별 MD5를 공개하고, local download 10개
모두 공개 MD5와 일치했습니다.

| File | Bytes | MD5 |
| --- | ---: | --- |
| `dev_data_fan.zip` | 1,072,486,301 | `2fd8c081d1adf559372763f204fd154f` |
| `dev_data_gearbox.zip` | 1,200,236,895 | `16a22870056194a1da6ace2f1f5b42b5` |
| `dev_data_pump.zip` | 1,077,021,452 | `8c7090f0974336404070315a1e1445f4` |
| `dev_data_slider.zip` | 1,086,886,830 | `788d8942aae1f8da4e851d16946b05ab` |
| `dev_data_valve.zip` | 1,070,937,861 | `bc456bef6bc28decc1f9e74ca11480c3` |
| `eval_data_fan_train.zip` | 759,752,515 | `57afe982988072fa2c96faefd5516a73` |
| `eval_data_gearbox_train.zip` | 847,594,100 | `a3ce10fd1d8a7ce668dd0171ddf3d21f` |
| `eval_data_pump_train.zip` | 762,916,640 | `a1fad9e61ba0d1fde48aefd02aa2c1fa` |
| `eval_data_slider_train.zip` | 791,961,571 | `3b1ff6887aceb50d51f901704dc63e33` |
| `eval_data_valve_train.zip` | 758,251,874 | `ddf7513b752946acd07c75ad8fce7dc4` |

현재 `DatasetManifest`는 archive 하나와 SHA-256만 표현합니다. MIMII DUE는 파일 10개와 MD5를 제공하므로
manifest는 `provider = "manual"`로 등록하고, 파일별 provenance는 이 표가 소유합니다. Multi-file Zenodo fetch를
framework acquisition으로 승격할지는 반복 요구가 확인될 때 별도로 결정합니다.

## 3. 이 record에 없는 것

Record 4740355에는 evaluation section의 **test audio가 없습니다.** Zenodo에서 확인되는 관련 record는 다음과
같습니다.

| Zenodo record | Title | 비고 |
| --- | --- | --- |
| 4884786 | DCASE 2021 Challenge Task 2 Evaluation Dataset | evaluation test audio |
| 5257674 | Ground Truth for DCASE 2021 Challenge Task 2 Evaluation Dataset | evaluation test 정답 label |

즉 evaluation section(03~05)의 test clip과 그 정답 label은 각각 별도 record에 있습니다. 이 repository는 두
record를 아직 획득하거나 검증하지 않았습니다. 어떤 partition을 어떤 label로 평가할지는 experiment protocol이
결정하며, 그 전에 필요한 record의 license, checksum, inventory를 같은 방식으로 확인합니다.

## 4. Observed local structure

Local 경로: archive는 `data/raw/mimii-due/`, 추출본은 `data/interim/mimii-due/source/{dev,eval}/`.

```text
source/
├── dev/{fan,gearbox,pump,slider,valve}/
│   ├── train/          section 00·01·02
│   ├── source_test/    section 00·01·02
│   └── target_test/    section 00·01·02
└── eval/{fan,gearbox,pump,slider,valve}/
    └── train/          section 03·04·05
```

전체 36,433개 WAV(train 30,212 / test 6,221)이며 아래 filename grammar에서 벗어난 파일은 없었습니다.

| Group | Machine | Split | Source normal | Source anomaly | Target normal | Target anomaly |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| dev | fan | train | 3,000 | 0 | 9 | 0 |
| dev | fan | test | 300 | 300 | 300 | 300 |
| dev | gearbox | train | 3,017 | 0 | 9 | 0 |
| dev | gearbox | test | 411 | 351 | 309 | 336 |
| dev | pump | train | 3,000 | 0 | 9 | 0 |
| dev | pump | test | 300 | 300 | 300 | 300 |
| dev | slider | train | 3,000 | 0 | 9 | 0 |
| dev | slider | test | 310 | 302 | 300 | 302 |
| dev | valve | train | 3,000 | 0 | 9 | 0 |
| dev | valve | test | 300 | 300 | 300 | 300 |
| eval | fan | train | 3,000 | 0 | 9 | 0 |
| eval | gearbox | train | 3,105 | 0 | 9 | 0 |
| eval | pump | train | 3,000 | 0 | 9 | 0 |
| eval | slider | train | 3,000 | 0 | 9 | 0 |
| eval | valve | train | 3,000 | 0 | 9 | 0 |

관찰한 구조적 사실은 다음과 같습니다.

- Train에는 normal만 있습니다.
- Target domain train은 모든 machine·section에서 **section당 정확히 3개**입니다. Source train은 gearbox를 제외하면
  section당 정확히 1,000개입니다. Gearbox는 dev section 00·01·02가 1,001 / 1,008 / 1,008개, eval section
  03·04·05가 1,005 / 1,092 / 1,008개입니다.
- Dev test는 fan, pump, valve에서 section·domain마다 normal 100 / anomaly 100으로 균형입니다. Gearbox와 slider는
  균형이 아닙니다. 예를 들어 gearbox source section 00은 normal 195 / anomaly 105입니다.

## 5. Audio profile

36,433개 WAV header가 모두 같았습니다.

| Channels | Sample width | Sampling rate | Frames | Duration |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 16-bit PCM | 16,000 Hz | 160,000 | 10.000 s |

Filename에는 clip 사이의 연속 시간축이나 acquisition timestamp가 없습니다. `NNNN`은 split·section·domain·label
안의 파일 번호이며, 이것이 녹음 순서나 lifecycle 순서를 뜻한다는 근거는 source에서 확인하지 못했습니다. XJTU/IMS의
acquisition index와 같은 의미로 쓰지 않습니다.

## 6. Filename grammar

```text
section_{SS}_{source|target}_{train|test}_{normal|anomaly}_{NNNN}[_{attributes}].wav
```

Section, domain, split, clip label은 **filename에서만** 얻습니다. Clip label(`normal`/`anomaly`)은 clip 단위입니다.

Operating/environment attribute는 **train filename에만** 붙습니다. Test filename 6,221개 중 attribute가 붙은
파일은 0개이므로, test clip의 운전 조건은 filename으로 복원할 수 없습니다.

Attribute grammar는 machine마다 다릅니다. 숫자는 `<n>`으로 표시했습니다.

| Machine | Observed train attribute patterns |
| --- | --- |
| fan | `strength_<n>_ambient`, `strength_<n>_temp_min`, `strength_<n>_temp_max`, `strength_<n>_small_ambient`, `strenght_<n>_ambient`, `strenght_<n>_big_ambient` |
| gearbox | `<n>_g_<n>_mm_<n>_mV_none`, `<n>_g_<n>_mm_<n>_mV_None` |
| pump | `serial_no_<n>`, `serial_no_<n>_water`, `serial_no_<n>_viscous_liquid`, `serial_no_<n>_<n>`, `serial_no_<n>_<n>_<n>` |
| slider | `vel<n>_dis<n>_accl<n>`, `glassfiber_none`, `polyurethane_none` |
| valve | `pattern_<n>_air_pump`, `pattern_<n>_no_pump`, `pattern_<n>_air_pump_comb`, `pattern_<n>_water_pump` |

Source에는 표기 불일치가 그대로 있습니다. Fan은 `strength`와 철자가 다른 `strenght`가 공존하고(2,000개가
`strenght`), gearbox는 `none`과 `None`이 공존합니다. Adapter는 이를 조용히 정정하지 않고 원문 attribute
문자열을 보존합니다. 정규화가 필요하면 원문과 별도로, 규칙을 명시해 적용합니다.

## 7. Canonical mapping 쟁점

`CanonicalTimeSeries`로 한 clip을 표현하는 데 새 필드는 필요하지 않아 보입니다.

- `timestamps=None`, `sampling_rate_hz=16000`, channel 1개로 waveform을 표현할 수 있습니다. 규모는 160,000 × 1로
  XJTU acquisition(32,768 × 2)과 같은 범주입니다.
- Clip label은 sample 단위 `labels` 필드에 복사하지 않습니다. 16만 개 sample마다 같은 값을 반복하면 clip 속성을
  sample 속성처럼 보이게 만들기 때문입니다. XJTU Adapter가 lifecycle 정보를 sample에 투영하지 않은 것과 같은
  원칙입니다. Label, domain, section, split, 원문 attribute는 clip metadata로 둡니다.
- Asset 의미가 bearing과 다릅니다. Source가 제공하는 식별 단위는 machine type과 section이며, clip 사이에
  run-to-failure 순서를 나타내는 값이 없습니다. 따라서 XJTU/IMS evaluation이 쓰는 acquisition order, lifecycle
  third, late-vs-middle 통계는 이 source에 그대로 적용할 근거가 없습니다. Section이 물리적으로 무엇을 뜻하는지는
  source 문서로 확인한 뒤 Adapter metadata 이름을 정합니다.
- `vibration-statistical-v1`은 channel 이름에 무관하게 계산은 되지만, audio에 대한 적절한 feature로 채택하지
  않습니다. Audio feature는 protocol에서 별도로 정합니다.

이 쟁점들은 Adapter를 구현하면서 contract test로 확인합니다. 실제 구현에서 현재 contract로 의미를 잃지 않고
표현하기 어렵다는 것이 드러날 때만 canonical contract 변경을 검토합니다.

## 8. 구현된 source validator

`industrial-phm data validate mimii-due`는 prepared source의 visible file 전체에 대해 directory/filename grammar와
group·machine·domain·split·label count를 검사합니다. 기본 mode는 각 관찰 stratum의 first/middle/last WAV
header를 확인하고, `--full`은 36,433개 WAV header를 모두 확인합니다.

이 validator는 WAV payload normalization, audio feature 계산 또는 clip label의 sample-level 투영을 수행하지
않습니다. Source profile 호환성만 production code로 반복 검증하며, Adapter/canonical mapping은 다음 변경이
소유합니다.

## 9. 다음 단계에서 결정할 것

- Audio-specific `DomainAdapter`: validator가 고정한 구조·filename 의미를 canonical mapping으로 보존
- Clip metadata key 이름과 원문 attribute 보존 방식
- Evaluation test audio(4884786)와 ground truth(5257674)의 획득·검증 여부
- Experiment protocol: 대상 machine·section·domain, train/evaluation scope, label 사용 방식, feature와
  preprocessing ownership, model family, metric과 aggregation, capability claim

## Sources

- Zenodo record 4740355: `https://zenodo.org/records/4740355`
- DOI: `https://doi.org/10.5281/zenodo.4740355`
- Zenodo record 4884786 (evaluation test audio): `https://zenodo.org/records/4884786`
- Zenodo record 5257674 (evaluation ground truth): `https://zenodo.org/records/5257674`
