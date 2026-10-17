from datetime import datetime, timezone
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


def fake_routes(origin, destination, count=3):
    return [
        {"distance_miles": 100.0, "duration_min": 120.0, "geometry": FAKE_GEOMETRY},
        {"distance_miles": 110.0, "duration_min": 150.0, "geometry": FAKE_GEOMETRY},
    ]


def fake_calm_weather(points, times):
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

    def test_missing_geometry_rejected(self):
        resp = self.client.post("/api/heatmap/", {"time": "2026-10-18T12:00:00Z"}, format="json")
        self.assertEqual(resp.status_code, 400)
