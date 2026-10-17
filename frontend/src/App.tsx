import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchHeatmap, fetchPlan, HeatCell, PlanInput, PlanResult } from "./api";
import RouteMap from "./components/RouteMap";
import RouteList from "./components/RouteList";
import TripForm from "./components/TripForm";

export default function App() {
  const [plan, setPlan] = useState<PlanResult | null>(null);
  const [selected, setSelected] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [heatOn, setHeatOn] = useState(false);
  const [heatHour, setHeatHour] = useState(0);
  const [heatCells, setHeatCells] = useState<HeatCell[] | null>(null);
  const [heatLoading, setHeatLoading] = useState(false);

  const handleSubmit = useCallback((input: PlanInput) => {
    setLoading(true);
    setError(null);
    setHeatCells(null);
    fetchPlan(input)
      .then((result) => {
        setPlan(result);
        const best = result.routes.findIndex((r) => r.recommended);
        setSelected(best >= 0 ? best : 0);
      })
      .catch((err: Error) => {
        setPlan(null);
        setError(err.message);
      })
      .finally(() => setLoading(false));
  }, []);

  const heatTime = useMemo(() => {
    if (!plan) return null;
    const base = new Date(plan.departure).getTime();
    return new Date(base + heatHour * 3600 * 1000);
  }, [plan, heatHour]);

  useEffect(() => {
    if (!plan || !heatOn || !heatTime) return;
    const route = plan.routes[selected];
    if (!route) return;
    setHeatLoading(true);
    const timer = setTimeout(() => {
      fetchHeatmap(route.geometry, heatTime.toISOString(), plan.load_lbs)
        .then(setHeatCells)
        .catch(() => setHeatCells(null))
        .finally(() => setHeatLoading(false));
    }, 350);
    return () => clearTimeout(timer);
  }, [plan, selected, heatOn, heatTime]);

  return (
    <div className="layout">
      <aside className="sidebar">
        <header>
          <h1>Haulcast</h1>
          <p>Pick the safest route across weather, load and time.</p>
        </header>
        <TripForm loading={loading} onSubmit={handleSubmit} />
        {error && <div className="error-banner">{error}</div>}
        {plan && (
          <>
            <RouteList routes={plan.routes} selected={selected} onSelect={setSelected} />
            <div className="heat-panel">
              <label className="heat-toggle">
                <input
                  type="checkbox"
                  checked={heatOn}
                  onChange={(e) => setHeatOn(e.target.checked)}
                />
                Weather heatmap
              </label>
              {heatOn && (
                <>
                  <input
                    type="range"
                    min="0"
                    max="48"
                    step="1"
                    value={heatHour}
                    onChange={(e) => setHeatHour(Number(e.target.value))}
                  />
                  <div className="heat-time">
                    {heatLoading
                      ? "Loading forecast..."
                      : heatTime
                        ? `Forecast for ${heatTime.toLocaleString(undefined, {
                            weekday: "short",
                            month: "short",
                            day: "numeric",
                            hour: "numeric",
                            minute: "2-digit",
                          })}`
                        : ""}
                  </div>
                </>
              )}
            </div>
            <div className="legend">
              <span><i style={{ background: "#2da44e" }} /> Low</span>
              <span><i style={{ background: "#d4a72c" }} /> Moderate</span>
              <span><i style={{ background: "#e0823d" }} /> High</span>
              <span><i style={{ background: "#cf222e" }} /> Severe</span>
              <span><i style={{ background: "#57606a" }} /> No travel</span>
            </div>
          </>
        )}
      </aside>
      <main>
        <RouteMap
          routes={plan ? plan.routes : null}
          selected={selected}
          heatCells={heatCells}
          heatVisible={heatOn}
        />
      </main>
    </div>
  );
}
