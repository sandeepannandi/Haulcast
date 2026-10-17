LEVELS = ["low", "moderate", "high", "severe", "no_travel"]

RANK = {name: i for i, name in enumerate(LEVELS)}


def wind_level(mph):
    if mph < 25:
        return "low"
    if mph < 35:
        return "moderate"
    if mph < 45:
        return "high"
    if mph < 55:
        return "severe"
    return "no_travel"


def rain_level(in_per_hr):
    if in_per_hr < 0.10:
        return "low"
    if in_per_hr < 0.25:
        return "moderate"
    if in_per_hr < 0.50:
        return "high"
    if in_per_hr <= 1.00:
        return "severe"
    return "no_travel"


def snow_level(in_per_hr):
    if in_per_hr < 0.5:
        return "low"
    if in_per_hr < 1.0:
        return "moderate"
    if in_per_hr < 2.0:
        return "high"
    if in_per_hr <= 3.0:
        return "severe"
    return "no_travel"


def worst(*levels):
    return max(levels, key=lambda level: RANK[level])


def apply_load_rules(level, wind_mph, load_lbs):
    if wind_mph >= 55:
        return "no_travel"
    if wind_mph >= 45 and load_lbs > 30000:
        return "no_travel"
    if wind_mph >= 35 and load_lbs > 40000:
        return worst(level, "severe")
    return level


def classify_weather(weather, load_lbs):
    level = worst(
        wind_level(weather["wind_mph"]),
        rain_level(weather["rain_in_hr"]),
        snow_level(weather["snow_in_hr"]),
    )
    return apply_load_rules(level, weather["wind_mph"], load_lbs)


def summarize(levels, total_miles, duration_min):
    coverage = total_miles / max(len(levels), 1)
    miles = {level: 0.0 for level in LEVELS}
    for level in levels:
        miles[level] += coverage
    avg = sum(RANK[level] for level in levels) / max(len(levels), 1)
    worst_level = max(levels, key=lambda level: RANK[level]) if levels else "low"
    return {
        "miles_by_level": {name: round(value, 1) for name, value in miles.items()},
        "avg_risk": round(avg, 3),
        "worst": worst_level,
        "duration_min": round(duration_min, 1),
    }


def rank_key(summary):
    miles = summary["miles_by_level"]
    return (
        miles["no_travel"],
        miles["severe"],
        miles["high"],
        summary["avg_risk"],
        summary["duration_min"],
    )


def pick_best(summaries):
    return min(range(len(summaries)), key=lambda i: rank_key(summaries[i]))
