import unittest

from core.v1_weekly_engine import run_weekly_v1_engine


class TestConstraintDayMapping(unittest.TestCase):
    def test_unavailability_weekday_name_applies_with_j_days(self):
        days = [f"J{i}" for i in range(7)]
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
            },
            "solver": {"max_time_seconds": 10},
            "solver_max_time_seconds": 10,
            "solver_num_workers": 4,
        }

        result = run_weekly_v1_engine(
            employees=["Employee 1", "Employee 2"],
            contracts=[35, 35],
            roles=["opticien", "opticien"],
            constraints=[{"type": "unavailability", "employee": "Employee 1", "day": "monday"}],
            days=days,
            config=config,
            unavailabilities=[],
        )

        self.assertIn(result["status"], ("optimal", "feasible"))
        schedule = result.get("schedule") or {}
        employee_1_days = (schedule.get("Employee 1") or {}).get("days", {})
        self.assertNotIn("J0", employee_1_days)


if __name__ == "__main__":
    unittest.main()
