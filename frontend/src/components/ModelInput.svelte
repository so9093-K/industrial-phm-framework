<script lang="ts">
  import {onMount} from "svelte";
  import {num} from "../format";
  import type {ModelBinding} from "../model-evidence";
  import {inputCheck, readInput, type Waveform, type WindowInput} from "../model-trend";
  import StatusNotice from "./StatusNotice.svelte";

  /** The stored raw input this result was computed from: the vibration waveform's min/max
   * envelope per channel, or a window's observed values. A failed read is never a flat line. */
  type Props = {binding: ModelBinding; position: number; feature?: string | null; place: (position: number) => string};
  let {binding, position, feature = null, place}: Props = $props();
  let input: Waveform | WindowInput | null = $state(null);
  let loadState: "loading" | "ready" | "failed" = $state("loading");
  const selected = (channel: {channel: string;unit?: string | null;property?: string | null;scope?: string | null}) => {
    if (!feature || feature === "primary") return false;
    if (feature.startsWith("feature.")) return feature.slice(8).split(".").slice(0, -1).join(".") === channel.channel;
    const unit = feature.startsWith("current.") ? "A" : feature.startsWith("voltage.") ? "V" : feature.startsWith("frequency.") ? "Hz" : null;
    const property = unit === "A" ? "phase current" : unit === "V" ? "phase voltage" : "frequency";
    const phase = feature.match(/\.phase_([rst])\./)?.[1]?.toUpperCase();
    return unit !== null && channel.unit === unit && channel.property === property && (!phase || channel.scope === "phase " + phase);
  };
  const W = 640, H = 90;
  const clock = (at: string) => new Date(at).toLocaleString("ko-KR", {timeZone: "Asia/Seoul"});

  function bands(values: [number, number][]): string {
    const low = Math.min(...values.map((v) => v[0])), high = Math.max(...values.map((v) => v[1]), low + 1e-12);
    const y = (v: number) => H - 6 - ((v - low) / (high - low)) * (H - 12);
    const x = (i: number) => (i / Math.max(1, values.length - 1)) * W;
    const top = values.map((v, i) => x(i).toFixed(1) + "," + y(v[1]).toFixed(1));
    const bottom = values.map((v, i) => x(i).toFixed(1) + "," + y(v[0]).toFixed(1)).reverse();
    return [...top, ...bottom].join(" ");
  }
  function line(points: {value: number | null}[]): string {
    const values = points.map((p) => p.value).filter((v): v is number => v !== null);
    if (!values.length) return "";
    const low = Math.min(...values), high = Math.max(...values, low + 1e-12);
    let d = "", drawing = false;
    points.forEach((point, i) => {
      if (point.value === null) { drawing = false; return; }
      const x = (i / Math.max(1, points.length - 1)) * W, y = H - 6 - ((point.value - low) / (high - low)) * (H - 12);
      d += (drawing ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1) + " "; drawing = true;
    });
    return d;
  }
  function range(values: number[]): string {
    return values.length ? num(Math.min(...values)) + " ~ " + num(Math.max(...values)) : "값 없음";
  }
  onMount(() => {
    const request = new AbortController();
    void readInput(binding, position, request.signal).then((value) => {
      if (!request.signal.aborted) { input = value; loadState = "ready"; }
    }).catch(() => { if (!request.signal.aborted) loadState = "failed"; });
    return () => request.abort();
  });
</script>

<section class="input" aria-labelledby={"input-" + binding.bindingId + "-" + position}>
  <h3 id={"input-" + binding.bindingId + "-" + position}>{place(position)} 원본 {binding.stepKind === "acquisition-snapshot" ? "파형" : "관측"}</h3>
  {#if feature}<p class="context">선택한 측정 특징 · {feature === "primary" ? "모델 점수" : feature}</p>{/if}
  {#if loadState === "loading"}
    <StatusNotice message="이 측정의 원본을 확인하고 있습니다." />
  {:else if loadState === "failed" || !input}
    <StatusNotice kind="uncertain" message="원본을 불러오지 못했습니다. 원본이 없다는 뜻은 아닙니다." />
  {:else if !input.available}
    <StatusNotice kind="uncertain" title="원본을 보여 줄 수 없습니다" message={input.reason} />
  {:else if "fileName" in input}
    {#if inputCheck(input)}<p class="check">{inputCheck(input)}</p>{/if}
    <p class="context">{input.fileName} · 샘플링 {num(input.rateHz / 1000)} kHz · 표본 {input.perBin}개마다 최소·최대</p>
    {#each input.channels as channel (channel.channel)}
      <figure class:selected={selected(channel)}>
        <figcaption>{channel.channel} · 범위 {range(channel.bands.flat())}</figcaption>
        <svg viewBox={"0 0 " + W + " " + H} role="img" aria-label={channel.channel + " 원본 파형의 최소·최대 범위"}>
          <polygon points={bands(channel.bands)} class="envelope" />
        </svg>
      </figure>
    {/each}
  {:else}
    {#if inputCheck(input)}<p class="check">{inputCheck(input)}</p>{/if}
    <p class="context">{clock(input.start)} ~ {clock(input.end)} · 품질이 좋은 값만 잇고, 쓸 수 없는 값은 비워 둡니다.</p>
    {#each input.channels as channel (channel.channel)}
      <figure class:selected={selected(channel)}>
        <figcaption>{channel.channel}{channel.unit ? " (" + channel.unit + ")" : ""} · 범위 {range(channel.points.map((p) => p.value).filter((v): v is number => v !== null))}</figcaption>
        <svg viewBox={"0 0 " + W + " " + H} role="img" aria-label={channel.channel + " 관측값"}>
          <path d={line(channel.points)} class="series" />
        </svg>
      </figure>
    {/each}
  {/if}
</section>

<style>
  .check { margin: 0; font-size: var(--font-small); color: var(--color-ink); overflow-wrap: anywhere; }
  .input { display: grid; gap: var(--space-2); margin-block: var(--space-4); min-width: 0; }
  h3 { margin: 0; font-size: var(--font-section); }
  p { margin: 0; overflow-wrap: anywhere; }
  .context { color: var(--color-ink-muted); font-size: var(--font-small); }
  figure { margin: 0; display: grid; gap: var(--space-1); }
  figure.selected { border-inline-start: 4px solid var(--color-action); padding-inline-start: var(--space-2); }
  figcaption { font-size: var(--font-small); font-weight: 650; overflow-wrap: anywhere; }
  svg { width: 100%; height: auto; max-height: 110px; border-bottom: 1px solid var(--color-border); }
  .envelope { fill: var(--color-action); fill-opacity: 0.45; stroke: var(--color-action); stroke-width: 1; stroke-linejoin: round; }
  .series { fill: none; stroke: var(--color-action); stroke-width: 1.2; }
</style>
