<script lang="ts">
  import OverviewTrace from "./OverviewTrace.svelte";
  import {changeValue} from "../record-findings";
  import {changeConclusion, latestNumber} from "../change-story";
  import ChangeNumbers from "./ChangeNumbers.svelte";
  import {vibrationShape, type VibrationChange, type VibrationFindings} from "../vibration-findings";
  import type {ModelRug} from "../model-context";

  /** 진동 측정 기록에서 고른 변화 하나: 결론, 숫자, 기록 전체를 측정 회차로 그린 그래프 하나. */
  let {record, change, rugs = []}: {assetId?: string; record: VibrationFindings; change: VibrationChange; rugs?: ModelRug[]} = $props();
  // 변화가 기록 끝까지 이어졌으면 마지막 측정의 값이 '지금'이다.
  const shape = $derived(vibrationShape(change, record.last));
  const last = $derived(shape.atEnd ? change.trace.at(-1) : undefined);
  const latest = $derived(last ? latestNumber("마지막 측정 · " + last.at + "번째", last.value, change.reference, change.unit) : null);
</script>

<div class="change-lead"><div class="lead-copy"><h3 class="change-sentence">{changeConclusion(change, {span: shape.span, now: shape.now, jump: shape.jump})}</h3></div>
<ChangeNumbers facts={change} spanCaption={change.from + "~" + change.to + "번째 · " + (change.to - change.from + 1) + "회"} {latest}
  fallback={"가장 " + (change.direction === "up" ? "높을" : "낮을") + " 때 " + changeValue(change.value, change.unit)} />
</div>
<OverviewTrace main={{label:change.label,unit:change.unit,axis:"acquisition",periodSeconds:record.periodSeconds,latest:null,trace:change.trace.map(point=>({x:point.at,value:point.value,join:point.join}))}} range={change} usual={change.usual} marks={shape.marks} {rugs} height={200}/>


