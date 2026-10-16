<script lang="ts">
  import StatusNotice from "./StatusNotice.svelte";
  import type {ReviewInbox,Review} from "../reviews";
  let {inbox,assetId}:{inbox:ReviewInbox;assetId:string}=$props();
  const selected=$derived(inbox.reviews.filter(row=>row.assetId===assetId));
  const states:Record<Review["status"],string>={
    open:"확인 필요",acknowledged:"확인함",closed:"검토 종료",
  };
  const date=(value:string|null)=>value?new Date(value).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"}):"미확인";
</script>
<section class="ui-panel inbox" aria-labelledby="inbox-title">
  <h2 id="inbox-title">저장된 사람 검토 목록</h2>
  <p class="context">선택 설비 <strong>{assetId}</strong>의 서버 저장 Finding·AnalysisRun·Evidence 식별자를 확인합니다.
    이 화면은 읽기 전용이며, 검토 상태는 정비 실행·수리 완료 또는 고장 확진을 의미하지 않습니다.</p>
  {#if !inbox.available}
    <StatusNotice kind="uncertain" title="검토 목록을 확인할 수 없습니다"
      message="이 조회 응답에는 검토 목록이 포함되지 않았습니다. 검토가 없다고 판단하지 않습니다."/>
  {:else}
    {#if inbox.partial}
      <StatusNotice kind="uncertain" title="검토 근거가 일부만 조회됐습니다"
        message="서버 조회 제한·저장소 오류·분석 근거 누락이 있을 수 있습니다. 보이지 않는 기록을 삭제되거나 검토 완료된 것으로 해석하지 않습니다."/>
    {/if}
    {#if !selected.length}
      <StatusNotice message="이번 조회에 포함된 이 설비의 검토 요청이 없습니다. 전체 기록이 없다는 뜻은 아닙니다."/>
    {:else}
      <ol class="items">
        {#each selected as review(review.findingId)}
          <li class="item">
            <h3>{states[review.status]}</h3>
            <dl>
              <div><dt>Finding</dt><dd>{review.findingId}</dd></div>
              <div><dt>AnalysisRun</dt><dd>{review.runId}</dd></div>
            </dl>
            <h4>검토가 참조하는 Evidence</h4>
            <ul>
              {#each review.linked as evidence(evidence.evidenceId)}
                <li><strong>{evidence.evidenceId}</strong>
                  · {evidence.kind==="phase"?"전력 불균형 분석":"등록 파일 특징 분석"}
                  · 출처 {evidence.sourceId} / 측정점 {evidence.pointId??"미확인"}
                  · 데이터 품질 {evidence.quality??"미확인"}
                  · 완료 {date(evidence.completedAt)}
                </li>
              {/each}
              {#each review.missing as evidenceId(evidenceId)}
                <li>Evidence {evidenceId} — 이번 목록에 일치하는 AnalysisRun·설비·근거가 없습니다.
                  제한된 조회 또는 오류일 수 있으므로 다른 근거로 대체하지 않습니다.</li>
              {/each}
            </ul>
            <p><a href={"/web/?monitor_asset="+encodeURIComponent(assetId)+"#evidence"}>
              기존 운영 화면에서 검토 작업 열기 →
            </a></p>
            <p class="context">검토 조치·메모 작성은 기존 운영 화면을 이용하세요. 해당 링크는 Finding 직접 선택 링크가 아닙니다.</p>
          </li>
        {/each}
      </ol>
    {/if}
  {/if}
</section>
<style>
  .inbox{min-width:0}.context{color:var(--color-ink-muted);overflow-wrap:anywhere}
  .items{padding-inline-start:var(--space-5)}
  .item{border-top:1px solid var(--color-border);padding-block:var(--space-4)}
  h3{margin-block:var(--space-2)}h4{font-size:var(--font-body)}
  dl{display:grid;gap:var(--space-3)}
  dt{color:var(--color-ink-muted)}dd{margin:0;font-weight:650;overflow-wrap:anywhere}
  li{overflow-wrap:anywhere}
</style>
