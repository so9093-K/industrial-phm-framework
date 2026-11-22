<script lang="ts">
  import {untrack,type Snippet} from "svelte";
  /** 부하(전류) 한 칸: 평균과 그 시간의 최저~최고. */
  type LoadPoint={x:number;value:number;join:boolean;low:number;high:number};
  import XAxis from "./XAxis.svelte";
  import TrendChart from "./TrendChart.svelte";
  import {measure} from "../chart-axis";
  import {measurementScale} from "../time-axis";
  import {bandName} from "../record-findings";
  import {versusStart} from "../change-story";
  import {SERIES_COLORS, type FleetChange, type FleetGroup} from "../fleet-observation";
  import type {Evidence} from "../change-investigation";
  import {clockText,focusWindow,spanText,startsZoomed,valueAt,visiblePoints,type Span,type TimelineLane,type TimelineOperation} from "../asset-timeline";
  /** 고른 변화를 관제 화면과 같은 그래프 규칙으로 크게 본다. 같은 시기에 함께 변한 신호 중 단위가 같은 것은
   * 한 그래프에 겹치고(R·S·T상은 관제 화면과 같은 색), 단위가 다른 것은 같은 시간축의 작은 그래프로 아래에 둔다.
   * 처음 범위(변화로 판단하지 않는 범위)·처음 수준·같은 운전 수준의 값은 고른 신호에만 그린다. */
  let {axis,record,episode,ongoing,episodes=[],lanes,operation=null,load=null,periodSeconds=null,selected=null,onSelect,onFocus,actions,context,assistant,assistantFirst=false}:{
    axis:"time"|"acquisition";record:Span;episode:Span;ongoing:boolean;
    episodes?:{label:string;selected:boolean;onPick:()=>void}[];lanes:TimelineLane[];operation?:TimelineOperation|null;
    /** 부하 신호(전류): 보이는 구간의 실제 추이를 읽어 그래프 아래에 그린다. 없으면 운전 수준 띠를 그린다. */
    load?:{label:string;unit:string|null;read:(from:number,to:number,signal:AbortSignal)=>Promise<LoadPoint[]>}|null;
    actions?:Snippet;context?:Snippet;periodSeconds?:number|null;selected?:number|null;onSelect?:(at:number)=>void;onFocus?:(key:string)=>void;
    /** 오른쪽 칸의 AI 조사. 답의 근거를 가리키면(point) 그래프가 그 선·구간·운전 수준 띠만 또렷하게 남긴다. */
    assistant?:Snippet<[{colorOf:(reviewKey:string)=>string|null;labelOf:(reviewKey:string)=>string|null;point:(evidence:Evidence|null)=>void;close:()=>void}]>;
    /** 관제의 'AI 조사'로 들어왔으면 오른쪽 칸을 AI 조사로 연다. */
    assistantFirst?:boolean}=$props();
  let zoomed=$state(false),cursor:number|null=$state(null);
  let rail=$state<"context"|"assistant">(untrack(()=>assistantFirst)?"assistant":"context");
  const chatting=$derived(rail==="assistant"&&!!assistant);
  // 가리킨 근거: 찾은 변화는 그 줄, 운전 수준은 띠와 고른 신호의 같은 수준 값. 그래프 밖의 근거는 가리키지 않는다.
  let pointed:Evidence|null=$state(null);
  const emphasis=$derived.by(()=>{
    const target=pointed;
    if(target?.kind==="change"){const lane=lanes.find(row=>row.reviewKey===target.review_key);return lane?{lanes:[lane.key],operation:false}:null;}
    if(target?.kind==="operation"&&operation)return {lanes:[focused.key],operation:true};
    return null;
  });
  const focused=$derived(lanes.find(lane=>lane.focus)??lanes[0]);
  $effect(()=>{zoomed=startsZoomed(record,episode)||(axis==="time"&&(episode.to-episode.from)<(record.to-record.from)/4);});
  const range=$derived(zoomed?focusWindow(record,episode):record);
  const lo=$derived(range.from),hi=$derived(Math.max(range.to,range.from+1));
  const place=(at:number)=>axis==="time"?clockText(at):at+"번째 측정";
  const span=(r:Span)=>axis==="time"?spanText(r.from,r.to):r.from+"–"+r.to+"번째 측정";
  const scale=$derived(axis==="time"?{kind:"clock" as const}:measurementScale(periodSeconds));
  // 'R상전압' → 'R상': 같은 그래프에 상이 여럿일 때만 줄여 쓴다.
  const short=(lane:TimelineLane,many:boolean)=>many&&/^[RST]상/.test(lane.label)?lane.label.slice(0,2):lane.label;
  /** 단위가 같은 줄끼리 한 그래프. 고른 신호의 그래프가 맨 위, 상은 R·S·T 순서(색이 관제 화면과 같다). */
  const panels=$derived.by(()=>{
    const groups=new Map<string,TimelineLane[]>();
    for(const lane of lanes){const key=lane.unit?"unit:"+lane.unit:"lane:"+lane.key;groups.set(key,[...(groups.get(key)??[]),lane]);}
    return [...groups.values()].map(members=>[...members].sort((a,b)=>a.label.localeCompare(b.label,"ko")))
      .sort((a,b)=>Number(b.includes(focused))-Number(a.includes(focused)));
  });
  function chartOf(members:TimelineLane[]){
    const main=members.includes(focused)?focused:members[0],many=members.length>1;
    const group:FleetGroup={label:many?members.map(lane=>short(lane,true).replace(/상$/,"")).join("·")+"상 "+main.label.replace(/^[RST]상/,""):main.label,
      unit:main.unit,axis,focus:main.key,record,bucketMs:null,periodSeconds,
      series:members.map(lane=>({key:lane.key,channel:lane.key,label:lane.label,short:short(lane,many),
        points:visiblePoints(lane,range,zoomed).map(point=>({x:point.x,value:point.value,join:point.join===true}))}))};
    const changes:FleetChange[]=members.map(lane=>({key:lane.key,channel:lane.key,label:lane.label,from:lane.interval.from,to:lane.interval.to,
      up:lane.up,before:lane.values?.before??null,after:lane.values?.after??null}));
    return {group,changes,main,many};
  }
  const charts=$derived(panels.map(chartOf));
  /** 근거 줄의 색 표시: 그 변화가 그래프에서 쓰는 색. */
  function colorOf(reviewKey:string):string|null{
    const lane=lanes.find(row=>row.reviewKey===reviewKey);
    for(const chart of charts){const index=chart.group.series.findIndex(row=>row.key===lane?.key);if(index>=0)return SERIES_COLORS[index%SERIES_COLORS.length];}
    return null;
  }
  /** 근거 줄의 이름: 그 변화가 그래프에서 쓰는 이름. */
  const labelOf=(reviewKey:string)=>lanes.find(row=>row.reviewKey===reviewKey)?.label??null;
  const point=(evidence:Evidence|null)=>pointed=evidence;
  $effect(()=>{if(rail!=="assistant")pointed=null;});
  // 값 읽기는 가장 가까운 점이 점 간격의 1.5배 안에 있을 때만(공백의 다른 측정으로 대신하지 않는다).
  const reach=$derived.by(()=>{
    const points=charts[0]?.group.series[0]?.points??[];
    const gaps=points.slice(1).map((p,i)=>p.x-points[i].x).sort((a,b)=>a-b);
    return Math.max(gaps[Math.floor(gaps.length/2)]??1,axis==="time"?1000:1)*1.5;
  });
  // 포인터가 없으면 보이는 범위 안의 마지막 점(확대 중이면 확대 범위의 끝)을 읽는다.
  const shownLast=$derived(charts[0]?.group.series.find(row=>row.key===focused?.key)?.points.at(-1)?.x??null);
  // 보이는 범위 밖의 자리(재생으로 범위가 바뀐 뒤의 이전 선택 등)는 읽지 않는다.
  const inside=(at:number|null)=>at!==null&&at>=lo&&at<=hi?at:null;
  const readAt=$derived(inside(cursor)??inside(selected)??shownLast);
  const shade=(level:number,count:number)=>.18+.72*level/Math.max(1,count);
  // 보이는 구간(기록 전체·확대)이 바뀔 때마다 그 구간의 부하 추이를 다시 읽는다.
  let loadPoints:LoadPoint[]|null=$state(null);
  $effect(()=>{
    const source=load,from=lo,to=hi;
    loadPoints=null;
    if(!source||axis!=="time")return;
    const request=new AbortController();
    void source.read(from,to,request.signal).then(points=>{if(!request.signal.aborted)loadPoints=points;}).catch(()=>{});
    return()=>request.abort();
  });
  // 부하 값 읽기도 자기 점 간격의 1.5배 안에서만(보이는 구간을 120칸으로 읽어 전압 칸과 간격이 다르다).
  const loadReach=$derived.by(()=>{const points=loadPoints??[];const gaps=points.slice(1).map((p,i)=>p.x-points[i].x).sort((a,b)=>a-b);
    return Math.max(gaps[Math.floor(gaps.length/2)]??1,1000)*1.5;});
  const loadGroup=$derived.by(():FleetGroup|null=>!load||!loadPoints?null:{label:load.label,unit:load.unit,axis,focus:"load",record,bucketMs:null,periodSeconds,
    series:[{key:"load",channel:"load",label:load.label,short:load.label,points:loadPoints}]});
