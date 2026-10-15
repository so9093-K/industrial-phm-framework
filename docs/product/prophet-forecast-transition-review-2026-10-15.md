# Prophet 기반 미래 예측 전환 — 사례 리서치·현행 구조 리뷰·작업 계획

> **구현 상태 (2026-10-15)**: #578(RUL 폐기, [ADR-0026](../adr/0026-retire-remaining-life-estimation.md))과
> #579(미래 예측)로 구현했습니다. 구현은 이 계획보다 단순합니다. 예측은 요청할 때 계산하고(0.1–0.5초) 저장하지
> 않으며(`GET /api/v1/forecast/options`, `GET /api/v1/forecast`), 저장된 ForecastRun·POST 실행 작업·실행 보호
> 단계는 두지 않았습니다. 현재 동작은 [현재 지원 상태](../status.md)의 `미래 예측` 항목을 따릅니다.

> 2026-10-15 · 현행 검토 기준: `main` 975d2ea · **문서 리뷰/실행 계획, 구현 완료 아님**
> 관련 UX PR: [#575](https://github.com/so9093-K/industrial-phm-framework/pull/575) (조사 당시 미병합)

## 1. 결론과 사용자가 정한 결정

- 기존 제품의 **Ridge·LSTM 기반 RUL 추정 기능은 운영 경로에서 제거**한다. 모델끼리 정확도 비교 실험은 수행하지 않는다.
- 새 제품 기능 이름은 **미래 예측**. Prophet으로 선택한 센서/지표의 미래 측정값·추세·불확실성·조건에 따른 관리 기준 도달 예상 등을 제공한다.
- Prophet 시계열 예측은 **실제 잔여수명(RUL) 예측과 같지 않다.** 고장 종료점 근거가 없으면 '고장까지 남은 시간'을 표시하지 않는다.
- 기존 이상 탐지(PCA/Isolation Forest 및 독립적인 LSTM Autoencoder), EDA, 데이터 원본/품질/출처, 사람 검토 경로는 유지한다.
- 예제 체험→내 데이터 등록→검증→가능한 분석 안내→예측 실행→결과 확인의 **한 제품 경험**을 구성한다.

## 2. 외부 사례 및 활용 연구

| 검토 사례 | 사실과 활용 | 우리 제품 적용 / 한계 |
|---|---|---|
| [Prophet 공식 Quick Start](https://facebook.github.io/prophet/docs/quick_start.html) | `ds` 시각과 `y` 수치를 받아 `yhat`, `yhat_lower`, `yhat_upper`, 추세·주기 요소 제공 | CSV의 명시적인 신호 하나를 선택해 관측/예측 그래프 구성. 산업 고장 보증으로 해석 금지 |
| [해상풍력 디지털 트윈 논문(2023)](https://link.springer.com/article/10.1186/s42162-023-00257-4) | OPC UA·시각화와 Prophet으로 베어링 관련 온도·진동 상태 지표의 미래 추세 예측을 구성 | 센서의 상태 지표를 예측하고 사람이 검토하는 UI 참고. **시뮬레이션 기반 연구**이지 현장 정확성 보증 아님 |
| [열교환기 예측정비 연구(2024)](https://www.frontiersin.org/journals/manufacturing-technology/articles/10.3389/fmtec.2024.1475078/full) | 산업용 온도·압력의 미래 예측을 수행; 신호별로 적합한 모델이 달랐음 | 입력·시계열 특성에 따른 **예측 가능/불가 이유** 제공. 이번 제품에서 Ridge·LSTM RUL 비교 실험을 하자는 의미 아님 |
| [중소기업 의사결정 프로토타입(2023)](https://www.mdpi.com/2411-9660/7/4/98) | **합성** 산업 데이터의 일별 집계 시계열을 Prophet으로 예측 | 고주파 데이터의 요약 지표 예측과 결과 시각화 참고. 실설비 검증 사례로 주장 금지 |
| [Gradio Interface](https://gradio.app/guides/the-interface-class) / [Examples](https://gradio.app/guides/more-on-examples) | 예제·사용자 입력을 바꾸며 동일한 계산의 출력을 확인할 수 있음 | 예시→내 CSV→분석으로 자연스럽게 전환. 기존 Web을 Gradio로 교체할 필요 없음 |
| [AWS Lookout for Equipment](https://aws.amazon.com/lookout-for-equipment/) (구제품) | 데이터 업로드, 품질·모델 적합성, 결과 설명의 제품 경험 | 입력 품질·가능 기능 안내 참고. **2026-10-07 지원 종료**로 신규 기술 도입 대상으로 보지 않음 |

**활용 시나리오:** 공기압축기 전류·전압·주파수, 베어링 원본 파형에서 정당하게 추출한 획득별 RMS, 일관된 측정 시각/단위의 일반 CSV 센서값, 주기적으로 수집된 검사 수치. 원본 고주파 파형을 그대로 Prophet에 fit하지 않는다.

## 3. Prophet 기능·의존성·한계

- **추세와 변화점:** [Trend changepoints](https://facebook.github.io/prophet/docs/trend_changepoints.html). 추세 변화가 곧 열화·고장 원인은 아니다.
- **주기성 및 외생 변수:** [Seasonality and regressors](https://facebook.github.io/prophet/docs/seasonality%2C_holiday_effects%2C_and_regressors.html). 일/주/년 주기 추정은 충분한 과거 주기 자료가 있을 때만 사용. 미래 외생 변수도 준비돼야 한다(1.4.0 nested forecast는 별도 불확실성 포함).
- **예측 구간:** [Uncertainty intervals](https://facebook.github.io/prophet/docs/uncertainty_intervals.html). 기본 band는 과거 변화가 미래에도 유사하다는 가정에 의존; 검증되지 않은 '95% 고장 확률'로 바꾸지 않는다.
- **불규칙·부분 구간:** [Non-daily data](https://facebook.github.io/prophet/docs/non-daily_data.html). 수집 간격과 실제 관측 시간대에 맞춰 미래 시간축 제한.
- **극단치:** [Outliers](https://facebook.github.io/prophet/docs/outliers.html). 이상 데이터는 가정한 미래 trend 불확실성을 왜곡할 수 있으므로 원본 품질/의미 분리.
- **상한·하한:** [Saturating forecasts](https://facebook.github.io/prophet/docs/saturating_forecasts.html). 사용자 관리 기준이 모델의 물리적 cap/floor라는 뜻은 아니다.
- **결과 저장:** [Prophet serialization](https://facebook.github.io/prophet/docs/additional_topics.html)에서 제공하는 JSON을 사용. pickle 금지.
- **라이선스와 현황:** 공식 [GitHub](https://github.com/facebook/prophet)는 **v1.4.0(2026-08-01)부터 유지보수 모드**(기능 추가 계획 없음)를 명시. [MIT 라이선스](https://github.com/facebook/prophet/blob/main/LICENSE). Stan/CmdStanPy, pandas 등 운영 설치·배포 복잡도를 별도로 검증해야 한다. 현재 프로젝트의 **Python 3.14** 환경 호환성/성능은 아직 실행 검증하지 않았다.

## 4. 현재 저장소를 처음부터 검토한 구조와 문제

| 영역 | 현재 사실 | 관련 파일 |
|---|---|---|
| 데이터 등록 | 예시, CSV(20 MiB 이하 브라우저/서버 검증 후 저장), OPC UA 제공 | `apps/web/index.html`, `apps/web/csv-start.js`, `apps/README.md` |
| 신호 탐색 | Asset History, 시간/품질/출처, A/B 분포, 관계 및 조건부 원본 PSD | `apps/web/signal-explore.js`, `monitor-history.js` |
| 이상 탐지 | 명시적 모델 패키지 binding으로 XJTU IForest·LSTM AE/AI-Hub PCA·IForest 등 일부 지원. AI-Hub 운영 성능 평가 FAIL 보존 | `docs/status.md`, `apps/web/phm.js` |
| 기존 RUL | XJTU-SY 연구 Ridge/선택 LSTM으로 '마지막 기록 획득까지 남은 구간 수' 추정; 물리 고장 날짜 아님 | `docs/status.md`, `runtime/operations_web_phm.py` |
| 모델 호환 | snapshot/window 구분, 채널·샘플링 주파수·표본 수, 전기 신호 역할·단위 검증 | `runtime/operations_web_phm_models.py` |
| Web·권한 | `#rul` 탭, `rul-estimate` 결과, AI/Review 연동. 감독형 write broker와 독립 preview 분리 | `apps/web/navigation.js`, `phm.js`, `phm-explanation.js`, `runtime/operations_web_http.py` |
| Python 패키징 | `>=3.14,<3.15`; 기본 numpy/sklearn, `deep-learning` 선택 torch | `pyproject.toml` |

**문제 진단:** 현재 CSV가 저장되더라도 사용자가 즉시 사용할 수 있는 예측이 없다. `#rul`은 연결된 연구 모델이 없는 일반 데이터에서는 빈 화면이 된다. 사용자 요구는 물리적 잔여수명이 아니라 **내 데이터의 시간적 변화를 앞으로 살펴볼 수 있는 도구**에 가깝다. 단, Prophet을 붙인다고 모든 센서가 자동 예측 가능하거나 기존 이상 탐지 평가 문제가 해결되는 것은 아니다.

**중요한 기술 주의:** RUL은 화면에만 있지 않다. package output task, `operations phm bind`, runner/step 결과, Review와 AI 설명, URL bookmark, DB 및 테스트에 분산돼 있다. 단순 rename 또는 파일 일괄 삭제는 **이상 탐지 공유 기능을 망가뜨리거나 구형 결과를 새 Prophet 결과로 오해**하게 만들 수 있다.

## 5. 바꿀 사용자 경험

1. **예시 또는 내 데이터 선택**. 합성/기록 재생/실제 데이터 구별. 예시에서 **내 데이터로 해보기**로 이동.
2. **데이터 확인**. 원래 측정 시각, 출처/측정점, 단위, 누락/충돌/빈 값, 실제 그래프 및 현재 저장 여부 안내.
3. **할 수 있는 작업 안내**. `신호 탐색`, `이상 탐지(연결 모델 필요)`, `미래 예측(예측 적합성 확인)`의 실제 사용 가능 상태와 이유.
4. **미래 예측 설정**. 센서, 역사 기간, 예측 간격·미래 구간, 옵션인 관리 기준 지정 후 명시적 실행.
5. **예측 결과**. 과거 실측/미래 예상/모델 예측 구간, 단위, 각종 시각, 데이터 품질, 지원 조건에서 추세 변화·주기 상세. 점수/물리 고장 판정과 혼동 금지.
6. **후속 탐색**. 기간 바꾸기, EDA와 다른 센서, 지원되는 이상 탐지, 기록 저장/AI 질문으로 이동하되 신호·시간·출처 맥락 유지.

**명칭 규칙:** `RUL`→`미래 예측`; `고장 임계값` 대신 `명시적인 관리 기준`; `남은 수명 X일` 대신 `예상 기준 도달 시점(관리 기준에 한함)`; Prophet 기본 band를 고장 확률이나 보증된 신뢰 구간이라고 하지 않는다.

## 6. 기술 목표 설계

```text
CSV / OPC UA / 격리 예시
  -> 검증된 Asset History/획득별 요약 신호
  -> 데이터·예측 가능성 점검 (신호/단위/품질/시간 간격)
  -> 명시적 Forecast Job (Prophet optional runtime)
  -> 저장된 ForecastRun + 근거 snapshot + 모델/기간/생성 시각
  -> Web "미래 예측" (실측 / 예측 / band / 관리 기준)
```

- **단변량부터**: 선택한 `asset/source/measurement_point/channel/semantic_binding` 한 가지 의미·단위의 수치만 사용; 다른 소스와 측정 지점의 임의 병합 금지.
- **시간**: 원본 event timestamp를 UTC로 해석하고 화면은 KST로 표시. 시간대 없는 CSV·중복 시각·품질 불량·장기 갭을 무시하거나 합성값으로 채우지 않음. 베어링 **획득 번호를 시간 단위로 조용히 바꾸지 않음**.
- **적합성**: 수치·time span·cadence·연속 구간·gap·중복·선택 horizon의 구체적 거부 이유. 최소 표본 수, 최대 horizon, timeout 등은 별도 명시적 정책으로 확정할 것(임의로 보편 성능 기준 선언 금지).
- **엔진**: `ForecastService`(가칭)와 Prophet 어댑터 분리. `forecast` optional extra 고려, uv.lock/Python 3.14/Linux CI 설치를 검증해 버전 결정. fit은 조회 GET에 포함하지 않고 명시적 run으로만 실행.
- **저장**: 원본 이력 snapshot, source/point/channel/semantic/unit, cutoff, freq/horizon, run/job 상태, Prophet/package/runtime version, user threshold origin, predicted `at/yhat/lower/upper`, 경고·오류, 입력 해시와 계산 근거.
- **API(제안)**: `GET /api/v1/forecast/capabilities`, `POST /api/v1/forecast/runs`, `GET /api/v1/forecast/runs/{run_id}`, `GET /api/v1/forecast/runs?asset_id=...`. 세부 URI는 구현 시 확정.
- **실행 보호**: supervisor-owned job/command 제어, CSRF/origin/권한 서버 검증, 중복 요청과 재시작·취소·timeout·자원 상한·stale response 처리.
- **기준 도달 예상**: 사용자가 정의한 기준값과 출처·단위를 명시했을 때만 계산. `yhat` 최초 교차는 **평균 예측 경로의 교차 시점**일 뿐 고장 날짜가 아니다. 예측 구간의 교차가 불확실하면 단정적인 시간 금지.
- **검증**: Ridge/LSTM RUL과 **성능 비교 없음**. 대신 제품 기능 자체에 대한 시간 누수, 과거 cutoff 기반 단독 시계열 검증, 결과 유한성, 단위/원본 무결성, 설치·성능·동시성·에러를 확인. 품질 근거 부족 시 '정확도 미검증'이라고 표시. [Prophet diagnostics](https://facebook.github.io/prophet/docs/diagnostics.html), [rolling-origin evaluation](https://otexts.com/fpp3/tscv.html).

## 7. 운영 RUL 제거 영향도(기존 연구 보존)

| 확인할 경로 | 안전한 처리 |
|---|---|
| `apps/web/index.html`, `navigation.js`, `phm.js`, `phm-connect.js`, `phm-explanation.js`, `monitor.js` | 기존 RUL 화면·설명·권한 경로 정리; anomaly 관련 UI 공유 부분 보존 |
| `runtime/operations_web_phm.py`, `operations_web_phm_models.py`, PHM runner/패키지 | `rul-estimate`의 생성·연결·분석 제거, anomaly 동작·binding 유지 |
| `models/rul_ridge_regression.py`, `models/lstm_rul_regression.py`, `models/package.py`, `models/package_lstm.py` | 참조 추적 후 운영 전용 코드만 제거, 공용/연구 사용 여부 확인 |
| XJTU `package-xjtu`/replay/CLI | 이상 탐지용 패키징·원본 재생이 RUL 제거와 함께 삭제되지 않도록 분리 |
| 과거 PHM SQLite 결과, AI/Review, bookmarks | 구형 RUL 기록은 과거의 의미로 보존/읽기 전용 처리 정책; `#rul` URL이 새 Prophet 값으로 조용히 이동하지 않도록 명시 |
| `tests/acceptance/test_operations_phm_*browser.py`, `tests/unit/test_rul_*`, `tests/contract/test_xjtu_rul_*` | 운영 RUL에만 속하는 테스트 교체; anomalyl/공용 재생/연구 재현 근거 테스트는 보존하거나 research로 이동 |
| `README.md`, `apps/README.md`, `docs/status.md`, `docs/product/overview.md`, ADR | 새 제품 기능 반영, 과거 연구 평가 결과를 현행 운영 지원으로 주장하지 않음 |

위 파일들은 **영향 조사 대상**으로, 전부 삭제한다는 뜻이 아니다. 특히 LSTM Autoencoder는 이상 탐지 기능이므로 'LSTM RUL 제거'와 혼동하면 안 된다.

## 8. 실행 백로그 및 인수 기준

| 순위 | 작업 | 완료 기준 |
|---|---|---|
| P0-1 | 요구·명칭·schema 정의 | 예측/RUL/관리 기준 의미 분리, 과거 결과 호환 정책 명시 |
| P0-2 | `rul-estimate` 사용처/DB/API 의존성 전수 조사 | 제거/유지/읽기 전용 대상 목록 리뷰 |
| P0-3 | 데이터 적합성·기능 안내 API | CSV/베어링 요약/전기 신호/모델 없음의 사용 가능 이유 표시 |
| P0-4 | Prophet optional extra·어댑터·CI | Python 3.14 설치, 예측 입력/출력, bounded 실행 |
| P0-5 | ForecastRun·job·결과 조회 | 재시작/중복/실패 안정성, cutoff·원본 스냅샷 보존 |
| P0-6 | 미래 예측 Web | 내 데이터→신호·기간→실행→측정/예측/band 결과 |
| P0-7 | 예시→내 데이터 UX | 예시 격리와 실제 데이터 등록·저장을 모두 지원 |
| P0-8 | 운영 Ridge/LSTM RUL 삭제 | anomaly/EDA/AI/replay/Review 회귀 통과 |
| P0-9 | legacy RUL URL·저장 이력 처리 | 구 결과 오표시·데이터 손실 없음 |
| P1-10 | 관리 기준·조건부 도달 예상 | 기준 출처/단위 확인, 고장 날짜 자동 판단 금지 |
| P1-11 | 추세·계절성 상세와 화면/AI 연결 | 허용 조건 명시, 390/1024/1440px·키보드 확인 |
| P1-12 | 문서·최종 상태 갱신 | CLI·README·docs/status 일치, 기존 연구 근거 보존 |
| P2 | 다변량 운전 조건·알림·자동 갱신 | 별도 요구/안전/운영 검증 후 판단 |

**권장 PR 분리**
1. PR-A: capability·입력/결과 계약·RUL 영향 명세.
2. PR-B: Prophet adapter·job·provenance·단위/계약 검사.
3. PR-C: 예시/내 데이터 체험 + 미래 예측 UI(#575 공통 UX 변경과 rebase).
4. PR-D: 기존 RUL 운영 코드 제거·legacy compatibility·문서·회귀.

이는 모델 우열 실험이 아니라, 이상 탐지와 데이터 근거를 보호하며 단계적으로 운영 기능을 교체하는 전략이다. 하나의 큰 PR보다 리뷰·롤백이 명확하다.

### 필수 사용자 인수 시나리오

- 빈 작업공간→예제 열기→실제 CSV로 전환→검증·저장→예측 첫 결과.
- 적합한 CSV의 한 센서 예측, time zone 누락/중복 시각/NaN/단위 변경/기록 공백 오류.
- 고주파 베어링 파형을 그대로 fit하지 않음, 정당한 획득 요약을 사용.
- 모델 없는 설비에서 EDA는 계속 사용, 예측 사용 가능 조건 별도 안내.
- 기준값 없음/있음, 예상 교차 없음, 불확실한 예상 교차 각각 올바른 문구.
- 기록 재생과 실제 수집 시각을 구분하고, 예측 생성 시각·학습 cutoff 표시.
- Prophet 미설치·감독형 종료·오류·중복/취소/재시작에서도 무근거 결과 미표시.
- 구 `#rul` 링크와 저장 결과를 새 Prophet 예측이라고 재해석하지 않음.
- 이상 탐지 IForest/PCA/LSTM AE, AI 질문, 사람 검토, CSV/EDA, 브라우저 390/1024/1440px 회귀 통과.

## 9. 명시적 비범위 / 남은 검증

- Ridge·LSTM RUL과 Prophet 사이의 **모델 비교 실험을 하지 않음**.
- 새로운 물리 고장 날짜·잔여 수명·고장 확률·자동 정비 권고를 주장하지 않음.
- 연구 노트북·XJTU RUL 실험·기존 검증 기록을 무조건 삭제하지 않음.
- Prophet 신규 의존성의 실제 설치, 예측 품질/자원 한도, 전체 코드/브라우저 회귀는 **이번 조사 단계에서 수행하지 않음**.
- 현재 프로젝트는 로컬 단일 사용자 파일럿이며 원격/멀티테넌트 운영 보증 대상이 아님.

## 10. 참고 저장소·문서

- [현재 기능 상태](https://github.com/so9093-K/industrial-phm-framework/blob/main/docs/status.md)
- [Operations 사용법](https://github.com/so9093-K/industrial-phm-framework/blob/main/apps/README.md)
- [모델 입력 호환성](https://github.com/so9093-K/industrial-phm-framework/blob/main/src/industrial_phm/runtime/operations_web_phm_models.py)
- [PHM Web](https://github.com/so9093-K/industrial-phm-framework/blob/main/src/industrial_phm/apps/web/phm.js)
- [CSV 등록](https://github.com/so9093-K/industrial-phm-framework/blob/main/src/industrial_phm/apps/web/csv-start.js)
- [Python 의존성](https://github.com/so9093-K/industrial-phm-framework/blob/main/pyproject.toml)

**범위 고지:** 저장소 현재 상태·주요 경로를 정적 검토하고 공식 문서·연구 사례를 확인한 결과다. 새 코드 구현/실행 검증/실제 사용성 테스트는 후속 작업이다.
