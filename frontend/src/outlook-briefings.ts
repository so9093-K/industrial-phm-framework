/** Version-bound outlook explanations; the server alone computes facts and authorizes writes. */
import {parseOutlookSettings,type Projection} from "./projections.ts";
import type {AcquisitionProjection} from "./acquisition-outlook.ts";
export type BriefingProjection=Projection|AcquisitionProjection;
const isAcquisition=(p:BriefingProjection):p is AcquisitionProjection=>"featureId" in p;

export type BriefingFact={label:string;text:string};
export type BriefingAnswer={
  summary:string;points:Array<{text:string;evidence:string[]}>;
  evidence:Record<string,BriefingFact>;source:string;
};
export type Briefing={
  id:string;question:string;status:"pending"|"complete"|"failed";
  requestedAt:string;finishedAt:string|null;model:string|null;answer:BriefingAnswer|null;
};
export class BriefingEvidenceChanged extends Error {}
export class BriefingUnavailable extends Error {}

function object(raw:unknown):Record<string,unknown>|null{
  return raw!==null&&typeof raw==="object"&&!Array.isArray(raw)?raw as Record<string,unknown>:null;
}
function value(raw:unknown,label:string,max=600):string{
  if(typeof raw!=="string"||!raw.trim()||raw.length>max)
    throw new Error(label+" 형식이 올바르지 않습니다.");
  return raw;
}
function time(raw:unknown):string{
  const text=value(raw,"해설 시각",64);
  if(!/(?:Z|[+-]\d{2}:\d{2})$/.test(text)||!Number.isFinite(Date.parse(text)))
    throw new Error("해설 시각이 올바르지 않습니다.");
  return text;
}

/** Python urlencode(sorted(selection.items())) is the authoritative identity. */
export function briefingSelection(projection:BriefingProjection):string{
  if(!/^[a-f0-9]{64}$/.test(projection.dataVersion)
    ||!projection.outlookSettings||!projection.assetId
    ||!(isAcquisition(projection)?projection.featureId:projection.channel)
    ||!["upper","lower"].includes(projection.conditions.direction))
    throw new Error("해설을 만들 결과의 조건을 확인할 수 없습니다.");
  const entries:Record<string,string>={
    asset_id:projection.assetId,
    kind:isAcquisition(projection)?"acquisition":"history",
    series:isAcquisition(projection)?projection.featureId:projection.channel,
    direction:projection.conditions.direction,data_version:projection.dataVersion,
    changepoint_prior_scale:String(projection.outlookSettings.changepointPriorScale),
    changepoint_range:String(projection.outlookSettings.changepointRange),
    seasonality:projection.outlookSettings.seasonality,
  };
  if(isAcquisition(projection)){
    entries.source_id=projection.sourceId;
    entries.binding_id=projection.bindingId;
    entries.measurement_version=projection.measurementVersion;
    entries.time_basis=projection.timeBasis;
    if(projection.recordedPeriod!==null)
      entries.recorded_period_seconds=String(projection.recordedPeriod);
    if(projection.assumedPeriod!==null)
      entries.assumed_period_seconds=String(projection.assumedPeriod);
  }
  if(projection.outlookSettings.trainingPoints!==null)
    entries.training_points=String(projection.outlookSettings.trainingPoints);
  if(projection.conditions.management!==null)
    entries.management_limit=String(projection.conditions.management);
  if(projection.conditions.end!==null)
    entries.end_limit=String(projection.conditions.end);
  const query=new URLSearchParams();
  for(const key of Object.keys(entries).sort())query.set(key,entries[key]);
  return query.toString();
}
function requestArgs(projection:BriefingProjection):Record<string,string>{
  return Object.fromEntries(new URLSearchParams(briefingSelection(projection)));
}

/** The outlook is recomputed by the server; a changed data version invalidates the
 * cached measurement projection even when the original last timestamp did not move. */
