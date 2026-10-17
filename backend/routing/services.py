import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_ROUTE_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

HEADERS = {"User-Agent": "haulcast/1.0"}

WEATHER_CACHE_TTL = 1800
WEATHER_BATCH_SIZE = 80

NWS_POINTS_URL = "https://api.weather.gov/points/{lat},{lon}"
NWS_HEADERS = {"User-Agent": "haulcast (github.com/sandeepannandi/haulcast)", "Accept": "application/geo+json"}

_geocode_cache = {}
_weather_cache = {}
_nws_url_cache = {}
_nws_grid_cache = {}


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


def _duration_hours(text):
    match = re.match(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?)?", text or "")
    if not match:
        return 1
    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    return days * 24 + hours or 1


def _series(raw, kind):
    out = {}
    if not raw:
        return out
    uom = raw.get("uom", "")
    for entry in raw.get("values", []):
        value = entry.get("value")
        if value is None:
            continue
        start_text, _, duration = entry["validTime"].partition("/")
        start = datetime.fromisoformat(start_text.replace("Z", "+00:00"))
        hours = _duration_hours(duration)
        per_hour = value / hours
        if kind == "wind":
            per_hour = per_hour * 0.621371 if "km_h" in uom else per_hour
        else:
            per_hour = per_hour / 25.4 if "mm" in uom else per_hour
        for h in range(hours):
            key = (start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:00")
            out[key] = per_hour
    return out


def _nws_series(lat, lon):
    cell = (round(lat, 2), round(lon, 2))
    url = _nws_url_cache.get(cell)
    if url is None:
        resp = requests.get(
            NWS_POINTS_URL.format(lat=round(lat, 4), lon=round(lon, 4)),
            headers=NWS_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        url = resp.json()["properties"]["forecastGridData"]
        _nws_url_cache[cell] = url
    entry = _nws_grid_cache.get(url)
    if entry and entry[0] > time.time():
        return entry[1]
    resp = requests.get(url, headers=NWS_HEADERS, timeout=20)
    resp.raise_for_status()
    props = resp.json()["properties"]
    series = {
        "wind": _series(props.get("windSpeed"), "wind"),
        "rain": _series(props.get("quantitativePrecipitation"), "precip"),
        "snow": _series(props.get("snowfallAmount"), "precip"),
    }
    _nws_grid_cache[url] = (time.time() + WEATHER_CACHE_TTL, series)
    return series


def _open_meteo_single(lat, lon, wanted):
    resp = requests.get(
        OPEN_METEO_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "hourly": "windspeed_10m,rain,snowfall",
            "windspeed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "UTC",
            "forecast_days": 16,
        },
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    hours = payload["hourly"]["time"]
    index = {t: n for n, t in enumerate(hours)}
    if wanted in index:
        n = index[wanted]
    elif wanted > hours[-1]:
        n = len(hours) - 1
    else:
        n = 0
    return {
        "wind_mph": payload["hourly"]["windspeed_10m"][n] or 0,
        "rain_in_hr": payload["hourly"]["rain"][n] or 0,
        "snow_in_hr": payload["hourly"]["snowfall"][n] or 0,
    }


def _nws_weather(lat, lon, wanted):
    series = _nws_series(lat, lon)

    def pick(name):
        values = series.get(name) or {}
        if wanted in values:
            return values[wanted]
        if not values:
            return 0.0
        keys = sorted(values)
        return values[keys[-1]] if wanted > keys[-1] else values[keys[0]]

    return {
        "wind_mph": round(pick("wind"), 1),
        "rain_in_hr": round(pick("rain"), 3),
        "snow_in_hr": round(pick("snow"), 3),
    }


def _fetch_one(point, wanted):
    hit = _cached_weather(point[0], point[1], wanted)
    if hit is not None:
        return hit
    try:
        weather = _nws_weather(point[0], point[1], wanted)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            weather = _open_meteo_single(point[0], point[1], wanted)
        else:
            raise
    cache_key = (round(point[0], 3), round(point[1], 3), wanted)
    _weather_cache[cache_key] = (time.time() + WEATHER_CACHE_TTL, weather)
    return weather


def weather_for(points, times):
    wanted = [_hour_key(moment) for moment in times]
    results = [None] * len(points)
    todo = []
    for i, (point, key) in enumerate(zip(points, wanted)):
        hit = _cached_weather(point[0], point[1], key)
        if hit is not None:
            results[i] = hit
        else:
            todo.append(i)
    if todo:
        with ThreadPoolExecutor(max_workers=6) as pool:
            fetched = pool.map(lambda i: (i, _fetch_one(points[i], wanted[i])), todo)
        for i, weather in fetched:
            results[i] = weather
    return [r if r is not None else {"wind_mph": 0, "rain_in_hr": 0, "snow_in_hr": 0} for r in results]
