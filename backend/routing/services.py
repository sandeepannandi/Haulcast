import time
from datetime import datetime, timezone

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_ROUTE_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

HEADERS = {"User-Agent": "haulcast/1.0"}

WEATHER_CACHE_TTL = 1800
WEATHER_BATCH_SIZE = 80

_geocode_cache = {}
_weather_cache = {}


def geocode(place):
    key = place.strip().lower()
    if key in _geocode_cache:
        return _geocode_cache[key]
    resp = requests.get(
        NOMINATIM_URL,
        params={"q": place, "format": "json", "limit": 1},
        headers=HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    hits = resp.json()
    if not hits:
        raise ValueError("Could not find " + place)
    point = {"lat": float(hits[0]["lat"]), "lon": float(hits[0]["lon"]), "label": hits[0]["display_name"]}
    _geocode_cache[key] = point
    return point


def get_routes(origin, destination, count=3):
    url = OSRM_ROUTE_URL.format(
        lon1=origin["lon"], lat1=origin["lat"],
        lon2=destination["lon"], lat2=destination["lat"],
    )
    resp = requests.get(
        url,
        params={"alternatives": "true", "geometries": "geojson", "overview": "full"},
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise ValueError("No route found between those points")
    routes = []
    for raw in data["routes"][:count]:
        coords = [[round(lat, 5), round(lon, 5)] for lon, lat in raw["geometry"]["coordinates"]]
        routes.append({
            "distance_miles": raw["distance"] / 1609.344,
            "duration_min": raw["duration"] / 60,
            "geometry": coords,
        })
    return routes


def _hour_key(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00")


def _cached_weather(lat, lon, key):
    entry = _weather_cache.get((round(lat, 3), round(lon, 3), key))
    if entry and entry[0] > time.time():
        return entry[1]
    return None


def weather_for(points, times):
    out = {}
    missing = []
    for i, (point, moment) in enumerate(zip(points, times)):
        key = _hour_key(moment)
        hit = _cached_weather(point[0], point[1], key)
        if hit is not None:
            out[i] = hit
        else:
            missing.append(i)
    for start in range(0, len(missing), WEATHER_BATCH_SIZE):
        batch = missing[start:start + WEATHER_BATCH_SIZE]
        resp = requests.get(
            OPEN_METEO_URL,
            params={
                "latitude": ",".join(str(points[i][0]) for i in batch),
                "longitude": ",".join(str(points[i][1]) for i in batch),
                "hourly": "windspeed_10m,rain,snowfall",
                "windspeed_unit": "mph",
                "precipitation_unit": "inch",
                "timezone": "UTC",
                "forecast_days": 16,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            data = [data]
        for i, payload in zip(batch, data):
            hours = payload["hourly"]["time"]
            wanted = _hour_key(times[i])
            index = {t: n for n, t in enumerate(hours)}
            if wanted in index:
                n = index[wanted]
            elif wanted > hours[-1]:
                n = len(hours) - 1
            else:
                n = 0
            weather = {
                "wind_mph": payload["hourly"]["windspeed_10m"][n] or 0,
                "rain_in_hr": payload["hourly"]["rain"][n] or 0,
                "snow_in_hr": payload["hourly"]["snowfall"][n] or 0,
            }
            cache_key = (round(points[i][0], 3), round(points[i][1], 3), wanted)
            _weather_cache[cache_key] = (time.time() + WEATHER_CACHE_TTL, weather)
            out[i] = weather
    return [out.get(i, {"wind_mph": 0, "rain_in_hr": 0, "snow_in_hr": 0}) for i in range(len(points))]
