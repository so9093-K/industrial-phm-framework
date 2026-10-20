/** Reading a CSV in the browser before anything is sent: which columns hold times and
 * numbers, what would stop it being stored, and what the values look like. Only an
 * orientation; the server's validator decides. */

const ISO=/^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?(Z|[+-]\d{2}:?\d{2})?$/;
const NUMBER=/^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/;
const TIME_NAME=/time|timestamp|date|시각|시간|일시/i;
export const MAX_CSV_BYTES=20*1024*1024;
export const MAX_CHANNELS=12;

export type CsvColumn={
  name:string;index:number;numeric:number;missing:number;invalid:number;iso:number;
  firstMissing:number|null;firstInvalid:number|null;firstNonIso:number|null;
};
export type CsvTable={header:string[];rows:string[][];columns:CsvColumn[];problems:string[];times:CsvColumn[];sampleCount:number};
export type TimeReading={points:{at:number;row:string[]}[];naive:boolean;firstBackwards:number|null;firstInvalidDate:number|null};
export type ColumnSummary={count:number;missing:number;min:number|null;median:number|null;max:number|null;mean:number|null};
export type IntervalSummary={usualSeconds:number;uneven:number;longestSeconds:number;longestAfter:number|null};
export type PreviewPoint={at:number;mean:number;min:number;max:number};

/** "1e999" or "NaN" is not a measured value. */
export function numberOf(text:string):number|null{
  return text&&NUMBER.test(text)&&Number.isFinite(Number(text))?Number(text):null;
}

/** RFC 4180 subset matching the server's csv module: comma, double quotes, CRLF or LF. */
export function parseCsv(text:string):string[][]{
  const rows:string[][]=[];let row:string[]=[],field="",quoted=false;
  for(let i=0;i<text.length;i++){
    const c=text[i];
    if(quoted){
      if(c!=='"')field+=c;
      else if(text[i+1]==='"'){field+='"';i++;}else quoted=false;
    }else if(c==='"'&&field==="")quoted=true;
    else if(c===","){row.push(field);field="";}
    else if(c==="\n"||c==="\r"){
      if(c==="\r"&&text[i+1]==="\n")i++;
      row.push(field);rows.push(row);row=[];field="";
    }else field+=c;
  }
  if(field!==""||row.length){row.push(field);rows.push(row);}
  return rows;
}

export function inspectCsv(rows:string[][]):CsvTable{
  const header=rows[0]??[];
  const columns:CsvColumn[]=header.map((name,index)=>({name,index,numeric:0,missing:0,invalid:0,iso:0,
    firstMissing:null,firstInvalid:null,firstNonIso:null}));
  const problems:string[]=[];
  let blank:number|null=null,width:number|null=null;
  const data=rows.slice(1);
  data.forEach((row,offset)=>{
    const line=offset+2;
    if(row.length===1&&row[0]===""){blank??=line;return;}
    if(row.length!==header.length){width??=line;return;}
    for(const column of columns){
      const value=row[column.index].trim();
      if(!value){column.missing++;column.firstMissing??=line;continue;}
      if(ISO.test(value))column.iso++;else column.firstNonIso??=line;
      if(numberOf(value)!==null)column.numeric++;
      else{column.invalid++;column.firstInvalid??=line;}
    }
  });
  if(!header.length||header.some(name=>!name.trim()))problems.push("첫 줄에 이름이 빈 열이 있습니다. 첫 줄의 열 이름을 확인하세요.");
  if(new Set(header).size!==header.length)problems.push("첫 줄에 같은 열 이름이 두 번 이상 있습니다.");
  if(blank)problems.push(blank+"행이 빈 줄입니다. 빈 줄을 지우세요.");
  if(width)problems.push(width+"행의 값 개수가 헤더와 다릅니다. 쉼표와 따옴표를 확인하세요.");
  const sampleCount=data.filter(row=>row.length===header.length&&!(row.length===1&&row[0]==="")).length;
  // A time column may still contain a bad row; keep it as a candidate and report that row.
  const times=columns.filter(c=>c.iso&&c.iso>=sampleCount/2)
    .sort((a,b)=>Number(TIME_NAME.test(b.name))-Number(TIME_NAME.test(a.name))||a.index-b.index);
  return {header,rows:data,columns,problems,times,sampleCount};
}

export function readTimes(table:CsvTable,columnIndex:number):TimeReading{
  const points:{at:number;row:string[]}[]=[];
  let previous:number|null=null,firstBackwards:number|null=null,firstInvalidDate:number|null=null,naive=false;
  table.rows.forEach((row,offset)=>{
    if(row.length!==table.header.length)return;
    const text=row[columnIndex].trim(),match=ISO.exec(text);
    if(!match)return;
    if(!match[1])naive=true;
    // Without an offset the wall time is placed on UTC only to order and space the preview.
    const at=Date.parse(match[1]?text.replace(" ","T"):text.replace(" ","T")+"Z");
    const day=Date.parse(text.slice(0,10)+"T00:00:00Z");
    if(!Number.isFinite(at)||!Number.isFinite(day)||new Date(day).toISOString().slice(0,10)!==text.slice(0,10)
      ||Number(text.slice(11,13))>23){firstInvalidDate??=offset+2;return;}
    if(previous!==null&&!(at>previous))firstBackwards??=offset+2;
    previous=at;points.push({at,row});
  });
  return {points,naive,firstBackwards,firstInvalidDate};
}

