import time
import logging
from typing import List, Dict, Optional
from ortools.sat.python import cp_model
from src.hard_constraints import (
    add_min_coverage, add_max_weekly_hours, add_max_daily_hours,
    add_qualified_optician_coverage, add_unavailabilities, add_rest_between_days,
    add_max_days_per_week, add_weekly_rest_35h
)
from src.soft_constraints import (
    add_monthly_hours_balancing, add_saturday_fairness, add_contiguity_preference
)

logger = logging.getLogger(__name__)


def _minutes_to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _hhmm_to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _build_contiguous_ranges(
    slots_worked: List[int],
    start_time_minutes: int,
    slot_minutes: int
) -> List[Dict[str, str]]:
    sorted_slots = sorted(slots_worked)
    ranges = []
    range_start = sorted_slots[0]
    prev = sorted_slots[0]

    for s in sorted_slots[1:]:
        if s == prev + 1:
            prev = s
        else:
            r_start = start_time_minutes + range_start * slot_minutes
            r_end = start_time_minutes + (prev + 1) * slot_minutes
            ranges.append({
                "start": _minutes_to_hhmm(r_start),
                "end": _minutes_to_hhmm(r_end)
            })
            range_start = s
            prev = s

    r_start = start_time_minutes + range_start * slot_minutes
    r_end = start_time_minutes + (prev + 1) * slot_minutes
    ranges.append({
        "start": _minutes_to_hhmm(r_start),
        "end": _minutes_to_hhmm(r_end)
    })

    return ranges


def _sum_ranges_hours(ranges: List[Dict[str, str]]) -> float:
    total_minutes = 0
    for r in ranges:
        total_minutes += _hhmm_to_minutes(r["end"]) - _hhmm_to_minutes(r["start"])
    return total_minutes / 60


