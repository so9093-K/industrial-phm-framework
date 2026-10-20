/** What a person calls a stored series: a signal's name and unit, or a vibration feature's label.
 * Saved reviews keep the series ID; the name is looked up when shown and falls back to the ID. */
import {loadAcquisitionOptions} from "./acquisition-outlook.ts";
import {readSignalNames, signalName} from "./history.ts";

const features = new Map<string, Promise<Map<string, string>>>();
function featureLabels(assetId: string): Promise<Map<string, string>> {
  let found = features.get(assetId);
  if (!found) {
    found = loadAcquisitionOptions(assetId, new AbortController().signal)
      .then((options) => new Map((options?.features ?? []).map((item) => [item.id, item.label])))
      .catch(() => new Map<string, string>());
    features.set(assetId, found);
  }
  return found;
}

export async function seriesName(assetId: string, kind: "history" | "acquisition", series: string): Promise<string> {
  if (kind === "acquisition") return (await featureLabels(assetId)).get(series) ?? series;
  return signalName(await readSignalNames(assetId), series);
}
