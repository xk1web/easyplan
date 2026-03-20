from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.explanation.planning_explainer import explain_planning
from core.feasibility_precheck import run_employee_feasibility_precheck
from core.infeasibility_diagnosis import diagnose_infeasibility
from core.metrics.kpi_calculator import calculate_kpi
from metrics.v1_kpi import compute_v1_kpi
from model.weekly_model import WeeklyModelArtifacts, build_weekly_model
from solve.weekly_solver import WeeklySolveOutput, solve_weekly_model
from utils.time_slots import effective_worked_minutes


def _minutes_to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _build_ranges(slots: List[int], start_time_minutes: int, slot_minutes: int) -> List[Dict[str, str]]:
    if not slots:
        return []
    active_slots = sorted(slots)
    merged_segments: List[Tuple[int, int]] = []
    start = active_slots[0]
    prev = active_slots[0]

    for slot_idx in active_slots[1:]:
        if slot_idx == prev + 1:
            prev = slot_idx
        else:
            merged_segments.append((start, prev))
            start = slot_idx
            prev = slot_idx

    merged_segments.append((start, prev))

    ranges: List[Dict[str, str]] = []
    for segment_start, segment_end in merged_segments:
        start_time = start_time_minutes + segment_start * slot_minutes
        end_time = start_time_minutes + (segment_end + 1) * slot_minutes
        ranges.append({"start": _minutes_to_hhmm(start_time), "end": _minutes_to_hhmm(end_time)})

    return ranges


def _build_schedule(
    artifacts: WeeklyModelArtifacts,
    solve_output: WeeklySolveOutput,
) -> Tuple[Dict[str, Dict], Dict[str, Dict[str, List[int]]]]:
    print("EXTRACTION DEBUG")
    print("employees:", artifacts.employees)
    print("days:", artifacts.num_days)
    print("slots:", artifacts.num_slots)

    schedule: Dict[str, Dict] = {}
    coverage_slots_per_day: Dict[str, Dict[str, List[int]]] = {}

    for e, emp_name in enumerate(artifacts.employees):
        schedule[emp_name] = {"days": {}, "total_hours": 0.0}
        coverage_slots_per_day[emp_name] = {}

        for d, day_name in enumerate(artifacts.days):
            active_slots = [
                s
                for s in range(artifacts.num_slots)
                if solve_output.x_values.get((e, d, s), 0) == 1
            ]
            if not active_slots:
                continue

            print(
                "[DEBUG BUILD_RANGES INPUT]",
                "employee=", e,
                "day=", d,
                "slots=", active_slots,
            )
            ranges = _build_ranges(active_slots, artifacts.start_time_minutes, artifacts.slot_minutes)
            print(
                "[DEBUG BUILD_RANGES OUTPUT]",
                "employee=", e,
                "day=", d,
                "ranges=", ranges,
            )
            hours = effective_worked_minutes(len(active_slots) * artifacts.slot_minutes) / 60.0
            schedule[emp_name]["days"][day_name] = {
                "ranges": ranges,
                "hours": hours,
            }
            schedule[emp_name]["total_hours"] += hours
            coverage_slots_per_day[emp_name][day_name] = active_slots

    return schedule, coverage_slots_per_day