def build_and_solve_v1(
    employees: List[str],
    days: List[str],
    contracts: List[int],
    config: dict,
    roles: Optional[List[str]] = None,
    unavailabilities: Optional[List] = None,
    previous_month_stats: Optional[Dict] = None
) -> Dict:
    warnings = []

    num_employees = len(employees)
    num_days = len(days)
    if num_employees > 10:
        warnings.append(f"Performance warning: {num_employees} employés (>10). Le solveur peut être lent.")
    if num_days > 35:
        warnings.append(f"Performance warning: {num_days} jours (>35). Le solveur peut être lent.")

    model = cp_model.CpModel()

    sched = config.get("schedule", config)
    slot_minutes = sched.get("slot_minutes", 15)
    start_time_minutes = sched.get("start_time_minutes", 9 * 60 + 30)
    end_time_minutes = sched.get("end_time_minutes", 20 * 60 + 15)
    min_staff = sched.get("min_staff_per_slot", 1)

    hard = config.get("hard_constraints", {})
    max_daily_min = hard.get("max_daily_minutes", 600)
    rest_min = hard.get("rest_between_days_minutes", 660)
    require_optician = hard.get("require_qualified_optician", True)
    max_days_week = hard.get("max_days_per_week", 6)
    weekly_rest_min = hard.get("weekly_rest_minutes", 2100)

    weights = config.get("soft_weights", {})
    fast_solve = config.get("fast_solve", False)

    w_balance = weights.get("hours_balancing", 10)
    w_saturday = 0 if fast_solve else weights.get("saturday_fairness", 5)
    w_contiguity = 0 if fast_solve else weights.get("contiguity", 3)

    long_term_weight = config.get("long_term_equity_weight", 0.0)

    solver_cfg = config.get("solver", {})
    max_time = solver_cfg.get("max_time_seconds", 30)

    num_slots = (end_time_minutes - start_time_minutes) // slot_minutes

    x = {}
    for e in range(num_employees):
        for d in range(num_days):
            for s in range(num_slots):
                x[(e, d, s)] = model.NewBoolVar(f"x_{e}_{d}_{s}")

    add_min_coverage(model, x, num_employees, num_days, num_slots, min_staff)
    if hard.get("max_weekly_hours", True):
        add_max_weekly_hours(model, x, num_employees, num_days, num_slots, contracts, slot_minutes)
    add_max_daily_hours(model, x, num_employees, num_days, num_slots, slot_minutes,
                        max_daily_minutes=max_daily_min)
    add_max_days_per_week(model, x, num_employees, num_days, num_slots, max_days=max_days_week)
    if require_optician and roles is not None:
        add_qualified_optician_coverage(model, x, num_employees, num_days, num_slots, roles)
    if unavailabilities:
        add_unavailabilities(model, x, unavailabilities, num_slots)
    add_rest_between_days(model, x, num_employees, num_days, num_slots,
                          start_time_minutes, slot_minutes, rest_minutes=rest_min)
    if weekly_rest_min > 0 and num_days >= 3:
        add_weekly_rest_35h(model, x, num_employees, num_days, num_slots,
                            start_time_minutes, slot_minutes, rest_minutes=weekly_rest_min)

    all_penalties = []
    if w_balance > 0:
        all_penalties.extend(
            add_monthly_hours_balancing(model, x, num_employees, num_days, num_slots,
                                        contracts, slot_minutes, weight=w_balance,
                                        previous_month_stats=previous_month_stats,
                                        long_term_equity_weight=long_term_weight,
                                        employees=employees)
        )
    if w_saturday > 0:
        all_penalties.extend(
            add_saturday_fairness(model, x, num_employees, num_days, num_slots,
                                  days, slot_minutes, weight=w_saturday,
                                  previous_month_stats=previous_month_stats,
                                  long_term_equity_weight=long_term_weight,
                                  employees=employees)
        )
    if w_contiguity > 0:
        all_penalties.extend(
            add_contiguity_preference(model, x, num_employees, num_days, num_slots,
                                      slot_minutes, weight=w_contiguity)
        )

    if all_penalties:
        model.Minimize(
            sum(var * w for var, w in all_penalties)
        )

    num_variables = model.Proto().variables.__len__()
    num_constraints = len(model.Proto().constraints)

    logger.info(f"Model: {num_variables} variables, {num_constraints} constraints")

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_time

    t0 = time.time()
    status = solver.Solve(model)
    solver_wall_time = round(time.time() - t0, 3)

    status_name = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.MODEL_INVALID: "MODEL_INVALID",
        cp_model.UNKNOWN: "UNKNOWN",
    }.get(status, "UNKNOWN")

    gap = None
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        obj_val = solver.ObjectiveValue()
        best_bound = solver.BestObjectiveBound()
        if obj_val != 0:
            gap = round(abs(obj_val - best_bound) / abs(obj_val) * 100, 2)
        else:
            gap = 0.0

    metrics = {
        "num_variables": num_variables,
        "num_constraints": num_constraints,
        "solver_wall_time": solver_wall_time,
        "solver_status": status_name,
        "gap_percent": gap,
    }

    if warnings:
        metrics["warnings"] = warnings

    logger.info(f"Solver: status={status_name}, time={solver_wall_time}s, gap={gap}%")

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"error": "Aucune solution trouvée par le solveur.", "metrics": metrics}

    schedule = {}
    for e in range(num_employees):
        emp_name = employees[e]
        schedule[emp_name] = {"days": {}, "total_hours": 0.0}
        for d in range(num_days):
            slots_worked = [
                s for s in range(num_slots)
                if solver.Value(x[(e, d, s)]) == 1
            ]
            if slots_worked:
                ranges = _build_contiguous_ranges(
                    slots_worked, start_time_minutes, slot_minutes
                )
                model_hours = len(slots_worked) * slot_minutes / 60
                display_hours = _sum_ranges_hours(ranges)
                assert abs(model_hours - display_hours) < 1e-9, (
                    f"Incohérence heures {emp_name} {days[d]}: "
                    f"modèle={model_hours}h, affichage={display_hours}h"
                )
                schedule[emp_name]["days"][days[d]] = {
                    "ranges": ranges,
                    "hours": model_hours
                }
                schedule[emp_name]["total_hours"] += model_hours

    return {"schedule": schedule, "metrics": metrics}
