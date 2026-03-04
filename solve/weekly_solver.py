from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple, Any

from ortools.sat.python import cp_model

from model.weekly_model import WeeklyModelArtifacts


@dataclass
class WeeklySolveOutput:
    solver_status: str
    api_status: str
    wall_time_seconds: float
    num_branches: int
    num_conflicts: int
    num_variables: int
    num_constraints: int
    x_values: Dict[Tuple[int, int, int], int]
    hours_per_employee: Dict[str, float]
    solver_result: Dict[str, Any]


def map_solver_status_to_api(status: str) -> str:
    mapping = {
        "OPTIMAL": "optimal",
        "FEASIBLE": "feasible",
        "INFEASIBLE": "infeasible",
        "UNKNOWN": "timeout",
    }
    return mapping.get(status, "timeout")


def build_solver_result(status_name: str, solver: cp_model.CpSolver) -> Dict[str, Any]:
    return {
        "status": map_solver_status_to_api(status_name),
        "wall_time": solver.WallTime(),
        "num_branches": solver.NumBranches(),
        "num_conflicts": solver.NumConflicts(),
    }


def solve_weekly_model(
    artifacts: WeeklyModelArtifacts,
    *,
    max_time_seconds: int,
    num_workers: int,
) -> WeeklySolveOutput:
    model = artifacts.model
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_time_seconds
    solver.parameters.num_search_workers = max(1, num_workers)
    solver.parameters.random_seed = 42

    # Structural observability of the solved CP-SAT model.
    try:
        num_variables = model.NumVariables()
        num_constraints = model.NumConstraints()
    except AttributeError:
        num_variables = len(model.Proto().variables)
        num_constraints = len(model.Proto().constraints)
    model_stats = {
        "num_variables": num_variables,
        "num_constraints": num_constraints,
    }
    print("MODEL_STATS", model_stats)

    status_code = solver.Solve(model)

    status_name = solver.StatusName(status_code)
    api_status = map_solver_status_to_api(status_name)
    metrics = {
        "status": api_status,
        "wall_time": solver.WallTime(),
        "num_branches": solver.NumBranches(),
        "num_conflicts": solver.NumConflicts(),
        "num_variables": model_stats["num_variables"],
        "num_constraints": model_stats["num_constraints"],
    }
    solver_result = build_solver_result(status_name, solver)
    solver_result["metrics"] = metrics

    x_values: Dict[Tuple[int, int, int], int] = {}
    hours_per_employee = {name: 0.0 for name in artifacts.employees}

    if status_name in ("OPTIMAL", "FEASIBLE"):
        for e, emp_name in enumerate(artifacts.employees):
            total_slots = 0
            for d in range(artifacts.num_days):
                for s in range(artifacts.num_slots):
                    value = int(solver.Value(artifacts.x[(e, d, s)]))
                    x_values[(e, d, s)] = value
                    total_slots += value
            hours_per_employee[emp_name] = total_slots * artifacts.slot_minutes / 60.0

    return WeeklySolveOutput(
        solver_status=status_name,
        api_status=api_status,
        wall_time_seconds=solver.WallTime(),
        num_branches=solver.NumBranches(),
        num_conflicts=solver.NumConflicts(),
        num_variables=model_stats["num_variables"],
        num_constraints=model_stats["num_constraints"],
        x_values=x_values,
        hours_per_employee=hours_per_employee,
        solver_result=solver_result,
    )
