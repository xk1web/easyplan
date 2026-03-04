from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from explanation.v1_explanation import build_v1_explanation
from metrics.v1_kpi import compute_v1_kpi
from model.weekly_model import WeeklyModelArtifacts, build_weekly_model
from solve.weekly_solver import WeeklySolveOutput, solve_weekly_model


def _minutes_to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _build_ranges(slots: List[int], start_time_minutes: int, slot_minutes: int) -> List[Dict[str, str]]:
    if not slots:
        return []
    sorted_slots = sorted(slots)
    ranges = []
    block_start = sorted_slots[0]
    previous = sorted_slots[0]

    for slot_idx in sorted_slots[1:]:
        if slot_idx == previous + 1:
            previous = slot_idx
            continue

        start = start_time_minutes + block_start * slot_minutes
        end = start_time_minutes + (previous + 1) * slot_minutes
        ranges.append({"start": _minutes_to_hhmm(start), "end": _minutes_to_hhmm(end)})
        block_start = slot_idx
        previous = slot_idx

    start = start_time_minutes + block_start * slot_minutes
    end = start_time_minutes + (previous + 1) * slot_minutes
    ranges.append({"start": _minutes_to_hhmm(start), "end": _minutes_to_hhmm(end)})

    return ranges


def _build_schedule(
    artifacts: WeeklyModelArtifacts,
    solve_output: WeeklySolveOutput,
) -> Tuple[Dict[str, Dict], Dict[str, Dict[str, List[int]]]]:
    schedule: Dict[str, Dict] = {}
    coverage_slots_per_day: Dict[str, Dict[str, List[int]]] = {}

    for e, emp_name in enumerate(artifacts.employees):
        schedule[emp_name] = {"days": {}, "total_hours": 0.0}
        coverage_slots_per_day[emp_name] = {}

        for d, day_name in enumerate(artifacts.days):
            slots = [
                s
                for s in range(artifacts.num_slots)
                if solve_output.x_values.get((e, d, s), 0) == 1
            ]
            if not slots:
                continue

            ranges = _build_ranges(slots, artifacts.start_time_minutes, artifacts.slot_minutes)
            hours = len(slots) * artifacts.slot_minutes / 60.0
            schedule[emp_name]["days"][day_name] = {
                "ranges": ranges,
                "hours": hours,
            }
            schedule[emp_name]["total_hours"] += hours
            coverage_slots_per_day[emp_name][day_name] = slots

    return schedule, coverage_slots_per_day


def run_weekly_v1_engine(
    *,
    employees: List[str],
    contracts: List[float],
    roles: List[str],
    days: List[str],
    config: dict,
    unavailabilities: Optional[List[Tuple[int, ...]]] = None,
) -> Dict:
    artifacts = build_weekly_model(
        employees=employees,
        contracts=contracts,
        roles=roles,
        days=days,
        config=config,
        unavailabilities=unavailabilities,
    )

    solver_cfg = config.get("solver", {})
    max_time_seconds = int(config.get("solver_max_time_seconds", solver_cfg.get("max_time_seconds", 30)))
    num_workers = int(config.get("solver_num_workers", solver_cfg.get("num_search_workers", 8)))

    solve_output = solve_weekly_model(
        artifacts,
        max_time_seconds=max_time_seconds,
        num_workers=num_workers,
    )

    kpi = compute_v1_kpi(artifacts, solve_output.x_values)
    explanation = build_v1_explanation(solver_status=solve_output.solver_status, kpi=kpi)

    metrics = {
        "num_variables": solve_output.num_variables,
        "num_constraints": solve_output.num_constraints,
        "solver_wall_time": solve_output.wall_time_seconds,
        "solver_status": solve_output.solver_status,
    }

    result = {
        "status": solve_output.api_status,
        "solver_time": solve_output.wall_time_seconds,
        "solve_time_seconds": solve_output.wall_time_seconds,
        "metrics": metrics,
        "kpi": kpi,
        "explanation": explanation,
        "hours_per_employee": solve_output.hours_per_employee,
    }

    if solve_output.solver_status in ("OPTIMAL", "FEASIBLE"):
        schedule, coverage_slots_per_day = _build_schedule(artifacts, solve_output)
        result["schedule"] = schedule
        result["coverage_slots_per_day"] = coverage_slots_per_day
        result["traceability"] = {
            "x": solve_output.x_values,
        }
    else:
        result["schedule"] = None
        result["coverage_slots_per_day"] = {}
        result["traceability"] = {"x": {}}
        if solve_output.solver_status == "INFEASIBLE":
            result["error"] = "Aucune solution conforme n'a ete trouvee."
        elif solve_output.solver_status == "UNKNOWN":
            result["error"] = "Timeout solveur: aucune solution garantie dans le temps imparti."

    return result
