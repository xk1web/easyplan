import unittest
from unittest.mock import patch

from main import SimulatePlanningRequest, simulate_planning


class TestSimulatePlanningEndpoint(unittest.TestCase):
    @patch("main.run_weekly_v1_engine")
    def test_simulate_planning_maps_global_opening_hours(self, mock_engine):
        mock_engine.return_value = {
            "schedule": {"Alice": {"days": {}, "total_hours": 0.0}},
            "kpi_summary": {"coverage_rate": 0.95},
            "explanation": {"summary": "ok"},
        }
        request = SimulatePlanningRequest(
            employees=["Alice"],
            contracts=[35],
            roles=["opticien"],
            opening_hours={"open": "09:30", "close": "18:30"},
            min_staff=1,
        )

        response = simulate_planning(request)

        self.assertEqual(response.kpi_summary, {"coverage_rate": 0.95})
        self.assertEqual(response.explanation, {"summary": "ok"})
        self.assertIsNotNone(response.schedule)
        kwargs = mock_engine.call_args.kwargs
        self.assertEqual(kwargs["days"], [f"J{i}" for i in range(7)])
        self.assertEqual(kwargs["config"]["schedule"]["start_time_minutes"], 570)
        self.assertEqual(kwargs["config"]["schedule"]["end_time_minutes"], 1110)
        self.assertEqual(kwargs["config"]["schedule"]["min_staff_per_slot"], 1)

    @patch("main.run_weekly_v1_engine")
    def test_simulate_planning_maps_day_based_min_staff(self, mock_engine):
        mock_engine.return_value = {
            "schedule": {"Bob": {"days": {}, "total_hours": 0.0}},
            "kpi_summary": {"coverage_rate": 1.0},
            "explanation": {"summary": "ok"},
        }
        request = SimulatePlanningRequest(
            employees=["Bob"],
            contracts=[35],
            roles=["opticien"],
            opening_hours={
                "LUN": {"open": "09:00", "close": "17:00"},
                "MAR": {"open": "09:00", "close": "17:00"},
                "MER": {"open": "09:00", "close": "17:00"},
                "JEU": {"open": "09:00", "close": "17:00"},
                "VEN": {"open": "09:00", "close": "17:00"},
                "SAM": {"open": "09:00", "close": "17:00"},
                "DIM": {"open": "09:00", "close": "17:00"},
            },
            min_staff={"LUN": 2, "MAR": 2, "MER": 1, "JEU": 1, "VEN": 2, "SAM": 2, "DIM": 1},
        )

        response = simulate_planning(request)

        self.assertEqual(response.kpi_summary, {"coverage_rate": 1.0})
        kwargs = mock_engine.call_args.kwargs
        self.assertEqual(kwargs["days"], ["LUN", "MAR", "MER", "JEU", "VEN", "SAM", "DIM"])
        self.assertEqual(kwargs["config"]["schedule"]["start_time_minutes"], 540)
        self.assertEqual(kwargs["config"]["schedule"]["end_time_minutes"], 1020)
        self.assertEqual(kwargs["config"]["schedule"]["min_staff_per_day"], [2, 2, 1, 1, 2, 2, 1])


if __name__ == "__main__":
    unittest.main()
