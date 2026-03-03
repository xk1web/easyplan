import time
import logging
from typing import List, Dict, Optional
from ortools.sat.python import cp_model
from src.hard_constraints import (
    add_min_coverage, add_max_weekly_hours, add_max_daily_hours,
    add_qualified_optician_coverage, add_unavailabilities, add_rest_between_days,
    add_max_days_per_week, add_weekly_rest_35h, add_min_daily_work_duration
)
from src.soft_constraints import (
    add_monthly_hours_balancing, add_saturday_fairness, add_contiguity_preference,
    add_contract_target_penalty, add_weekly_hours_fairness, add_close_fairness,
    add_amplitude_fairness, add_max_daily_hours_penalty, add_overstaffing_penalty,
    add_target_staffing_penalty, add_internal_hours_penalty
)

logger = logging.getLogger(__name__)
TARGET_OBJECTIVE = 42  # seuil cible empirique


class EarlyStopCallback(cp_model.CpSolverSolutionCallback):
    def __init__(self, target):
        super().__init__()
        self.target = target
        self.best = float("inf")

    def on_solution_callback(self):
        current = self.ObjectiveValue()
        if current < self.best:
            self.best = current
        if current <= self.target:
            self.StopSearch()


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
    staffing = config.get("staffing", {})
    min_staff = staffing.get("min_staff_per_slot", sched.get("min_staff_per_slot", 1))
    target_staff = staffing.get("target_staff_per_slot", min_staff)
    min_staff_per_day = sched.get("min_staff_per_day")

    hard = config.get("hard_constraints", {})
    max_daily_min = hard.get("max_daily_minutes", 600)
    rest_min = hard.get("rest_between_days_minutes", 660)
    require_optician = hard.get("require_qualified_optician", True)
    max_days_week = hard.get("max_days_per_week", 6)
    weekly_rest_min = hard.get("weekly_rest_minutes", 2100)
    contract_mode = hard.get("contract_hours_mode", "soft")
    if hard.get("contract_hours_hard", False):
        contract_mode = "hard"
    if contract_mode not in ("hard", "soft", "off"):
        contract_mode = "soft"
    contract_tolerance_slots = hard.get("contract_hours_tolerance_slots", 0)
    contract_overtime_slots = hard.get("contract_overtime_slots", 0)

    weights = config.get("soft_weights", {})
    fast_solve = config.get("fast_solve", False)

    w_balance = weights.get("hours_balancing", 10)
    w_saturday = 0 if fast_solve else weights.get("saturday_fairness", 5)
    w_contiguity = 0 if fast_solve else weights.get("contiguity", 3)
    w_contract_target = 0 if fast_solve else weights.get("contract_target", 50)
    w_contract_under = weights.get("contract_target_under")
    w_contract_over = weights.get("contract_target_over")
    w_contract_overtime = 0 if fast_solve else weights.get("contract_overtime_penalty", 0)
    w_weekly_fairness = 0 if fast_solve else weights.get("weekly_hours_fairness", 0)
    w_close_fairness = 0 if fast_solve else weights.get("close_fairness", 0)
    w_amplitude_fairness = 0 if fast_solve else weights.get("amplitude_fairness", 0)
    w_max_daily_penalty = 0 if fast_solve else weights.get("max_daily_hours_penalty", 20)
    w_target_staffing_penalty = 0 if fast_solve else weights.get("target_staffing_penalty", 5)
    w_overstaffing_penalty = 0 if fast_solve else weights.get("overstaffing_penalty", 1)
    w_internal_hours_penalty = 0 if fast_solve else weights.get("internal_hours_penalty", 1)
    if contract_mode == "off":
        w_contract_target = 0

    long_term_weight = config.get("long_term_equity_weight", 0.0)

    solver_cfg = config.get("solver", {})
    max_time = solver_cfg.get("max_time_seconds", 30)

    num_slots = (end_time_minutes - start_time_minutes) // slot_minutes

    x = {}
    for e in range(num_employees):
        for d in range(num_days):
            for s in range(num_slots):
                x[(e, d, s)] = model.NewBoolVar(f"x_{e}_{d}_{s}")

    internal = {}
    worked = {}
    for e in range(num_employees):
        for d in range(num_days):
            for s in range(num_slots):
                internal[(e, d, s)] = model.NewBoolVar(f"internal_{e}_{d}_{s}")
                model.Add(x[(e, d, s)] + internal[(e, d, s)] <= 1)
                worked[(e, d, s)] = model.NewBoolVar(f"worked_{e}_{d}_{s}")
                model.Add(worked[(e, d, s)] == x[(e, d, s)] + internal[(e, d, s)])

    if isinstance(min_staff_per_day, (list, tuple)) and len(min_staff_per_day) == num_days:
        add_min_coverage(model, x, num_employees, num_days, num_slots, min_staff_per_day)
    else:
        add_min_coverage(model, x, num_employees, num_days, num_slots, min_staff)
    if hard.get("max_weekly_hours", True):
        add_max_weekly_hours(model, x, num_employees, num_days, num_slots, contracts, slot_minutes, internal=internal)
    # max_daily_hours is now a soft constraint (penalized in objective)
    min_daily_min = hard.get("min_daily_minutes", 0)
    if min_daily_min > 0:
        add_min_daily_work_duration(model, x, num_employees, num_days, num_slots,
                                    slot_minutes, min_daily_minutes=min_daily_min)
    add_max_days_per_week(model, x, num_employees, num_days, num_slots, max_days=max_days_week)
    if require_optician and roles is not None:
        add_qualified_optician_coverage(model, x, num_employees, num_days, num_slots, roles)
    if unavailabilities:
        add_unavailabilities(model, x, unavailabilities, num_slots, internal=internal)
    add_rest_between_days(model, x, num_employees, num_days, num_slots,
                          start_time_minutes, slot_minutes, rest_minutes=rest_min)
    if weekly_rest_min > 0 and num_days >= 3:
        add_weekly_rest_35h(model, x, num_employees, num_days, num_slots,
                            start_time_minutes, slot_minutes, rest_minutes=weekly_rest_min)

    overtime_penalties = []
    if contract_mode == "hard":
        # Contrats stricts par semaine complète + plage pour semaine partielle
        # Semaines complètes: somme == H_e
        # Semaine partielle: somme ∈ [floor(k/7 * H_e), ceil(k/7 * H_e)]
        weeks = []
        start = 0
        while start < num_days:
            end = min(start + 7, num_days)
            weeks.append(list(range(start, end)))
            start = end
        for e in range(num_employees):
            weekly_target_slots = contracts[e] * 60 / slot_minutes
            for w_idx, week_days in enumerate(weeks):
                week_slots = sum(
                    x[(e, d, s)]
                    for d in week_days
                    for s in range(num_slots)
                )
                if len(week_days) == 7:
                    min_slots = int(weekly_target_slots // 1)
                    max_slots = int(-(-weekly_target_slots // 1))
                    if min_slots == max_slots:
                        if contract_overtime_slots and contract_overtime_slots > 0:
                            overtime = model.NewIntVar(0, contract_overtime_slots, f"overtime_{e}_{w_idx}")
                            model.Add(week_slots == min_slots + overtime)
                            overtime_penalties.append(overtime)
                        else:
                            model.Add(week_slots == min_slots)
                    else:
                        model.Add(week_slots >= min_slots)
                        if contract_overtime_slots and contract_overtime_slots > 0:
                            overtime = model.NewIntVar(0, contract_overtime_slots, f"overtime_{e}_{w_idx}")
                            model.Add(week_slots <= max_slots + overtime)
                            overtime_penalties.append(overtime)
                        else:
                            model.Add(week_slots <= max_slots)
                else:
                    partial_target = weekly_target_slots * (len(week_days) / 7.0)
                    min_slots = int(partial_target // 1)
                    max_slots = int(-(-partial_target // 1))
                    model.Add(week_slots >= min_slots)
                    model.Add(week_slots <= max_slots)

    if contract_mode == "hard":
        w_balance = 0
        w_contract_target = 0

    all_penalties = []
    phase2_penalties = []
    penalty_groups = {}
    if w_balance > 0:
        penalties = add_monthly_hours_balancing(model, x, num_employees, num_days, num_slots,
                                                contracts, slot_minutes, weight=w_balance,
                                                previous_month_stats=previous_month_stats,
                                                long_term_equity_weight=long_term_weight,
                                                employees=employees, internal=internal)
        all_penalties.extend(penalties)
        phase2_penalties.extend(penalties)
        penalty_groups["monthly_hours_balancing"] = penalties
    if w_saturday > 0:
        penalties = add_saturday_fairness(model, x, num_employees, num_days, num_slots,
                                          days, slot_minutes, weight=w_saturday,
                                          previous_month_stats=previous_month_stats,
                                          long_term_equity_weight=long_term_weight,
                                          employees=employees)
        all_penalties.extend(penalties)
        phase2_penalties.extend(penalties)
        penalty_groups["saturday_fairness"] = penalties
    if w_contiguity > 0:
        penalties = add_contiguity_preference(model, worked, num_employees, num_days, num_slots,
                                              slot_minutes, weight=w_contiguity)
        all_penalties.extend(penalties)
        phase2_penalties.extend(penalties)
        penalty_groups["contiguity"] = penalties
    contract_deviation_terms = []
    if w_contract_target > 0:
        penalties, deviation_terms = add_contract_target_penalty(
            model, x, num_employees, num_days, num_slots,
            contracts, slot_minutes,
            weight=w_contract_target,
            weight_under=w_contract_under,
            weight_over=w_contract_over,
            internal=internal,
        )
        all_penalties.extend(penalties)
        penalty_groups["contract_target"] = penalties
        contract_deviation_terms = deviation_terms
    if w_target_staffing_penalty > 0 and target_staff > min_staff:
        penalties = add_target_staffing_penalty(model, x, num_employees, num_days, num_slots,
                                                target_staff, weight=w_target_staffing_penalty)
        all_penalties.extend(penalties)
        phase2_penalties.extend(penalties)
        penalty_groups["target_staffing"] = penalties
    if w_overstaffing_penalty > 0:
        penalties = add_overstaffing_penalty(model, x, num_employees, num_days, num_slots,
                                             min_staff, min_staff_per_day,
                                             weight=w_overstaffing_penalty)
        all_penalties.extend(penalties)
        phase2_penalties.extend(penalties)
        penalty_groups["overstaffing"] = penalties
    if w_internal_hours_penalty > 0:
        penalties = add_internal_hours_penalty(
            model, internal, num_employees, num_days, num_slots, weight=w_internal_hours_penalty
        )
        all_penalties.extend(penalties)
        phase2_penalties.extend(penalties)
        penalty_groups["internal_hours"] = penalties
    if w_max_daily_penalty > 0:
        penalties = add_max_daily_hours_penalty(model, x, num_employees, num_days, num_slots,
                                                slot_minutes,
                                                max_daily_minutes=max_daily_min,
                                                weight=w_max_daily_penalty,
                                                internal=internal)
        all_penalties.extend(penalties)
        phase2_penalties.extend(penalties)
        penalty_groups["max_daily_hours"] = penalties
    if overtime_penalties and w_contract_overtime > 0:
        penalties = [(o, w_contract_overtime) for o in overtime_penalties]
        all_penalties.extend(penalties)
        phase2_penalties.extend(penalties)
        penalty_groups["overtime_penalty"] = penalties
    if w_weekly_fairness > 0:
        penalties = add_weekly_hours_fairness(model, x, num_employees, num_days, num_slots,
                                              contracts, slot_minutes,
                                              weight=w_weekly_fairness,
                                              internal=internal)
        all_penalties.extend(penalties)
        phase2_penalties.extend(penalties)
        penalty_groups["weekly_hours_fairness"] = penalties
    if w_close_fairness > 0:
        penalties = add_close_fairness(model, x, num_employees, num_days, num_slots,
                                       weight=w_close_fairness)
        all_penalties.extend(penalties)
        phase2_penalties.extend(penalties)
        penalty_groups["close_fairness"] = penalties
    if w_amplitude_fairness > 0:
        penalties = add_amplitude_fairness(model, x, num_employees, num_days, num_slots,
                                           weight=w_amplitude_fairness)
        all_penalties.extend(penalties)
        phase2_penalties.extend(penalties)
        penalty_groups["amplitude_fairness"] = penalties

    total_contract_deviation = model.NewIntVar(
        0, num_employees * num_days * num_slots, "total_contract_deviation"
    )
    if contract_deviation_terms:
        model.Add(total_contract_deviation == sum(contract_deviation_terms))
    else:
        model.Add(total_contract_deviation == 0)

    num_variables = model.Proto().variables.__len__()
    num_constraints = len(model.Proto().constraints)

    logger.info(f"Model: {num_variables} variables, {num_constraints} constraints")

    def build_solver():
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max_time
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 42
        solver.parameters.log_search_progress = False
        return solver

    status = cp_model.UNKNOWN
    solver_wall_time = 0.0

    if contract_mode != "off":
        model.Minimize(total_contract_deviation)
        solver_phase1 = build_solver()
        t0 = time.time()
        status_phase1 = solver_phase1.Solve(model)
        solver_wall_time = round(time.time() - t0, 3)

        if status_phase1 in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            best_deviation = solver_phase1.Value(total_contract_deviation)
            model.Add(total_contract_deviation == best_deviation)
            if phase2_penalties:
                model.Minimize(sum(var * w for var, w in phase2_penalties))
            else:
                model.Minimize(0)
            solver = build_solver()
            t0 = time.time()
            status = solver.Solve(model)
            solver_wall_time = round(time.time() - t0, 3)
        else:
            solver = solver_phase1
            status = status_phase1
    else:
        if all_penalties:
            model.Minimize(sum(var * w for var, w in all_penalties))
        else:
            model.Minimize(0)
        solver = build_solver()
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
    obj_val = None
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        obj_val = solver.ObjectiveValue()
        best_bound = solver.BestObjectiveBound()
        if obj_val != 0:
            gap = round(abs(obj_val - best_bound) / abs(obj_val) * 100, 2)
        else:
            gap = 0.0

    overtime_used_slots = None
    if overtime_penalties and status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        overtime_used_slots = sum(solver.Value(o) for o in overtime_penalties)

    internal_used_slots = None
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        internal_used_slots = sum(solver.Value(v) for v in internal.values())
        if internal_used_slots is not None:
            internal_used_slots = int(internal_used_slots)

    objective_breakdown = None
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) and penalty_groups:
        objective_breakdown = {}
        for name, penalties in penalty_groups.items():
            if not penalties:
                continue
            total = 0.0
            for var, weight in penalties:
                total += solver.Value(var) * weight
            objective_breakdown[name] = total

    metrics = {
        "num_variables": num_variables,
        "num_constraints": num_constraints,
        "solver_wall_time": solver_wall_time,
        "solver_status": status_name,
        "gap_percent": gap,
        "total_overtime_used_slots": overtime_used_slots,
        "total_internal_hours": (
            internal_used_slots * slot_minutes / 60.0
            if internal_used_slots is not None
            else None
        ),
        "objective_value": obj_val,
        "objective_breakdown": objective_breakdown,
    }

    if warnings:
        metrics["warnings"] = warnings

    logger.info(f"Solver: status={status_name}, time={solver_wall_time}s, gap={gap}%")

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"error": "Aucune solution trouvée par le solveur.", "metrics": metrics}

    schedule = {}
    internal_hours_per_employee = {}
    internal_hours_per_day = {}
    coverage_slots_per_day = {}
    internal_slots_per_day = {}
    for e in range(num_employees):
        emp_name = employees[e]
        schedule[emp_name] = {"days": {}, "total_hours": 0.0}
        internal_hours_per_employee[emp_name] = 0.0
        internal_hours_per_day[emp_name] = {}
        coverage_slots_per_day[emp_name] = {}
        internal_slots_per_day[emp_name] = {}
        for d in range(num_days):
            internal_slots = [s for s in range(num_slots) if solver.Value(internal[(e, d, s)]) == 1]
            if internal_slots:
                internal_hours = len(internal_slots) * slot_minutes / 60.0
                internal_hours_per_employee[emp_name] += internal_hours
                internal_hours_per_day[emp_name][days[d]] = internal_hours
                internal_slots_per_day[emp_name][days[d]] = internal_slots
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
                coverage_slots_per_day[emp_name][days[d]] = slots_worked

    return {
        "schedule": schedule,
        "metrics": metrics,
        "internal_hours_per_employee": internal_hours_per_employee,
        "internal_hours_per_day": internal_hours_per_day,
        "coverage_slots_per_day": coverage_slots_per_day,
        "internal_slots_per_day": internal_slots_per_day,
    }
