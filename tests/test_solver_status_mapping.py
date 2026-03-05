import unittest

from ortools.sat.python import cp_model
from solve.weekly_solver import status_code_to_planning_status


class TestSolverStatusMapping(unittest.TestCase):
    def test_mapping_unknown_returns_unknown(self):
        self.assertEqual(status_code_to_planning_status(cp_model.UNKNOWN), "unknown")

    def test_mapping_canonical_statuses(self):
        self.assertEqual(status_code_to_planning_status(cp_model.OPTIMAL), "optimal")
        self.assertEqual(status_code_to_planning_status(cp_model.FEASIBLE), "feasible")
        self.assertEqual(status_code_to_planning_status(cp_model.INFEASIBLE), "infeasible")


if __name__ == "__main__":
    unittest.main()
