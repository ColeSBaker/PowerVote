export type ServerTimingMetric = {
  name: string;
  dur?: number;
  desc?: string;
};

function sanitizeToken(input: string): string {
  return input.trim().replace(/[^a-zA-Z0-9_-]/g, "_");
}

function sanitizeDesc(input: string): string {
  return input.replace(/"/g, "'").trim();
}

export function formatServerTiming(metrics: ServerTimingMetric[]): string {
  return metrics
    .map((metric) => {
      const name = sanitizeToken(metric.name);
      const parts = [name];
      if (typeof metric.dur === "number" && Number.isFinite(metric.dur)) {
        parts.push(`dur=${metric.dur.toFixed(2)}`);
      }
      if (metric.desc) {
        parts.push(`desc="${sanitizeDesc(metric.desc)}"`);
      }
      return parts.join(";");
    })
    .join(", ");
}
