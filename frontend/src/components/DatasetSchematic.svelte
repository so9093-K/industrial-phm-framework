<script lang="ts">
  import {SERIES_COLORS} from "../fleet-observation";
  import {equipmentRole} from "../equipment-roles";
  /** Equipment role, measured signals and the investigation they support.
   * These drawings explain the measurement setup; the plots below contain the actual data. */
  let {kind, equipment}: {kind: string; equipment: string | null} = $props();
  const [c1, c2, c3] = SERIES_COLORS;
  const role=$derived(equipmentRole(kind,equipment));
</script>

{#if kind === "aihub-239"}
  <figure class="schematic">
    <div class="role">
      <strong>{equipment ?? "산업 설비"}</strong>
      <p>{role?.role??"설비에 공급되는 전압과 소비 전류를 관측합니다."}</p>
      <p class="why">{role?.purpose??"이전과 달라진 전원·운전 패턴을 찾아 점검에 활용합니다."}</p>
    </div>
    <div class="measurement"><p class="diagram-label">측정 구조 · 개념도</p>
    <svg viewBox="0 0 400 104" role="img" aria-label="설비 전원선 R·S·T상에서 전압·전류를 재어 약 1분 간격 시계열로 저장">
      {#each [["R", 30, c1], ["S", 52, c2], ["T", 74, c3]] as [phase, y, color] (phase)}
        <text x="6" y={Number(y) + 4} class="tag">{phase}</text>
        <line x1="22" x2="132" y1={y} y2={y} stroke={String(color)} stroke-width="2"/>
        <circle cx="72" cy={y} r="6" class="clamp"/>
      {/each}
      <rect x="58" y="16" width="28" height="72" rx="5" class="meter"/>
      <text x="72" y="100" class="note" text-anchor="middle">계측</text>
      <circle cx="166" cy="52" r="32" class="machine"/>
      <text x="166" y="58" class="machine-mark" text-anchor="middle">M</text>
      <text x="166" y="100" class="note" text-anchor="middle">{equipment ?? "설비"}</text>
      <path d="M72 16 V4 H316 V14" class="flow"/><path d="M311 9 L316 16 L321 9" class="flow"/>
      <rect x="240" y="18" width="152" height="70" rx="4" class="panel"/>
      {#each [[c1, 0], [c2, 3], [c3, 6]] as [color, shift], index (index)}
        <polyline points={[0, 1, 2, 3, 4, 5, 6, 7, 8].map(i => (250 + i * 16) + "," + (64 - Number(shift) - (i % 3 === 1 ? 14 : i % 3 === 2 ? 6 : 0) - (i > 5 ? 10 : 0))).join(" ")}
          fill="none" stroke={String(color)} stroke-width="1.5"/>
      {/each}
      <text x="316" y="100" class="note" text-anchor="middle">1분 간격 시계열</text>
    </svg></div>
    <dl>
      <div><dt>측정</dt><dd>R·S·T 상전압·상전류 등 35개 · 1분 간격</dd></div>
      <div><dt>분석</dt><dd>상별 변화 · 3상 불평형</dd></div>
    </dl>
  </figure>
{:else if kind === "xjtu-sy"}
  <figure class="schematic">
    <div class="role">
      <strong>베어링</strong>
      <p>{role?.role}</p>
      <p class="why">{role?.purpose}</p>
    </div>
    <div class="measurement"><p class="diagram-label">측정 구조 · 개념도</p>
    <svg viewBox="0 0 400 104" role="img" aria-label="베어링 하우징의 수평·수직 가속도를 1분마다 1.28초씩 재어 특징으로 계산">
      <rect x="20" y="14" width="84" height="76" rx="8" class="housing"/>
      <circle cx="62" cy="52" r="30" class="ring"/>
      <circle cx="62" cy="52" r="14" class="ring"/>
      {#each [0, 1, 2, 3, 4, 5, 6, 7] as i (i)}
        <circle cx={62 + 22 * Math.cos(i * Math.PI / 4)} cy={52 + 22 * Math.sin(i * Math.PI / 4)} r="5" class="ball"/>
      {/each}
      <circle cx="62" cy="52" r="5" class="shaft"/>
      <rect x="104" y="44" width="12" height="16" rx="2" fill={c1}/>
      <text x="122" y="40" class="tag" fill={c1}>수평</text>
      <rect x="56" y="2" width="12" height="12" rx="2" fill={c2}/>
      <text x="74" y="11" class="tag" fill={c2}>수직</text>
      <text x="62" y="102" class="note" text-anchor="middle">베어링 단면(개념)</text>
      <path d="M150 52 L172 52" class="flow"/><path d="M166 47 L173 52 L166 57" class="flow"/>
      <rect x="178" y="18" width="104" height="68" rx="4" class="panel"/>
      <polyline points={Array.from({length: 40}, (_, i) => (184 + i * 2.4) + "," + (52 + Math.sin(i * 1.9) * (6 + (i % 7) * 2.2))).join(" ")}
        fill="none" stroke={c1} stroke-width="1"/>
      <text x="230" y="100" class="note" text-anchor="middle">1.28초 파형</text>
      <path d="M286 52 L302 52" class="flow"/><path d="M296 47 L303 52 L296 57" class="flow"/>
      <rect x="306" y="18" width="88" height="68" rx="4" class="panel"/>
      <polyline points="312,74 324,73 336,72 348,70 358,64 368,52 378,40 388,26" fill="none" stroke={c1} stroke-width="1.5"/>
      <polyline points="312,76 324,76 336,75 348,74 358,70 368,62 378,54 388,44" fill="none" stroke={c2} stroke-width="1.5"/>
      <text x="350" y="100" class="note" text-anchor="middle">측정마다 RMS</text>
    </svg></div>
    <dl>
      <div><dt>측정</dt><dd>수평·수직 진동 · 1분마다 1.28초</dd></div>
      <div><dt>분석</dt><dd>진동 크기 추이 · 주파수 성분</dd></div>
      <div><dt>기록</dt><dd>고장까지 운전한 가속 수명시험</dd></div>
    </dl>
  </figure>
{/if}

<style>
  /* 안내 창 폭에 맞춰: 하는 일을 위에 한 줄로, 그 아래 측정 구조와 측정·분석 목록을 나란히. */
  .schematic{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(220px,1fr);gap:14px 24px;align-items:center;margin:0;padding:14px 20px;background:var(--color-surface);border:1px solid var(--color-border);border-radius:8px;min-width:0}
  .role{grid-column:1/-1;min-width:0;display:grid;grid-template-columns:auto minmax(0,1fr);gap:2px 12px;padding-bottom:12px;border-bottom:1px solid var(--color-border)}
  .role strong{grid-row:span 2}
  .role strong{font-size:var(--font-body);color:var(--color-ink)}
  .role p{margin:0;font-size:var(--font-small);line-height:1.5;color:var(--color-ink)}
  .role p.why{color:var(--color-ink-muted)}
  .measurement{min-width:0;max-width:400px}.diagram-label{margin:0 0 4px;font-size:var(--font-label);color:var(--color-ink-muted)}
  svg{display:block;width:100%;height:auto;aspect-ratio:400/104;overflow:visible}
  .tag{font-size:12px;font-weight:650;fill:var(--color-ink)}
  .note{font-size:11px;fill:var(--color-ink-muted)}
  .meter{fill:none;stroke:var(--color-ink-muted);stroke-width:1;stroke-dasharray:3 3}
  .clamp{fill:var(--color-surface);stroke:var(--color-ink);stroke-width:1.2}
  .machine{fill:var(--color-surface-selected);stroke:var(--color-ink);stroke-width:1.5}
  .machine-mark{font-size:20px;font-weight:700;fill:var(--color-ink)}
  .flow{fill:none;stroke:var(--color-ink-muted);stroke-width:1.2}
  .panel{fill:none;stroke:var(--color-border);stroke-width:1}
  .housing{fill:#f4f6f8;stroke:var(--color-ink-muted);stroke-width:1}
  .ring{fill:none;stroke:var(--color-ink);stroke-width:1.5}
  .ball{fill:var(--color-surface);stroke:var(--color-ink);stroke-width:1.2}
  .shaft{fill:var(--color-ink)}
  dl{display:grid;gap:8px;margin:0}
  dl div{display:grid;grid-template-columns:44px minmax(0,1fr);gap:10px;align-items:baseline}
  dt{font-size:var(--font-label);font-weight:650;color:var(--color-ink-muted)}
  dd{margin:0;font-size:var(--font-small);line-height:1.5;color:var(--color-ink)}
  @media(max-width:600px){
    .schematic{grid-template-columns:minmax(0,1fr);padding:12px;gap:12px}
    .role{grid-template-columns:1fr}.role strong{grid-row:auto}.measurement{width:100%}
    dl{gap:5px}
  }
</style>
