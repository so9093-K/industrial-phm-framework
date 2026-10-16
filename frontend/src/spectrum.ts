/** Server-owned Welch PSD of verified original acquisition waveforms, by ordinal. */
export type Span={from:number;to:number};
export type Spans={a:Span;b:Span};
export type Acquisition={source:string;binding:string;first:number;last:number;count:number};
export type FrequencyBand={from:number;to:number;changeDb:number};
export type SpectrumChannel={id:string;label:string;a:number[];b:number[];bands:FrequencyBand[]};
export type Spectrum={asset:string;source:string;samplingRate:number;segment:number;
  frequencies:number[];used:{a:number[];b:number[]};channels:SpectrumChannel[]};
export class SpectrumUnavailable extends Error {}
export class WaveformUnavailable extends Error {}
function record(value:unknown):Record<string,unknown>|null{
  return value && typeof value==="object" && !Array.isArray(value)?value as Record<string,unknown>:null;
}
function id(raw:unknown):string{
  if(typeof raw!=="string" || !raw)throw new Error("획득 신호 식별자가 올바르지 않습니다.");
  return raw;
}
function count(raw:unknown):number{
  if(typeof raw!=="number" || !Number.isSafeInteger(raw) || raw<0)
    throw new Error("획득 회차의 기록 수가 올바르지 않습니다.");
  return raw;
}
function num(raw:unknown):number{
  if(typeof raw!=="number" || !Number.isFinite(raw))
    throw new Error("주파수 또는 파워 스펙트럼 수치가 올바르지 않습니다.");
  return raw;
}
export function parseAcquisition(payload:unknown,asset:string):Acquisition|null{
  const body=record(payload);
  if(!body || body.schema_version!==1 || body.asset_id!==asset)
    throw new Error("다른 설비의 획득 데이터 목록이 반환됐습니다.");
  if(body.acquisition===null)return null;
  const acquisition=record(body.acquisition);
  if(!acquisition)throw new Error("획득 데이터 계약이 올바르지 않습니다.");
  const first=count(acquisition.first),last=count(acquisition.last);
  if(last<first)throw new Error("획득 회차 순서가 올바르지 않습니다.");
  return {source:id(acquisition.source_id),binding:id(acquisition.binding_id),
    first,last,count:count(acquisition.count)};
}
export function defaultSpans(acq:Acquisition):Spans{
  if(acq.first>=acq.last)throw new SpectrumUnavailable("비교할 획득 회차가 두 개 이상 필요합니다.");
  const mid=Math.floor((acq.first+acq.last)/2);
  return {a:{from:acq.first,to:mid},b:{from:mid+1,to:acq.last}};
}
export function validateSpans(spans:Spans):void{
  for(const name of ["a","b"] as const){
    const value=spans[name];
    if(count(value.from)>count(value.to))throw new Error("획득 회차 범위가 뒤바뀌었습니다.");
  }
}
export function parseSpectrum(
  payload:unknown,asset:string,acq:Acquisition,spans:Spans,
):Spectrum{
  validateSpans(spans);
  const data=record(payload),used=record(data?.acquisitions);
  if(!data || data.schema_version!==1 || data.asset_id!==asset || data.kind!=="acquisition"
    || !Array.isArray(data.frequencies) || !Array.isArray(data.channels)||!used
    || !Array.isArray(used.a)||!Array.isArray(used.b))
    throw new Error("서버 파형 스펙트럼 응답의 자료 형태가 맞지 않습니다.");
  const frequency=data.frequencies.map(num);
  if(frequency.length===0 || frequency.some((n,i)=>n<0||(i>0&&n<=frequency[i-1])))
    throw new Error("스펙트럼 주파수 축이 증가하지 않습니다.");
  const usedOrdinal={a:used.a.map(count),b:used.b.map(count)};
  for(const n of ["a","b"] as const){
    if(usedOrdinal[n].length===0||usedOrdinal[n].length>8
      ||usedOrdinal[n].some(v=>v<spans[n].from||v>spans[n].to))
      throw new Error("요청하지 않은 획득 회차가 스펙트럼에 포함됐습니다.");
  }
  const keys=new Set<string>();
  const channels=data.channels.map((raw:unknown):SpectrumChannel=>{
    const channel=record(raw);
    if(!channel || !Array.isArray(channel.a)||!Array.isArray(channel.b)
      || !Array.isArray(channel.band_changes))
      throw new Error("파형별 스펙트럼 구조가 올바르지 않습니다.");
    const name=id(channel.channel);
    if(keys.has(name))throw new Error("획득 신호가 중복됐습니다.");
    keys.add(name);
    const a=channel.a.map(num),b=channel.b.map(num);
    if(a.length!==frequency.length||b.length!==frequency.length||a.some(n=>n<0)||b.some(n=>n<0))
      throw new Error("주파수와 스펙트럼 파워 배열이 일치하지 않습니다.");
    const bands=channel.band_changes.map((item:unknown):FrequencyBand=>{
      const row=record(item);
      if(!row)throw new Error("대역 변화 수치가 올바르지 않습니다.");
      const from=num(row.from_hz),to=num(row.to_hz),changeDb=num(row.change_db);
      if(from<0||to<from||to>frequency[frequency.length-1])
        throw new Error("파워 대역 범위가 유효하지 않습니다.");
      return {from,to,changeDb};
    });
    return {id:name,label:typeof channel.label==="string"?channel.label:name,a,b,bands};
  });
  const rate=num(data.sampling_rate_hz),segment=count(data.segment);
  if(rate<=0||segment<2)throw new Error("파형의 기록 주파수 또는 분석 구간이 올바르지 않습니다.");
  return {asset,source:acq.source,samplingRate:rate,segment,frequencies:frequency,
    used:usedOrdinal,channels};
}
async function json(path:string,signal:AbortSignal):Promise<unknown>{
  const response=await fetch(path,{signal,cache:"no-store",credentials:"same-origin"});
  if(response.status===404){
    const error:unknown=await response.json().catch(()=>null);
    if(record(error)?.error==="nothing_to_explore")
      throw new SpectrumUnavailable("선택한 획득 회차에 저장된 원본 파형이 없습니다.");
  }
  if(response.status===409){
    const error:unknown=await response.json().catch(()=>null);
    if(record(error)?.error==="original_waveform_unavailable")
      throw new WaveformUnavailable("검증된 원본 파형 파일에 접근할 수 없습니다.");
  }
  if(!response.ok)throw new Error("파형 스펙트럼 조회 오류입니다. 스펙트럼 없음과 다릅니다.");
  return await response.json() as unknown;
}
export async function readAcquisition(asset:string,signal:AbortSignal):Promise<Acquisition|null>{
  return parseAcquisition(await json(
    "/api/v1/explore/sources?"+new URLSearchParams({asset_id:asset}),signal),asset);
}
export async function readSpectrum(
  asset:string,acq:Acquisition,spans:Spans,signal:AbortSignal,
):Promise<Spectrum>{
  validateSpans(spans);
  const query=new URLSearchParams({asset_id:asset,
    a_from:String(spans.a.from),a_to:String(spans.a.to),
    b_from:String(spans.b.from),b_to:String(spans.b.to)});
  return parseSpectrum(await json("/api/v1/explore/spectrum?"+query,signal),asset,acq,spans);
}
