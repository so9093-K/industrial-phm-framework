// Plot the verified original input. No invented points, score normalization or health colors.
const ns = "http://www.w3.org/2000/svg";
const svgNode = (tag, attrs = {}) => {
  const n = document.createElementNS(ns, tag);for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);return n;
};
const number = (n) => n.toLocaleString("ko-KR", {maximumFractionDigits: 3});
export const channelName = (name) => ({Horizontal_vibration_signals: "수평 진동", Vertical_vibration_signals: "수직 진동"}[name] || name);
export function signalChoices(preview) {
  if (!preview?.available) return [];
  if (preview.sample_count) return preview.channels.map((c, i) => ({id: String(i), name: channelName(c.channel), channels: [c]}));
  return [...new Set(preview.channels.map((c) => c.unit))].map((unit) => ({id: unit,
    name: ({A: "3상 전류 · A", V: "3상 전압 · V", Hz: "주파수 · Hz"}[unit] || unit),
    channels: preview.channels.filter((c) => c.unit === unit)}));
}
export function drawSignal(root, preview, choiceId) {
  root.replaceChildren();
  const choice = signalChoices(preview).find((c) => c.id === choiceId);
  if (!choice) return;
  const waveform = Boolean(preview.sample_count);
  const width = Math.max(260, root.clientWidth), height = 180, left = 56, right = width - 14, top = 16, bottom = 150;
  const sequences = choice.channels.map((channel) => waveform ? channel.envelope.map((pair, i) => ({
    x: (i * preview.samples_per_bin + (Math.min(preview.samples_per_bin, preview.sample_count - i * preview.samples_per_bin) - 1) / 2)
      / (preview.sampling_rate_hz || 1), lo: pair[0], hi: pair[1],
  })) : channel.points.map((p) => ({x: Date.parse(p.at), lo: p.value, hi: p.value})));
  const values = sequences.flatMap((seq) => seq.flatMap((p) => [p.lo, p.hi])).filter((v) => typeof v === "number" && Number.isFinite(v));
  if (!values.length) {root.textContent = "표시할 유효 관측이 없습니다.";return;}
  const min = Math.min(...values), max = Math.max(...values), pad = (max - min) * .08 || Math.abs(max) * .05 || 1;
  const x0 = waveform ? 0 : Date.parse(preview.start), x1 = waveform
    ? (preview.sample_count - 1) / (preview.sampling_rate_hz || 1) : Date.parse(preview.end);
  const x = (v) => left + (v - x0) / (x1 - x0 || 1) * (right - left);
  const y = (v) => bottom - (v - min + pad) / (max - min + 2 * pad) * (bottom - top);
  const svg = svgNode("svg", {viewBox: `0 0 ${width} ${height}`, class: "monitor-raw-chart", role: "img", "aria-label": choice.name + " 실제 원본 신호"});
  svg.append(svgNode("path", {d: `M${left} ${top}V${bottom}H${right}`, class: "axis"}));
  for (const [index, seq] of sequences.entries()) {
    let path = "", previous = null;
    const gaps = seq.slice(1).map((p, i) => p.x - seq[i].x).filter((d) => d > 0).sort((a, b) => a - b);
    const gapLimit = (gaps[Math.floor(gaps.length / 2)] || 0) * 1.5;
    for (const point of seq) {
      if (typeof point.lo !== "number" || !Number.isFinite(point.lo)) {previous = null;continue;}
      if (waveform) path += `M${x(point.x).toFixed(2)} ${y(point.lo).toFixed(2)}V${y(point.hi).toFixed(2)} `;
      else {
        path += (previous && point.x - previous.x <= gapLimit ? "L" : "M") + x(point.x).toFixed(2) + " " + y(point.lo).toFixed(2) + " ";
        const dot = svgNode("circle", {cx: x(point.x), cy: y(point.lo), r: 3, class: "monitor-raw-dot phase-" + index});
        const title = svgNode("title");title.textContent = point.x + " · " + number(point.lo) + " " + choice.id;dot.append(title);svg.append(dot);
      }
      previous = point;
    }
    svg.append(svgNode("path", {d: path, class: "monitor-raw-line phase-" + index}));
  }
  const text = (label, attrs) => {const n = svgNode("text", attrs);n.textContent = label;svg.append(n);};
  text(number(max), {x: 2, y: 25});text(number(min), {x: 2, y: bottom});
  const formatX = waveform ? (v) => number(v) + (preview.sampling_rate_hz ? "초" : " 표본") : (v) => new Date(v).toISOString().slice(11, 19);
  text(formatX(x0), {x: left, y: 176});text(formatX(x1), {x: right, y: 176, "text-anchor": "end"});
  root.append(svg);
}

