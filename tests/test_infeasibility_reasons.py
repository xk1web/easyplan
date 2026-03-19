import io
import unittest
from contextlib import redirect_stdout

from core.v1_weekly_engine import run_weekly_v1_engine


class TestInfeasibilityReasons(unittest.TestCase):
    def test_engine_returns_structured_infeasibility_reasons(self):
        days = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        config = {
            "schedule": {
                "start_time_minutes": 9 * 60,
                "end_time_minutes": 17 * 60,
                "slot_minutes": 60,
                "min_staff_per_slot": 1,
            },
            "hard_constraints": {
                "rest_between_days_minutes": 660,
                "weekly_rest_minutes": 2100,
                "require_qualified_optician": True,
                "min_shift_minutes": 360,
            },
            "solver_max_time_seconds": 10,
            "solver_num_workers": 4,
        }

        # No optician remains available on Monday.
        constraints = [
            {"type": "unavailability", "employee": "A", "day": "monday"},
            {"type": "day_status", "employee": "B", "day": "monday", "status": "off"},
        ]

        with redirect_stdout(io.StringIO()):
            result = run_weekly_v1_engine(
                employees=["A", "B", "C"],
                contracts=[35, 35, 35],
                roles=["opticien", "opticien", "vendeur"],
                constraints=constraints,
                days=days,
                config=config,
                unavailabilities=[],
            )

        self.assertEqual(result["status"], "infeasible")
        self.assertTrue(result.get("error"))
        reasons = result.get("infeasibility_reasons") or []
        codes = {reason.get("code") for reason in reasons}
        self.assertIn("NO_OPTICIAN_AVAILABLE", codes)


if __name__ == "__main__":
    unittest.main()
