"use client";

import { sankey, sankeyLinkHorizontal, type SankeyLink, type SankeyNode } from "d3-sankey";
import { useMemo, useState } from "react";

import { fmt } from "@/lib/format";

export interface Flow {
  from: string;
  to: string;
  amount: number;
  /** Extra lines for the tooltip, e.g. "₹12 / unit". */
  detail?: string[];
}

interface NodeDatum {
  id: string;
  side: "from" | "to";
  label: string;
}

interface LinkDatum {
  flow: Flow;
}

type LaidNode = SankeyNode<NodeDatum, LinkDatum>;
type LaidLink = SankeyLink<NodeDatum, LinkDatum>;

const WIDTH = 760;
const LABEL_GUTTER = 120;
const NODE_WIDTH = 10;
const NODE_GAP = 14;
const ROW_HEIGHT = 34;

export function FlowDiagram({
  flows,
  fromLabel,
  toLabel,
  unit,
}: {
  flows: Flow[];
  fromLabel: string;
  toLabel: string;
  unit: string;
}) {
  const [hover, setHover] = useState<{ link?: LaidLink; node?: LaidNode; x: number; y: number }>();

  const layout = useMemo(() => {
    const froms = [...new Set(flows.map((f) => f.from))];
    const tos = [...new Set(flows.map((f) => f.to))];
    const height = Math.max(froms.length, tos.length) * ROW_HEIGHT + 24;
    const nodes: NodeDatum[] = [
      ...froms.map((id) => ({ id: `from:${id}`, side: "from" as const, label: id })),
      ...tos.map((id) => ({ id: `to:${id}`, side: "to" as const, label: id })),
    ];
    const generator = sankey<NodeDatum, LinkDatum>()
      .nodeId((n) => n.id)
      .nodeWidth(NODE_WIDTH)
      .nodePadding(NODE_GAP)
      .nodeSort(null)
      .extent([
        [LABEL_GUTTER, 12],
        [WIDTH - LABEL_GUTTER, height - 12],
      ]);
    const graph = generator({
      nodes: nodes.map((n) => ({ ...n })),
      links: flows.map((f) => ({
        source: `from:${f.from}`,
        target: `to:${f.to}`,
        value: f.amount,
        flow: f,
      })),
    });
    return { graph, height };
  }, [flows]);

  if (flows.length === 0) {
    return <p className="text-sm text-muted-foreground">Nothing flows in this solution.</p>;
  }

  const { graph, height } = layout;
  const activeNode = hover?.node;
  const isActive = (l: LaidLink) =>
    hover?.link ? hover.link === l : activeNode ? l.source === activeNode || l.target === activeNode : true;

  const path = sankeyLinkHorizontal<NodeDatum, LinkDatum>();

  return (
    <figure className="relative">
      <div className="mb-2 flex justify-between text-xs font-medium text-muted-foreground">
        <span>{fromLabel}</span>
        <span>{toLabel}</span>
      </div>
      <svg
        viewBox={`0 0 ${WIDTH} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label={`Flow from ${fromLabel.toLowerCase()} to ${toLabel.toLowerCase()}`}
        onMouseLeave={() => setHover(undefined)}
      >
        <g fill="none">
          {graph.links.map((l, i) => (
            <path
              key={i}
              d={path(l) ?? undefined}
              stroke="var(--primary)"
              strokeOpacity={isActive(l) ? 0.42 : 0.08}
              strokeWidth={Math.max(1.5, l.width ?? 1)}
              className="transition-[stroke-opacity] duration-150"
              onMouseMove={(e) => {
                const box = e.currentTarget.ownerSVGElement!.getBoundingClientRect();
                setHover({ link: l, x: e.clientX - box.left, y: e.clientY - box.top });
              }}
            />
          ))}
        </g>
        {graph.nodes.map((n) => {
          const h = (n.y1 ?? 0) - (n.y0 ?? 0);
          const left = n.side === "from";
          return (
            <g
              key={n.id}
              onMouseEnter={(e) => {
                const box = e.currentTarget.ownerSVGElement!.getBoundingClientRect();
                setHover({ node: n, x: e.clientX - box.left, y: e.clientY - box.top });
              }}
            >
              {/* Hit target larger than the 10px node. */}
              <rect
                x={(n.x0 ?? 0) - (left ? LABEL_GUTTER - 8 : 4)}
                y={n.y0}
                width={LABEL_GUTTER + NODE_WIDTH - 4}
                height={Math.max(h, 16)}
                fill="transparent"
              />
              <rect
                x={n.x0}
                y={n.y0}
                width={NODE_WIDTH}
                height={Math.max(h, 2)}
                rx={2}
                fill="var(--primary)"
              />
              <text
                x={left ? (n.x0 ?? 0) - 8 : (n.x1 ?? 0) + 8}
                y={((n.y0 ?? 0) + (n.y1 ?? 0)) / 2}
                dy="0.35em"
                textAnchor={left ? "end" : "start"}
                className="fill-foreground text-[12px]"
              >
                {n.label}
              </text>
              <text
                x={left ? (n.x0 ?? 0) - 8 : (n.x1 ?? 0) + 8}
                y={((n.y0 ?? 0) + (n.y1 ?? 0)) / 2 + 14}
                dy="0.35em"
                textAnchor={left ? "end" : "start"}
                className="fill-muted-foreground font-mono text-[10px]"
              >
                {fmt(n.value)}
              </text>
            </g>
          );
        })}
      </svg>

      {hover && (
        <div
          className="pointer-events-none absolute z-10 min-w-40 rounded-md border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md"
          style={{
            left: hover.x + 12,
            top: hover.y + 12,
            transform: hover.x > 420 ? "translateX(calc(-100% - 24px))" : undefined,
          }}
        >
          {hover.link ? (
            <>
              <p className="font-medium">
                {(hover.link.source as LaidNode).label} → {(hover.link.target as LaidNode).label}
              </p>
              <p className="font-mono tabular-nums">
                {fmt(hover.link.flow.amount)} {unit}
              </p>
              {hover.link.flow.detail?.map((d) => (
                <p key={d} className="text-muted-foreground">
                  {d}
                </p>
              ))}
            </>
          ) : hover.node ? (
            <>
              <p className="font-medium">{hover.node.label}</p>
              <p className="font-mono tabular-nums">
                {fmt(hover.node.value)} {unit} {hover.node.side === "from" ? "out" : "in"}
              </p>
            </>
          ) : null}
        </div>
      )}
    </figure>
  );
}
