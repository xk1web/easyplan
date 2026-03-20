import io
import unittest
from contextlib import redirect_stdout

from core.v1_weekly_engine import run_weekly_v1_engine


class TestFeasibilityPrecheck(unittest.TestCase):
    def test_returns_clear_diagnostic_when_contract_is_mathematically_unreachable(self):
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
                "end_time_minutes": 18 * 60,
                "slot_minutes": 60,
                "min_staff_per_slot": 0,
            },
            "hard_constraints": {
                "rest_between_days_minutes": 660,
                "weekly_rest_minutes": 2100,
                "require_qualified_optician": True,
                "min_shift_minutes": 360,
            },
            "closed_weekdays": [5, 6],
            "solver_max_time_seconds": 10,
            "solver_num_workers": 4,
        }
        constraints = [{"type": "unavailability", "employee": "Solo", "day": "monday"}]

        with redirect_stdout(io.StringIO()):
            result = run_weekly_v1_engine(
                employees=["Solo"],
                contracts=[35],
                roles=["opticien"],
                constraints=constraints,
                days=days,
                config=config,
                unavailabilities=[],
            )

        self.assertEqual(result["status"], "infeasible")
        reasons = result.get("infeasibility_reasons") or []
        codes = {reason.get("code") for reason in reasons}
        self.assertIn("EMPLOYEE_CONTRACT_UNREACHABLE", codes)
        precheck = result.get("feasibility_precheck") or {}
        self.assertFalse(precheck.get("is_feasible", True))
        unreachable = precheck.get("unreachable_contracts") or []
        self.assertEqual(len(unreachable), 1)
        self.assertEqual(unreachable[0]["employee"], "Solo")
        self.assertLess(unreachable[0]["max_possible_effective_minutes"], unreachable[0]["contract_minutes"])


if __name__ == "__main__":
    unittest.main()
