import io
import unittest
from contextlib import redirect_stdout

from core.v1_weekly_engine import run_weekly_v1_engine


class TestCpSatFeasibilityAudit(unittest.TestCase):
    DAYS = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]

    EMPLOYEES = ["A", "B", "C"]
    CONTRACTS = [35, 35, 35]
    ROLES = ["opticien", "opticien", "vendeur"]

    @staticmethod
    def _config(require_optician: bool = True) -> dict:
        return {
            "schedule": {
                "start_time_minutes": 9 * 60,
                "end_time_minutes": 17 * 60,
                "slot_minutes": 60,
                "min_staff_per_slot": 1,
            },
            "hard_constraints": {
                "rest_between_days_minutes": 660,
                "weekly_rest_minutes": 2100,
                "require_qualified_optician": require_optician,
                "min_shift_minutes": 360,
            },
            "solver_max_time_seconds": 10,
            "solver_num_workers": 8,
        }

    def _run(self, constraints, *, require_optician: bool = True):
        with redirect_stdout(io.StringIO()):
            return run_weekly_v1_engine(
                employees=self.EMPLOYEES,
                contracts=self.CONTRACTS,
                roles=self.ROLES,
                constraints=constraints,
                days=self.DAYS,
                config=self._config(require_optician=require_optician),
                unavailabilities=[],
            )

    def test_single_employee_unavailability_is_still_feasible_with_two_opticians(self):
        result = self._run(
            constraints=[{"type": "unavailability", "employee": "A", "day": "monday"}]
        )
        self.assertIn(result["status"], ("optimal", "feasible"))

    def test_infeasible_when_no_optician_left_on_monday(self):
        # A is unavailable Monday, B is fixed OFF Monday, C is not an optician:
        # with require_qualified_optician=True the model is infeasible.
        result = self._run(
            constraints=[
                {"type": "unavailability", "employee": "A", "day": "monday"},
                {"type": "day_status", "employee": "B", "day": "monday", "status": "off"},
            ]
        )
        self.assertEqual(result["status"], "infeasible")

    def test_same_case_becomes_feasible_if_optician_rule_is_disabled(self):
        result = self._run(
            constraints=[
                {"type": "unavailability", "employee": "A", "day": "monday"},
                {"type": "day_status", "employee": "B", "day": "monday", "status": "off"},
            ],
            require_optician=False,
        )
        self.assertIn(result["status"], ("optimal", "feasible"))


if __name__ == "__main__":
    unittest.main()
