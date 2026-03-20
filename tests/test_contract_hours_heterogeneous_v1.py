import io
import unittest
from contextlib import redirect_stdout

from core.v1_weekly_engine import run_weekly_v1_engine


DAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def _base_config(*, closed_weekdays):
    return {
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
        "closed_weekdays": closed_weekdays,
        "solver_max_time_seconds": 10,
        "solver_num_workers": 8,
    }


class TestContractHoursHeterogeneousV1(unittest.TestCase):
    def _run(self, *, contracts, closed_weekdays, constraints=None):
        with redirect_stdout(io.StringIO()):
            return run_weekly_v1_engine(
                employees=[f"E{i + 1}" for i in range(len(contracts))],
                contracts=contracts,
                roles=["opticien"] + ["vendeur"] * (len(contracts) - 1),
                constraints=constraints or [],
                days=DAYS,
                config=_base_config(closed_weekdays=closed_weekdays),
                unavailabilities=[],
            )

    def test_mixed_team_25_35_39_is_feasible(self):
        result = self._run(
            contracts=[25, 35, 39],
            closed_weekdays=[6],  # 6 jours ouverts
        )

        self.assertIn(result["status"], ("optimal", "feasible"))
        self.assertIsNotNone(result.get("schedule"))
        hours = result.get("hours_per_employee") or {}
        self.assertAlmostEqual(hours.get("E1", 0.0), 25.0, places=6)
        self.assertAlmostEqual(hours.get("E2", 0.0), 35.0, places=6)
        self.assertAlmostEqual(hours.get("E3", 0.0), 39.0, places=6)

    def test_39h_is_feasible_with_five_open_days(self):
        result = self._run(
            contracts=[39],
            closed_weekdays=[5, 6],  # 5 jours ouverts
        )

        self.assertIn(result["status"], ("optimal", "feasible"))
        self.assertAlmostEqual(result["hours_per_employee"]["E1"], 39.0, places=6)

    def test_39h_is_feasible_with_six_open_days(self):
        result = self._run(
            contracts=[39],
            closed_weekdays=[6],  # 6 jours ouverts
        )

        self.assertIn(result["status"], ("optimal", "feasible"))
        self.assertAlmostEqual(result["hours_per_employee"]["E1"], 39.0, places=6)

    def test_39h_is_unreachable_with_unavailability_and_five_open_days(self):
        result = self._run(
            contracts=[39],
            closed_weekdays=[5, 6],  # 5 jours ouverts
            constraints=[{"type": "unavailability", "employee": "E1", "day": "monday"}],
        )

        self.assertEqual(result["status"], "infeasible")
        precheck = result.get("feasibility_precheck") or {}
        self.assertFalse(precheck.get("is_feasible", True))
        unreachable = precheck.get("unreachable_contracts") or []
        self.assertEqual(len(unreachable), 1)
        self.assertEqual(unreachable[0]["employee"], "E1")
        self.assertEqual(unreachable[0]["contract_minutes"], 39 * 60)
        self.assertLess(unreachable[0]["max_possible_effective_minutes"], 39 * 60)


if __name__ == "__main__":
    unittest.main()
