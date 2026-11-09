<script lang="ts">
  import SourceIdentity from "./SourceIdentity.svelte";
  import {assetOptionLabel, flowLabel, type Asset} from "../monitor";
  import {attentionText, notePriority, type AttentionState, type Note} from "../monitor-attention";
  type Props = {
    assets: Asset[];
    observed: (at: string | null) => string;
    href: (assetId: string) => string;
    /** Model, receipt and baseline notes per asset, added to the monitor's own count. */
    notes?: Record<string, number>;
    /** On 관측 현황 the reasons are in the operating details on the same page. */
    reasons?: boolean;
    primaryNotes?:Record<string,Note>;
    notesState?: AttentionState;
  };
  let {assets, observed, href, notes = {}, reasons = false, primaryNotes={}, notesState = "ready"}: Props = $props();
  const count = (asset: Asset): number | null =>
    asset.attentionCount === null && notes[asset.assetId] === undefined ? null : (asset.attentionCount ?? 0) + (notes[asset.assetId] ?? 0);
  // Use the most important known reason, then the count and stable server order.
  const ordered = $derived(assets
    .map((asset, index) => ({asset, index}))
    .sort((a, b) => notePriority(primaryNotes[a.asset.assetId]) - notePriority(primaryNotes[b.asset.assetId])
      || (count(b.asset) ?? 0) - (count(a.asset) ?? 0) || a.index - b.index)
    .map(({asset}) => asset));
  function showReasons(assetId:string) {
    const heading=document.getElementById("attention-"+assetId);
    const detail=heading?.closest("details");
    if(detail)detail.open=true;
  }
  function attention(count: number | null): string {
    return "확인할 항목 " + attentionText(count, notesState);
  }
</script>

<section class="ui-panel" aria-labelledby="asset-list-title">
  <h2 id="asset-list-title">설비 <span>{assets.length}개</span></h2>
  <p class="context">중요한 변화부터 살펴보세요.</p>
  <ul class="rows">
    {#each ordered as asset (asset.assetId)}
      {@const note=primaryNotes[asset.assetId]}
      {@const stored=asset.flow==="stored-history"}
      <li><article class="row">
        <header><h3><a href={href(asset.assetId)}>{assetOptionLabel(assets,asset.assetId)}</a></h3>
          <span class="data-kind">{stored?"과거 저장 기록":flowLabel(asset.flow)}</span></header>
        {#if note}<div class="finding">
          <p class="primary-reason">{note.label}</p>
          <p class="reason-detail">{note.detail}</p>
        </div>{/if}
        <div class="record-context">
          <p>{#if note?.departure}분석한 마지막 측정 · {note.departure.lastAt?observed(note.departure.lastAt):"시각 미확인"}
            {:else if asset.lastObservedAt}마지막 저장 측정 · {observed(asset.lastObservedAt)}
            {:else if asset.lastPosition!=null}마지막 저장 측정 · {asset.lastPosition}번째 · 측정 시각 정보 없음
            {:else}측정 시각 정보 없음{/if}</p>
          <p>{stored?"현재 수신 중인 데이터가 아닙니다.":note?.departure?"변화 분석은 저장된 측정 기록을 기준으로 합니다.":""}</p>
        </div>
        {#if note?.departure?.context}
          <SourceIdentity id={note.departure.context.sourceId} pointId={note.departure.context.pointId} interpretationId={note.departure.context.interpretationId}/>
        {/if}
        <div class="actions">
          {#if note}<a class="ui-button ui-button-primary investigate" href={note.href}>{note.action} →</a>{/if}
          <a class="ui-button" href={href(asset.assetId)}>설비 상세 보기</a>
        </div>
        <footer><span class="attention">{attention(count(asset))}</span>
          {#if reasons && (notes[asset.assetId]??0)>0}<a class="reason-link" href={"#attention-"+encodeURIComponent(asset.assetId)} onclick={()=>showReasons(asset.assetId)}>확인 항목 모두 보기 →</a>{/if}
        </footer>
      </article></li>
    {/each}
  </ul>
</section>

<style>
  h2 span{font-weight:400;color:var(--color-ink-muted);font-size:var(--font-small)}
  .context{color:var(--color-ink-muted)}
  .rows{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-3)}
  .row{display:grid;gap:var(--space-3);padding:var(--space-5);border:1px solid var(--color-border);border-radius:var(--radius-control);min-width:0;overflow-wrap:anywhere}
  header{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:var(--space-2) var(--space-4)}
  h3{margin:0;font-size:var(--font-body)}h3 a{color:var(--color-ink);text-decoration:none}h3 a:hover{text-decoration:underline}
  .data-kind,.record-context,footer{font-size:var(--font-small);color:var(--color-ink-muted)}
  .primary-reason{font-size:var(--font-section);font-weight:700;line-height:1.5;margin:0 0 var(--space-1)}
  .reason-detail{line-height:1.6;color:var(--color-ink-muted);margin:0;max-width:72ch}
  .record-context p{margin:0;line-height:1.6}
  .actions{display:flex;flex-wrap:wrap;gap:var(--space-2)}.actions a{display:inline-flex;align-items:center;min-height:44px;text-decoration:none}
  footer{display:flex;align-items:center;flex-wrap:wrap;gap:var(--space-2) var(--space-4)}.reason-link{padding-block:var(--space-2)}
  @media(max-width:480px){.row{padding:var(--space-4)}.data-kind{flex-basis:100%}.actions a{flex:1 1 auto;justify-content:center}}
</style>
