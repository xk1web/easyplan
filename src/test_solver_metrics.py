import unittest

from core.v1_weekly_engine import run_weekly_v1_engine


class TestSolverMetrics(unittest.TestCase):
    def test_model_size_metrics_present_and_positive(self):
        config = {
            "schedule": {
                "start_time_minutes": 9 * 60,
                "end_time_minutes": 14 * 60,
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
        }

        result = run_weekly_v1_engine(
            employees=["Opt1", "Opt2"],
            contracts=[20, 15],
            roles=["opticien", "opticien"],
            days=[f"J{i}" for i in range(7)],
            config=config,
            unavailabilities=[],
        )

        solver_metrics = result.get("solver_result", {}).get("metrics", {})
        self.assertGreater(solver_metrics.get("num_variables", 0), 0)
        self.assertGreater(solver_metrics.get("num_constraints", 0), 0)


if __name__ == "__main__":
    unittest.main()
