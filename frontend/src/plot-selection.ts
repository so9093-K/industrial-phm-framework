/** Pick stored coordinates, including sparse records; never invent a measurement in a gap. */
export function nearestPosition(positions: readonly number[], at: number): number | null {
  if (!positions.length || !Number.isFinite(at)) return null;
  let left = 0, right = positions.length - 1;
  while (left < right) {
    const mid = Math.floor((left + right) / 2);
    if (positions[mid] < at) left = mid + 1; else right = mid;
  }
  return left && at - positions[left - 1] <= positions[left] - at ? positions[left - 1] : positions[left];
}
export function movePosition(positions: readonly number[], at: number | null, key: string): number | null {
  if (!positions.length) return null;
  if (key === "Home") return positions[0];
  if (key === "End") return positions.at(-1)!;
  const direction = key === "ArrowLeft" ? -1 : key === "ArrowRight" ? 1 : 0;
  if (!direction) return null;
  const current = nearestPosition(positions, at ?? positions.at(-1)!);
  return positions[Math.max(0, Math.min(positions.length - 1, positions.indexOf(current!) + direction))];
}
