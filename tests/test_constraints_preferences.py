import unittest

from core.v1_weekly_engine import run_weekly_v1_engine


class TestConstraintsPreferences(unittest.TestCase):
    def test_unavailability_constraint_is_applied_and_explained(self):
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
                "max_daily_minutes": 600,
                "rest_between_days_minutes": 660,
                "weekly_rest_minutes": 2100,
                "max_days_per_week": 6,
                "require_qualified_optician": True,
            },
            "solver": {"max_time_seconds": 10},
            "solver_max_time_seconds": 10,
            "solver_num_workers": 4,
        }

        result = run_weekly_v1_engine(
            employees=["Marie", "Paul"],
            contracts=[35, 35],
            roles=["opticien", "opticien"],
            constraints=[{"type": "unavailability", "employee": "Marie", "day": "tuesday"}],
            days=days,
            config=config,
            unavailabilities=[],
        )

        self.assertIn(result["status"], ("optimal", "feasible"))

        schedule = result.get("schedule") or {}
        marie_days = (schedule.get("Marie") or {}).get("days", {})
        paul_days = (schedule.get("Paul") or {}).get("days", {})

        # 1) Marie has no shift on Tuesday.
        self.assertNotIn("tuesday", marie_days)

        # 2) Paul can still be planned.
        self.assertGreater(len(paul_days), 0)

        # 3) Explanation contains the structured constraint.
        constraints = (result.get("explanation") or {}).get("constraints", [])
        self.assertIn("Marie indisponible mardi", constraints)

    def test_day_scoped_preferences_are_explained(self):
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
                "max_daily_minutes": 600,
                "rest_between_days_minutes": 660,
                "weekly_rest_minutes": 2100,
                "max_days_per_week": 6,
                "require_qualified_optician": True,
            },
            "solver": {"max_time_seconds": 10},
            "solver_max_time_seconds": 10,
            "solver_num_workers": 4,
        }

        result = run_weekly_v1_engine(
            employees=["Marie", "Paul"],
            contracts=[35, 35],
            roles=["opticien", "opticien"],
            constraints=[
                {"type": "prefer_morning", "employee": "Marie", "day": "tuesday"},
                {"type": "avoid_closing", "employee": "Paul", "day": "friday"},
            ],
            days=days,
            config=config,
            unavailabilities=[],
        )

        self.assertIn(result["status"], ("optimal", "feasible"))
        constraint_messages = (result.get("explanation") or {}).get("constraints", [])
        self.assertIn("Marie prefere les matinees le mardi", constraint_messages)
        self.assertIn("Paul evite la fermeture le vendredi", constraint_messages)


if __name__ == "__main__":
    unittest.main()
