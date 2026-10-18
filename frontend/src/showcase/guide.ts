/** A finite, reproducible reading path through real application results. */
export const steps = [
  {id:"observe", title:"무엇부터 볼까요?", label:"1. 관측", href:"/web/",
    question:"일정한 기록과 변화가 있는 기록을 구분해 보세요.",
    evidence:"두 합성 펌프의 4시간 기록입니다. 순환 펌프 2호기의 변화 기록을 골라 신호를 확인할 수 있습니다."},
  {id:"signals", title:"어떤 값이 변했나요?", label:"2. 신호",
    href:"/web/?page=assets&tab=signals&monitor_asset=demo-pump-change&monitor_channel=current_a&monitor_range=24h&monitor_anchor=latest",
    question:"전반부와 후반부의 전류 흐름은 어떻게 다른가요?",
    evidence:"처음 120분은 약 8 A, 이후에는 의도적으로 증가시킨 입력입니다. 온도 신호(temperature_c)도 함께 증가하도록 생성했습니다."},
  {id:"anomaly", title:"기준에서 벗어나기 시작한 때는?", label:"3. 이상 탐지",
    href:"/web/?page=assets&tab=anomaly&method=baseline&monitor_asset=demo-pump-change&monitor_channel=current_a&departure_baseline=first-30",
    question:"기록 초반과 비교해 크게 벗어난 구간과 그 정도를 확인하세요.",
    evidence:"이 체험은 중앙값·MAD 기반의 기준 구간 이탈 분석입니다. 학습한 이상 탐지 모델 점수나 고장 확률은 아닙니다. 제품의 별도 모델 점수 분석에는 모델 패키지와 측정 기록이 필요합니다."},
  {id:"compare", title:"변화를 숫자로 확인하세요", label:"4. 비교",
    href:"/web/?page=assets&tab=change&method=compare&data=history&monitor_asset=demo-pump-change&monitor_channel=current_a",
    question:"두 기간의 대표값과 유효한 측정 수를 비교해 보세요.",
    evidence:"A와 B는 같은 파일의 앞·뒤 절반입니다. A를 정상 기준으로 검증한 것은 아닙니다."},
  {id:"outlook", title:"추세 예측과 잔여수명(RUL)을 확인하세요", label:"5. 추세 예측·RUL",
    href:"/web/?page=assets&tab=outlook&data=history&monitor_asset=demo-pump-change&monitor_channel=current_a&projection_horizon=1h&projection_management=13&projection_end=15&forecast_seasonality=off",
    question:"‘계산하기’를 눌러 1시간 추세 예측과 종료 기준 15 A까지 남은 시간을 확인하세요.",
    evidence:"실제 Prophet 계산 결과입니다. RUL은 사용자가 정한 종료 기준까지의 조건부 전망입니다. 13 A·15 A는 체험용 임의 기준이므로 실제 고장 시각이나 검증된 수명을 뜻하지 않습니다."},
  {id:"review", title:"판단의 근거를 남깁니다", label:"6. 검토",
    href:"/web/?page=maintenance&monitor_asset=demo-pump-change",
    question:"어떤 입력에서 나온 분석인지, 무엇을 더 확인할지 읽어 보세요.",
    evidence:"실제 애플리케이션으로 저장한 분석·검토 메모입니다. 이 체험은 보기 전용이며 새 기록이나 AI 답변을 만들지 않습니다."},
] as const;

export function currentStep(search: string): number {
  const query = new URLSearchParams(search);
  if(query.get("page")==="maintenance")return 5;
  if(query.get("tab")==="outlook")return 4;
  if(query.get("tab")==="change")return 3;
  if(query.get("tab")==="anomaly")return 2;
  if(query.get("tab")==="signals")return 1;
  return 0;
}
