import unittest

from solve.weekly_solver import map_solver_status_to_api


class TestSolverStatusMapping(unittest.TestCase):
    def test_mapping_unknown_returns_timeout(self):
        self.assertEqual(map_solver_status_to_api("UNKNOWN"), "timeout")

    def test_mapping_canonical_statuses(self):
        self.assertEqual(map_solver_status_to_api("OPTIMAL"), "optimal")
        self.assertEqual(map_solver_status_to_api("FEASIBLE"), "feasible")
        self.assertEqual(map_solver_status_to_api("INFEASIBLE"), "infeasible")


if __name__ == "__main__":
    unittest.main()
