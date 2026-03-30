export function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export function formatDistance(meters: number): string {
  if (meters >= 1000) return `${(meters / 1000).toFixed(2)} km`;
  return `${Math.round(meters)} m`;
}

export function formatPace(metersPerSecond: number, type: string): string {
  if (metersPerSecond === 0) return 'N/A';
  if (type === 'Run' || type === 'Walk' || type === 'Hike') {
    const minPerKm = 1000 / metersPerSecond / 60;
    const mins = Math.floor(minPerKm);
    const secs = Math.round((minPerKm - mins) * 60);
    return `${mins}:${secs.toString().padStart(2, '0')} /km`;
  }
  return `${(metersPerSecond * 3.6).toFixed(1)} km/h`;
}
