import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import { HeatCell, LEVEL_COLORS, LEVEL_ORDER, RouteOption } from "../api";

interface Props {
  routes: RouteOption[] | null;
  selected: number;
  heatCells: HeatCell[] | null;
  heatVisible: boolean;
}

const STYLE_URL = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";

function formatEta(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function RouteMap({ routes, selected, heatCells, heatVisible }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const popup = useRef<maplibregl.Popup | null>(null);

  useEffect(() => {
    if (!container.current || map.current) return;
    map.current = new maplibregl.Map({
      container: container.current,
      style: STYLE_URL,
      center: [-98.5, 39.8],
      zoom: 3.5,
    });
    map.current.addControl(new maplibregl.NavigationControl(), "top-right");
    return () => {
      map.current?.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m) return;

    function teardown() {
      if (!m) return;
      const style = m.getStyle();
      if (!style || !style.layers) return;
      for (const layer of [...style.layers]) {
        if (layer.id.startsWith("haul-")) m.removeLayer(layer.id);
      }
      for (const id of Object.keys(style.sources)) {
        if (id.startsWith("haul-")) m.removeSource(id);
      }
      popup.current?.remove();
    }

    function build() {
      if (!m || !routes || routes.length === 0) return;
      const bounds = new maplibregl.LngLatBounds();
      const lineColors = ["#8250df", "#1a7f37", "#0969da"];
      const order = routes.map((_, i) => i).sort((a, b) => (a === selected ? 1 : 0) - (b === selected ? 1 : 0));

      for (const i of order) {
        const route = routes[i];
        const coords = route.geometry.map(([lat, lon]) => [lon, lat] as [number, number]);
        coords.forEach((c) => bounds.extend(c));
        m.addSource(`haul-route-${i}`, {
          type: "geojson",
          data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: coords } },
        });
        const isSelected = i === selected;
        m.addLayer({
          id: `haul-route-${i}-line`,
          type: "line",
          source: `haul-route-${i}`,
          paint: {
            "line-color": isSelected ? lineColors[i % lineColors.length] : "#9fa8b3",
            "line-width": isSelected ? 5 : 3,
            "line-opacity": isSelected ? 0.95 : 0.55,
          },
        });
      }

      const route = routes[selected];
      if (route) {
        m.addSource("haul-checkpoints", {
          type: "geojson",
          data: {
            type: "FeatureCollection",
            features: route.checkpoints.map((c) => ({
              type: "Feature" as const,
              properties: {
                mile: c.mile,
                eta: formatEta(c.eta),
                level: c.level,
                wind: c.wind_mph,
                rain: c.rain_in_hr,
                snow: c.snow_in_hr,
                color: LEVEL_COLORS[c.level],
              },
              geometry: { type: "Point" as const, coordinates: [c.lon, c.lat] },
            })),
          },
        });
        m.addLayer({
          id: "haul-checkpoints-dots",
          type: "circle",
          source: "haul-checkpoints",
          paint: {
            "circle-radius": 6,
            "circle-color": ["get", "color"],
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 1.5,
          },
        });
        m.on("click", "haul-checkpoints-dots", (e) => {
          const f = e.features?.[0];
          if (!f) return;
          const p = f.properties as Record<string, string | number>;
          popup.current?.remove();
          popup.current = new maplibregl.Popup({ closeButton: true })
            .setLngLat((f.geometry as GeoJSON.Point).coordinates as [number, number])
            .setHTML(
              `<div class="checkpoint-pop">
                <strong>Mile ${p.mile}</strong> - ${p.eta}<br/>
                Wind ${p.wind} mph - Rain ${p.rain} in/hr - Snow ${p.snow} in/hr<br/>
                Risk: <strong>${p.level}</strong>
              </div>`
            )
            .addTo(m);
        });
        m.on("mouseenter", "haul-checkpoints-dots", () => {
          m.getCanvas().style.cursor = "pointer";
        });
        m.on("mouseleave", "haul-checkpoints-dots", () => {
          m.getCanvas().style.cursor = "";
        });
      }

      if (!bounds.isEmpty()) {
        m.fitBounds(bounds, { padding: 60, duration: 600 });
      }
    }

    if (!m.isStyleLoaded()) {
      m.once("load", () => {
        teardown();
        build();
      });
    } else {
      teardown();
      build();
    }
  }, [routes, selected]);

  useEffect(() => {
    const m = map.current;
    if (!m) return;

    function apply() {
      if (!m) return;
      const style = m.getStyle();
      if (style.layers.some((l) => l.id === "haul-heat")) {
        m.removeLayer("haul-heat");
      }
      if (style.sources["haul-heat"]) {
        m.removeSource("haul-heat");
      }
      if (!heatVisible || !heatCells || heatCells.length === 0) return;
      m.addSource("haul-heat", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: heatCells.map((c) => ({
            type: "Feature" as const,
            properties: { intensity: c.intensity },
            geometry: { type: "Point" as const, coordinates: [c.lon, c.lat] },
          })),
        },
      });
      m.addLayer(
        {
          id: "haul-heat",
          type: "heatmap",
          source: "haul-heat",
          paint: {
            "heatmap-weight": ["interpolate", ["linear"], ["get", "intensity"], 0, 0.05, 1, 1],
            "heatmap-radius": 28,
            "heatmap-opacity": 0.75,
            "heatmap-color": [
              "interpolate",
              ["linear"],
              ["heatmap-density"],
              0,
              "rgba(45,164,78,0)",
              0.25,
              "rgba(45,164,78,0.55)",
              0.5,
              "rgba(212,167,44,0.65)",
              0.75,
              "rgba(224,130,61,0.75)",
              1,
              "rgba(207,34,46,0.85)",
            ],
          },
        },
        m.getStyle().layers.find((l) => l.id.startsWith("haul-route"))?.id
      );
    }

    if (!m.isStyleLoaded()) {
      m.once("load", apply);
    } else {
      apply();
    }
  }, [heatCells, heatVisible]);

  return <div className="map" ref={container} />;
}

export { LEVEL_ORDER };
