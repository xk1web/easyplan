import io
import unittest
from contextlib import redirect_stdout

from core.v1_weekly_engine import run_weekly_v1_engine


class TestFiveDaysOpenInfeasibility(unittest.TestCase):
    def _run(self, *, closed_weekdays, constraints):
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
                "min_staff_per_slot": 1,
            },
            "hard_constraints": {
                "rest_between_days_minutes": 660,
                "weekly_rest_minutes": 2100,
                "require_qualified_optician": True,
                "min_shift_minutes": 360,
            },
            "closed_weekdays": closed_weekdays,
            "solver_max_time_seconds": 10,
            "solver_num_workers": 8,
        }
        with redirect_stdout(io.StringIO()):
            return run_weekly_v1_engine(
                employees=["A", "B", "C", "D"],
                contracts=[35, 35, 35, 35],
                roles=["opticien", "opticien", "vendeur", "vendeur"],
                constraints=constraints,
                days=days,
                config=config,
                unavailabilities=[],
            )

    def test_same_team_contracts_switches_feasible_to_infeasible_when_open_days_drop(self):
        constraints = [{"type": "unavailability", "employee": "A", "day": "monday"}]

        # 6 days open (Sunday closed): still feasible.
        six_open = self._run(closed_weekdays=[6], constraints=constraints)
        self.assertIn(six_open["status"], ("optimal", "feasible"))

        # 5 days open (Saturday + Sunday closed): infeasible with strict contracts.
        five_open = self._run(closed_weekdays=[5, 6], constraints=constraints)
        self.assertEqual(five_open["status"], "infeasible")

    def test_five_days_open_without_unavailability_stays_feasible(self):
        result = self._run(closed_weekdays=[5, 6], constraints=[])
        self.assertIn(result["status"], ("optimal", "feasible"))

    def test_single_employee_can_work_all_five_open_days_without_forced_extra_off(self):
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

        with redirect_stdout(io.StringIO()):
            result = run_weekly_v1_engine(
                employees=["Solo"],
                contracts=[35],
                roles=["opticien"],
                constraints=[],
                days=days,
                config=config,
                unavailabilities=[],
            )

        self.assertIn(result["status"], ("optimal", "feasible"))
        worked_days = set(result["schedule"]["Solo"]["days"].keys())
        self.assertEqual(worked_days, {"monday", "tuesday", "wednesday", "thursday", "friday"})


if __name__ == "__main__":
    unittest.main()
