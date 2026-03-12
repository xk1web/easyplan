import unittest

from core.v1_weekly_engine import run_weekly_v1_engine


def _days7():
    return [f"J{i}" for i in range(7)]


def _base_config(start=9 * 60, end=14 * 60, min_staff=1):
    return {
        "schedule": {
            "start_time_minutes": start,
            "end_time_minutes": end,
            "slot_minutes": 60,
            "min_staff_per_slot": min_staff,
        },
        "hard_constraints": {
            "max_daily_minutes": 600,
            "rest_between_days_minutes": 660,
            "weekly_rest_minutes": 2100,
            "max_days_per_week": 6,
            "require_qualified_optician": True,
        },
        "closed_weekdays": [],
        "solver": {"max_time_seconds": 10},
        "solver_max_time_seconds": 10,
        "solver_num_workers": 4,
    }


class TestV1WeeklyRegression(unittest.TestCase):
    def test_case_a_two_opticians_min_staff_1_is_feasible(self):
        result = run_weekly_v1_engine(
            employees=["Opt1", "Opt2"],
            contracts=[20, 15],
            roles=["opticien", "opticien"],
            days=_days7(),
            config=_base_config(),
            unavailabilities=[],
        )

        self.assertIn(result["metrics"]["solver_status"], ("FEASIBLE", "OPTIMAL"))
        self.assertIn(result["status"], ("feasible", "optimal"))
        self.assertIsNotNone(result["schedule"])

    def test_case_b_one_optician_min_staff_1_is_infeasible(self):
        result = run_weekly_v1_engine(
            employees=["Opt1"],
            contracts=[35],
            roles=["opticien"],
            days=_days7(),
            config=_base_config(),
            unavailabilities=[],
        )

        self.assertEqual(result["metrics"]["solver_status"], "INFEASIBLE")
        self.assertEqual(result["status"], "infeasible")

    def test_case_c_structural_overstaffing(self):
        result = run_weekly_v1_engine(
            employees=["Opt1", "Opt2"],
            contracts=[24, 24],
            roles=["opticien", "opticien"],
            days=_days7(),
            config=_base_config(start=9 * 60, end=15 * 60, min_staff=1),
            unavailabilities=[],
        )

        # With shift templates (>=6h), structural overstaffing can occur
        # because the solver must assign full shifts.
        # This scenario should remain FEASIBLE even if staffing exceeds
        # the minimum coverage.
        self.assertIn(result["status"], ("optimal", "feasible"))
        self.assertGreater(result["kpi"]["surstaffing_net"], 0.0)

    def test_case_d_structural_undercoverage(self):
        result = run_weekly_v1_engine(
            employees=["Opt1", "Opt2"],
            contracts=[14, 14],
            roles=["opticien", "opticien"],
            days=_days7(),
            config=_base_config(start=9 * 60, end=15 * 60, min_staff=1),
            unavailabilities=[],
        )

        self.assertEqual(result["metrics"]["solver_status"], "INFEASIBLE")
        self.assertEqual(result["status"], "infeasible")
        self.assertGreater(result["kpi"]["sous_couverture_nette"], 0.0)

    def test_hidden_break_deducted_from_worked_hours_only(self):
        config = _base_config(start=9 * 60, end=17 * 60, min_staff=0)

        result = run_weekly_v1_engine(
            employees=["Opt1"],
            contracts=[35],
            roles=["opticien"],
            days=_days7(),
            config=config,
            unavailabilities=[],
        )

        self.assertIn(result["status"], ("optimal", "feasible"))
        schedule = result["schedule"]["Opt1"]["days"]
        self.assertTrue(schedule)

        # At least one displayed 8h continuous range with only 7h counted as worked.
        found_long_shift = False
        for day_data in schedule.values():
            ranges = day_data.get("ranges", [])
            if not ranges:
                continue
            day_hours_displayed = 0.0
            for r in ranges:
                start_h, start_m = map(int, r["start"].split(":"))
                end_h, end_m = map(int, r["end"].split(":"))
                day_hours_displayed += ((end_h * 60 + end_m) - (start_h * 60 + start_m)) / 60.0
            if day_hours_displayed >= 8.0:
                self.assertAlmostEqual(day_data["hours"], day_hours_displayed - 1.0, places=6)
                found_long_shift = True
                break

        self.assertTrue(found_long_shift)


if __name__ == "__main__":
    unittest.main()
