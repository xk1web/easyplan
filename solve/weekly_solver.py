from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple, Any

from ortools.sat.python import cp_model

from model.weekly_model import WeeklyModelArtifacts
from model.shift_templates import CLOSING_TEMPLATES, SHIFT_TEMPLATES
from utils.time_slots import effective_worked_minutes


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
    min_shift_length: float
    avg_shift_length: float


def status_code_to_planning_status(status: int) -> str:
    if status == cp_model.OPTIMAL:
        return "optimal"
    if status == cp_model.FEASIBLE:
        return "feasible"
    if status == cp_model.INFEASIBLE:
        return "infeasible"
    return "unknown"


def build_solver_result(planning_status: str, solver: cp_model.CpSolver) -> Dict[str, Any]:
    return {
        "status": planning_status,
        "wall_time": solver.WallTime(),
        "num_branches": solver.NumBranches(),
        "num_conflicts": solver.NumConflicts(),
    }


def solve_weekly_model(
    artifacts: WeeklyModelArtifacts,
    *,
    max_time_seconds: int,
    num_workers: int,
    random_seed: int = 42,
) -> WeeklySolveOutput:
    print("INPUT DEBUG")
    print("employees received:", len(artifacts.employees))
    print("employee list:", artifacts.employees)
    print(
        "opening hours:",
        {
            "open": artifacts.start_time_minutes,
            "close": artifacts.end_time_minutes,
        },
    )
    print("slot duration:", artifacts.slot_minutes)

    model = artifacts.model
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_time_seconds
    solver.parameters.num_search_workers = max(1, num_workers)
    solver.parameters.random_seed = max(0, int(random_seed))

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
    print("MODEL DEBUG INFO")
    print("employees:", len(artifacts.employees))
    print("days:", artifacts.num_days)
    print("slots per day:", artifacts.num_slots)
    print("MIN_STAFF_PER_DAY:", artifacts.min_staff_per_day)
    print("CLOSING_TEMPLATES:", CLOSING_TEMPLATES)
    missing_closing_templates = [t for t in CLOSING_TEMPLATES if t not in SHIFT_TEMPLATES]
    if missing_closing_templates:
        print("WARNING: missing closing templates in SHIFT_TEMPLATES:", missing_closing_templates)

    total_required = 0
    for d in range(artifacts.num_days):
        required_staff = int(artifacts.min_staff_per_day[d])
        for s in range(artifacts.num_slots):
            total_required += required_staff
    print("TOTAL STAFF REQUIRED:", total_required)

    max_possible = len(artifacts.employees) * artifacts.num_days * artifacts.num_slots
    print("MAX STAFF CAPACITY:", max_possible)

    status = solver.Solve(model)
    print("SOLVER STATUS:", status)
    active_vars = 0
    for idx, _ in enumerate(model.Proto().variables):
        try:
            val = solver.Value(model.GetIntVarFromProtoIndex(idx))
            if val == 1:
                active_vars += 1
        except Exception:
            pass
    print("ACTIVE_VARIABLES_IN_SOLUTION:", active_vars)

    active_slots = 0
    for e in range(len(artifacts.employees)):
        for d in range(artifacts.num_days):
            for s in range(artifacts.num_slots):
                if solver.Value(artifacts.x[(e, d, s)]) == 1:
                    active_slots += 1
    print("ACTIVE_SLOT_ASSIGNMENTS:", active_slots)

    status_name = solver.StatusName(status)
    api_status = status_code_to_planning_status(status)
    metrics = {
        "status": api_status,
        "wall_time": solver.WallTime(),
        "num_branches": solver.NumBranches(),
        "num_conflicts": solver.NumConflicts(),
        "num_variables": model_stats["num_variables"],
        "num_constraints": model_stats["num_constraints"],
    }
    solver_result = build_solver_result(api_status, solver)
    solver_result["metrics"] = metrics

    x_values: Dict[Tuple[int, int, int], int] = {}
    hours_per_employee = {name: 0.0 for name in artifacts.employees}
    min_shift_length = 0.0
    avg_shift_length = 0.0

    if status_name in ("OPTIMAL", "FEASIBLE"):
        shift_lengths_slots = []
        for e, emp_name in enumerate(artifacts.employees):
            total_slots = 0
            for d in range(artifacts.num_days):
                day_slots = 0
                active_slots = []
                for s in range(artifacts.num_slots):
                    value = int(solver.Value(artifacts.x[(e, d, s)]))
                    x_values[(e, d, s)] = value
                    total_slots += value
                    day_slots += value
                    if value == 1:
                        active_slots.append(s)
                if active_slots:
                    print(
                        f"[DEBUG] employee={emp_name} day={artifacts.days[d]} "
                        f"slots={active_slots} "
                        f"count={len(active_slots)}"
                    )
                    first_slot = min(active_slots)
                    last_slot = max(active_slots)
                    span_slots = last_slot - first_slot + 1
                    span_minutes = span_slots * artifacts.slot_minutes
                    span_hours = span_minutes / 60
                    print(
                        "[DEBUG SHIFT SPAN]",
                        "employee=", e,
                        "day=", d,
                        "span_minutes=", span_minutes,
                        "span_hours=", span_hours,
                    )
                    if span_minutes > 600:
                        print(
                            "[VIOLATION MAX DAY]",
                            "employee=", e,
                            "day=", d,
                            "span_hours=", span_hours,
                            "first_slot=", first_slot,
                            "last_slot=", last_slot,
                        )
                if day_slots > 0:
                    shift_lengths_slots.append(day_slots)
            total_effective_minutes = 0
            for d in range(artifacts.num_days):
                day_slots = sum(
                    int(solver.Value(artifacts.x[(e, d, s)]))
                    for s in range(artifacts.num_slots)
                )
                total_effective_minutes += effective_worked_minutes(day_slots * artifacts.slot_minutes)
            hours_per_employee[emp_name] = total_effective_minutes / 60.0

        if shift_lengths_slots:
            min_shift_length = min(shift_lengths_slots) * artifacts.slot_minutes / 60.0
            avg_shift_length = (
                sum(shift_lengths_slots) / len(shift_lengths_slots)
            ) * artifacts.slot_minutes / 60.0

    metrics["min_shift_length"] = min_shift_length
    metrics["avg_shift_length"] = avg_shift_length
    solver_result["metrics"] = metrics

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
        min_shift_length=min_shift_length,
        avg_shift_length=avg_shift_length,
    )
