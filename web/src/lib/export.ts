import type { SolveReport } from "@/lib/api";

function csvCell(value: unknown): string {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

/** The solved plan as CSV rows (shipments or assignments), or null if there is no solution. */
export function planCsv(report: SolveReport): string | null {
  const s = report.solution;
  if (!s) return null;
  const rows: unknown[][] =
    s.kind === "transportation"
      ? [
          ["from", "to", "quantity", "unit_cost", "cost"],
          ...s.shipments.map((x) => [x.source, x.destination, x.quantity, x.unit_cost, x.cost]),
        ]
      : [["agent", "task", "value"], ...s.assignments.map((x) => [x.agent, x.task, x.value])];
  return rows.map((r) => r.map(csvCell).join(",")).join("\n") + "\n";
}

export function download(filename: string, content: string, type = "text/csv") {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function slug(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "plan";
}
