import "maplibre-gl/dist/maplibre-gl.css";

import maplibregl, {
  type Map as MapLibreMap,
  type GeoJSONSource,
  type LayerSpecification,
} from "maplibre-gl";
import type { Feature, FeatureCollection as GeoJsonCollection, Geometry } from "geojson";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  geoEvents,
  geoLocations,
  type EventProperties,
  type GeoFeature,
  type PlaceProperties,
} from "../../api/client";
import { entityPath } from "../../routing";
import { OFFLINE_STYLE, configureWorker } from "./style";
import { describeMark, markFor, type Mark, type MarkInput } from "./marks";

/**
 * The map (T60, spec 10 §9–§10).
 *
 * Three things it is careful about, in order of how badly they would fail:
 *
 * 1. **It cannot draw a pin it has not earned.** Every feature's mark comes
 *    from `markFor`, which has exactly one point branch and reaches it only for
 *    a non-administrative level. The store enforces the same rule from the
 *    other side (spec 10 §4.3), so a `country`-level location has no path to a
 *    point at any zoom — the charter's third criterion, held twice.
 * 2. **It fetches nothing from anyone.** The default style declares a plain
 *    background and this app's own GeoJSON. No basemap tiles, no glyph server,
 *    no geocoder; sending a viewport to a third party is telling that party
 *    which places an investigation is looking at (M-19, §10).
 * 3. **It says what it is not showing.** A place whose geometry is above the
 *    viewer's clearance, unrecorded, or invalid is listed beside the map with
 *    the reason — never dropped, and never placed at a guessed position (§7.3).
 *
 * The time window and the selection live in the URL, so a view an analyst is
 * looking at is a view they can send to someone.
 */

interface Drawn {
  feature: GeoFeature;
  mark: Mark;
  input: MarkInput;
}

/** An event feature is a place feature that also carries an occurrence. */
export function isEventProperties(
  properties: PlaceProperties | EventProperties,
): properties is EventProperties {
  return "event_id" in properties;
}

/**
 * The generated properties, as the mark rules want them.
 *
 * The casts are at this one boundary on purpose. `geometry_state` and the two
 * vocabulary fields are open `string` in the contract — the server validates
 * them against code-owned lists (`aegis/ontology/registries.py`) rather than
 * against an OpenAPI enum that would churn on every addition — and `markFor`
 * is written to handle a value it does not recognise by drawing *nothing*,
 * which is what makes the loose typing safe rather than merely convenient.
 */
function markInputOf(feature: GeoFeature): MarkInput {
  const p = feature.properties;
  return {
    geometryState: p.geometry_state as MarkInput["geometryState"],
    geometryKind: p.geometry_kind ?? null,
    adminLevel: (p.admin_level ?? null) as MarkInput["adminLevel"],
    derivation: (p.derivation ?? null) as MarkInput["derivation"],
    accuracyM: p.accuracy_m ?? null,
  };
}

/** A circle of `radiusM`, as a polygon: MapLibre sizes `circle` in pixels. */
function circlePolygon(centre: [number, number], radiusM: number) {
  const [lon, lat] = centre;
  const points: [number, number][] = [];
  const latRadius = radiusM / 111_320;
  const lonRadius = radiusM / (111_320 * Math.cos((lat * Math.PI) / 180) || 1);
  for (let i = 0; i <= 64; i += 1) {
    const angle = (i / 64) * 2 * Math.PI;
    points.push([lon + lonRadius * Math.cos(angle), lat + latRadius * Math.sin(angle)]);
  }
  return { type: "Polygon" as const, coordinates: [points] };
}

function centroidOf(geometry: GeoFeature["geometry"]): [number, number] | null {
  if (!geometry) return null;
  const coordinates = geometry.coordinates as unknown;
  const flat: [number, number][] = [];
  const walk = (node: unknown) => {
    if (Array.isArray(node) && typeof node[0] === "number" && typeof node[1] === "number") {
      flat.push([node[0], node[1]]);
      return;
    }
    if (Array.isArray(node)) node.forEach(walk);
  };
  walk(coordinates);
  if (flat.length === 0) return null;
  const sum = flat.reduce<[number, number]>((acc, [x, y]) => [acc[0] + x, acc[1] + y], [0, 0]);
  return [sum[0] / flat.length, sum[1] / flat.length];
}

/**
 * The drawn features, as one GeoJSON source per mark kind.
 *
 * Split by kind rather than styled with a data expression because the split is
 * the guarantee: a feature can only be drawn as a point by being in the point
 * source, and only `markFor` puts it there.
 */
