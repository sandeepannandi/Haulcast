from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIClient

from . import geo, risk


class WindBandsTest(SimpleTestCase):
    def test_boundaries(self):
        self.assertEqual(risk.wind_level(10), "low")
        self.assertEqual(risk.wind_level(24.9), "low")
        self.assertEqual(risk.wind_level(25), "moderate")
        self.assertEqual(risk.wind_level(34.9), "moderate")
        self.assertEqual(risk.wind_level(35), "high")
        self.assertEqual(risk.wind_level(44.9), "high")
        self.assertEqual(risk.wind_level(45), "severe")
        self.assertEqual(risk.wind_level(54.9), "severe")
        self.assertEqual(risk.wind_level(55), "no_travel")
        self.assertEqual(risk.wind_level(80), "no_travel")


class RainBandsTest(SimpleTestCase):
    def test_boundaries(self):
        self.assertEqual(risk.rain_level(0.05), "low")
        self.assertEqual(risk.rain_level(0.10), "moderate")
        self.assertEqual(risk.rain_level(0.24), "moderate")
        self.assertEqual(risk.rain_level(0.25), "high")
        self.assertEqual(risk.rain_level(0.49), "high")
        self.assertEqual(risk.rain_level(0.50), "severe")
        self.assertEqual(risk.rain_level(1.00), "severe")
        self.assertEqual(risk.rain_level(1.01), "no_travel")


class SnowBandsTest(SimpleTestCase):
    def test_boundaries(self):
        self.assertEqual(risk.snow_level(0.2), "low")
        self.assertEqual(risk.snow_level(0.5), "moderate")
        self.assertEqual(risk.snow_level(0.9), "moderate")
        self.assertEqual(risk.snow_level(1.0), "high")
        self.assertEqual(risk.snow_level(1.9), "high")
        self.assertEqual(risk.snow_level(2.0), "severe")
        self.assertEqual(risk.snow_level(3.0), "severe")
        self.assertEqual(risk.snow_level(3.1), "no_travel")


class LoadRulesTest(SimpleTestCase):
    def test_no_travel_wind_beats_everything(self):
        self.assertEqual(risk.apply_load_rules("low", 56, 5000), "no_travel")

    def test_heavy_load_in_severe_wind(self):
        self.assertEqual(risk.apply_load_rules("severe", 50, 30001), "no_travel")
        self.assertEqual(risk.apply_load_rules("severe", 50, 30000), "severe")

    def test_very_heavy_load_in_high_wind(self):
        self.assertEqual(risk.apply_load_rules("low", 40, 40001), "severe")
        self.assertEqual(risk.apply_load_rules("high", 40, 40000), "high")

    def test_light_load_untouched(self):
        self.assertEqual(risk.apply_load_rules("moderate", 40, 10000), "moderate")


class ClassifyTest(SimpleTestCase):
    def test_worst_condition_wins(self):
        weather = {"wind_mph": 10, "rain_in_hr": 0.6, "snow_in_hr": 0.0}
        self.assertEqual(risk.classify_weather(weather, 10000), "severe")

    def test_load_rule_applies_after_conditions(self):
        weather = {"wind_mph": 50, "rain_in_hr": 0.0, "snow_in_hr": 0.0}
        self.assertEqual(risk.classify_weather(weather, 35000), "no_travel")
        self.assertEqual(risk.classify_weather(weather, 20000), "severe")


class GeometryTest(SimpleTestCase):
    def test_known_distance(self):
        miles = geo.haversine_miles((40.7128, -74.0060), (42.3601, -71.0589))
        self.assertAlmostEqual(miles, 190, delta=10)

    def test_sampling_spacing_and_endpoints(self):
        coords = [[40.0 + i * 0.0145, -75.0] for i in range(100)]
        points, total = geo.sample_points(coords, 10)
        self.assertEqual(points[0]["mile"], 0.0)
        gaps = [points[i + 1]["mile"] - points[i]["mile"] for i in range(len(points) - 2)]
        for gap in gaps:
            self.assertAlmostEqual(gap, 10, places=3)
        self.assertEqual(points[-1]["lat"], coords[-1][0])
        self.assertAlmostEqual(total, geo.haversine_miles(coords[0], coords[-1]), delta=1)


def make_summary(no_travel=0.0, severe=0.0, high=0.0, avg=1.0, duration=100.0):
    return {
        "miles_by_level": {
            "no_travel": no_travel,
            "severe": severe,
            "high": high,
            "moderate": 0.0,
            "low": 50.0,
        },
        "avg_risk": avg,
        "worst": "low",
        "duration_min": duration,
    }


