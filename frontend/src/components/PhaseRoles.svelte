<script lang="ts">
  import {PHASE_ROLES, suggestRoles, type RoleInput} from "../connections";

  /** Voltage/current R·S·T roles for chosen columns, each with how its unit and phase were
   * confirmed. Column names may suggest a role; the evidence is always the person's own. */
  type Props = {channels: string[]; roles: RoleInput[]; disabled?: boolean; onchange: () => void};
  let {channels, roles = $bindable(), disabled = false, onchange}: Props = $props();
  const suggestion = $derived(suggestRoles(channels, roles));
  const canSuggest = $derived(suggestion.some((role, index) => role.channel !== roles[index].channel));
  function suggest() { roles = suggestion; onchange(); }
</script>

<fieldset class="roles">
  <legend>3상 역할 (선택 · 부하·불평형 분석에 필요)</legend>
  <p class="context">전압 또는 전류의 R/S/T 세 개를 한 세트로 지정하고, 단위와 상 배선을 무엇으로 확인했는지 적으세요.</p>
  {#if canSuggest}
    <button type="button" class="ui-button" {disabled} onclick={suggest}>열 이름으로 역할 채우기</button>
  {/if}
  {#each PHASE_ROLES as role, index (role.label)}
    <div class="role">
      <label class="field">{role.label}
        <select bind:value={roles[index].channel} {disabled} {onchange}>
          <option value="">지정 안 함</option>
          {#each channels as channel (channel)}<option value={channel}>{channel}</option>{/each}
        </select></label>
      {#if roles[index].channel}
        <label class="field">단위 근거<input maxlength="128" placeholder="예: 계측기 표시 V 확인" {disabled}
          bind:value={roles[index].unit} oninput={onchange} /></label>
        <label class="field">해석 근거<input maxlength="128" placeholder="예: 배선도에서 R상 확인" {disabled}
          bind:value={roles[index].meaning} oninput={onchange} /></label>
      {/if}
    </div>
  {/each}
</fieldset>

<style>
  .roles { border: 1px solid var(--color-border); border-radius: var(--radius-control); padding: var(--space-3) var(--space-4);
    display: grid; gap: var(--space-3); min-width: 0; margin: 0; }
  .roles > .ui-button { justify-self: start; }
  legend { font-weight: 700; padding-inline: var(--space-1); }
  .context { color: var(--color-ink-muted); font-size: var(--font-small); margin: 0; overflow-wrap: anywhere; }
  .role { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-2); align-items: end; }
  .field { display: grid; gap: var(--space-1); font-weight: 650; font-size: var(--font-small); min-width: 0; }
  select, input { min-width: 0; width: 100%; padding: var(--space-2) var(--space-3); color: var(--color-ink);
    background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-control); font: inherit; font-weight: 400; }
  @media (max-width: 640px) { .role { grid-template-columns: minmax(0, 1fr); } }
</style>
