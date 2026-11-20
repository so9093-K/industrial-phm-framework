<script lang="ts">
  import {onDestroy} from "svelte";
  import {playbackStep, type PlaybackScope} from "../record-playback";
  import {clockText} from "../asset-timeline";
  let {kind, from, to, scope = $bindable(null), busy = false,playing=$bindable(false),onRefresh}: {
    kind: "history" | "vibration"; from: number; to: number;
    scope?: PlaybackScope | null; busy?: boolean;playing?:boolean;onRefresh?:()=>void;
  } = $props();
  let frames = $state(60);
  let timer: ReturnType<typeof setTimeout> | null = null;
  const at = $derived(scope?.until ?? to);
  const label = (n: number) => kind === "history" ? clockText(n) : Math.floor(n) + "번째 측정";
  function pause() { playing = false; }
  function seek(n: number) { pause(); scope = {kind, until: Math.max(from + 1, Math.min(to, n))}; }
  function play() {
    if (!scope || at >= to) scope = {kind, until: from + Math.max(1, Math.ceil((to - from) * .1))};
    playing = true;
  }
  $effect(() => {
    if (timer !== null) clearTimeout(timer);
    timer = null;
    if (!playing || busy) return;
    if (at >= to) { playing = false; return; }
    timer = setTimeout(() => scope = {kind, until: playbackStep(from, to, at, frames)}, 1000);
    return () => { if (timer !== null) clearTimeout(timer); };
  });
  onDestroy(() => { if (timer !== null) clearTimeout(timer); });
</script>
<div class="playback" aria-label="저장된 실측 기록 재생">
  <div class="tools"><span class="kind">과거 실측 기록{scope ? " 재생" : ""}</span>
    <button type="button" class="ui-button" onclick={() => playing ? pause() : play()} disabled={to <= from}>{playing ? "일시정지" : scope ? "이어서 재생" : "빠르게 재생"}</button>
    <label>재생 속도<select bind:value={frames}><option value={60}>전체 약 1분</option><option value={20}>전체 약 20초</option><option value={120}>전체 약 2분</option></select></label>
    {#if scope}<button type="button" class="ui-button" onclick={() => {pause(); scope = null;}}>전체 기록 보기</button>{/if}
    {#if onRefresh}<button type="button" class="ui-button" onclick={()=>{pause();onRefresh();}} disabled={busy}>다시 읽기</button>{/if}
    <output aria-busy={busy}>{scope ? label(at) : label(from) + " — " + label(to)}{busy ? " · 읽는 중" : ""}</output>
  </div>
  {#if scope}<input type="range" aria-label="재생할 기록 위치" min={from + 1} max={to} step={kind === "history" ? 1000 : 1} value={at}
    oninput={e => seek(Number(e.currentTarget.value))} onpointerdown={pause} onkeydown={pause}/>{/if}
</div>
<style>
  .playback{display:grid;gap:8px;min-width:0}.tools{display:flex;align-items:center;flex-wrap:wrap;gap:8px 12px}.kind{font-size:var(--font-small);font-weight:650;color:var(--color-ink-muted)}label{display:flex;align-items:center;gap:6px;font-size:var(--font-label);color:var(--color-ink-muted)}select{padding:6px 8px}output{margin-left:auto;font-size:var(--font-small);font-variant-numeric:tabular-nums;color:var(--color-ink-muted)}input{width:100%;accent-color:var(--color-action)}
</style>