function sourcesFor(drawn: Drawn[]) {
  // One shape per *place*, even when an event happened there. The API returns
  // a feature per (event, place, role) on purpose — travel has two ends — but
  // two overlapping circles for one location read as two locations, and a
  // reader counting shapes would be counting wrong.
  const placed = new Set<string>();
  const buckets: Record<string, Feature[]> = {
    point: [],
    circle: [],
    area: [],
    coverage: [],
    estimate: [],
  };
  const bucket = (kind: string): Feature[] => (buckets[kind] ??= []);
  for (const item of drawn) {
    if (item.mark.kind === "none" || !item.feature.geometry) continue;
    const placeId = item.feature.properties.entity_id;
    if (placed.has(placeId)) continue;
    placed.add(placeId);
    const properties = { ...item.feature.properties, mark_kind: item.mark.kind };
    if (item.mark.kind === "circle" && item.mark.radiusM !== null) {
      const centre = centroidOf(item.feature.geometry);
      if (centre) {
        bucket("circle").push({
          type: "Feature",
          geometry: circlePolygon(centre, item.mark.radiusM),
          properties,
        });
        continue;
      }
    }
    bucket(item.mark.kind).push({
      type: "Feature",
      geometry: item.feature.geometry as unknown as Geometry,
      properties,
    });
  }
  return buckets;
}

