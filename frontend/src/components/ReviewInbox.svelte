<script lang="ts">
  import StatusNotice from "./StatusNotice.svelte";
  import {assetTabUrl} from "../routes";
  import type {ReviewInbox,Review} from "../reviews";
  /** `assetId` null lists every asset's reviews in this snapshot. */
  let {inbox,assetId}:{inbox:ReviewInbox;assetId:string|null}=$props();
  const shown=$derived(assetId===null?inbox.reviews:inbox.reviews.filter(row=>row.assetId===assetId));
  const states:Record<Review["status"],string>={
    open:"검토 대기",acknowledged:"확인함",closed:"검토 종료",
  };
  const analysis={phase:"3상 불평형 분석",file:"파일 특징 분석"};
  const date=(value:string|null)=>value?new Date(value).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"}):"기록 없음";
  const kinds=(review:Review)=>[...new Set(review.linked.map(item=>analysis[item.kind]))].join(" · ")||"분석 결과";
</script>
<section class="ui-panel inbox" aria-labelledby="inbox-title">
  <h2 id="inbox-title">검토 목록</h2>
  {#if !inbox.available}
    <StatusNotice kind="uncertain" title="검토 목록을 확인할 수 없습니다"
      message="이번 조회에 검토 목록이 포함되지 않았습니다. 검토가 없다는 뜻은 아닙니다."/>
  {:else}
    {#if inbox.partial}
      <StatusNotice kind="uncertain" title="검토 근거가 일부만 조회됐습니다"
        message="조회 제한이나 저장소 오류가 있을 수 있습니다. 보이지 않는 기록을 삭제되거나 종료된 것으로 보지 마세요."/>
    {/if}
    {#if !shown.length}
      <StatusNotice message="이번 조회에 포함된 검토 요청이 없습니다. 전체 기록이 없다는 뜻은 아닙니다."/>
    {:else}
      <ol class="items">
        {#each shown as review(review.findingId)}
          <li class="item">
            <div class="item-head">
              <h3>{review.assetId} · {kinds(review)}</h3>
              <span class="status">{states[review.status]}</span>
            </div>
            <ul class="evidence">
              {#each review.linked as evidence(evidence.evidenceId)}
                <li>{analysis[evidence.kind]} · 데이터 출처 {evidence.sourceId}
                  · 측정 위치 {evidence.pointId??"미확인"} · 원본 품질 {evidence.quality??"미확인"}
                  · 분석 {date(evidence.completedAt)}</li>
              {/each}
              {#each review.missing as evidenceId(evidenceId)}
                <li>분석 근거 {evidenceId}를 이번 목록에서 찾지 못했습니다. 조회 제한이나 오류일 수 있어 다른 근거로 대신하지 않습니다.</li>
              {/each}
            </ul>
            <details>
              <summary>기술 상세</summary>
              <dl>
                <div><dt>확인할 항목</dt><dd>{review.findingId}</dd></div>
                <div><dt>분석 실행</dt><dd>{review.runId}</dd></div>
                <div><dt>분석 근거</dt><dd>{review.evidenceIds.join(", ")}</dd></div>
              </dl>
            </details>
            <p class="links">
              <a href={"/web/?monitor_asset="+encodeURIComponent(review.assetId)+"#evidence"}>이전 화면에서 메모·확인·종료하기 →</a>
              <a href={assetTabUrl(review.assetId,"summary")}>설비 보기 →</a>
            </p>
          </li>
        {/each}
      </ol>
    {/if}
  {/if}
</section>
<style>
  .inbox{min-width:0}
  .items{list-style:none;margin:0;padding:0}
  .item{border-top:1px solid var(--color-border);padding-block:var(--space-4)}
  .item-head{display:flex;flex-wrap:wrap;justify-content:space-between;gap:var(--space-2) var(--space-4);align-items:center}
  h3{margin:0;font-size:var(--font-section);overflow-wrap:anywhere}
  .status{font-weight:700;border:1px solid var(--color-ink);border-radius:999px;padding:2px var(--space-3);font-size:var(--font-small)}
  .evidence{padding-inline-start:var(--space-5);color:var(--color-ink-muted)}
  summary{cursor:pointer;font-weight:700;padding-block:var(--space-2)}
  dl{display:grid;gap:var(--space-2);margin:var(--space-2) 0}
  dt{color:var(--color-ink-muted);font-size:var(--font-small)}dd{margin:0;font-family:ui-monospace,monospace;overflow-wrap:anywhere}
  .links{display:flex;flex-wrap:wrap;gap:var(--space-4)}
  li{overflow-wrap:anywhere}
</style>
