<script lang="ts">
  import {bandName,changeValue,shiftText,type FoundInterval,type Operation} from "../record-findings";
  let {item,operation,compareHref,relation}: {
    item:FoundInterval;operation?:Operation;compareHref:string|null;relation:{href:string;label:string}|null;
  }=$props();
  const changed=$derived(item.related.filter(row=>row.state!=="within"));
</script>
{#if operation && item.operation && (item.band!=null || item.operation.interval) || changed.length || compareHref || relation}
<aside class="finding-context" aria-label="이 변화의 해석과 다음 확인">
  {#if operation && item.operation && (item.band!=null || item.operation.interval)}
    <div>
    <h4>같은 운전 수준끼리 비교했습니다</h4>
    {#if item.band!=null}
      <p>{operation.label} 기준 <strong>{bandName(operation,item.band)}</strong> 때의 측정끼리 비교해 찾은 변화입니다.</p>
      <p class="limit">전류가 같아도 부하가 같았는지는 운전 기록으로 확인하세요.</p>
    {:else if item.operation.interval}
      <p>{shiftText(operation,item.operation)}</p>
      <p>전체 값의 차이에는 운전 수준별 측정 비중이 섞일 수 있습니다. 같은 수준의 값끼리도 비교해 보세요.</p>
    {/if}
    </div>
  {/if}
  {#if changed.length}
    <div>
    <h4>같은 구간에 함께 달라진 신호</h4>
    <p>{#each changed.slice(0,2) as other,i (other.channel)}{i?" · ":""}{other.label}
      {changeValue(other.reference,null)} → {changeValue(other.current,other.unit)}{/each}</p>
    </div>
  {/if}
  {#if compareHref || relation}
    <nav aria-label="이 변화에서 이어서 조사">
      {#if compareHref}<a href={compareHref}>{item.band!=null?"같은 운전 수준으로 두 기간 비교":"기준 기간과 이 구간 비교"} →</a>{/if}
      {#if relation}<a href={relation.href}>{relation.label} →</a>{/if}
    </nav>
  {/if}
</aside>
{/if}
<style>
  /* 넓은 화면에서는 운전 수준 설명과 함께 달라진 신호를 나란히 둔다. */
  .finding-context{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:var(--space-2) var(--space-6);padding:var(--space-3);margin-block:var(--space-2);border-radius:var(--radius-control);background:var(--color-surface-selected);font-size:var(--font-small);min-width:0}
  h4,p{margin:0;line-height:1.6;overflow-wrap:anywhere}h4{font-size:inherit}.limit{color:var(--color-ink-muted)}
  .finding-context>div{display:grid;gap:var(--space-1);align-content:start}
  nav{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:var(--space-2) var(--space-4)}a{font-weight:650}
</style>
