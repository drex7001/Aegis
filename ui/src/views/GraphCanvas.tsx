import cytoscape from "cytoscape";
import { useEffect, useRef } from "react";

import type { GraphView } from "../api/client";

/**
 * Cytoscape.js inside React (spec 07 §2): the canvas owns its own DOM, and
 * React owns when to hand it new elements. Wrapping it in a component library
 * would put a second, staler abstraction between us and the layout engine for
 * no gain.
 *
 * Styling follows spec 07 §5: no red-means-criminal palette, and a segment
 * whose support is contested is drawn *differently* rather than more faintly —
 * a contradiction is a lens, not a weakening (Article VIII).
 */

export interface GraphCanvasProps {
  view: GraphView;
  onSelectEdge?: (edgeId: string) => void;
  onSelectNode?: (entityId: string) => void;
}

/**
 * Deterministic per element set, so the same query redraws the same picture: an
 * analyst comparing two runs is comparing the graph, not the animation seed.
 */
const LAYOUT: cytoscape.LayoutOptions = {
  name: "cose",
  animate: false,
  randomize: false,
  padding: 40,
} as cytoscape.LayoutOptions;

/** Model units between adjacent nodes — roughly one name's width. */
const TARGET_EDGE_LENGTH = 130;

/**
 * Let `cose` decide the shape, then decide the scale here.
 *
 * `cose` lays out for topology and packs a small result into a few dozen model
 * units, which puts every name on top of its neighbour's — and its
 * `idealEdgeLength`/`nodeRepulsion` knobs barely move that on graphs this size.
 * Rescaling about the origin afterwards changes no relationship in the picture
 * (it is a similarity transform) and is deterministic, so the shape stays
 * comparable between runs while the labels become readable.
 */
function normalizeScale(cy: cytoscape.Core): void {
  const lengths = cy
    .edges()
    .map((edge) => {
      const a = edge.source().position();
      const b = edge.target().position();
      return Math.hypot(a.x - b.x, a.y - b.y);
    })
    .filter((length) => length > 0)
    .sort((a, b) => a - b);
  if (lengths.length === 0) return;

  const median = lengths[Math.floor(lengths.length / 2)] as number;
  const factor = TARGET_EDGE_LENGTH / median;
  if (!Number.isFinite(factor) || Math.abs(factor - 1) < 0.05) return;

  cy.nodes().positions((node) => {
    const { x, y } = node.position();
    return { x: x * factor, y: y * factor };
  });
}

/**
 * Fit, but never magnify. Node and font sizes are model units, so `fit()` on a
 * four-node result would zoom until the names cover the graph they label, while
 * a large result still needs to zoom out to be seen at all. Fitting and then
 * clamping to 1:1 gives both.
 */
function fitWithoutMagnifying(cy: cytoscape.Core): void {
  cy.fit(undefined, 40);
  if (cy.zoom() > 1) {
    cy.zoom(1);
    cy.center();
  }
}

const STYLE: cytoscape.StylesheetJson = [
  {
    selector: "node",
    style: {
      "background-color": "#5b7c99",
      label: "data(label)",
      color: "#1c2733",
      "font-size": "11px",
      "text-valign": "bottom",
      "text-margin-y": 4,
      width: 22,
      height: 22,
    },
  },
  {
    selector: "node.seed",
    style: { "background-color": "#2f5169", width: 30, height: 30 },
  },
  {
    selector: "edge",
    style: {
      "curve-style": "bezier",
      "line-color": "#9aa7b2",
      "target-arrow-shape": "none",
      width: 2,
      label: "data(predicate)",
      "font-size": "9px",
      color: "#5c6b7a",
      "text-rotation": "autorotate",
    },
  },
  {
    // Contested support: dashed, not dimmed. Dimming would read as "weaker
    // evidence"; the point is that two sources disagree.
    selector: "edge.contested",
    style: { "line-style": "dashed", "line-color": "#8a6d3b" },
  },
  {
    selector: ":selected",
    style: { "border-width": 3, "border-color": "#1c2733", "line-color": "#1c2733" },
  },
];

export function GraphCanvas({ view, onSelectEdge, onSelectNode }: GraphCanvasProps) {
  const container = useRef<HTMLDivElement | null>(null);
  const instance = useRef<cytoscape.Core | null>(null);

  useEffect(() => {
    if (!container.current) return;
    const cy = cytoscape({
      container: container.current,
      style: STYLE,
      layout: LAYOUT,
      wheelSensitivity: 0.2,
      minZoom: 0.15,
      maxZoom: 3,
    });
    instance.current = cy;
    return () => {
      cy.destroy();
      instance.current = null;
    };
  }, []);

  useEffect(() => {
    const cy = instance.current;
    if (!cy) return;
    const seeds = new Set(view.resolved_seed_ids);
    cy.elements().remove();
    cy.add([
      ...view.nodes.map((node) => ({
        group: "nodes" as const,
        data: { id: node.entity_id, label: node.label, type: node.entity_type },
        classes: seeds.has(node.entity_id) ? "seed" : undefined,
      })),
      ...view.edges.map((edge) => ({
        group: "edges" as const,
        data: {
          id: edge.edge_id,
          source: edge.subject_id,
          target: edge.object_id,
          predicate: edge.predicate,
        },
        classes: contested(edge.support) ? "contested" : undefined,
      })),
    ]);
    cy.layout(LAYOUT).run();
    normalizeScale(cy);
    fitWithoutMagnifying(cy);
  }, [view]);

  useEffect(() => {
    const cy = instance.current;
    if (!cy) return;
    const edgeTap = (event: cytoscape.EventObject) =>
      onSelectEdge?.(event.target.id() as string);
    const nodeTap = (event: cytoscape.EventObject) =>
      onSelectNode?.(event.target.id() as string);
    cy.on("tap", "edge", edgeTap);
    cy.on("tap", "node", nodeTap);
    return () => {
      cy.removeListener("tap", "edge", edgeTap);
      cy.removeListener("tap", "node", nodeTap);
    };
  }, [onSelectEdge, onSelectNode]);

  return <div className="canvas" ref={container} data-testid="graph-canvas" />;
}

function contested(support: Record<string, unknown> | undefined): boolean {
  return Number(support?.["contradiction_count"] ?? 0) > 0;
}