class RecommendationTest(SimpleTestCase):
    def test_fewest_severe_miles_wins_over_time(self):
        routes = [make_summary(severe=20, duration=90), make_summary(severe=5, duration=300)]
        self.assertEqual(risk.pick_best(routes), 1)

    def test_fewer_high_miles_breaks_severe_tie(self):
        routes = [make_summary(severe=5, high=40), make_summary(severe=5, high=10)]
        self.assertEqual(risk.pick_best(routes), 1)

    def test_avg_risk_breaks_tie_then_duration(self):
        routes = [
            make_summary(severe=5, high=10, avg=2.0, duration=100),
            make_summary(severe=5, high=10, avg=1.5, duration=400),
            make_summary(severe=5, high=10, avg=1.5, duration=200),
        ]
        self.assertEqual(risk.pick_best(routes), 2)

    def test_no_travel_route_is_always_last(self):
        routes = [make_summary(no_travel=1, severe=0), make_summary(severe=80, avg=3.9)]
        self.assertEqual(risk.pick_best(routes), 1)


FAKE_GEOMETRY = [[40.0 + i * 0.05, -75.0] for i in range(40)]


class PaceMathTest(SimpleTestCase):
    def test_cumulative_miles_grows(self):
        marks = geo.cumulative_miles(FAKE_GEOMETRY)
        self.assertEqual(marks[0], 0.0)
        self.assertEqual(len(marks), len(FAKE_GEOMETRY))
        self.assertTrue(all(b > a for a, b in zip(marks, marks[1:])))

    def test_pace_interpolates_between_marks(self):
        marks = [0.0, 10.0, 20.0]
        pace = [0.0, 30.0, 40.0]
        self.assertEqual(geo.pace_minutes(0, marks, pace, 40.0), 0.0)
        self.assertEqual(geo.pace_minutes(5, marks, pace, 40.0), 15.0)
        self.assertEqual(geo.pace_minutes(15, marks, pace, 40.0), 35.0)
        self.assertEqual(geo.pace_minutes(20, marks, pace, 40.0), 40.0)

    def test_pace_falls_back_to_even_spread(self):
        marks = [0.0, 10.0, 20.0]
        self.assertEqual(geo.pace_minutes(10, marks, None, 40.0), 20.0)
        self.assertEqual(geo.pace_minutes(10, marks, [0.0], 40.0), 20.0)
        self.assertEqual(geo.pace_minutes(10, [], None, 40.0), 0.0)


def fake_routes(origin, destination, count=3):
    return [
        {"distance_miles": 100.0, "duration_min": 120.0, "geometry": FAKE_GEOMETRY},
        {"distance_miles": 110.0, "duration_min": 150.0, "geometry": FAKE_GEOMETRY},
    ]


def fake_paced_routes(origin, destination, count=3):
    pace = [float(i * i) for i in range(len(FAKE_GEOMETRY))]
    return [{"distance_miles": 100.0, "duration_min": 120.0, "geometry": FAKE_GEOMETRY, "pace": pace}]


def fake_calm_weather(points, times, workers=16):
    return [{"wind_mph": 10, "rain_in_hr": 0.0, "snow_in_hr": 0.0} for _ in points]