def run_weekly_v1_engine(
    *,
    employees: List[str],
    contracts: List[float],
    roles: List[str],
    constraints=None,
    days: List[str],
    config: dict,
    unavailabilities: Optional[List[Tuple[int, ...]]] = None,
) -> Dict:
    opening_hours = config.get("opening_hours")
    if opening_hours is None:
        schedule_cfg = config.get("schedule", {})
        opening_hours = {
            "open": schedule_cfg.get("open_time"),
            "close": schedule_cfg.get("close_time"),
        }
    print("ENGINE INPUT DEBUG")
    print("opening_hours received:", opening_hours)
    print("employees received:", employees)
    if constraints:
        print("constraints received:", constraints)

    artifacts = build_weekly_model(
        employees=employees,
        contracts=contracts,
        roles=roles,
        days=days,
        config=config,
        unavailabilities=unavailabilities,
        constraints=constraints,
    )

    precheck = run_employee_feasibility_precheck(
        employees=employees,
        contracts=contracts,
        days=days,
        config=config,
        constraints=constraints,
        unavailabilities=unavailabilities,
    )
    if not precheck["is_feasible"]:
        unreachable = precheck.get("unreachable_contracts") or []
        unreachable_messages = [
            str(item.get("summary_message"))
            for item in unreachable
            if isinstance(item, dict) and item.get("summary_message")
        ]
        manager_error = (
            " | ".join(unreachable_messages[:2])
            if unreachable_messages
            else "Contrat mathematiquement inatteignable pour au moins un salarie."
        )
        metrics = {
            "num_variables": 0,
            "num_constraints": 0,
            "solver_wall_time": 0.0,
            "solver_status": "INFEASIBLE",
            "num_branches": 0,
            "num_conflicts": 0,
            "min_shift_length": 0.0,
            "avg_shift_length": 0.0,
        }
        result = {
            "status": "infeasible",
            "solver_time": 0.0,
            "solve_time_seconds": 0.0,
            "metrics": metrics,
            "kpi": {},
            "hours_per_employee": {name: 0.0 for name in employees},
            "solver_result": {"status": "infeasible", "wall_time": 0.0, "num_branches": 0, "num_conflicts": 0},
            "schedule": None,
            "coverage_slots_per_day": {},
            "traceability": {"x": {}},
            "error": manager_error,
            "infeasibility_reasons": [
                {
                    "code": "EMPLOYEE_CONTRACT_UNREACHABLE",
                    "title": "Contrat inatteignable par disponibilites",
                    "message": (
                        "Le volume contractuel ne peut pas etre atteint pour un ou plusieurs salaries. "
                        "Voir le detail par salarie ci-dessous."
                    ),
                    "details": precheck,
                }
            ],
            "feasibility_precheck": precheck,
        }
        result["explanation"] = explain_planning(result, [])
        result["kpi_summary"] = calculate_kpi(result)
        return result

    solver_cfg = config.get("solver", {})
    max_time_seconds = int(config.get("solver_max_time_seconds", solver_cfg.get("max_time_seconds", 30)))
    num_workers = int(config.get("solver_num_workers", solver_cfg.get("num_search_workers", 8)))
    random_seed = int(config.get("solver_random_seed", solver_cfg.get("random_seed", 42)))

    solve_output = solve_weekly_model(
        artifacts,
        max_time_seconds=max_time_seconds,
        num_workers=num_workers,
        random_seed=random_seed,
    )

    kpi = compute_v1_kpi(artifacts, solve_output.x_values)
    explanation_employees = [
        {"id": employee_id, "contract_hours": contract_hours}
        for employee_id, contract_hours in zip(employees, contracts)
    ]

    metrics = {
        "num_variables": solve_output.num_variables,
        "num_constraints": solve_output.num_constraints,
        "solver_wall_time": solve_output.wall_time_seconds,
        "solver_status": solve_output.solver_status,
        "num_branches": solve_output.num_branches,
        "num_conflicts": solve_output.num_conflicts,
        "min_shift_length": solve_output.min_shift_length,
        "avg_shift_length": solve_output.avg_shift_length,
    }

    result = {
        "status": solve_output.api_status,
        "solver_time": solve_output.wall_time_seconds,
        "solve_time_seconds": solve_output.wall_time_seconds,
        "metrics": metrics,
        "kpi": kpi,
        "hours_per_employee": solve_output.hours_per_employee,
        "solver_result": solve_output.solver_result,
        "feasibility_precheck": precheck,
    }
    result["explanation"] = explain_planning(result, explanation_employees, constraints=constraints)

    if solve_output.solver_status in ("OPTIMAL", "FEASIBLE"):
        schedule, coverage_slots_per_day = _build_schedule(artifacts, solve_output)
        result["schedule"] = schedule
        result["coverage_slots_per_day"] = coverage_slots_per_day
        result["traceability"] = {
            "x": solve_output.x_values,
        }
        print("[DEBUG FINAL SCHEDULE PAYLOAD]")
        for employee, data in schedule.items():
            for day, day_data in data["days"].items():
                print(employee, day, day_data["ranges"])
    else:
        result["schedule"] = None
        result["coverage_slots_per_day"] = {}
        result["traceability"] = {"x": {}}
        if solve_output.solver_status == "INFEASIBLE":
            result["error"] = "Aucune solution conforme n'a ete trouvee."
            result["infeasibility_reasons"] = diagnose_infeasibility(
                employees=employees,
                roles=roles,
                contracts=contracts,
                days=days,
                config=config,
                constraints=constraints,
                unavailabilities=unavailabilities,
            )
        elif solve_output.solver_status == "UNKNOWN":
            result["error"] = "Timeout solveur: aucune solution garantie dans le temps imparti."

    result["kpi_summary"] = calculate_kpi(result)

    return result