export function verifyOutlookVersion(raw:unknown,projection:BriefingProjection):void{
  const root=object(raw),conditions=object(root?.conditions);
  const actualSettings=parseOutlookSettings(root?.settings);
  const expectedSettings=projection.outlookSettings;
  const acquisition=isAcquisition(projection);
  const stream=acquisition?projection.featureId:projection.channel;
  const expectedKind=acquisition?"acquisition":"history";
  const expectedAxis=acquisition?"acquisition":"time";
  const acquireMatches=!acquisition||(
    root?.binding_id===projection.bindingId
    &&root?.time_basis===projection.timeBasis
    &&root?.recorded_period_seconds===projection.recordedPeriod
    &&root?.assumed_period_seconds===projection.assumedPeriod
    &&root?.period_seconds===projection.effectivePeriod
    &&object(root?.record)?.first===projection.record.first
    &&object(root?.record)?.last===projection.record.last
    &&object(root?.record)?.points===projection.record.points
    &&object(root?.search)?.acquisitions===projection.searchCount
    &&object(root?.search)?.until===projection.searchUntil
  );
  if(!root||root.schema_version!==1||root.asset_id!==projection.assetId
    ||root.kind!==expectedKind||root.series!==stream||root.axis!==expectedAxis
    ||root.source_id!==projection.sourceId
    ||(root.measurement_point_id??null)!==(acquisition?null:projection.pointId)
    ||!acquireMatches
    ||root.measurement_version!==projection.measurementVersion
    ||root.data_version!==projection.dataVersion
    ||!actualSettings||!expectedSettings
    ||actualSettings.changepointPriorScale!==expectedSettings.changepointPriorScale
    ||actualSettings.changepointRange!==expectedSettings.changepointRange
    ||actualSettings.trainingPoints!==expectedSettings.trainingPoints
    ||actualSettings.seasonality!==expectedSettings.seasonality
    ||!conditions||conditions.direction!==projection.conditions.direction
    ||conditions.management!==projection.conditions.management
    ||conditions.end!==projection.conditions.end)
    throw new BriefingEvidenceChanged(
      "계산 후 데이터나 계산 조건이 바뀌어 이전 결과와 해설을 숨겼습니다. 다시 계산하세요."
    );
}