class PlanViewTest(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()

    def post(self, **overrides):
        payload = {
            "origin": "New York, NY",
            "destination": "Boston, MA",
            "departure": "2026-10-18T08:00:00Z",
            "load_weight": 20000,
            "interval": 25,
        }
        payload.update(overrides)
        return self.client.post("/api/plan/", payload, format="json")

    def fake_geocode(self, place):
        return {"lat": 40.7, "lon": -74.0, "label": place}

    @patch("routing.views.services.weather_for", side_effect=fake_calm_weather)
    @patch("routing.views.services.get_routes", side_effect=fake_routes)
    @patch("routing.views.services.geocode")
    def test_happy_path(self, mock_geocode, mock_routes, mock_weather):
        mock_geocode.side_effect = self.fake_geocode
        resp = self.post()
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["routes"]), 2)
        first, second = data["routes"]
        self.assertTrue(first["recommended"])
        self.assertFalse(second["recommended"])
        self.assertGreater(len(first["checkpoints"]), 2)
        etas = [c["eta"] for c in first["checkpoints"]]
        self.assertEqual(etas, sorted(etas))
        self.assertTrue(all(c["level"] == "low" for c in first["checkpoints"]))
        self.assertEqual(first["summary"]["worst"], "low")

    @patch("routing.views.services.weather_for", side_effect=fake_calm_weather)
    @patch("routing.views.services.get_routes", side_effect=fake_paced_routes)
    @patch("routing.views.services.geocode")
    def test_etas_follow_segment_pace(self, mock_geocode, mock_routes, mock_weather):
        mock_geocode.side_effect = self.fake_geocode
        resp = self.post()
        self.assertEqual(resp.status_code, 200)
        checkpoints = resp.json()["routes"][0]["checkpoints"]
        self.assertEqual(checkpoints[0]["eta"], "2026-10-18T08:00:00+00:00")
        last = datetime.fromisoformat(checkpoints[-1]["eta"])
        departure = datetime(2026, 10, 18, 8, 0, tzinfo=timezone.utc)
        even_spread = departure + timedelta(minutes=120)
        self.assertGreater(last, even_spread + timedelta(hours=12))
        paced = (last - departure).total_seconds() / 60
        self.assertAlmostEqual(paced, 39 * 39, delta=2)
        etas = [c["eta"] for c in checkpoints]
        self.assertEqual(etas, sorted(etas))

    @patch("routing.views.services.weather_for")
    @patch("routing.views.services.get_routes", side_effect=fake_routes)
    @patch("routing.views.services.geocode")
    def test_stormy_route_loses_recommendation(self, mock_geocode, mock_routes, mock_weather):
        mock_geocode.side_effect = self.fake_geocode
        storm = [{"wind_mph": 50, "rain_in_hr": 0.0, "snow_in_hr": 0.0} for _ in range(50)]
        calm = [{"wind_mph": 10, "rain_in_hr": 0.0, "snow_in_hr": 0.0} for _ in range(50)]
        mock_weather.side_effect = [storm, calm]
        resp = self.post()
        data = resp.json()
        self.assertFalse(data["routes"][0]["recommended"])
        self.assertTrue(data["routes"][1]["recommended"])
        self.assertEqual(data["routes"][0]["summary"]["worst"], "severe")

    @patch("routing.views.services.weather_for")
    @patch("routing.views.services.get_routes", side_effect=fake_routes)
    @patch("routing.views.services.geocode")
    def test_weather_outage_returns_502(self, mock_geocode, mock_routes, mock_weather):
        import requests as real_requests

        mock_geocode.side_effect = self.fake_geocode
        mock_weather.side_effect = real_requests.ConnectionError("down")
        resp = self.post()
        self.assertEqual(resp.status_code, 502)
        self.assertIn("weather lookup failed", resp.json()["detail"])

    def test_invalid_interval_rejected(self):
        resp = self.post(interval=12)
        self.assertEqual(resp.status_code, 400)

    def test_missing_fields_rejected(self):
        resp = self.client.post("/api/plan/", {"origin": "Boston"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_negative_load_rejected(self):
        resp = self.post(load_weight=-5)
        self.assertEqual(resp.status_code, 400)


class HeatmapViewTest(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("routing.views.services.weather_for", side_effect=fake_calm_weather)
    def test_cells_cover_corridor(self, mock_weather):
        resp = self.client.post("/api/heatmap/", {
            "geometry": FAKE_GEOMETRY,
            "time": "2026-10-18T12:00:00Z",
            "load_weight": 20000,
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        cells = resp.json()["cells"]
        self.assertGreater(len(cells), 10)
        self.assertTrue(all(c["level"] == "low" for c in cells))
        self.assertTrue(all(c["intensity"] == 0.0 for c in cells))

    @patch("routing.views.services.weather_for", side_effect=fake_calm_weather)
    def test_coarse_detail_returns_fewer_cells(self, mock_weather):
        body = {"geometry": FAKE_GEOMETRY, "time": "2026-10-18T12:00:00Z", "load_weight": 20000}
        full = self.client.post("/api/heatmap/", body, format="json").json()["cells"]
        coarse = self.client.post("/api/heatmap/", {**body, "detail": "coarse"}, format="json").json()["cells"]
        self.assertGreater(len(coarse), 0)
        self.assertLess(len(coarse), len(full))

    def test_missing_geometry_rejected(self):
        resp = self.client.post("/api/heatmap/", {"time": "2026-10-18T12:00:00Z"}, format="json")
        self.assertEqual(resp.status_code, 400)


POINTS_RESPONSE = {"properties": {"forecastGridData": "https://api.weather.gov/gridpoints/LOT/76,73"}}

GRID_RESPONSE = {
    "properties": {
        "windSpeed": {
            "uom": "wmoUnit:km_h-1",
            "values": [
                {"validTime": "2026-10-18T08:00:00+00:00/PT1H", "value": 40.0},
                {"validTime": "2026-10-18T09:00:00+00:00/PT1H", "value": 80.0},
            ],
        },
        "quantitativePrecipitation": {
            "uom": "wmoUnit:mm",
            "values": [
                {"validTime": "2026-10-18T06:00:00+00:00/PT6H", "value": 12.7},
            ],
        },
        "snowfallAmount": {
            "uom": "wmoUnit:mm",
            "values": [
                {"validTime": "2026-10-18T08:00:00+00:00/PT2H", "value": 25.4},
            ],
        },
    }
}


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests as real_requests

            raise real_requests.HTTPError(str(self.status_code), response=self)

    def json(self):
        return self.payload


class NwsWeatherTest(SimpleTestCase):
    def setUp(self):
        from routing import services

        services._weather_cache.clear()
        services._nws_url_cache.clear()
        services._nws_grid_cache.clear()
        self.services = services

    def test_nws_values_converted_and_spread(self):
        calls = []

        def fake_get(url, **kwargs):
            calls.append(url)
            if "/points/" in url:
                return FakeResponse(POINTS_RESPONSE)
            return FakeResponse(GRID_RESPONSE)

        with patch("routing.services.requests.get", side_effect=fake_get):
            out = self.services.weather_for(
                [(41.88, -87.63)],
                [datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc)],
            )
        weather = out[0]
        self.assertAlmostEqual(weather["wind_mph"], 80.0 * 0.621371, places=1)
        self.assertAlmostEqual(weather["rain_in_hr"], round((12.7 / 6) / 25.4, 3), places=3)
        self.assertAlmostEqual(weather["snow_in_hr"], round((25.4 / 2) / 25.4, 3), places=3)

    def test_grids_cached_across_points(self):
        def fake_get(url, **kwargs):
            if "/points/" in url:
                return FakeResponse(POINTS_RESPONSE)
            return FakeResponse(GRID_RESPONSE)

        points = [(41.881, -87.631), (41.882, -87.632), (41.883, -87.633)]
        times = [datetime(2026, 10, 18, 8, 0, tzinfo=timezone.utc)] * 3
        with patch("routing.services.requests.get", side_effect=fake_get) as mock_get:
            self.services.weather_for(points, times)
        self.assertEqual(mock_get.call_count, 2)

    def test_outside_us_falls_back_to_open_meteo(self):
        def fake_get(url, **kwargs):
            if "api.weather.gov" in url:
                return FakeResponse({}, status=404)
            return FakeResponse({
                "hourly": {
                    "time": ["2026-10-18T08:00"],
                    "windspeed_10m": [12.0],
                    "rain": [0.2],
                    "snowfall": [0.0],
                }
            })

        with patch("routing.services.requests.get", side_effect=fake_get):
            out = self.services.weather_for(
                [(51.5, -0.12)],
                [datetime(2026, 10, 18, 8, 0, tzinfo=timezone.utc)],
            )
        self.assertEqual(out[0], {"wind_mph": 12.0, "rain_in_hr": 0.2, "snow_in_hr": 0.0})


class RoutePaceTest(SimpleTestCase):
    def osrm_payload(self, annotation=None):
        leg = {"distance": 1609.344, "duration": 180.0}
        if annotation is not None:
            leg["annotation"] = annotation
        route = {
            "distance": 1609.344,
            "duration": 180.0,
            "geometry": {"coordinates": [[-75.0, 40.0], [-75.01, 40.0], [-75.02, 40.0]]},
            "legs": [leg],
        }
        return {"code": "Ok", "routes": [route]}

    def fetch(self, payload):
        with patch("routing.services.requests.get", return_value=FakeResponse(payload)):
            from routing import services

            return services.get_routes({"lat": 40.0, "lon": -75.0}, {"lat": 40.1, "lon": -75.0})

    def test_pace_built_from_annotation(self):
        routes = self.fetch(self.osrm_payload({"duration": [120.0, 60.0]}))
        self.assertEqual(routes[0]["pace"], [0.0, 2.0, 3.0])

    def test_pace_none_without_legs(self):
        payload = self.osrm_payload({"duration": [120.0, 60.0]})
        payload["routes"][0]["legs"] = []
        self.assertIsNone(self.fetch(payload)[0]["pace"])

    def test_pace_none_without_annotation(self):
        self.assertIsNone(self.fetch(self.osrm_payload())[0]["pace"])

    def test_pace_none_on_length_mismatch(self):
        routes = self.fetch(self.osrm_payload({"duration": [120.0]}))
        self.assertIsNone(routes[0]["pace"])


class DurationParseTest(SimpleTestCase):
    def test_durations(self):
        from routing import services

        self.assertEqual(services._duration_hours("PT1H"), 1)
        self.assertEqual(services._duration_hours("PT6H"), 6)
        self.assertEqual(services._duration_hours("P1D"), 24)
        self.assertEqual(services._duration_hours(""), 1)
