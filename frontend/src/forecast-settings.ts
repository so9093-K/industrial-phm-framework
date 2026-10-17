import {parseOutlookSettings,type OutlookSettings} from "./projections.ts";
export type ForecastSettings = OutlookSettings & {backtest:"one"|"multi"};
export function savedSettings(params:URLSearchParams):ForecastSettings {
  return {changepointPriorScale:Number(params.get("forecast_prior")??"0.05"),
    changepointRange:Number(params.get("forecast_range")??"0.9"),
    trainingPoints:params.get("forecast_training")?Number(params.get("forecast_training")):null,
    seasonality:params.get("forecast_seasonality")==="off"?"off":"auto",
    backtest:params.get("forecast_backtest")==="multi"?"multi":"one"};
}
export function settingsQuery(settings?:ForecastSettings):Record<string,string> {
  if(!settings)return {};
  const s=settings;
  if(!Number.isFinite(s.changepointPriorScale)||s.changepointPriorScale<0.001||s.changepointPriorScale>0.5
    ||!Number.isFinite(s.changepointRange)||s.changepointRange<0.5||s.changepointRange>0.95
    ||(s.trainingPoints!==null&&(!Number.isSafeInteger(s.trainingPoints)||s.trainingPoints<20||s.trainingPoints>1000)))
    throw new Error("예측 설정의 범위를 확인하세요. 학습 개수는 20~1000 사이의 정수입니다.");
  return {changepoint_prior_scale:String(s.changepointPriorScale),changepoint_range:String(s.changepointRange),
    ...(s.trainingPoints===null?{}:{training_points:String(s.trainingPoints)}),seasonality:s.seasonality};
}
export function rememberSettings(url:URL,s:ForecastSettings):void {
  const values={forecast_prior:String(s.changepointPriorScale),forecast_range:String(s.changepointRange),
    forecast_training:s.trainingPoints===null?"":String(s.trainingPoints),forecast_seasonality:s.seasonality,forecast_backtest:s.backtest};
  for(const [key,value] of Object.entries(values))if(value)url.searchParams.set(key,value);else url.searchParams.delete(key);
}
export function verifySettings(forecast:unknown,outlook:unknown,expected?:ForecastSettings):void {
  if(!expected)return;
  const model=(forecast as {model?:unknown})?.model;
  const actual=parseOutlookSettings((outlook as {settings?:unknown})?.settings);
  const fitted=model as Record<string,unknown>|null;
  if(!actual||!fitted||fitted.changepoint_prior_scale!==expected.changepointPriorScale
    ||fitted.changepoint_range!==expected.changepointRange||fitted.training_points!==expected.trainingPoints
    ||actual.changepointPriorScale!==expected.changepointPriorScale||actual.changepointRange!==expected.changepointRange
    ||actual.trainingPoints!==expected.trainingPoints||actual.seasonality!==expected.seasonality)
    throw new Error("예측과 기준 도달 계산의 설정이 입력한 값과 달라 결과를 표시하지 않았습니다.");
}
export type Backtest={points:number;error:number;naive:number;coverage:number};
export function backtests(raw:unknown):Backtest[] {
  const data=raw as {backtest?:unknown;rolling_backtests?:unknown};
  const values=[...(data.backtest?[data.backtest]:[]),...(Array.isArray(data.rolling_backtests)?data.rolling_backtests:[])];
  return values.map(value=>{const v=value as Record<string,unknown>;
    if(!v||typeof v.points!=="number"||!Number.isSafeInteger(v.points)||v.points<1
      ||![v.mean_absolute_error,v.naive_mean_absolute_error,v.inside_interval].every(n=>typeof n==="number"&&Number.isFinite(n))
      ||Number(v.mean_absolute_error)<0||Number(v.naive_mean_absolute_error)<0||Number(v.inside_interval)<0||Number(v.inside_interval)>1)
      throw new Error("과거 예측 검증값의 형식이 올바르지 않습니다.");
    return {points:v.points,error:Number(v.mean_absolute_error),naive:Number(v.naive_mean_absolute_error),coverage:Number(v.inside_interval)};
  });
}