export function MapView() {
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const container = useRef<HTMLDivElement | null>(null);
  const map = useRef<MapLibreMap | null>(null);
  const [ready, setReady] = useState(false);
  const [selected, setSelected] = useState<Drawn | null>(null);

  const from = search.get("from") ?? undefined;
  const to = search.get("to") ?? undefined;
  const asOf = search.get("asOf") ?? undefined;

  const places = useQuery({
    queryKey: ["geo", "locations", asOf ?? null],
    queryFn: () => geoLocations({ asOf, limit: 200 }),
  });
  const events = useQuery({
    queryKey: ["geo", "events", from ?? null, to ?? null, asOf ?? null],
    queryFn: () => geoEvents({ from, to, asOf, limit: 200 }),
  });

  const drawn = useMemo<Drawn[]>(() => {
    const features = [
      ...(places.data?.features ?? []),
      ...(events.data?.features ?? []),
    ];
    return features.map((feature) => {
      const input = markInputOf(feature);
      return { feature, mark: markFor(input), input };
    });
  }, [places.data, events.data]);

  const undrawable = drawn.filter((item) => item.mark.kind === "none");

  useEffect(() => {
    if (!container.current || map.current) return;
    configureWorker();
    const instance = new maplibregl.Map({
      container: container.current,
      style: OFFLINE_STYLE,
      center: [80.0, 7.5],
      zoom: 6,
      attributionControl: false,
    });
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    instance.on("load", () => setReady(true));
    map.current = instance;
    return () => {
      instance.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready) return;
    const buckets = sourcesFor(drawn);

    for (const [kind, features] of Object.entries(buckets)) {
      const id = `aegis-${kind}`;
      const data: GeoJsonCollection = { type: "FeatureCollection", features };
      const existing = instance.getSource(id) as GeoJSONSource | undefined;
      if (existing) {
        existing.setData(data);
        continue;
      }
      instance.addSource(id, { type: "geojson", data });
      addLayersFor(instance, kind, id);
      instance.on("click", `${id}-hit`, (event) => {
        const hit = event.features?.[0];
        if (!hit) return;
        const entityId = hit.properties?.entity_id as string | undefined;
        const match = drawnRef.current.find(
          (item) => item.feature.properties.entity_id === entityId,
        );
        if (match) setSelected(match);
      });
    }
  }, [drawn, ready]);

  // The click handler is registered once per source, so it needs the current
  // features rather than the ones that existed when it was bound.
  const drawnRef = useRef<Drawn[]>(drawn);
  drawnRef.current = drawn;

  return (
    <section className="map" data-testid="map-view">
      <header className="map__header">
        <h1>Map</h1>
        <form
          className="map__filter"
          data-testid="map-time-filter"
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            const next = new URLSearchParams(search);
            for (const [key, field] of [
              ["from", "from"],
              ["to", "to"],
            ] as const) {
              const value = String(form.get(field) ?? "");
              if (value) next.set(key, new Date(value).toISOString());
              else next.delete(key);
            }
            setSearch(next);
          }}
        >
          <label>
            <span>From</span>
            <input type="date" name="from" defaultValue={from?.slice(0, 10)} data-testid="map-from" />
          </label>
          <label>
            <span>To</span>
            <input type="date" name="to" defaultValue={to?.slice(0, 10)} data-testid="map-to" />
          </label>
          <button type="submit" data-testid="map-apply">
            Apply
          </button>
        </form>
      </header>

      {(places.data?.stamp || events.data?.stamp) && (
        <p className="muted" data-testid="map-stamp">
          Ontology {(places.data?.stamp ?? events.data?.stamp)?.ontology_version} · identity
          revision {(places.data?.stamp ?? events.data?.stamp)?.identity_revision_id}
          {asOf ? ` · as of ${asOf}` : ""}
        </p>
      )}

      <div
        className="map__canvas"
        ref={container}
        data-testid="map-canvas"
        role="img"
        aria-label={`Map of ${drawn.length} located features`}
      />

      <Legend />

      {/*
        * The map, as text. A canvas is not readable by a screen reader, so
        * everything drawn is listed here with the mark it was drawn as and why
        * — which is the same information the legend gives a sighted reader.
        *
        * It is also what the browser test asserts against, and that is the
        * right way round: a test that reached into MapLibre's internals would
        * prove the source got the right feature while proving nothing about
        * what a person can find out.
        */}
      <h2>Drawn features</h2>
      <ul data-testid="map-features">
        {drawn
          .filter((item) => item.mark.kind !== "none")
          .map((item) => (
            <li
              key={item.feature.id}
              /*
               * The feature id, not the place id: an event at a place is a
               * separate row here (it has a time and participants the place
               * does not), and two rows sharing a test id is two rows a
               * reader cannot tell apart either.
               */
              data-testid={`map-feature-${item.feature.id}`}
              data-mark={item.mark.kind}
              data-radius={item.mark.radiusM ?? ""}
            >
              {item.feature.properties.label} —{" "}
              <span className="muted">{describeMark(item.mark, item.input)}</span>
            </li>
          ))}
      </ul>

      {selected && (
        <aside className="map__detail" data-testid="map-detail">
          <h2>{selected.feature.properties.label}</h2>
          <p className="muted">{describeMark(selected.mark, selected.input)}</p>
          <dl>
            <dt>Admin level</dt>
            <dd data-testid="map-detail-admin">{selected.feature.properties.admin_level ?? "—"}</dd>
            <dt>Derivation</dt>
            <dd data-testid="map-detail-derivation">
              {selected.feature.properties.derivation ?? "—"}
            </dd>
          </dl>
          <button
            type="button"
            data-testid="map-detail-open"
            onClick={() => navigate(entityPath(selected.feature.properties.entity_id))}
          >
            Open object view
          </button>
        </aside>
      )}

      <h2>Not shown on the map</h2>
      <div data-testid="map-undrawable">
        {undrawable.length === 0 ? (
          <p className="notice">Everything you can see has a geometry that can be drawn.</p>
        ) : (
          <ul>
            {undrawable.map((item) => (
              <li key={item.feature.id}>
                <a href={entityPath(item.feature.properties.entity_id)}>
                  {item.feature.properties.label}
                </a>{" "}
                <span className="muted">{item.mark.reason}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

/** One layer set per mark kind, plus an invisible fat hit layer for clicks. */
function addLayersFor(instance: MapLibreMap, kind: string, source: string) {
  const paint: Record<string, LayerSpecification[]> = {
    point: [
      {
        id: `aegis-${kind}-fill`,
        type: "circle",
        source,
        paint: { "circle-radius": 6, "circle-color": "#c62828", "circle-stroke-width": 1, "circle-stroke-color": "#fff" },
      },
    ],
    circle: [
      {
        id: `aegis-${kind}-fill`,
        type: "fill",
        source,
        paint: { "fill-color": "#c62828", "fill-opacity": 0.15 },
      },
      {
        id: `aegis-${kind}-line`,
        type: "line",
        source,
        paint: { "line-color": "#c62828", "line-width": 1.5 },
      },
    ],
    area: [
      {
        id: `aegis-${kind}-fill`,
        type: "fill",
        source,
        paint: { "fill-color": "#2e7d32", "fill-opacity": 0.2 },
      },
      {
        id: `aegis-${kind}-line`,
        type: "line",
        source,
        paint: { "line-color": "#2e7d32", "line-width": 2 },
      },
    ],
    coverage: [
      {
        id: `aegis-${kind}-fill`,
        type: "fill",
        source,
        paint: { "fill-color": "#6a1b9a", "fill-opacity": 0.12 },
      },
      {
        id: `aegis-${kind}-line`,
        type: "line",
        source,
        paint: { "line-color": "#6a1b9a", "line-width": 1, "line-dasharray": [1, 1] },
      },
    ],
    estimate: [
      {
        id: `aegis-${kind}-line`,
        type: "line",
        source,
        paint: { "line-color": "#ef6c00", "line-width": 2, "line-dasharray": [2, 2] },
      },
    ],
  };
  for (const layer of paint[kind] ?? []) instance.addLayer(layer);
  instance.addLayer({
    id: `aegis-${kind}-hit`,
    type: kind === "point" ? "circle" : "fill",
    source,
    paint:
      kind === "point"
        ? { "circle-radius": 14, "circle-opacity": 0 }
        : { "fill-opacity": 0 },
  } as LayerSpecification);
}

function Legend() {
  return (
    <ul className="map__legend" data-testid="map-legend">
      <li data-testid="legend-point">Exact position — a specific place, known specifically</li>
      <li data-testid="legend-circle">Circle — a stated radius, or a centroid standing for an area</li>
      <li data-testid="legend-area">Outline — a boundary the source drew</li>
      <li data-testid="legend-coverage">Hatched — the area something covers</li>
      <li data-testid="legend-estimate">Dashed — an analyst's estimate</li>
    </ul>
  );
}
