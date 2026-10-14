const number = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });

export function fmt(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : number.format(value);
}

export function fmtCompact(value: number): string {
  return Math.abs(value) >= 10_000 ? compact.format(value) : number.format(value);
}

export function fmtCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return number.format(value);
  return String(value);
}
