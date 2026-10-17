# Haulcast

Weather-aware truck routing. A driver enters an origin, a destination, a departure
time and a load weight; Haulcast pulls up to three route options, samples the
forecast along each one at the truck's own pace, scores every checkpoint against
wind, rain, snow and load limits, and recommends the safest route.

Live: https://haulcast.netlify.app

![React](https://img.shields.io/badge/frontend-React%20%2B%20MapLibre-61dafb)
![Django](https://img.shields.io/badge/backend-Django%20%2B%20DRF-0c4b33)

## How it works

```
origin, destination, departure, load weight
                |
        geocode (Nominatim)
                |
        3 route options (OSRM)
                |
  checkpoints every 10 / 25 / 50 miles
  ETA at each = departure + drive time x fraction of route
                |
   hourly weather per checkpoint (Open-Meteo)
                |
 risk per checkpoint: wind / rain / snow bands + load rules
                |
 recommendation: fewest no-travel miles, then severe,
 then high, then lowest average risk, then shortest time
```

The map shows every route with its checkpoints colored by risk, per-checkpoint
ETA and weather, a per-route risk breakdown, and a weather heatmap along the
corridor with a 0-48 hour forecast slider.

## Risk rules

Each checkpoint is classified from the hourly forecast:

| Condition | Low | Moderate | High | Severe | No travel |
| --------- | --- | -------- | ---- | ------ | --------- |
| Wind      | <25 mph | 25-34 | 35-44 | 45-54 | >=55 mph |
| Rain      | <0.10 in/hr | 0.10-0.25 | 0.25-0.50 | 0.50-1.00 | >1.00 |
| Snow      | <0.5 in/hr | 0.5-1.0 | 1.0-2.0 | 2.0-3.0 | >3.0 |

The checkpoint takes the worst of the three, then load rules apply:

- Wind >=55 mph: no travel, any load
- Wind 45-54 mph with load over 30,000 lb: no travel
- Wind 35-44 mph with load over 40,000 lb: severe

## Recommendation

Routes are ranked by, in order:

1. Fewest no-travel miles
2. Fewest severe miles
3. Fewest high miles
4. Lowest average risk
5. Shortest drive time

## API

### `POST /api/plan/`

```json
{
  "origin": "Chicago, IL",
  "destination": "Denver, CO",
  "departure": "2026-10-18T08:00:00Z",
  "load_weight": 32000,
  "interval": 25
}
```

`interval` is the checkpoint spacing in miles: 10, 25 or 50. Returns both
geocoded endpoints and up to three routes; each route carries its geometry,
checkpoints (mile, ETA, wind, rain, snow, risk level), a miles-by-risk summary
and a `recommended` flag on exactly one route.

### `POST /api/heatmap/`

```json
{
  "geometry": [[41.88, -87.63], [39.74, -104.99]],
  "time": "2026-10-18T14:00:00Z",
  "load_weight": 32000
}
```

Returns a grid of cells along the route corridor with a risk level and a 0-1
intensity, which the frontend renders as a MapLibre heatmap layer for any
forecast hour in the 0-48h slider.

## Running locally

Backend (Python 3.10+):

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate --run-syncdb  # not required, no models yet
python manage.py runserver
```

Frontend (Node 20+):

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to `localhost:8000`. To point at a deployed API instead,
set `VITE_API_URL` in `frontend/.env`.

## Tests

```bash
cd backend
python manage.py test
```

Covers the risk band boundaries, load rules, checkpoint sampling math,
recommendation ordering and both endpoints with mocked network services.

## Deployment

- Frontend: Netlify, builds `frontend/` per `netlify.toml`, auto-deploys from `main`.
- Backend: Render web service per `render.yaml` (gunicorn + Django).

Environment variables (backend): `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`,
`DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`.

Environment variables (frontend): `VITE_API_URL` - base API URL, e.g.
`https://haulcast-api.onrender.com/api`.

## Decisions and trade-offs

- **OSRM public demo server for routes.** No key, real road routing with
  alternatives. It is a shared demo service, so a production deployment would
  move to a paid or self-hosted router without code changes (one function).
- **National Weather Service for weather.** Keyless, hourly grid forecasts with
  wind speed, quantitative precipitation and snowfall, friendly to cloud
  hosting. Grid cells are fetched concurrently and cached in-process for 30
  minutes; rain uses QPF (liquid equivalent) and snow uses snowfall depth per
  hour. Points outside the US fall back to Open-Meteo.
- **ETA is proportional to distance.** A checkpoint at 40% of the route miles
  gets 40% of the drive time. Real trucks slow down for grades and weather;
  the hook for a per-segment speed model is `sample_points` in `geo.py`.
- **No database.** The app is stateless; geocoding and weather responses are
  cached in memory only.
- **Corridor heatmap grid.** The heatmap samples every ~12 miles along the
  route plus four offsets either side (~200 points, 3 batched weather calls),
  which keeps the 0-48h slider responsive.

## Project structure

```
backend/
  config/          Django project (settings, urls, wsgi)
  routing/
    risk.py        band tables, load rules, route scoring and ranking
    geo.py         haversine + checkpoint sampling along a polyline
    services.py    Nominatim, OSRM and Open-Meteo clients with caching
    views.py       /api/plan/ and /api/heatmap/
    tests.py
frontend/
  src/
    api.ts         typed API client
    components/    TripForm, RouteList, RouteMap
    App.tsx
```