</script>
{#if focused}
<section class="timeline" class:chatting aria-label="선택한 변화"><div class="main">
  <header class="headline"><div><h2>{focused.label} · {focused.values&&focused.values.after!==null?versusStart(focused.values.after,focused.values.before,focused.unit):"초기보다 "+(focused.up?"높음":"낮음")}</h2>
    <p>{span(focused.interval)}{ongoing?" · 기록 끝까지 이어짐":""}{focused.condition?" · "+focused.condition+"일 때":""}</p></div>
    <div class="head-tools">
      <label class="signal-choice">조사할 신호<select value={focused.key} onchange={e=>onFocus?.(e.currentTarget.value)}>{#each lanes as lane(lane.key)}<option value={lane.key}>{lane.label}</option>{/each}</select></label>
      {#if assistant}<button type="button" class="ai-toggle" aria-pressed={chatting} onclick={()=>rail=chatting?"context":"assistant"}>
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z"/></svg>AI 조사</button>{/if}
    </div>
  </header>
  {#if !focused.values}<p class="numbers">{focused.numbers}</p>{/if}
  <div class="toolbar"><div class="choices" role="group" aria-label="보는 범위"><button type="button" aria-pressed={!zoomed} onclick={()=>zoomed=false}>기록 전체</button><button type="button" aria-pressed={zoomed} onclick={()=>zoomed=true}>특이사항 확대</button></div>
    {#if episodes.length>1}<div class="choices" role="group" aria-label="변화 시기">{#each episodes as item,i(i)}<button type="button" aria-pressed={item.selected} onclick={item.onPick}>{item.label}</button>{/each}</div>{/if}
    <ul class="legend" aria-label="그래프 읽는 법">
      <li><i class="band-key"></i>초기 범위</li><li><i class="dash"></i>초기 수준</li><li><i class="change-key"></i>특이사항</li>
      {#if focused.condition && focused.matched?.length}<li><i class="dot" style:background={SERIES_COLORS[0]}></i>{focused.condition} 중의 값</li>{/if}
    </ul>
  </div>
  <div class="reading-layout" class:solo={chatting}><div class="plots">
    {#each charts as chart,index(chart.group.focus)}
      <div class="lane-heading" class:main={index===0}>
        <strong>{chart.group.label}</strong>
        {#if readAt!==null}<span class="readout">{#each chart.group.series as row,i(row.key)}{@const point=valueAt(row.points,readAt,reach)}<span><i style:background={SERIES_COLORS[i%SERIES_COLORS.length]}></i>{chart.many?row.short+" ":""}<b>{point?measure(point.value,chart.group.unit,4):"—"}</b></span>{/each}{#if index===0}<small>{place(readAt)}{readAt===shownLast&&inside(cursor)===null?(zoomed&&shownLast!==null&&hi<record.to?" · 확대 범위의 끝":" · 마지막"):""}</small>{/if}</span>{/if}
      </div>
      <TrendChart group={chart.group} series={chart.group.series} {lo} {hi} changes={chart.changes} axis={false}
        reference={chart.main===focused?focused.values?.before??null:null} band={chart.main===focused?focused.usual:null}
        marks={chart.main===focused?(focused.matched??[]):[]} height={index===0?(charts.length>2?190:240):76}
        dim={emphasis?chart.group.series.filter(row=>!emphasis.lanes.includes(row.key)).map(row=>row.key):[]}
        guide={cursor} picked={selected} onPick={at=>onSelect?.(at)} bind:cursor/>
    {/each}
    {#if load&&loadGroup}
      <div class="lane-heading"><strong>{load.label}</strong><span class="levels"><span><i class="mean-key"></i>평균</span><span><i class="spread-key"></i>최저~최고</span></span>
        {#if readAt!==null}{@const point=valueAt(loadPoints??[],readAt,loadReach)}<span class="readout"><span><i style:background="var(--color-ink-muted)"></i><b>{point?measure(point.value,load.unit,3):"—"}</b>{#if point&&point.high>point.low}<small>{measure(point.low,load.unit,3)}~{measure(point.high,load.unit,3)}</small>{/if}</span></span>{/if}</div>
      <!-- 운전 수준 띠 대신 실제 전류 추이: 전압이 오른 동안 부하가 어땠는지 같은 시간축에서 읽힌다. -->
      <div class="load-chart" class:pointed={emphasis?.operation} class:faint={emphasis&&!emphasis.operation}>
        <TrendChart group={loadGroup} series={loadGroup.series} spread={loadPoints??[]} {lo} {hi} axis={false} height={84} colors={["var(--color-ink-muted)"]}
          changes={[{key:"focus",channel:"focus",label:focused.label,from:focused.interval.from,to:focused.interval.to,up:focused.up,before:null,after:null}]}
          guide={cursor} picked={selected} onPick={at=>onSelect?.(at)} bind:cursor/>
      </div>
    {:else if operation}
      <div class="lane-heading"><strong>운전 수준</strong><span class="levels">{#each operation.names.levels as _,i(i)}<span><i class="level-key" style:opacity={shade(i+1,operation.names.levels.length)}></i>{bandName(operation.names,i+1)}</span>{/each}<span><i class="level-key stop"></i>정지</span></span></div>
      <!-- 칸마다 가장 오래 운전한 수준 하나를 진하기로 칠한다(진할수록 높은 전류). 부하가 바뀐 때가 띠에서 바로 보인다. -->
      <div class="strip" class:pointed={emphasis?.operation} class:faint={emphasis&&!emphasis.operation}><span></span><svg viewBox="0 0 1000 20" preserveAspectRatio="none" role="img" aria-label="같은 시각에 가장 오래 운전한 수준">
        {#each operation.columns.filter(c=>c.to>=lo&&c.from<=hi) as col(col.from)}{@const x0=Math.max(0,(col.from-lo)/(hi-lo)*1000)}{@const width=Math.max(1,Math.min(1000,(col.to-lo)/(hi-lo)*1000)-x0)}{@const top=col.shares.indexOf(Math.max(...col.shares))}
          <rect x={x0} {width} height="20" class="level" class:stop={top===0} style:opacity={top===0?1:shade(top,operation.names.levels.length)}/>{/each}
      </svg></div>
    {/if}
    <div class="strip"><span></span><XAxis {lo} {hi} {scale}/></div>
  </div>{#if !chatting}<div class="related-context">
      {#if focused.values}<div class="focus-values" aria-label="고른 신호의 초기와 특이사항 구간">
        <span class="name">{focused.label}</span>
        <div class="pair"><span><small>초기</small>{focused.values.before===null?"—":measure(focused.values.before,focused.unit)}</span><b aria-hidden="true">→</b><span><small>특이사항 구간</small><strong>{focused.values.after===null?"—":measure(focused.values.after,focused.unit)}</strong></span></div>
      </div>{/if}
      {#if context}{@render context()}{/if}
    </div>{/if}</div>
  {#if actions}<div class="actions">{@render actions()}</div>{/if}
  {#if focused.decision}<p class="decision">남긴 판단 · {focused.decision}</p>{/if}
  </div>
  <!-- AI 대화창은 조사 영역의 오른쪽 전체 높이에 붙는다. 대화가 길어져도 대화창 안에서만 스크롤하고 그래프는 그대로 보인다. -->
  {#if chatting&&assistant}<aside class="dock" aria-label="AI 조사"><div class="dock-inner">{@render assistant({colorOf,labelOf,point,close:()=>rail="context"})}</div></aside>{/if}
</section>
{/if}
<style>
  .timeline{display:grid;min-width:0}.main{display:grid;gap:var(--space-3);min-width:0}
  .timeline.chatting{grid-template-columns:minmax(0,1fr) 380px;column-gap:24px}
  .dock{position:relative;min-height:560px}.dock-inner{position:absolute;inset:0}
  .head-tools{display:flex;align-items:end;gap:8px}
  .ai-toggle{display:inline-flex;align-items:center;gap:6px;height:36px;padding:0 12px;border:1px solid var(--color-control-border);border-radius:var(--radius-control);background:var(--color-surface);color:var(--color-action);font-size:var(--font-small);font-weight:650}
  .ai-toggle svg{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:1.5;stroke-linejoin:round}
  .ai-toggle[aria-pressed="true"]{background:var(--color-action);border-color:var(--color-action);color:var(--color-action-ink)}
  .reading-layout.solo{grid-template-columns:minmax(0,1fr)}
  .headline{display:flex;align-items:start;justify-content:space-between;flex-wrap:wrap;gap:var(--space-3)}h2{margin:0;font-size:1.3rem;line-height:1.4}.headline p{margin:4px 0 0;font-size:var(--font-small);color:var(--color-ink-muted)}
  .signal-choice{display:grid;gap:4px;font-size:var(--font-label);min-width:220px}.signal-choice select{padding:7px}.numbers{margin:0;font-size:var(--font-section);font-weight:650}
  .toolbar{display:flex;align-items:center;flex-wrap:wrap;gap:var(--space-2) var(--space-3)}.choices{display:inline-flex;border:1px solid var(--color-control-border);border-radius:var(--radius-control);overflow:hidden}button{cursor:pointer;font:inherit}.choices button{padding:5px 10px;font-size:var(--font-label);border:0;background:var(--color-surface);color:var(--color-ink)}.choices button+button{border-left:1px solid var(--color-border)}.choices button[aria-pressed="true"]{background:var(--color-surface-selected);color:var(--color-action);font-weight:650}
  .legend{display:flex;flex-wrap:wrap;align-items:center;gap:4px 14px;margin:0 0 0 auto;padding:0;list-style:none;font-size:var(--font-label);color:var(--color-ink-muted)}.legend li{display:flex;align-items:center;gap:6px}
  .band-key{display:inline-block;width:14px;height:10px;background:var(--color-reference-line);opacity:.2}.dash{display:inline-block;width:18px;border-top:1.5px dashed var(--color-reference-line)}.change-key{display:inline-block;width:14px;height:12px;background:var(--color-change-fill);border-left:1.5px solid var(--color-change-line)}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;opacity:.6}
  .reading-layout{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:24px;align-items:start}.plots{min-width:0;display:grid;gap:4px}
  /* 그래프·운전 수준·가로축의 왼쪽 눈금 칸을 같은 폭으로 맞춘다. */
  .plots :global(.plotted){grid-template-columns:56px minmax(0,1fr)}.strip{display:grid;grid-template-columns:56px minmax(0,1fr);gap:var(--space-2)}.strip svg{display:block;width:100%;height:20px}.level{fill:var(--color-ink)}.level.stop{fill:none}
  .mean-key{display:inline-block;width:12px;height:2px;border-radius:1px;background:var(--color-ink-muted)}.spread-key{display:inline-block;width:12px;height:10px;background:var(--color-ink-muted);opacity:.25}
  .levels{display:inline-flex;flex-wrap:wrap;gap:4px 12px}.levels span{display:inline-flex;align-items:center;gap:5px}.level-key{display:inline-block;width:12px;height:10px;background:var(--color-ink)}.level-key.stop{background:none;border:1px solid var(--color-border);opacity:1}
  .lane-heading{display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:4px 12px;margin-top:8px;padding-left:64px;font-size:var(--font-small)}.lane-heading.main{margin-top:0}.lane-heading .levels{color:var(--color-ink-muted);font-size:var(--font-label)}
  .readout{display:flex;align-items:baseline;flex-wrap:wrap;gap:4px 14px;font-variant-numeric:tabular-nums}.readout span{display:inline-flex;align-items:center;gap:5px;color:var(--color-ink-muted)}.readout i{display:inline-block;width:12px;height:3px;border-radius:2px}.readout b{color:var(--color-ink);font-weight:650}.readout small{color:var(--color-ink-muted);font-size:var(--font-label)}
  .related-context{display:grid;gap:14px;align-content:start;border-left:1px solid var(--color-border);padding-left:20px;min-width:0}
  .strip.pointed svg{outline:2px solid var(--color-ink);outline-offset:1px}.strip.faint{opacity:.3}
  .load-chart.pointed :global(svg){outline:2px solid var(--color-ink);outline-offset:1px}.load-chart.faint{opacity:.3}
  .focus-values{display:grid;gap:4px;padding-bottom:12px;border-bottom:1px solid var(--color-border)}.focus-values .name{font-size:var(--font-small);font-weight:650}
  .pair{display:flex;align-items:end;gap:14px;font-variant-numeric:tabular-nums}.pair span{display:grid;gap:2px;font-size:1.35rem;font-weight:650;color:var(--color-ink-muted)}.pair small{font-size:var(--font-label);font-weight:400}.pair strong{color:var(--color-ink)}.pair b{padding-bottom:4px;color:var(--color-ink-muted);font-weight:400}.actions{border-top:1px solid var(--color-border);padding-top:12px}
  .decision{margin:0;font-size:var(--font-small);color:var(--color-action)}
  @media(max-width:1000px){.timeline.chatting{grid-template-columns:1fr}.reading-layout{grid-template-columns:1fr}.related-context{border-left:0;padding-left:0;border-top:1px solid var(--color-border);padding-top:12px}}
</style>
