import { LEVEL_COLORS, LEVEL_LABELS, LEVEL_ORDER, RouteOption } from "../api";

interface Props {
  routes: RouteOption[];
  selected: number;
  onSelect: (index: number) => void;
}

function formatDuration(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export default function RouteList({ routes, selected, onSelect }: Props) {
  return (
    <div className="route-list">
      {routes.map((route, i) => {
        const total = route.distance_miles || 1;
        return (
          <button
            key={i}
            className={`route-card${i === selected ? " selected" : ""}`}
            onClick={() => onSelect(i)}
            type="button"
          >
            <div className="route-card-head">
              <span className="route-name">Route {i + 1}</span>
              {route.recommended && <span className="badge">Recommended</span>}
            </div>
            <div className="route-stats">
              <span>{route.distance_miles.toFixed(0)} mi</span>
              <span>{formatDuration(route.duration_min)}</span>
              <span
                className="level-chip"
                style={{ background: LEVEL_COLORS[route.summary.worst] }}
              >
                {LEVEL_LABELS[route.summary.worst]}
              </span>
            </div>
            <div className="risk-bar">
              {LEVEL_ORDER.map((level) => {
                const miles = route.summary.miles_by_level[level];
                if (miles <= 0) return null;
                return (
                  <span
                    key={level}
                    title={`${LEVEL_LABELS[level]}: ${miles.toFixed(0)} mi`}
                    style={{
                      width: `${(miles / total) * 100}%`,
                      background: LEVEL_COLORS[level],
                    }}
                  />
                );
              })}
            </div>
            {route.summary.miles_by_level.no_travel > 0 && (
              <div className="no-travel-note">
                {route.summary.miles_by_level.no_travel.toFixed(0)} mi marked no-travel
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}
