<script lang="ts">
  let {kind, signal, color}: {kind: "bearing" | "compressor"; signal: string; color: string} = $props();
  const phases = ["R", "S", "T"];
</script>

<figure class="measurement" aria-label={"측정 위치 개념도 · " + signal} style:--selected={color}>
  {#if kind === "bearing"}
    <svg viewBox="0 0 266 83" aria-hidden="true">
      <path class="ground" d="M12 65 H249"/>
      <path class="wire" d="M62 41 H231"/>
      <rect class="body" x="14" y="25" width="49" height="32" rx="5"/>
      <path class="wire" d="M22 30 V52 M27 30 V52 M33 30 V52"/>
      <rect class="body" x="71" y="34" width="17" height="14" rx="3"/>
      <path class="body" d="M113 55 H144 L139 37 H118 Z M197 55 H238 L230 36 H205 Z"/>
      <rect class="body" x="161" y="22" width="29" height="38" rx="5"/>
      <circle class="body" cx="175.5" cy="41" r="9"/>
      <rect class="sensor" class:active={signal === "수직"} x="170" y="10" width="11" height="12" rx="2"/>
      <rect class="sensor" class:active={signal === "수평"} x="190" y="35" width="12" height="11" rx="2"/>
      <text x="38" y="81" text-anchor="middle">모터</text>
      <text x="175" y="81" text-anchor="middle">시험 베어링</text>
    </svg>
  {:else}
    <svg viewBox="0 0 266 83" aria-hidden="true">
      {#each phases as phase, i (phase)}
        {@const y = 24 + i * 14}
        <path class="wire" class:active={signal === phase + "상"} d={"M23 " + y + " H135"}/>
        <circle class="sensor" class:active={signal === phase + "상"} cx="72" cy={y} r="4"/>
        <text x="8" y={y + 4}>{phase}</text>
      {/each}
      <rect class="outline" x="62" y="15" width="20" height="46" rx="5"/>
      <rect class="body" x="128" y="22" width="43" height="31" rx="5"/>
      <path class="wire" d="M171 38 H188"/>
      <rect class="body" x="188" y="16" width="59" height="43" rx="11"/>
      <path class="wire" d="M199 31 H233 M199 37 H233 M199 43 H233"/>
      <text x="72" y="78" text-anchor="middle">전원 계측</text>
      <text x="195" y="78" text-anchor="middle">공기압축기</text>
    </svg>
  {/if}
  <figcaption><i></i>{kind === "bearing" ? signal + " 센서" : signal + " 전원선"} <span>· 개념도</span></figcaption>
</figure>

<style>
  .measurement{margin:0;width:204px;max-width:100%;color:var(--color-ink-muted)}
  svg{display:block;width:100%;height:auto}
  .body{fill:var(--color-surface-selected);stroke:currentColor;stroke-width:1.5}
  .wire,.ground,.outline{fill:none;stroke:currentColor;stroke-width:1.4}
  .ground,.outline{stroke:var(--color-control-border);stroke-dasharray:3 3}
  .sensor{fill:var(--color-surface);stroke:currentColor;stroke-width:1.6}
  .sensor.active{fill:var(--selected);stroke:var(--selected)}
  .wire.active{stroke:var(--selected);stroke-width:3}
  text{fill:currentColor;font-family:inherit;font-size:14px}
  figcaption{display:flex;justify-content:center;align-items:center;gap:5px;font-size:var(--font-label);color:var(--color-ink)}
  figcaption span{color:var(--color-ink-muted)}
  figcaption i{width:8px;height:8px;border-radius:50%;background:var(--selected)}
</style>
