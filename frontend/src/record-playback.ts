/** Original measurement time and accelerated viewing time are separate. */
export type PlaybackScope = {kind: "history" | "vibration"; until: number};
export function scopeParams(scope: PlaybackScope | null): Record<string, string> {
  return scope ? scope.kind === "history" ? {record_until: new Date(scope.until).toISOString()}
    : {acquisition_until: String(Math.floor(scope.until))} : {};
}
export function playbackScope(search: string): PlaybackScope | null {
  const query = new URLSearchParams(search);
  if (query.has("record_until")) {
    const until = Date.parse(query.get("record_until")!);
    return Number.isFinite(until) ? {kind: "history", until} : null;
  }
  if (query.has("acquisition_until")) {
    const until = Number(query.get("acquisition_until"));
    return Number.isSafeInteger(until) && until > 0 ? {kind: "vibration", until} : null;
  }
  return null;
}
export function scopedUrl(url: string, scope: PlaybackScope | null): string {
  const [path, search = ""] = url.split("?");
  const query = new URLSearchParams(search);
  for (const [key, value] of Object.entries(scopeParams(scope))) query.set(key, value);
  return path + "?" + query;
}
export function currentPlayback(): PlaybackScope | null {
  return typeof location === "undefined" ? null : playbackScope(location.search);
}