export function drawTrace(root, steps, task, threshold, height = 85) {
  root.replaceChildren();
  const field = task === "rul-estimate" ? "estimate" : "score";
  const rows = steps.filter((s) => s.state === "analyzed" && typeof s.output[field] === "number");
  if (!rows.length) return;
  const width = Math.max(260, root.clientWidth), left = 56, right = width - 14;
  const timed = steps.every((s) => s.event_start);
  const key = (s) => timed ? Date.parse(s.event_start) : s.position;
  const minX = key(steps[0]), maxX = key(steps.at(-1));
  const values = rows.map((s) => s.output[field]);
  const lo = Math.min(...values), hi = Math.max(...values, ...(typeof threshold === "number" ? [threshold] : []));
  const pad = (hi - lo) * .08 || Math.abs(hi) * .05 || 1;
  const x = (s) => left + (key(s) - minX) / (maxX - minX || 1) * (right - left);
  const bottom = height - 25;
  const y = (v) => bottom - (v - lo + pad) / (hi - lo + 2 * pad) * (bottom - 12);
  const svg = svgNode("svg", {viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "저장된 결과 추세", class: "monitor-result-chart"});
  svg.append(svgNode("path", {d: `M${left} 5V${bottom}H${right}`, class: "axis"}));
  let path = "", previous = null;
  const gaps = steps.slice(1).map((s, i) => key(s) - key(steps[i])).filter((v) => v > 0).sort((a, b) => a - b);
  const cadence = timed ? gaps[Math.floor(gaps.length / 2)] : 1;
  for (const s of steps) {
    if (s.state !== "analyzed" || typeof s.output[field] !== "number") {previous = null;continue;}
    path += (previous && key(s) - key(previous) <= cadence ? "L" : "M") + x(s).toFixed(2) + " " + y(s.output[field]).toFixed(2) + " ";previous = s;
  }
  svg.append(svgNode("path", {d: path, class: "monitor-raw-line phase-0"}));
  if (typeof threshold === "number") svg.append(svgNode("path", {d: `M${left} ${y(threshold)}H${right}`, class: "reference-line"}));
  for (const [label, attrs] of [[number(hi), {x: 2, y: 14}], [number(lo), {x: 2, y: bottom + 2}],
    [timed ? new Date(minX).toISOString().slice(11, 19) : "#" + minX, {x: left, y: height - 4}],
    [timed ? new Date(maxX).toISOString().slice(11, 19) : "#" + maxX, {x: right, y: height - 4, "text-anchor": "end"}]]) {
    const t = svgNode("text", attrs);t.textContent = label;svg.append(t);
  }
  root.append(svg);
}

export function drawMeasuredTrend(root, steps, channel) {
  const converted = steps.map((s) => {
    const feature = Object.keys(s.features || {}).find((key) => key.endsWith(channel + ".rms"));
    return {...s, output: {estimate: feature ? s.features[feature] : null}};
  });
  drawTrace(root, converted, "rul-estimate", undefined, 180);
  const svg = root.querySelector("svg");
  if (svg) {
    svg.setAttribute("aria-label", channelName(channel) + " 원본 RMS 추세");
    svg.classList.add("monitor-measured-trend");
  }
}
