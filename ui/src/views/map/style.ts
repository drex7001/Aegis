import maplibregl from "maplibre-gl";
import type { StyleSpecification } from "maplibre-gl";

/**
 * Base-map and worker governance (T60, M-19, spec 10 §10).
 *
 * **No external service is contacted, by default or by accident.** The style
 * below declares a plain background and nothing else; the app's own GeoJSON
 * sources are added at runtime. There is no tile URL, no glyph server, no
 * sprite sheet and no geocoder.
 *
 * That is a real cost — features float on a blank field, without coastlines to
 * orient against — and it is the right one. Sending a viewport to a third party
 * is telling that party which places an investigation is looking at, and a
 * basemap is not worth that. An operator who has a self-hosted style points
 * `AEGIS_MAP_STYLE_URL` at it; the setting is unset by default and the CSP is
 * what keeps a careless value from becoming an egress path.
 *
 * **Geocoding does not exist here at all.** No name, identifier, address or
 * selector from any claim may be sent to any external geocoding service — a
 * prohibition, not a default. Coordinates are entered or selected by an
 * analyst, who records the `derivation` that says how they got them.
 */

/**
 * The offline default. `background` is the one layer type that needs no
 * network, and the colours are neutral so a mark is never confused with terrain.
 */
export const OFFLINE_STYLE: StyleSpecification = {
  version: 8,
  name: "Aegis offline",
  // Empty on purpose: a `glyphs` URL would fetch fonts, and a `sprite` URL
  // would fetch icons. Neither is worth an origin.
  sources: {},
  layers: [
    {
      id: "background",
      type: "background",
      paint: { "background-color": "#eef1f4" },
    },
  ],
};

/**
 * MapLibre creates its workers from a `blob:` URL by default, which
 * `default-src 'self'` denies (spec 10 §10). Vite bundles the worker as a
 * same-origin asset and this points MapLibre at it, so the fix is a build
 * configuration rather than a widened policy — `script-src 'self'` does not
 * move.
 */
export function configureWorker(): void {
  if (typeof Worker === "undefined") return;
  const url = new URL("maplibre-gl/dist/maplibre-gl-csp-worker.js", import.meta.url);
  maplibregl.setWorkerUrl(url.toString());
}
