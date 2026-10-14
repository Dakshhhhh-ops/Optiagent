"use client";

import { Hash, Type } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { TableProfile } from "@/lib/api";
import { fmtCell } from "@/lib/format";

const PREVIEW_ROWS = 12;

export function TablePreview({ tables }: { tables: TableProfile[] }) {
  if (tables.length === 0) return null;
  return (
    <Tabs defaultValue={tables[0].name}>
      <TabsList className="h-auto flex-wrap">
        {tables.map((t) => (
          <TabsTrigger key={t.name} value={t.name} className="gap-2">
            <span className="font-mono text-xs">{t.name}</span>
            <span className="text-xs text-muted-foreground">{t.row_count}</span>
          </TabsTrigger>
        ))}
      </TabsList>
      {tables.map((t) => (
        <TabsContent key={t.name} value={t.name}>
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  {t.columns.map((c) => (
                    <th key={c.name} className="px-3 py-2 text-left font-medium whitespace-nowrap">
                      <div className="flex items-center gap-1.5">
                        {c.dtype === "number" ? (
                          <Hash className="size-3 text-primary" aria-label="numeric column" />
                        ) : (
                          <Type className="size-3 text-muted-foreground" aria-label="text column" />
                        )}
                        {c.name}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y">
                {t.preview.slice(0, PREVIEW_ROWS).map((row, i) => (
                  <tr key={i} className="hover:bg-muted/30">
                    {t.columns.map((c, j) => (
                      <td
                        key={c.name}
                        className={`px-3 py-1.5 whitespace-nowrap ${c.dtype === "number" ? "text-right font-mono tabular-nums" : ""}`}
                      >
                        {fmtCell(row[j])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {t.row_count > PREVIEW_ROWS && (
            <p className="mt-2 text-xs text-muted-foreground">
              Showing {PREVIEW_ROWS} of {t.row_count} rows.
            </p>
          )}
          <div className="mt-3 flex flex-wrap gap-1.5">
            {t.columns
              .filter((c) => c.dtype === "number")
              .map((c) => (
                <Badge key={c.name} variant="outline" className="font-mono text-xs font-normal">
                  {c.name}: {fmtCell(c.min)} – {fmtCell(c.max)}
                </Badge>
              ))}
          </div>
        </TabsContent>
      ))}
    </Tabs>
  );
}
