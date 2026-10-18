/** A finite, reproducible reading path through real application results. */
export const steps = [
  {id:"observe", title:"무엇부터 볼까요?", label:"1. 관측", href:"/web/",
    question:"일정한 기록과 변화가 있는 기록을 구분해 보세요.",
    evidence:"두 합성 펌프의 4시간 기록입니다. demo-pump-change(변화 기록)를 골라 신호를 확인할 수 있습니다."},
  {id:"signals", title:"어떤 값이 변했나요?", label:"2. 신호",
    href:"/web/?page=assets&tab=signals&monitor_asset=demo-pump-change&monitor_channel=current_a&monitor_range=24h&monitor_anchor=latest",
    question:"전반부와 후반부의 전류 흐름은 어떻게 다른가요?",
    evidence:"처음 120분은 약 8 A, 이후에는 의도적으로 증가시킨 입력입니다. 신호를 temperature_c로 바꿔 함께 살펴보세요."},
  {id:"compare", title:"변화를 숫자로 확인하세요", label:"3. 비교",
    href:"/web/?page=assets&tab=change&method=compare&data=history&monitor_asset=demo-pump-change&monitor_channel=current_a",
    question:"두 기간의 대표값과 유효한 측정 수를 비교해 보세요.",
    evidence:"A와 B는 같은 파일의 앞·뒤 절반입니다. A를 정상 기준으로 검증한 것은 아닙니다."},
  {id:"outlook", title:"이 추세가 이어진다면?", label:"4. 전망",
    href:"/web/?page=assets&tab=outlook&data=history&monitor_asset=demo-pump-change&monitor_channel=current_a&projection_horizon=1h&projection_management=13&projection_end=15&forecast_seasonality=off",
    question:"‘계산하기’를 눌러 1시간 전망과 기준 도달 조건을 확인하세요.",
    evidence:"13 A·15 A는 체험용 임의 기준입니다. 표시되는 전망은 실제 Prophet 계산 결과이며 고장 시점을 뜻하지 않습니다."},
  {id:"review", title:"판단의 근거를 남깁니다", label:"5. 검토",
    href:"/web/?page=maintenance&monitor_asset=demo-pump-change",
    question:"어떤 입력에서 나온 분석인지, 무엇을 더 확인할지 읽어 보세요.",
    evidence:"실제 애플리케이션으로 저장한 분석·검토 메모입니다. 이 체험은 보기 전용이며 새 기록이나 AI 답변을 만들지 않습니다."},
] as const;

export function currentStep(search: string): number {
  const query = new URLSearchParams(search);
  if(query.get("page")==="maintenance")return 4;
  if(query.get("tab")==="outlook")return 3;
  if(query.get("tab")==="change")return 2;
  if(query.get("tab")==="signals")return 1;
  return 0;
}
