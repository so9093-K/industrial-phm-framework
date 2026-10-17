<script lang="ts">
  import type {ForecastSettings} from "../forecast-settings";
  let {value,onChange}:{value:ForecastSettings;onChange:(value:ForecastSettings)=>void}=$props();
</script>
<details class="settings"><summary>예측 계산 설정</summary>
  <p>설정을 바꾸면 결과를 다시 계산해야 합니다. 과거 오차는 앞으로의 정확도나 고장 확률이 아닙니다.</p>
  <div class="fields">
    <label>추세 민감도 (0.001~0.5)<input type="number" min="0.001" max="0.5" step="0.001" value={value.changepointPriorScale} oninput={e=>onChange({...value,changepointPriorScale:Number(e.currentTarget.value)})}/></label>
    <label>변화점 탐색 범위 (0.5~0.95)<input type="number" min="0.5" max="0.95" step="0.01" value={value.changepointRange} oninput={e=>onChange({...value,changepointRange:Number(e.currentTarget.value)})}/></label>
    <label>최근 학습 개수 (선택 · 20~1000)<input type="number" min="20" max="1000" step="1" value={value.trainingPoints??""} oninput={e=>onChange({...value,trainingPoints:e.currentTarget.value?Number(e.currentTarget.value):null})}/></label>
    <label>계절성<select value={value.seasonality} onchange={e=>onChange({...value,seasonality:e.currentTarget.value as "auto"|"off"})}><option value="auto">자동 (진동 측정은 사용하지 않음)</option><option value="off">사용하지 않음</option></select></label>
    <label>과거 자료로 확인<select value={value.backtest} onchange={e=>onChange({...value,backtest:e.currentTarget.value as "one"|"multi"})}><option value="one">최근 과거 한 시점</option><option value="multi">여러 과거 시점 비교</option></select></label>
  </div>
</details>
<style>
  .settings{margin-block:var(--space-4)}summary{cursor:pointer;font-weight:650;color:var(--color-action)}p{color:var(--color-ink-muted)}
  .fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:var(--space-3)}label{display:grid;gap:var(--space-2)}
  input,select{width:100%;min-width:0;padding:var(--space-2);background:var(--color-surface);color:var(--color-ink);border:1px solid var(--color-border);border-radius:var(--radius-control)}
</style>