/** The offsets offered for wall times written without one: Korea first, then UTC and this
 * computer's own offset when it differs. */
export function offsetChoices(minutesWestOfUtc=new Date().getTimezoneOffset()):{value:string;label:string}[]{
  const choices=[{value:"+09:00",label:"한국 표준시 (UTC+09:00)"},{value:"+00:00",label:"UTC (UTC+00:00)"}];
  const east=-minutesWestOfUtc,hours=Math.floor(Math.abs(east)/60),minutes=Math.abs(east)%60;
  const local=(east<0?"-":"+")+String(hours).padStart(2,"0")+":"+String(minutes).padStart(2,"0");
  return choices.some(choice=>choice.value===local)?choices:[...choices,{value:local,label:"이 컴퓨터의 시간대 (UTC"+local+")"}];
}

/** Problems that would stop this file from being stored, in the words a person can act on.
 * Wall times without an offset are fine once the person says which offset they were written in. */
export function previewProblems(table:CsvTable,timeIndex:number,channels:string[],offset:string|null=null):string[]{
  const list=[...table.problems];
  if(timeIndex<0)list.push("시각 열을 찾지 못했습니다. 예: 2026-10-11T09:00:00+09:00 형식의 시각이 있어야 저장할 수 있습니다.");
  else{
    const timing=readTimes(table,timeIndex);
    const column=table.columns.find(c=>c.index===timeIndex)!;
    if(timing.naive&&!offset)list.push("시각에 시간대(+09:00, Z 등)가 없습니다. 어느 시간대의 시각인지 고르세요.");
    if(column.missing)list.push(column.firstMissing+"행의 시각이 비어 있습니다 (빈 시각 "+column.missing+"개).");
    if(column.firstNonIso)list.push(column.firstNonIso+"행의 시각을 읽을 수 없습니다. 예: 2026-10-11T09:00:00+09:00");
    if(timing.firstBackwards)list.push(timing.firstBackwards+"행의 시각이 앞 행보다 늦지 않습니다. 시간 순서로 정렬하고 중복 시각을 확인하세요.");
    if(timing.firstInvalidDate)list.push(timing.firstInvalidDate+"행의 날짜·시각이 달력에 없는 값입니다.");
  }
  for(const name of channels){
    const column=table.columns.find(c=>c.name===name);
    if(column?.missing)list.push(name+" 열의 "+column.firstMissing+"행이 비어 있습니다 (빈 값 "+column.missing+"개). 빈 측정값은 저장할 수 없습니다.");
  }
  if(!channels.length)list.push("저장할 측정값 열을 하나 이상 고르세요.");
  return list;
}

/** Numeric columns other than the time column, chosen by default up to the limit. */
export function channelChoices(table:CsvTable,timeIndex:number):{name:string;usable:boolean;note:string}[]{
  return table.columns.filter(c=>c.index!==timeIndex).map(column=>{
    const usable=column.numeric>0&&!column.invalid;
    const note=!usable?(column.invalid?"숫자가 아닌 값 "+column.invalid+"개 ("+column.firstInvalid+"행부터)":"값 없음")
      :column.missing?"빈 값 "+column.missing+"개 ("+column.firstMissing+"행부터)":"";
    return {name:column.name,usable,note};
  });
}

function median(sorted:number[]):number|null{
  if(!sorted.length)return null;
  const middle=sorted.length>>1;
  return sorted.length%2?sorted[middle]:(sorted[middle-1]+sorted[middle])/2;
}

export function summarize(table:CsvTable,name:string):ColumnSummary{
  const column=table.columns.find(c=>c.name===name)!;
  const values:number[]=[];
  for(const row of table.rows){
    if(row.length!==table.header.length)continue;
    const value=numberOf(row[column.index].trim());
    if(value!==null)values.push(value);
  }
  const sorted=values.slice().sort((a,b)=>a-b);
  let total=0;for(const value of values)total+=value;
  return {count:values.length,missing:column.missing,min:sorted[0]??null,median:median(sorted),
    max:sorted.at(-1)??null,mean:values.length?total/values.length:null};
}

/** How regularly rows were measured: the usual gap, how many gaps differ from it a lot,
 * and the longest gap. */
export function intervals(timing:TimeReading):IntervalSummary|null{
  if(timing.points.length<3)return null;
  const gaps:number[]=[];
  for(let i=1;i<timing.points.length;i++)gaps.push((timing.points[i].at-timing.points[i-1].at)/1000);
  const usual=median(gaps.filter(gap=>gap>0).sort((a,b)=>a-b))??0;
  const uneven=gaps.filter(gap=>usual>0&&(gap>usual*1.5||gap<usual*0.5)).length;
  let longest=0;
  for(let i=1;i<gaps.length;i++)if(gaps[i]>gaps[longest])longest=i;
  return {usualSeconds:usual,uneven,longestSeconds:gaps[longest],
    longestAfter:gaps[longest]>usual*1.5&&!timing.naive?timing.points[longest].at:null};
}

