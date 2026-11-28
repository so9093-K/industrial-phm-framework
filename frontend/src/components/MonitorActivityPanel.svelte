<script lang="ts">
  import {newChangeConversation} from "../change-investigation";
  import type {ChangeActivity, MonitorActivity, MonitorChatPoint} from "../monitor-activity";
  import MonitorChat, {type MonitorConversation} from "./MonitorChat.svelte";

  let {activities, chosen, point, reading, focusRequest, writable, onChoose, onCollapse, onUnpoint, onPause}: {
    activities: MonitorActivity[]; chosen: ChangeActivity | null; point: MonitorChatPoint | null; reading: boolean; focusRequest: number; writable: boolean;
    onChoose: (item: ChangeActivity) => void; onCollapse: () => void; onUnpoint: () => void; onPause: () => void;
  } = $props();
  let expanded = $state(false);
  const shown = $derived(expanded ? activities : activities.slice(0, 4));
  const target = $derived(chosen?.question ?? null);
  const threadKey = $derived(target ? JSON.stringify([target.assetId, target.reviewKey, target.scope]) : null);
  const conversations = new Map<string, MonitorConversation>();
  function conversation(key: string): MonitorConversation {
    let current = conversations.get(key);
    if (!current) {
      current = {id: newChangeConversation(), submitted: false, pending: null};
      conversations.set(key, current);
    }
    return current;
  }
</script>

<div class="activity-panel">
  <header class="panel-head">
    <h2>관제 활동</h2>
    <button type="button" aria-label="관제 활동 접기" onclick={onCollapse}>
      <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6 4l4 4-4 4M13 3v10"/></svg>
    </button>
  </header>

  {#if shown.length}
    <ul class="events" aria-label="설비 활동">
      {#each shown as item (item.kind + item.id)}
        <li class:alert={item.kind === "alert"}>
          {#snippet event()}
            <span class="event-name">{item.name}{#if item.kind === "alert"}<span class="flag">수신 알림</span>{/if}</span>
            <strong>{item.title}</strong><span class="event-detail">{item.detail}</span>
          {/snippet}
          {#if item.kind === "change"}
            <button type="button" aria-pressed={chosen?.id === item.id} onclick={() => onChoose(item)}>{@render event()}</button>
          {:else}<a href={item.href}>{@render event()}</a>{/if}
        </li>
      {/each}
    </ul>
    {#if activities.length > 4}<button type="button" class="more" aria-expanded={expanded} onclick={() => expanded = !expanded}>{expanded ? "간단히 보기" : `활동 ${activities.length - 4}건 더 보기`}</button>{/if}
  {:else}<p class="no-activity" role="status">{reading ? "측정 기록을 확인하고 있습니다" : "표시할 설비 활동이 없습니다"}</p>{/if}

  <div class="question">
    {#if target && threadKey}
      {#key threadKey}
        <MonitorChat {target} session={conversation(threadKey)} pointed={point?.point ?? null} {onUnpoint} {onPause} {focusRequest} {writable}/>
      {/key}
    {:else}
      {#if chosen}<a class="inspect" href={chosen.href}>선택한 구간의 실측 보기 →</a>{/if}
      <p class="choose-change">{chosen ? "저장된 변화에서 질문할 수 있습니다." : "위에서 변화를 선택해 질문할 수 있습니다."}</p>
    {/if}
  </div>
</div>

<style>
  .activity-panel{display:grid;min-width:0;gap:10px;padding:14px;background:var(--color-surface);border:1px solid var(--color-border);border-radius:10px}
  .panel-head{display:flex;align-items:center;justify-content:space-between;gap:8px}
  h2{margin:0;font-size:var(--font-body);line-height:1.3}
  .panel-head button{display:grid;place-items:center;width:30px;height:30px;padding:0;border:0;border-radius:6px;background:none;color:var(--color-ink-muted);cursor:pointer}
  .panel-head button:hover{background:var(--color-surface-selected);color:var(--color-ink)}
  svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
  .events{display:grid;gap:4px;max-height:min(42dvh,360px);overflow:auto;overscroll-behavior:contain;padding:3px;margin:-3px;list-style:none}
  .events a,.events button{position:relative;display:grid;width:100%;min-width:0;gap:2px;padding:8px 23px 8px 9px;border:1px solid transparent;border-radius:7px;
    background:transparent;color:var(--color-ink);text-align:left;text-decoration:none;font:inherit;cursor:pointer;overflow-wrap:anywhere}
  .events a::after,.events button::after{content:"";position:absolute;right:10px;top:50%;width:5px;height:5px;border:solid var(--color-ink-muted);border-width:1.5px 1.5px 0 0;transform:translateY(-50%) rotate(45deg)}
  .events a:hover,.events button:hover,.events button[aria-pressed="true"]{background:var(--color-surface-selected)}
  .events button[aria-pressed="true"]{border-color:var(--color-action)}
  .events strong{font-size:var(--font-small);line-height:1.35}
  .event-name,.event-detail,.no-activity{color:var(--color-ink-muted);font-size:var(--font-label)}
  .event-name{display:flex;align-items:baseline;flex-wrap:wrap;gap:4px 8px}
  .flag{color:var(--color-caution-ink);font-weight:650}
  .alert a{background:var(--color-uncertain-surface)}
  .more,.inspect{justify-self:start;padding:0;border:0;background:none;color:var(--color-action);font:inherit;font-size:var(--font-label);cursor:pointer;text-decoration:underline}
  .question{display:grid;gap:8px;padding-top:10px;border-top:1px solid var(--color-border);min-width:0}
  .choose-change{margin:0;color:var(--color-ink-muted);font-size:var(--font-small)}
  .no-activity{margin:0;padding:4px 0}
</style>
