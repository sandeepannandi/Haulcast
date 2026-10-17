# Haulcast

Weather-aware truck routing. Enter an origin, destination, departure time and
load weight; Haulcast returns up to three route options, samples the forecast
along each at the truck's own pace, scores every checkpoint against wind, rain,
snow and load limits, and recommends the safest route. The map shows routes,
checkpoints and ETAs, plus a weather heatmap along the corridor with a 0-48
hour forecast slider.

Live: https://haulcast.netlify.app
API: https://haulcast-api.onrender.com
Code: https://github.com/sandeepannandi/Haulcast

Stack: React + TypeScript + MapLibre frontend, Django REST backend. Routing by
OSRM, geocoding by Nominatim, weather by the National Weather Service
(Open-Meteo fallback outside the US). All keyless.

## Risk rules

Each checkpoint takes the worst of wind, rain and snow, then load rules apply.

| Condition | Low | Moderate | High | Severe | No travel |
| --------- | --- | -------- | ---- | ------ | --------- |
| Wind      | <25 mph | 25-34 | 35-44 | 45-54 | >=55 mph |
| Rain      | <0.10 in/hr | 0.10-0.25 | 0.25-0.50 | 0.50-1.00 | >1.00 |
| Snow      | <0.5 in/hr | 0.5-1.0 | 1.0-2.0 | 2.0-3.0 | >3.0 |

- Wind >=55 mph: no travel, any load
- Wind 45-54 mph with load over 30,000 lb: no travel
- Wind 35-44 mph with load over 40,000 lb: severe

Routes are ranked by fewest no-travel miles, then severe, then high, then
lowest average risk, then shortest drive time.

## API

`POST /api/plan/` - `{origin, destination, departure, load_weight, interval}`
with interval 10, 25 or 50 miles. Returns both geocoded endpoints and up to
three routes; each route carries its geometry, checkpoints (mile, ETA, wind,
rain, snow, risk), a miles-by-risk summary and a `recommended` flag on exactly
one route.

`POST /api/heatmap/` - `{geometry, time, load_weight}`. Returns risk cells
along the corridor for the heatmap layer at any forecast hour in the slider.

## Running locally

```bash
cd backend && pip install -r requirements.txt && python manage.py runserver
cd frontend && npm install && npm run dev
```

Vite proxies `/api` to `localhost:8000`. Set `VITE_API_URL` in `frontend/.env`
to use a deployed API instead.

## Tests

```bash
cd backend && python manage.py test
```

Covers risk band boundaries, load rules, sampling math, recommendation
ordering, the NWS client and both endpoints with mocked services.

## Deployment

Frontend on Netlify (`netlify.toml`), backend on Render (`render.yaml`), both
auto-deploying from `main`. The free Render tier sleeps when idle, so the
first request after a quiet stretch can take up to a minute while the service
wakes and the weather cache fills; later requests are fast. Backend env vars: `DJANGO_SECRET_KEY`,
`DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`. Frontend env:
`VITE_API_URL`.

## Trade-offs

- OSRM public demo server: keyless real road routing; a production deployment
  would swap one function for a paid or self-hosted router.
- ETA is proportional to distance covered; the hook for a per-segment speed
  model is `sample_points` in `geo.py`.
- Stateless: weather is cached in memory for 30 minutes; geocoding is cached
  in memory until restart. No database.
