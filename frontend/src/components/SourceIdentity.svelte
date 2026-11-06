<script lang="ts">
  import {publicSourceInfo,readableSourceId,sourceSummary} from "../operations-status";
  let {id,name,pointId,interpretationId,among=[]}: {
    id:string;name?:string;pointId?:string|null;interpretationId?:string;among?:readonly string[];
  }=$props();
  const info=$derived(publicSourceInfo(id));
  const multiple=$derived(info&&new Set(among.filter(source=>publicSourceInfo(source)?.name===info?.name)).size>1);
</script>
<div class="source-identity">
  <p class="source-name">{name&&name!==id?name:multiple?readableSourceId(id):sourceSummary(id)}{#if pointId} · 측정 위치 {pointId}{/if}</p>
  <details>
    <summary>데이터 상세</summary>
    <dl>
      <dt>출처 식별자</dt><dd>{id}</dd>
      {#if name}<dt>등록된 이름</dt><dd>{name}</dd>{/if}
      {#if info?.partition}<dt>원본 데이터 분류</dt><dd>{info.partition} · 제공 기관의 분류이며 모델 학습 여부를 뜻하지 않습니다.</dd>{/if}
      {#if info}<dt>원본 지문</dt><dd>{info.fingerprint??"기록되지 않음"}</dd>{/if}
      {#if pointId!==undefined}<dt>측정 위치</dt><dd>{pointId??"지정되지 않음"}</dd>{/if}
      {#if interpretationId}<dt>측정 항목 식별자</dt><dd>{interpretationId}</dd>{/if}
    </dl>
  </details>
</div>
<style>
  .source-identity{display:flex;flex-wrap:wrap;align-items:baseline;gap:0 var(--space-3);min-width:0;color:var(--color-ink-muted);font-size:var(--font-small)}
  p{margin:0;overflow-wrap:anywhere}summary{cursor:pointer;min-height:32px;padding-block:var(--space-2);color:var(--color-action)}
  details{min-width:0}details[open]{flex-basis:100%}
  dl{display:grid;grid-template-columns:minmax(6rem,auto) minmax(0,1fr);gap:var(--space-2);margin:var(--space-2) 0}
  dd{margin:0;overflow-wrap:anywhere}dt{font-weight:650}
  @media(max-width:480px){dl{grid-template-columns:1fr;gap:var(--space-1)}dd{margin-bottom:var(--space-2)}}
</style>