/** Mean, minimum and maximum per equal time slice; never spreads a large file into arguments. */
export function previewPoints(table:CsvTable,timing:TimeReading,name:string,slices=120):PreviewPoint[]{
  const column=table.columns.find(c=>c.name===name);
  if(!column||!timing.points.length)return [];
  let start=Infinity,end=-Infinity;
  for(const {at} of timing.points){if(at<start)start=at;if(at>end)end=at;}
  const step=Math.max(1,Math.ceil((Math.max(end,start+1000)-start)/slices));
  const buckets=new Map<number,{sum:number;count:number;min:number;max:number}>();
  for(const {at,row} of timing.points){
    const value=numberOf(row[column.index].trim());
    if(value===null)continue;
    const index=Math.min(slices-1,Math.floor((at-start)/step));
    const bucket=buckets.get(index);
    if(bucket){bucket.sum+=value;bucket.count++;bucket.min=Math.min(bucket.min,value);bucket.max=Math.max(bucket.max,value);}
    else buckets.set(index,{sum:value,count:1,min:value,max:value});
  }
  return [...buckets].sort((a,b)=>a[0]-b[0]).map(([index,b])=>({at:start+index*step,mean:b.sum/b.count,min:b.min,max:b.max}));
}

/** A readable, unique-enough source ID from the file name. */
export function suggestedSourceId(fileName:string,suffix:string):string{
  const stem=fileName.replace(/\.csv$/i,"").toLowerCase().replace(/[^a-z0-9_-]+/g,"-").replace(/^-+|-+$/g,"").slice(0,80)||"file";
  return "csv-"+stem+"-"+suffix;
}

const QUANTITY: [RegExp, string][] = [
  [/^(current|curr|amps?)$/, "전류"], [/^(voltage|volt|volts)$/, "전압"], [/^(temperature|temp)$/, "온도"],
  [/^(pressure|press)$/, "압력"], [/^(vibration|vib)$/, "진동"], [/^(flow|flowrate)$/, "유량"],
  [/^humidity$/, "습도"], [/^power$/, "전력"], [/^(frequency|freq)$/, "주파수"], [/^torque$/, "토크"],
  [/^(speed|rpm)$/, "회전 속도"],
];
// What a column measures on, when its name says so before the quantity (motor_temp_c → 모터 온도).
const SUBJECT: Record<string, string> = {
  motor: "모터", bearing: "베어링", pump: "펌프", oil: "오일", inlet: "입구", outlet: "출구",
  ambient: "주변", winding: "권선", gear: "기어", fan: "팬", casing: "케이싱",
};
// An example unit per quantity for the unit field's placeholder; the field itself stays empty.
const UNIT_EXAMPLE: Record<string, string> = {
  전류: "A", 전압: "V", 온도: "°C", 압력: "bar", 진동: "mm/s", 유량: "m³/h", 습도: "%", 전력: "kW",
  주파수: "Hz", 토크: "N·m", "회전 속도": "rpm",
};
function readName(name: string): {quantity: string; subject: string | null; rest: string[] | null} | null {
  const tokens = name.toLowerCase().split(/[_\-\s.]+/).filter(Boolean);
  const at = tokens.findIndex((token) => QUANTITY.some(([pattern]) => pattern.test(token)));
  if (at < 0 || at > 1) return null;
  const subject = at === 1 ? SUBJECT[tokens[0]] ?? null : null;
  if (at === 1 && !subject) return null;
  const rest = tokens.slice(at + 1);
  return {quantity: QUANTITY.find(([pattern]) => pattern.test(tokens[at]))![1], subject,
    rest: rest.length <= 2 && rest.every((token) => /^[a-z0-9]{1,3}$/.test(token)) ? rest : null};
}
/** A starting name for each column whose name says what it measures (current_a → 전류,
 * motor_temp_c → 모터 온도). Only the quantity is suggested; a unit is never read from a
 * suffix, since "a" may be a phase. */
export function suggestSignalNames(columns: string[]): Map<string, string> {
  const parsed = columns.map((name) => ({name, read: readName(name)}));
  const names = new Map<string, string>();
  for (const {name, read} of parsed) {
    if (!read || read.rest === null) continue;
    const word = (read.subject ? read.subject + " " : "") + read.quantity;
    const shared = parsed.filter((other) => other.read && (other.read.subject ? other.read.subject + " " : "") + other.read.quantity === word).length > 1;
    names.set(name, shared && read.rest.length ? word + " " + read.rest.join(" ").toUpperCase() : word);
  }
  return names;
}
/** An example unit for a column's quantity, shown as a hint only. */
export function unitExample(column: string): string | null {
  const read = readName(column);
  return read ? UNIT_EXAMPLE[read.quantity] ?? null : null;
}
