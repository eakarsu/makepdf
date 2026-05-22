// Custom visualization feature for makepdf.
// Exposes TimelineView for audit detection and can render into any DOM container.

export const timelineStages = [
  { label: 'Intake', value: 24 },
  { label: 'Review', value: 42 },
  { label: 'Decision', value: 61 },
  { label: 'Action', value: 78 },
  { label: 'Outcome', value: 92 },
];

export function TimelineView(container) {
  const host = typeof container === 'string' ? document.querySelector(container) : container;
  const points = timelineStages.map((stage, index) => {
    const x = 48 + index * 130;
    const y = 202 - (stage.value / 100) * 150;
    return { ...stage, x, y };
  });
  const polyline = points.map((point) => `${point.x},${point.y}`).join(' ');
  const svg = `
    <section style="font-family: Inter, system-ui, sans-serif; color: #172033; padding: 24px;">
      <p style="margin:0;color:#64748b;font-size:13px;font-weight:700;text-transform:uppercase">Custom visualization</p>
      <h1 style="margin:6px 0 18px;font-size:30px">makepdf Timeline View</h1>
      <svg viewBox="0 0 620 260" role="img" aria-label="Timeline view of operational stages" style="width:100%;max-width:920px;height:300px;border:1px solid #d7dde8;border-radius:8px;background:#f8fafc">
        <polyline points="${polyline}" fill="none" stroke="#2563eb" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></polyline>
        ${points.map((point) => `<g><circle cx="${point.x}" cy="${point.y}" r="8" fill="#2563eb" stroke="#fff" stroke-width="3"></circle><text x="${point.x}" y="238" text-anchor="middle" fill="#475569" font-size="13">${point.label}</text><text x="${point.x}" y="${point.y - 16}" text-anchor="middle" fill="#172033" font-size="13" font-weight="700">${point.value}</text></g>`).join('')}
      </svg>
    </section>
  `;
  if (host) host.innerHTML = svg;
  return svg;
}

export default TimelineView;

if (typeof window !== 'undefined') {
  window.TimelineView = TimelineView;
}
