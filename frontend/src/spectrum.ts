/** Server-owned Welch PSD of verified original acquisition waveforms, by ordinal. */
export type Span={from:number;to:number};
export type Spans={a:Span;b:Span};
export type Acquisition={source:string;binding:string;first:number;last:number;count:number};
export type FrequencyBand={from:number;to:number;changeDb:number};
export type SpectrumChannel={id:string;label:string;unit?:string|null;a:number[];b:number[];bands:FrequencyBand[]};
export type Spectrum={asset:string;source:string;samplingRate:number;segment:number;
  frequencies:number[];used:{a:number[];b:number[]};channels:SpectrumChannel[]};
export class SpectrumUnavailable extends Error {}
export class WaveformUnavailable extends Error {}
function record(value:unknown):Record<string,unknown>|null{
  return value && typeof value==="object" && !Array.isArray(value)?value as Record<string,unknown>:null;
}
function id(raw:unknown):string{
  if(typeof raw!=="string" || !raw)throw new Error("진동 채널 식별 정보가 올바르지 않습니다.");
  return raw;
}
function count(raw:unknown):number{
  if(typeof raw!=="number" || !Number.isSafeInteger(raw) || raw<0)
    throw new Error("진동 측정 수가 올바르지 않습니다.");
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
    throw new Error("다른 설비의 진동 측정 목록이 돌아왔습니다.");
  if(body.acquisition===null)return null;
  const acquisition=record(body.acquisition);
  if(!acquisition)throw new Error("진동 측정 목록의 형식이 올바르지 않습니다.");
  const first=count(acquisition.first),last=count(acquisition.last);
  if(last<first)throw new Error("측정 순서가 올바르지 않습니다.");
  return {source:id(acquisition.source_id),binding:id(acquisition.binding_id),
    first,last,count:count(acquisition.count)};
}
export function defaultSpans(acq:Acquisition):Spans{
  if(acq.first>=acq.last)throw new SpectrumUnavailable("비교하려면 진동 측정이 두 번 이상 필요합니다.");
  const mid=Math.floor((acq.first+acq.last)/2);
  return {a:{from:acq.first,to:mid},b:{from:mid+1,to:acq.last}};
}
export function validateSpans(spans:Spans):void{
  for(const name of ["a","b"] as const){
    const value=spans[name];
    if(count(value.from)>count(value.to))throw new Error("처음 측정이 마지막 측정보다 뒤에 있습니다.");
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
    throw new Error("주파수 분석 결과의 형식이 올바르지 않습니다.");
  const frequency=data.frequencies.map(num);
  if(frequency.length===0 || frequency.some((n,i)=>n<0||(i>0&&n<=frequency[i-1])))
    throw new Error("스펙트럼 주파수 축이 증가하지 않습니다.");
  const usedOrdinal={a:used.a.map(count),b:used.b.map(count)};
  for(const n of ["a","b"] as const){
    if(usedOrdinal[n].length===0||usedOrdinal[n].length>8
      ||usedOrdinal[n].some(v=>v<spans[n].from||v>spans[n].to))
      throw new Error("고르지 않은 측정이 주파수 분석에 들어 있어 표시하지 않았습니다.");
  }
  const rate=num(data.sampling_rate_hz),segment=count(data.segment);
  if(rate<=0||segment<2)throw new Error("파형의 기록 주파수 또는 분석 구간이 올바르지 않습니다.");
  // Band edges retain the original Welch frequency resolution; displayed
  // frequencies are *averages* of bins, whose last center is below Nyquist.
  const nyquist=rate/2;
  if(frequency[frequency.length-1]>nyquist)
    throw new Error("표시 주파수가 측정 가능한 범위(Nyquist)를 넘었습니다.");
  const keys=new Set<string>();
  const channels=data.channels.map((raw:unknown):SpectrumChannel=>{
    const channel=record(raw);
    if(!channel || !Array.isArray(channel.a)||!Array.isArray(channel.b)
      || !Array.isArray(channel.band_changes))
      throw new Error("파형별 스펙트럼 구조가 올바르지 않습니다.");
    const name=id(channel.channel);
    if(keys.has(name))throw new Error("같은 진동 채널이 두 번 들어 있습니다.");
    keys.add(name);
    const a=channel.a.map(num),b=channel.b.map(num);
    if(a.length!==frequency.length||b.length!==frequency.length||a.some(n=>n<0)||b.some(n=>n<0))
      throw new Error("주파수와 스펙트럼 파워 배열이 일치하지 않습니다.");
    const bands=channel.band_changes.map((item:unknown):FrequencyBand=>{
      const row=record(item);
      if(!row)throw new Error("대역 변화 수치가 올바르지 않습니다.");
      const from=num(row.from_hz),to=num(row.to_hz),changeDb=num(row.change_db);
      if(from<0||to<from||to>nyquist)
        throw new Error("파워 대역 범위가 유효하지 않습니다.");
      return {from,to,changeDb};
    });
    return {id:name,label:typeof channel.label==="string"?channel.label:name,
      unit:typeof channel.unit==="string"?channel.unit:null,a,b,bands};
  });
  return {asset,source:acq.source,samplingRate:rate,segment,frequencies:frequency,
    used:usedOrdinal,channels};
}
async function json(path:string,signal:AbortSignal):Promise<unknown>{
  const response=await fetch(path,{signal,cache:"no-store",credentials:"same-origin"});
  if(response.status===404){
    const error:unknown=await response.json().catch(()=>null);
    if(record(error)?.error==="nothing_to_explore")
      throw new SpectrumUnavailable("고른 측정에는 저장된 원본 파형이 없습니다.");
  }
  if(response.status===409){
    const error:unknown=await response.json().catch(()=>null);
    if(record(error)?.error==="original_waveform_unavailable")
      throw new WaveformUnavailable("검증된 원본 파형 파일에 접근할 수 없습니다.");
  }
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new Error("파형 스펙트럼 조회 오류입니다. 스펙트럼 없음과 다릅니다.");
  }
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
