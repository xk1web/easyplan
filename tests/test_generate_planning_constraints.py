import unittest
from unittest.mock import patch

from main import PlanningRequest, generate_planning


class TestGeneratePlanningConstraints(unittest.TestCase):
    @patch("main.run_weekly_v1_engine")
    def test_generate_planning_forwards_constraints(self, mock_engine):
        mock_engine.return_value = {
            "status": "optimal",
            "schedule": {},
            "solver_time": 0.1,
            "solve_time_seconds": 0.1,
            "metrics": None,
            "kpi": {},
            "hours_per_employee": {},
            "explanation": {},
        }

        request = PlanningRequest(
            employees=["Employee 1"],
            contracts=[35],
            roles=["opticien"],
            days=["J0", "J1", "J2", "J3", "J4", "J5", "J6"],
            constraints=[{"type": "unavailability", "employee": "Employee 1", "day": "J0"}],
            unavailabilities=[],
            config={"schedule": {"start_time_minutes": 540, "end_time_minutes": 1080, "min_staff_per_slot": 1}},
        )

        _ = generate_planning(request)

        kwargs = mock_engine.call_args.kwargs
        self.assertEqual(
            kwargs["constraints"],
            [{"type": "unavailability", "employee": "Employee 1", "day": "J0"}],
        )


if __name__ == "__main__":
    unittest.main()
