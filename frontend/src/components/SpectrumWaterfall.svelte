<script lang="ts">
  import {onMount} from "svelte";
  import XAxis from "./XAxis.svelte";
  import {frequencyText} from "../spectrum";
  import {GRADIENT, readWaterfall, shade, type Waterfall, type WaterfallChannel} from "../waterfall";
  /** Every acquisition's spectrum down the record, so the acquisition a band began to change at shows. */
  let {assetId, place, onUse}: {assetId: string; place: (at: number) => string; onUse: (period: "a" | "b", ordinal: number) => void} = $props();
  let data: Waterfall | null = $state(null);
  let loadState: "loading" | "ready" | "failed" = $state("loading");
  let picked: {channel: string; row: number; bin: number; left: number; top: number} | null = $state(null);
  let selected: number | null = $state(null);
  const selectedRow = $derived.by(() => {
    const read: Waterfall | null = data;
    return read && selected !== null ? read.acquisitions.indexOf(selected) : -1;
  });
  onMount(() => {
    const request = new AbortController();
    void readWaterfall(assetId, request.signal).then(value => { data = value; selected = value.acquisitions[0] ?? null; loadState = "ready"; })
      .catch(() => { if (!request.signal.aborted) loadState = "failed"; });
    return () => request.abort();
  });
  function paint(canvas: HTMLCanvasElement, channel: WaterfallChannel) {
    const draw = (rows: number[][]) => {
      const read = data;
      if (!read) return;
      canvas.width = read.frequencies.length; canvas.height = rows.length;
      const context = canvas.getContext("2d");
      if (!context) return;
      const image = context.createImageData(canvas.width, canvas.height);
      rows.forEach((line, row) => line.forEach((value, bin) => {
        const [r, g, b] = shade(value, read.floorDb), at = (row * canvas.width + bin) * 4;
        image.data[at] = r; image.data[at + 1] = g; image.data[at + 2] = b; image.data[at + 3] = 255;
      }));
      context.putImageData(image, 0, 0);
    };
    draw(channel.decibels);
    return {update: (next: WaterfallChannel) => draw(next.decibels)};
  }
  function hover(event: PointerEvent, channel: WaterfallChannel) {
    const read = data;
    if (!read) return;
    const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
    const bin = Math.min(read.frequencies.length - 1, Math.max(0, Math.floor((event.clientX - box.left) / box.width * read.frequencies.length)));
    const row = Math.min(read.acquisitions.length - 1, Math.max(0, Math.floor((event.clientY - box.top) / box.height * read.acquisitions.length)));
    picked = {channel: channel.id, row, bin, left: Math.min(70, (event.clientX - box.left) / box.width * 100), top: event.clientY - box.top};
  }
  function selectRow(event: MouseEvent) {
    if (!data) return;
    const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
    const index = Math.min(data.acquisitions.length - 1, Math.max(0, Math.floor((event.clientY - box.top) / box.height * data.acquisitions.length)));
    selected = data.acquisitions[index];
  }
  function keyRow(event: KeyboardEvent) {
    if (!data || !["ArrowUp", "ArrowDown", "Home", "End", "Enter", " "].includes(event.key)) return;
    event.preventDefault();
    const row = selectedRow < 0 ? 0 : selectedRow;
    const index = event.key === "Home" ? 0 : event.key === "End" ? data.acquisitions.length - 1
      : Math.max(0, Math.min(data.acquisitions.length - 1, row + (event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0)));
    selected = data.acquisitions[index];
  }
</script>