function parseAnswer(raw:unknown):BriefingAnswer{
  const result=object(raw),facts=object(result?.evidence),points=result?.points;
  if(!result||!facts||!Array.isArray(points)||points.length>4)
    throw new Error("해설에 쓴 계산 사실의 형식이 올바르지 않습니다.");
  const evidence:Record<string,BriefingFact>={};
  for(const [key,rawFact] of Object.entries(facts)){
    const fact=object(rawFact);
    if(!fact||Object.keys(evidence).length>=32)
      throw new Error("해설에 쓴 계산 사실을 확인할 수 없습니다.");
    evidence[key]={
      label:value(fact.label,"근거 이름",200),
      text:value(fact.text,"근거 설명",1800),
    };
  }
  const parsed=points.map((p:unknown)=>{
    const part=object(p);
    if(!part||!Array.isArray(part.evidence)||part.evidence.length>3
      ||part.evidence.length===0)
      throw new Error("해설 문장과 계산 사실의 연결이 올바르지 않습니다.");
    const referenced=part.evidence.map((k:unknown)=>{
      const key=value(k,"근거 식별자",128);
      if(!Object.hasOwn(evidence,key))
        throw new Error("해설이 없는 계산 사실을 근거로 들어 숨겼습니다.");
      return key;
    });
    return {text:value(part.text,"해설 문장",280),evidence:referenced};
  });
  const checks=object(result.checks);
  const source=checks?.source;
  if(source!==undefined&&source!=="model"&&source!=="model-trimmed"&&source!=="computed")
    throw new Error("해설을 만든 방식을 확인할 수 없습니다.");
  return {summary:value(result.summary,"AI 요약",700),
    points:parsed,evidence,source:typeof source==="string"?source:"unknown"};
}
export function parseBriefings(raw:unknown,expectedSelection:string):Briefing[]{
  const root=object(raw);
  if(!root||root.schema_version!==1||root.selection!==expectedSelection
    ||!Array.isArray(root.briefings)||root.briefings.length>5)
    throw new BriefingEvidenceChanged("해설이 지금 결과와 다른 조건에 대한 것이라 숨겼습니다.");
  const seen=new Set<string>();
  return root.briefings.map((item:unknown):Briefing=>{
    const row=object(item);
    if(!row||!["pending","failed","complete"].includes(String(row.status)))
      throw new Error("해설의 저장 상태가 올바르지 않습니다.");
    const id=value(row.id,"해설 ID",128);
    if(seen.has(id))throw new Error("같은 해설이 두 번 돌아왔습니다.");
    seen.add(id);
    const status=row.status as Briefing["status"];
    if(row.answer!==null&&status!=="complete")
      throw new Error("아직 만드는 중인 해설에 답변이 붙어 있습니다.");
    if(status==="complete"&&row.answer===null)
      throw new Error("완료된 해설에 내용이 없습니다.");
    return {id,status,question:value(row.question,"질문",600),
      requestedAt:time(row.requested_at),
      finishedAt:row.finished_at===null?null:time(row.finished_at),
      model:row.model===null?null:value(row.model,"AI 모델 이름",256),
      answer:row.answer===null?null:parseAnswer(row.answer)};
  });
}
async function fetchJson(url:string,signal:AbortSignal,options:RequestInit={}):Promise<unknown>{
  const response=await fetch(url,{...options,signal,cache:"no-store",credentials:"same-origin"});
  if(!response.ok){
    if(response.status===404||response.status===422)
      throw new BriefingUnavailable("이 결과나 저장된 해설을 찾을 수 없습니다.");
    throw new Error("해설을 불러오지 못했습니다. 이전 해설을 최신으로 보여 주지 않습니다.");
  }
  return await response.json() as unknown;
}
export async function assertCurrentVersion(projection:BriefingProjection,signal:AbortSignal):Promise<void>{
  const query=new URLSearchParams(requestArgs(projection));
  for(const key of ["data_version","source_id","binding_id","measurement_version",
    "time_basis","recorded_period_seconds"])query.delete(key);
  const body=await fetchJson("/api/v1/outlook?"+query,signal);
  verifyOutlookVersion(body,projection);
}
export async function readBriefings(projection:BriefingProjection,signal:AbortSignal):Promise<Briefing[]>{
  const selection=briefingSelection(projection);
  return parseBriefings(
    await fetchJson("/api/v1/outlook/briefings?"+selection,signal),selection);
}
export async function readPermission(signal:AbortSignal):Promise<boolean>{
  const response=object(await fetchJson("/api/v1/session",signal));
  if(!response||response.schema_version!==1)
    throw new Error("해설 작성 권한을 확인할 수 없습니다.");
  return response.can_change===true&&response.write_scope==="supervisor-owned-source-control";
}
export async function requestBriefing(
  projection:BriefingProjection,question:string,signal:AbortSignal,
):Promise<string>{
  const selection=briefingSelection(projection);
  const trimmed=question.trim();
  if(!trimmed||trimmed.length>600)throw new Error("질문은 1~600자로 입력하세요.");
  await assertCurrentVersion(projection,signal);
  const session=object(await fetchJson("/api/v1/session",signal));
  if(!session||session.schema_version!==1
    ||session.can_change!==true
    ||session.write_scope!=="supervisor-owned-source-control"
    ||typeof session.csrf_token!=="string"||session.csrf_token.length<16)
    throw new BriefingUnavailable("보기 전용이라 해설을 만들 수 없습니다.");
  const raw=await fetchJson("/api/v1/outlook/briefings/request",signal,{
    method:"POST",
    headers:{"Content-Type":"application/json","X-CSRF-Token":session.csrf_token},
    body:JSON.stringify({...requestArgs(projection),question:trimmed}),
  });
  const result=object(raw);
  if(!result||result.status!=="pending"||result.selection!==selection)
    throw new BriefingEvidenceChanged("요청한 조건과 다른 해설 요청이 접수돼 결과를 숨겼습니다.");
  return value(result.briefing_id,"AI 브리핑 요청 식별자",128);
}
