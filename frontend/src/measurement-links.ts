/** Links that keep one vibration measurement in view across the feature trend, the model score
 * and raw waveform, the spectrum and the feature comparison. Every target reads the measurement
 * from its own address and shows it as the chosen one; nothing else of the current screen travels. */
import {assetTabUrl} from "./routes.ts";

/** Measurements on each side of the chosen one for a before/after feature comparison. */
export const AROUND = 10;

export type MeasurementLink = {key: "trend" | "model" | "spectrum" | "features"; label: string; href: string};
export type MeasurementContext = {
  /** First and last stored measurement of the stream, so no link asks for one that is not there. */
  first: number; last: number;
  feature?: string | null;
  /** The applied model whose results carry this measurement, when known. */
  bindingId?: string | null;
};

function withParams(href: string, params: Record<string, string | number>): string {
  const url = new URL(href, "http://local");
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, String(value));
  return url.pathname + url.search;
}

export function measurementLinks(assetId: string, ordinal: number, context: MeasurementContext,
  omit: MeasurementLink["key"] | null = null): MeasurementLink[] {
  const {first, last, feature, bindingId} = context;
  if (!Number.isSafeInteger(ordinal) || ordinal < first || ordinal > last) return [];
  const chosenFeature: Record<string, string> = feature ? {vibration_feature: feature} : {};
  const links: MeasurementLink[] = [
    {key: "trend", label: "진동 특징 추이에서 보기",
      href: withParams(assetTabUrl(assetId, "signals"), {vibration_at: ordinal, ...chosenFeature})},
    {key: "model", label: "원본 파형·모델 점수 보기",
      href: withParams(assetTabUrl(assetId, "anomaly", "model"),
        {model_position: ordinal, ...(bindingId ? {model_binding: bindingId} : {})})},
  ];
  if (ordinal > first) {
    links.push({key: "spectrum", label: "바로 앞 측정과 주파수 비교",
      href: withParams(assetTabUrl(assetId, "change", "spectrum"),
        {spectrum_a_from: ordinal - 1, spectrum_a_to: ordinal - 1, spectrum_b_from: ordinal, spectrum_b_to: ordinal})});
    links.push({key: "features", label: "앞뒤 " + AROUND + "회 특징 비교",
      href: withParams(assetTabUrl(assetId, "change", "compare", "vibration"), {
        feature_a_from: Math.max(first, ordinal - AROUND), feature_a_to: ordinal - 1,
        feature_b_from: ordinal, feature_b_to: Math.min(last, ordinal + AROUND - 1),
        ...(feature ? {acquisition_feature: feature} : {}),
      })});
  }
  return links.filter((link) => link.key !== omit);
}
