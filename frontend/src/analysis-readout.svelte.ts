import {getContext} from "svelte";

export type AnalysisReadout = Record<string, string>;
export type PublishAnalysis = (panel: symbol, values: AnalysisReadout | null) => void;
export const ANALYSIS_READOUT = Symbol("analysis-readout");

/** Reuse the result already loaded for the active chart. Remove it when its panel closes. */
export function exposeAnalysis(read: () => AnalysisReadout | null): void {
  const publish = getContext<PublishAnalysis | undefined>(ANALYSIS_READOUT);
  const panel = Symbol();
  $effect(() => {
    if (!publish) return;
    publish(panel, read());
    return () => publish(panel, null);
  });
}