{#if loadState === "failed"}
  <p class="context">측정별 스펙트럼을 불러오지 못했습니다. 아래 두 기간 비교는 그대로 쓸 수 있습니다.</p>
{:else if data && data.acquisitions.length > 1}
  {@const read = data}
  <section class="waterfall" aria-labelledby="waterfall-title">
    <h3 id="waterfall-title">측정별 스펙트럼 <small>{place(read.acquisitions[0])} ~ {place(read.acquisitions[read.acquisitions.length - 1])} · 측정 {read.acquisitions.length}개</small></h3>
    <p class="context">한 줄이 한 측정입니다. 위에서 아래로 시간이 흐르고, 색이 진할수록 그 주파수의 에너지가 큽니다. 달라진 줄을 선택해 아래 비교에 사용하세요.</p>
    {#each read.channels as channel (channel.id)}
      <div class="channel">
        <h4>{channel.label}</h4>
        <div class="plot">
          <div class="rows" aria-hidden="true"><span>{place(read.acquisitions[0])}</span><span>{place(read.acquisitions[read.acquisitions.length - 1])}</span></div>
          <div class="map">
            <canvas use:paint={channel} onpointermove={event => hover(event, channel)} onpointerleave={() => picked = null}
              role="button" tabindex="0" onclick={selectRow} onkeydown={keyRow}
              aria-label={channel.label + " 측정별 주파수 세기 · 위아래 방향키로 측정 선택"}></canvas>
            {#if selectedRow >= 0}<span class="selected-row" aria-hidden="true" style={"top:" + (180 * (selectedRow + 0.5) / read.acquisitions.length) + "px"}></span>{/if}
            {#if picked?.channel === channel.id}
              <div class="tip" style={"left:" + picked.left + "%;top:" + (picked.top + 12) + "px"}>
                <strong>{place(read.acquisitions[picked.row])}</strong>
                <span>{frequencyText(read.frequencies[picked.bin])} Hz · {channel.decibels[picked.row][picked.bin].toFixed(1)} dB</span>
              </div>
            {/if}
            <XAxis lo={read.frequencies[0]} hi={read.frequencies[read.frequencies.length - 1]} scale={{kind: "value"}} note="가로축 · 주파수 (Hz)" />
          </div>
        </div>
      </div>
    {/each}
    <p class="legend"><span>{read.floorDb} dB 이하</span><i style={"background:" + GRADIENT}></i><span>0 dB · 그 채널에서 가장 센 주파수</span></p>
    <div class="selection" role="group" aria-label="선택한 측정으로 주파수 비교">
      <label>비교에 사용할 측정 <select value={selected ?? ""} onchange={event => selected = Number(event.currentTarget.value)}>
        {#each read.acquisitions as ordinal (ordinal)}<option value={ordinal}>{place(ordinal)}</option>{/each}
      </select></label>
      <p role="status">선택한 측정 · {selected === null ? "없음" : place(selected)}</p>
      <div class="actions">
        <button type="button" class="ui-button" disabled={selected === null} onclick={() => { if (selected !== null) onUse("a", selected); }}>기간 A로 사용</button>
        <button type="button" class="ui-button" disabled={selected === null} onclick={() => { if (selected !== null) onUse("b", selected); }}>기간 B로 사용</button>
      </div>
      <p class="context">선택한 한 측정으로 해당 기간만 바꾸고 다시 비교합니다. 반대 기간은 유지합니다.</p>
    </div>
  </section>
{/if}

<style>
  .waterfall { display: grid; gap: var(--space-2); margin: var(--space-3) 0; }
  h3 { margin: 0; font-size: var(--font-body); }
  h3 small { font-weight: 400; color: var(--color-ink-muted); font-size: var(--font-small); }
  h4 { margin: var(--space-2) 0 var(--space-1); font-size: var(--font-small); }
  .context { margin: 0; color: var(--color-ink-muted); font-size: var(--font-small); }
  .plot { display: grid; grid-template-columns: minmax(0, 9rem) minmax(0, 1fr); gap: var(--space-2); }
  .rows { display: flex; flex-direction: column; justify-content: space-between; height: 180px; font-size: 12px; color: var(--color-ink-muted); text-align: right; }
  .map { position: relative; min-width: 0; }
  canvas { display: block; width: 100%; height: 180px; image-rendering: pixelated; border-radius: 4px; cursor:crosshair; }
  canvas:focus-visible { outline:3px solid var(--color-focus); outline-offset:3px; }
  .selected-row { position:absolute; left:0; right:0; border-top:2px dashed var(--color-ink); pointer-events:none; }
  .selection { display:grid; gap:var(--space-2); padding:var(--space-3); background:var(--color-surface-selected); border-radius:var(--radius-control); }
  .selection label { display:grid; gap:var(--space-1); font-weight:650; }.selection p{margin:0;overflow-wrap:anywhere}
  .selection select { min-width:0; max-width:100%; padding:var(--space-2); color:var(--color-ink); background:var(--color-surface); border:1px solid var(--color-border); border-radius:var(--radius-control); }
  .actions{display:flex;flex-wrap:wrap;gap:var(--space-2)}
  .tip { position: absolute; z-index: 1; display: grid; gap: 2px; padding: var(--space-2); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-control); font-size: var(--font-small); pointer-events: none; white-space: nowrap; box-shadow: 0 2px 8px rgb(0 0 0 / 0.12); }
  .legend { display: flex; align-items: center; gap: var(--space-2); margin: 0; font-size: var(--font-small); color: var(--color-ink-muted); }
  .legend i { display: inline-block; width: 160px; height: 10px; border-radius: 2px; }
  @media (max-width: 560px) { .plot { grid-template-columns: 1fr; } .rows { flex-direction: row; height: auto; text-align: left; } }
</style>
