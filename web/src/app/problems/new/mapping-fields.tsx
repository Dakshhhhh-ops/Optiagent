"use client";

import { Hash, Type } from "lucide-react";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type {
  ColumnProfile,
  KeyValue,
  LongLayout,
  MatrixLayout,
  TableProfile,
} from "@/lib/api";

const NONE = "__none__";

export type PairLayout = LongLayout | MatrixLayout;

function firstOf(table: TableProfile | undefined, dtype: ColumnProfile["dtype"]): string {
  return table?.columns.find((c) => c.dtype === dtype)?.name ?? table?.columns[0]?.name ?? "";
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  );
}

export function TableSelect({
  tables,
  value,
  onChange,
}: {
  tables: TableProfile[];
  value: string;
  onChange: (name: string) => void;
}) {
  return (
    <Field label="Table">
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="w-full font-mono text-xs">
          <SelectValue placeholder="Choose a table" />
        </SelectTrigger>
        <SelectContent>
          {tables.map((t) => (
            <SelectItem key={t.name} value={t.name} className="font-mono text-xs">
              {t.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  );
}

export function ColumnSelect({
  label,
  table,
  value,
  onChange,
  optional = false,
}: {
  label: string;
  table: TableProfile | undefined;
  value: string | null | undefined;
  onChange: (column: string | null) => void;
  optional?: boolean;
}) {
  return (
    <Field label={label}>
      <Select
        value={value ?? NONE}
        onValueChange={(v) => onChange(v === NONE ? null : v)}
        disabled={!table}
      >
        <SelectTrigger className="w-full font-mono text-xs">
          <SelectValue placeholder="Choose a column" />
        </SelectTrigger>
        <SelectContent>
          {optional && (
            <SelectItem value={NONE} className="text-xs text-muted-foreground">
              None
            </SelectItem>
          )}
          {table?.columns.map((c) => (
            <SelectItem key={c.name} value={c.name} className="font-mono text-xs">
              {c.dtype === "number" ? (
                <Hash className="size-3 text-primary" />
              ) : (
                <Type className="size-3 text-muted-foreground" />
              )}
              {c.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  );
}

export function PairLayoutEditor({
  tables,
  value,
  onChange,
  labels,
}: {
  tables: TableProfile[];
  value: PairLayout;
  onChange: (layout: PairLayout) => void;
  labels: { from: string; to: string; value: string; capacity?: string };
}) {
  const table = tables.find((t) => t.name === value.table);

  function switchLayout(layout: string) {
    if (!layout || layout === value.layout) return;
    if (layout === "matrix") {
      onChange({ layout: "matrix", table: value.table, row_id_column: firstOf(table, "text"), ignore_columns: [] });
    } else {
      const text = table?.columns.filter((c) => c.dtype === "text") ?? [];
      onChange({
        layout: "long",
        table: value.table,
        from_column: text[0]?.name ?? "",
        to_column: text[1]?.name ?? text[0]?.name ?? "",
        value_column: firstOf(table, "number"),
        capacity_column: null,
      });
    }
  }

  function switchTable(name: string) {
    const next = tables.find((t) => t.name === name);
    if (value.layout === "matrix") {
      onChange({ ...value, table: name, row_id_column: firstOf(next, "text"), ignore_columns: [] });
    } else {
      const text = next?.columns.filter((c) => c.dtype === "text") ?? [];
      onChange({
        ...value,
        table: name,
        from_column: text[0]?.name ?? "",
        to_column: text[1]?.name ?? "",
        value_column: firstOf(next, "number"),
        capacity_column: null,
      });
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <TableSelect tables={tables} value={value.table} onChange={switchTable} />
        <Field label="Layout">
          <ToggleGroup
            type="single"
            variant="outline"
            value={value.layout}
            onValueChange={switchLayout}
            className="w-full"
          >
            <ToggleGroupItem value="long" className="flex-1 text-xs">
              One row per pair
            </ToggleGroupItem>
            <ToggleGroupItem value="matrix" className="flex-1 text-xs">
              Matrix
            </ToggleGroupItem>
          </ToggleGroup>
        </Field>
      </div>

      {value.layout === "long" ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <ColumnSelect
            label={labels.from}
            table={table}
            value={value.from_column}
            onChange={(c) => onChange({ ...value, from_column: c ?? "" })}
          />
          <ColumnSelect
            label={labels.to}
            table={table}
            value={value.to_column}
            onChange={(c) => onChange({ ...value, to_column: c ?? "" })}
          />
          <ColumnSelect
            label={labels.value}
            table={table}
            value={value.value_column}
            onChange={(c) => onChange({ ...value, value_column: c ?? "" })}
          />
          {labels.capacity && (
            <ColumnSelect
              label={labels.capacity}
              table={table}
              value={value.capacity_column}
              optional
              onChange={(c) => onChange({ ...value, capacity_column: c })}
            />
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <ColumnSelect
            label={`${labels.from} (row ids)`}
            table={table}
            value={value.row_id_column}
            onChange={(c) => onChange({ ...value, row_id_column: c ?? "", ignore_columns: [] })}
          />
          <Field label={`Every other column is a ${labels.to.toLowerCase()} — untick side columns`}>
            <div className="flex flex-wrap gap-x-4 gap-y-2 rounded-md border p-3">
              {table?.columns
                .filter((c) => c.name !== value.row_id_column)
                .map((c) => {
                  const included = !(value.ignore_columns ?? []).includes(c.name);
                  return (
                    <label key={c.name} className="flex items-center gap-2 font-mono text-xs">
                      <Checkbox
                        checked={included}
                        onCheckedChange={(checked) =>
                          onChange({
                            ...value,
                            ignore_columns: checked
                              ? (value.ignore_columns ?? []).filter((n) => n !== c.name)
                              : [...(value.ignore_columns ?? []), c.name],
                          })
                        }
                      />
                      {c.name}
                    </label>
                  );
                })}
            </div>
          </Field>
        </div>
      )}
    </div>
  );
}

export function KeyValueEditor({
  tables,
  value,
  onChange,
  idLabel,
  valueLabel,
}: {
  tables: TableProfile[];
  value: KeyValue;
  onChange: (kv: KeyValue) => void;
  idLabel: string;
  valueLabel: string;
}) {
  const table = tables.find((t) => t.name === value.table);
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <TableSelect
        tables={tables}
        value={value.table}
        onChange={(name) => {
          const next = tables.find((t) => t.name === name);
          onChange({ table: name, id_column: firstOf(next, "text"), value_column: firstOf(next, "number") });
        }}
      />
      <ColumnSelect
        label={idLabel}
        table={table}
        value={value.id_column}
        onChange={(c) => onChange({ ...value, id_column: c ?? "" })}
      />
      <ColumnSelect
        label={valueLabel}
        table={table}
        value={value.value_column}
        onChange={(c) => onChange({ ...value, value_column: c ?? "" })}
      />
    </div>
  );
}

export function defaultKeyValue(tables: TableProfile[]): KeyValue {
  const t = tables[0];
  return { table: t?.name ?? "", id_column: firstOf(t, "text"), value_column: firstOf(t, "number") };
}

export function defaultPairLayout(tables: TableProfile[]): PairLayout {
  const t = tables[0];
  return { layout: "matrix", table: t?.name ?? "", row_id_column: firstOf(t, "text"), ignore_columns: [] };
}
