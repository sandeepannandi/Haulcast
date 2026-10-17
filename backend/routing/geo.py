import math

EARTH_RADIUS_MILES = 3958.7613


def haversine_miles(a, b):
    lat1, lon1 = a
    lat2, lon2 = b
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(h))


def sample_points(coords, spacing_miles, max_points=200):
    if len(coords) < 2:
        return [{"lat": c[0], "lon": c[1], "mile": 0.0} for c in coords], 0.0
    points = [{"lat": coords[0][0], "lon": coords[0][1], "mile": 0.0}]
    mile = 0.0
    next_mark = spacing_miles
    for prev, cur in zip(coords, coords[1:]):
        seg = haversine_miles(prev, cur)
        if seg == 0:
            continue
        while mile + seg >= next_mark:
            frac = (next_mark - mile) / seg
            lat = prev[0] + (cur[0] - prev[0]) * frac
            lon = prev[1] + (cur[1] - prev[1]) * frac
            points.append({"lat": round(lat, 5), "lon": round(lon, 5), "mile": next_mark})
            next_mark += spacing_miles
        mile += seg
    total = mile
    points.append({"lat": coords[-1][0], "lon": coords[-1][1], "mile": round(total, 1)})
    if len(points) > max_points:
        step = len(points) / max_points
        points = [points[int(i * step)] for i in range(max_points - 1)] + [points[-1]]
    return points, total


def cumulative_miles(coords):
    marks = [0.0]
    for prev, cur in zip(coords, coords[1:]):
        marks.append(marks[-1] + haversine_miles(prev, cur))
    return marks


def pace_minutes(mile, marks, pace, total_minutes):
    if not marks or not pace or len(pace) != len(marks) or marks[-1] <= 0:
        frac = mile / marks[-1] if marks and marks[-1] else 0.0
        return total_minutes * frac
    if mile <= 0:
        return 0.0
    if mile >= marks[-1]:
        return pace[-1]
    lo, hi = 0, len(marks) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if marks[mid] <= mile:
            lo = mid
        else:
            hi = mid
    span = marks[hi] - marks[lo]
    frac = (mile - marks[lo]) / span if span else 0.0
    return pace[lo] + (pace[hi] - pace[lo]) * frac
