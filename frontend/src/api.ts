export type RiskLevel = "low" | "moderate" | "high" | "severe" | "no_travel";

export interface Checkpoint {
  lat: number;
  lon: number;
  mile: number;
  eta: string;
  wind_mph: number;
  rain_in_hr: number;
  snow_in_hr: number;
  level: RiskLevel;
}

export interface RouteSummary {
  miles_by_level: Record<RiskLevel, number>;
  avg_risk: number;
  worst: RiskLevel;
  duration_min: number;
}

export interface RouteOption {
  distance_miles: number;
  duration_min: number;
  geometry: [number, number][];
  checkpoints: Checkpoint[];
  summary: RouteSummary;
  recommended: boolean;
}

export interface PlanResult {
  origin: { lat: number; lon: number; label: string };
  destination: { lat: number; lon: number; label: string };
  departure: string;
  load_lbs: number;
  interval: number;
  routes: RouteOption[];
}

export interface HeatCell {
  lat: number;
  lon: number;
  level: RiskLevel;
  intensity: number;
}

export interface PlanInput {
  origin: string;
  destination: string;
  departure: string;
  load_weight: number;
  interval: number;
}

const API_URL = import.meta.env.VITE_API_URL ?? "/api";

async function readDetail(resp: Response): Promise<string> {
  try {
    const body = await resp.json();
    return body.detail ?? "something went wrong";
  } catch {
    return "something went wrong";
  }
}

const RETRY_DELAYS = [3000, 6000, 12000];
const RETRY_STATUSES = [502, 503, 504];

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function post(path: string, body: unknown, onWaking?: () => void): Promise<Response> {
  for (let attempt = 0; ; attempt++) {
    let resp: Response | null = null;
    try {
      resp = await fetch(`${API_URL}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch (err) {
      if (attempt >= RETRY_DELAYS.length) {
        throw new Error("The server is not responding. Please try again in a moment.");
      }
    }
    if (resp && !RETRY_STATUSES.includes(resp.status)) return resp;
    if (attempt >= RETRY_DELAYS.length) {
      throw new Error("The server is not responding. Please try again in a moment.");
    }
    onWaking?.();
    await sleep(RETRY_DELAYS[attempt]);
  }
}

export async function fetchPlan(input: PlanInput, onWaking?: () => void): Promise<PlanResult> {
  const resp = await post("/plan/", input, onWaking);
  if (!resp.ok) {
    throw new Error(await readDetail(resp));
  }
  return resp.json();
}

export async function fetchHeatmap(
  geometry: [number, number][],
  time: string,
  loadLbs: number,
  detail: "coarse" | "full" = "full"
): Promise<HeatCell[]> {
  const resp = await post("/heatmap/", { geometry, time, load_weight: loadLbs, detail });
  if (!resp.ok) {
    throw new Error(await readDetail(resp));
  }
  const body = await resp.json();
  return body.cells;
}

export const LEVEL_ORDER: RiskLevel[] = ["low", "moderate", "high", "severe", "no_travel"];

export const LEVEL_COLORS: Record<RiskLevel, string> = {
  low: "#2da44e",
  moderate: "#d4a72c",
  high: "#e0823d",
  severe: "#cf222e",
  no_travel: "#57606a",
};

export const LEVEL_LABELS: Record<RiskLevel, string> = {
  low: "Low",
  moderate: "Moderate",
  high: "High",
  severe: "Severe",
  no_travel: "No travel",
};
