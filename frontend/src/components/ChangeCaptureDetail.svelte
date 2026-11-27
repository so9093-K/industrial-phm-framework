<script lang="ts">
  import {changeCaptureCaption,type ChangeCapture} from "../change-reviews";
  import {findingLinks} from "../record-findings";
  import {vibrationLinks} from "../vibration-findings";
  import ChangeReview from "./ChangeReview.svelte";
  import ChangeNumbers from "./ChangeNumbers.svelte";
  import ChangeInterval from "./ChangeInterval.svelte";
  import OverviewTrace from "./OverviewTrace.svelte";
  import {lastNumber} from "../change-story";
  import {measurementLabel} from "../time-axis";
  let {assetId,capture,onUpdated=()=>{}}:{assetId:string;capture:ChangeCapture;onUpdated?:(value:ChangeCapture)=>void}=$props();
  const finding=$derived(capture.finding);
  // 기록 끝까지 이어진 진동 특이사항이면 조사 화면처럼 마지막 측정과 그 배수를 보인다.
  const latest=$derived.by(()=>{
    if(capture.kind!=="vibration")return null;
    const last=capture.finding.trace.at(-1);
    return last&&last.at===capture.finding.to?lastNumber(capture.finding,last.value,"마지막 측정 · "+measurementLabel(last.at,capture.periodSeconds)):null;
  });
  const links=$derived(capture.kind==="vibration"?vibrationLinks(assetId,capture.finding):findingLinks(assetId,capture.finding,capture.finding.baseline,capture.finding.bucketSeconds??null));
</script>
<h3>{finding.label} · 특이사항</h3>
<p>{changeCaptureCaption(capture)}</p>
<ChangeNumbers facts={finding} fallback="저장한 측정의 변화" {latest}/>
{#if capture.kind==="vibration"}
  <OverviewTrace main={{label:finding.label,unit:finding.unit,axis:"acquisition",periodSeconds:capture.periodSeconds,latest:null,trace:capture.finding.trace.map(row=>({x:row.at,value:row.value,join:row.join}))}} range={capture.finding} height={180}/>
{:else}<ChangeInterval finding={capture.finding} height={180} focus/>{/if}
<p class="links"><a href={links.signal??undefined}>당시 구간의 원본 보기 →</a><a href={links.compare??undefined}>당시 기준과 비교 →</a></p>
<ChangeReview {assetId} {finding} saved={capture} onSaved={onUpdated}/>
<style>p{font-size:var(--font-small)}.links{display:flex;flex-wrap:wrap;gap:var(--space-3)}</style>
