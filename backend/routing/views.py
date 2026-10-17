from datetime import datetime, timedelta, timezone

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import geo, risk, services

VALID_INTERVALS = (10, 25, 50)


def parse_moment(raw):
    moment = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def parse_inputs(data):
    origin = str(data["origin"]).strip()
    destination = str(data["destination"]).strip()
    departure = parse_moment(data["departure"])
    load_lbs = float(data["load_weight"])
    interval = int(data.get("interval", 25))
    if not origin or not destination:
        raise ValueError("origin and destination are required")
    if interval not in VALID_INTERVALS:
        raise ValueError("interval must be 10, 25 or 50")
    if load_lbs < 0:
        raise ValueError("load weight cannot be negative")
    return origin, destination, departure, load_lbs, interval


@api_view(["POST"])
def plan(request):
    try:
        origin_name, destination_name, departure, load_lbs, interval = parse_inputs(request.data)
    except (KeyError, TypeError, ValueError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    try:
        origin = services.geocode(origin_name)
        destination = services.geocode(destination_name)
        raw_routes = services.get_routes(origin, destination)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except services.requests.RequestException as exc:
        return Response({"detail": "a map or weather service is unreachable, try again"}, status=status.HTTP_502_BAD_GATEWAY)

    routes = []
    for raw in raw_routes:
        checkpoints, total_miles = geo.sample_points(raw["geometry"], interval)
        duration = raw["duration_min"]
        etas = []
        for point in checkpoints:
            frac = point["mile"] / total_miles if total_miles else 0
            etas.append(departure + timedelta(minutes=duration * frac))
        try:
            weather = services.weather_for([[p["lat"], p["lon"]] for p in checkpoints], etas)
        except services.requests.RequestException as exc:
            return Response({"detail": "weather lookup failed: " + str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        levels = [risk.classify_weather(w, load_lbs) for w in weather]
        rows = []
        for point, eta, w, level in zip(checkpoints, etas, weather, levels):
            rows.append({
                "lat": point["lat"],
                "lon": point["lon"],
                "mile": point["mile"],
                "eta": eta.isoformat(),
                "wind_mph": w["wind_mph"],
                "rain_in_hr": w["rain_in_hr"],
                "snow_in_hr": w["snow_in_hr"],
                "level": level,
            })
        routes.append({
            "distance_miles": round(total_miles, 1),
            "duration_min": round(duration, 1),
            "geometry": raw["geometry"],
            "checkpoints": rows,
            "summary": risk.summarize(levels, total_miles, duration),
        })

    best = risk.pick_best([route["summary"] for route in routes])
    for i, route in enumerate(routes):
        route["recommended"] = i == best
    return Response({
        "origin": origin,
        "destination": destination,
        "departure": departure.isoformat(),
        "load_lbs": load_lbs,
        "interval": interval,
        "routes": routes,
    })


@api_view(["POST"])
def heatmap(request):
    geometry = request.data.get("geometry") or []
    try:
        moment = parse_moment(request.data.get("time"))
    except (TypeError, ValueError):
        return Response({"detail": "a valid time is required"}, status=status.HTTP_400_BAD_REQUEST)
    if len(geometry) < 2:
        return Response({"detail": "geometry is required"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        load_lbs = float(request.data.get("load_weight", 0))
        coords = [[float(p[0]), float(p[1])] for p in geometry]
    except (TypeError, ValueError, IndexError):
        return Response({"detail": "geometry must be a list of [lat, lon] pairs"}, status=status.HTTP_400_BAD_REQUEST)

    along, _ = geo.sample_points(coords, 12, max_points=16)
    spread = 0.09
    grid = []
    for point in along:
        for dlat, dlon in ((0, 0), (spread, 0), (-spread, 0), (0, spread), (0, -spread)):
            grid.append((round(point["lat"] + dlat, 4), round(point["lon"] + dlon, 4)))
    try:
        weather = services.weather_for(grid, [moment] * len(grid))
    except services.requests.RequestException as exc:
        return Response({"detail": "weather lookup failed: " + str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
    cells = []
    for (lat, lon), w in zip(grid, weather):
        level = risk.classify_weather(w, load_lbs)
        cells.append({
            "lat": lat,
            "lon": lon,
            "level": level,
            "intensity": round(risk.RANK[level] / (len(risk.LEVELS) - 1), 3),
        })
    return Response({"time": moment.isoformat(), "cells": cells})
