import time
import logging
import copy
import itertools
from datetime import date, timedelta
from typing import List, Dict, Optional
from ortools.sat.python import cp_model
from src.hard_constraints import (
    add_min_coverage, add_max_weekly_hours, add_max_daily_hours,
    add_qualified_optician_coverage, add_unavailabilities, add_rest_between_days,
    add_max_days_per_week, add_weekly_rest_35h, add_min_daily_work_duration,
    add_single_contiguous_block_per_day
)
from src.soft_constraints import (
    add_monthly_hours_balancing, add_saturday_fairness, add_contiguity_preference,
    add_contract_target_penalty, add_weekly_hours_fairness, add_close_fairness,
    add_amplitude_fairness, add_max_daily_hours_penalty, add_overstaffing_penalty,
    add_target_staffing_penalty, add_days_concentration_penalty,
    add_hourly_demand_reward, add_late_days_fairness,
    add_long_day_requirement_penalty, add_non_template_penalty,
    add_contract_minimum_constraint
)
from src.kpi import compute_global_kpi

logger = logging.getLogger(__name__)
TARGET_OBJECTIVE = 42  # seuil cible empirique


def _domain_bounds(domain: List[int]) -> Optional[tuple]:
    if not domain:
        return None
    return domain[0], domain[-1]


def _intervals_overlap(a_min: int, a_max: int, domain: List[int]) -> bool:
    for i in range(0, len(domain), 2):
        d_min = domain[i]
        d_max = domain[i + 1]
        if not (a_max < d_min or a_min > d_max):
            return True
    return False


def _find_first_linear_domain_contradiction(model: cp_model.CpModel) -> Optional[Dict]:
    proto = model.Proto()
    var_bounds = {}
    for idx, var in enumerate(proto.variables):
        bounds = _domain_bounds(list(var.domain))
        if bounds is None:
            continue
        var_bounds[idx] = bounds

    for c_idx, ct in enumerate(proto.constraints):
        if not ct.has_linear():
            continue
        linear = ct.linear
        expr_min = 0
        expr_max = 0
        for v_idx, coeff in zip(linear.vars, linear.coeffs):
            lb, ub = var_bounds.get(v_idx, (0, 0))
            if coeff >= 0:
                expr_min += coeff * lb
                expr_max += coeff * ub
            else:
                expr_min += coeff * ub
                expr_max += coeff * lb
        domain = list(linear.domain)
        if not _intervals_overlap(expr_min, expr_max, domain):
            involved = []
            for v_idx, coeff in zip(linear.vars, linear.coeffs):
                v = proto.variables[v_idx]
                vb = _domain_bounds(list(v.domain))
                involved.append(
                    {
                        "index": int(v_idx),
                        "name": v.name,
                        "coeff": int(coeff),
                        "domain": [int(vb[0]), int(vb[1])] if vb else None,
                    }
                )
            return {
                "constraint_index": c_idx,
                "constraint_type": "linear",
                "expression_min": int(expr_min),
                "expression_max": int(expr_max),
                "allowed_domain": [int(x) for x in domain],
                "involved_variables": involved[:30],
                "message": "linear expression range has empty intersection with constraint domain",
            }
    return None


def _collect_named_var_bounds(model: cp_model.CpModel, prefixes: List[str]) -> Dict[str, List[Dict]]:
    out = {p: [] for p in prefixes}
    for idx, var in enumerate(model.Proto().variables):
        name = var.name
        bounds = _domain_bounds(list(var.domain))
        if bounds is None:
            continue
        for prefix in prefixes:
            if name.startswith(prefix):
                out[prefix].append(
                    {"index": idx, "name": name, "min": int(bounds[0]), "max": int(bounds[1])}
                )
    return out


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


def _build_slot_weights(num_slots: int, start_time_minutes: int, slot_minutes: int, hourly_ranges: Dict) -> List[int]:
    slot_weights = [1 for _ in range(num_slots)]
    if not isinstance(hourly_ranges, dict):
        return slot_weights

    for window, weight in hourly_ranges.items():
        if not isinstance(window, str) or "-" not in window:
            continue
        try:
            start_hhmm, end_hhmm = window.split("-", 1)
            w_start = _hhmm_to_minutes(start_hhmm.strip())
            w_end = _hhmm_to_minutes(end_hhmm.strip())
            w_val = int(weight)
        except Exception:
            continue
        if w_end <= w_start:
            continue
        for s in range(num_slots):
            slot_start = start_time_minutes + s * slot_minutes
            if w_start <= slot_start < w_end:
                slot_weights[s] = w_val
    return slot_weights


def _solver_status_from_result(result: Dict) -> str:
    metrics = result.get("metrics") or {}
    status = metrics.get("solver_status")
    if status:
        return status
    if result.get("error"):
        return "INFEASIBLE"
    if result.get("schedule"):
        return "FEASIBLE"
    return "UNKNOWN"


def _run_hard_debug_diagnosis(
    employees: List[str],
    days: List[str],
    contracts: List[int],
    config: dict,
    roles: Optional[List[str]],
    unavailabilities: Optional[List],
    previous_month_stats: Optional[Dict],
) -> Dict:
    families = [
        "max_days_per_week",
        "repos_11h",
        "bloc_unique_par_jour",
        "min_staff",
        "optician_requirement",
    ]

    def _build_variant(disabled: List[str]) -> dict:
        cfg = copy.deepcopy(config)
        cfg["hard_debug_mode"] = False

        sched = cfg.setdefault("schedule", {})
        hard = cfg.setdefault("hard_constraints", {})

        if "max_days_per_week" in disabled:
            hard["max_days_per_week"] = max(7, len(days))
        if "repos_11h" in disabled:
            hard["rest_between_days_minutes"] = 0
            hard["weekly_rest_minutes"] = 0
        if "bloc_unique_par_jour" in disabled:
            hard["single_contiguous_block_per_day"] = False
        if "min_staff" in disabled:
            if isinstance(sched.get("min_staff_per_day"), (list, tuple)) and len(sched["min_staff_per_day"]) == len(days):
                sched["min_staff_per_day"] = [0 for _ in range(len(days))]
            else:
                sched["min_staff_per_slot"] = 0
        if "optician_requirement" in disabled:
            hard["require_qualified_optician"] = False

        return cfg

    tests = []
    first_feasible = None

    baseline_cfg = _build_variant([])
    baseline_result = build_and_solve_v1(
        employees=employees,
        days=days,
        contracts=contracts,
        config=baseline_cfg,
        roles=roles,
        unavailabilities=unavailabilities,
        previous_month_stats=previous_month_stats,
    )
    baseline_status = _solver_status_from_result(baseline_result)
    tests.append({
        "disabled": [],
        "active": families,
        "status": baseline_status,
    })

    for r in range(1, len(families) + 1):
        for combo in itertools.combinations(families, r):
            disabled = list(combo)
            cfg = _build_variant(disabled)
            result = build_and_solve_v1(
                employees=employees,
                days=days,
                contracts=contracts,
                config=cfg,
                roles=roles,
                unavailabilities=unavailabilities,
                previous_month_stats=previous_month_stats,
            )
            status = _solver_status_from_result(result)
            entry = {
                "disabled": disabled,
                "active": [f for f in families if f not in disabled],
                "status": status,
            }
            tests.append(entry)

            if first_feasible is None and status in ("FEASIBLE", "OPTIMAL"):
                first_feasible = entry

    return {
        "baseline_status": baseline_status,
        "tests": tests,
        "first_feasible_after_disabling": first_feasible,
    }


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
    min_daily_min = hard.get("min_daily_minutes", 0)
    contract_mode = hard.get("contract_hours_mode", "soft")
    if hard.get("contract_hours_hard", False):
        contract_mode = "hard"
    if contract_mode not in ("hard", "soft", "off"):
        contract_mode = "soft"
    contract_tolerance_slots = hard.get("contract_hours_tolerance_slots", 0)
    contract_overtime_slots = hard.get("contract_overtime_slots", 0)
    debug_cfg = config.get("debug_diagnosis", {})
    debug_mode = bool(debug_cfg.get("enabled", False))
    debug_solver_logs = bool(debug_cfg.get("solver_logs", False))
    deep_debug_mode = bool(config.get("deep_debug_mode", False) or debug_cfg.get("deep_debug", False))
    hard_debug_mode = bool(config.get("hard_debug_mode", False))

    weights = config.get("soft_weights", {})
    fast_solve = config.get("fast_solve", False)

    w_balance = weights.get("hours_balancing", 10)
    w_saturday = 0 if fast_solve else weights.get("saturday_fairness", 5)
    w_contiguity = 0 if fast_solve else weights.get(
        "contiguity_penalty",
        weights.get("contiguity", 1),
    )
    w_contract_target = 0 if fast_solve else weights.get("contract_target", 50)
    w_contract_under = weights.get("contract_target_under")
    w_contract_over = weights.get("contract_target_over")
    w_contract_overtime = 0 if fast_solve else weights.get("contract_overtime_penalty", 0)
    w_weekly_fairness = 0 if fast_solve else weights.get("weekly_hours_fairness", 0)
    w_close_fairness = 0 if fast_solve else weights.get("close_fairness", 0)
    w_late_fairness = 0 if fast_solve else weights.get("late_fairness_penalty", 0)
    w_amplitude_fairness = 0 if fast_solve else weights.get("amplitude_fairness", 0)
    w_max_daily_penalty = 0 if fast_solve else weights.get("max_daily_hours_penalty", 20)
    w_target_staffing_penalty = 0 if fast_solve else weights.get("target_staffing_penalty", 5)
    w_overstaffing_penalty = 0 if fast_solve else weights.get("overstaffing_penalty", 1)
    w_days_concentration_penalty = 0 if fast_solve else weights.get("days_concentration_penalty", 0)
    w_long_day_requirement = 0 if fast_solve else weights.get("long_day_requirement", 0)
    w_non_template_penalty = 0 if fast_solve else weights.get("non_template_penalty", 0)
    w_template_deviation = 0 if fast_solve else weights.get("template_deviation_weight", 0)
    w_shift_type_presence = 0 if fast_solve else weights.get("shift_type_presence_penalty", 2)
    w_hourly_demand = 0 if fast_solve else weights.get("hourly_demand_weight", 2)
    days_concentration_target_days = weights.get("days_concentration_target_days", 5)
    shift_templates = config.get("shift_templates", [])
    if contract_mode == "off":
        w_contract_target = 0

    long_term_weight = config.get("long_term_equity_weight", 0.0)

    solver_cfg = config.get("solver", {})
    max_time = config.get("solver_max_time_seconds", solver_cfg.get("max_time_seconds", 45))
    num_workers = config.get("solver_num_workers", solver_cfg.get("num_search_workers", 8))
    log_search_progress = config.get("solver_log_search_progress", debug_solver_logs)
    closed_weekdays = set(config.get("closed_weekdays", []))
    start_date_str = config.get("start_date")
    start_date = None
    if isinstance(start_date_str, str):
        try:
            start_date = date.fromisoformat(start_date_str)
        except ValueError:
            start_date = None
    closed_day_indices = []
    for d in range(num_days):
        if start_date is not None:
            weekday_index = (start_date + timedelta(days=d)).weekday()
        else:
            weekday_index = d % 7
        if weekday_index in closed_weekdays:
            closed_day_indices.append(d)
    closed_day_set = set(closed_day_indices)
    if debug_mode:
        logger.info(f"closed_days_debug start_date={start_date_str}")
        for d in range(min(10, num_days)):
            current_date = (start_date + timedelta(days=d)).isoformat() if start_date is not None else None
            weekday_index = (start_date + timedelta(days=d)).weekday() if start_date is not None else (d % 7)
            logger.info(
                "closed_days_debug day_index=%s current_date=%s weekday_index=%s is_closed=%s",
                d,
                current_date,
                weekday_index,
                weekday_index in closed_weekdays,
            )

    num_slots = (end_time_minutes - start_time_minutes) // slot_minutes
    weeks_equivalent = num_days / 7.0
    weekly_hours_total = sum(contracts)
    computed_monthly_capacity_hours = weekly_hours_total * weeks_equivalent
    max_daily_slots_by_hard = max_daily_min // slot_minutes if max_daily_min > 0 else num_slots
    max_daily_slots_by_hard = min(num_slots, max_daily_slots_by_hard)
    full_weeks = num_days // 7
    remaining_days = num_days % 7
    max_days_cap = (
        full_weeks * max_days_week + min(remaining_days, max_days_week)
        if max_days_week > 0
        else num_days
    )
    use_day_list = isinstance(min_staff_per_day, (list, tuple)) and len(min_staff_per_day) == num_days
    required_slots_per_day = [
        (
            0
            if d in closed_day_set
            else (min_staff_per_day[d] if use_day_list else min_staff)
        ) * num_slots
        for d in range(num_days)
    ]
    total_required_slots = sum(required_slots_per_day)
    total_contract_slots = int(round(computed_monthly_capacity_hours * 60 / slot_minutes))
    per_employee_max_slots = []
    for c in contracts:
        max_slots_hard = max_daily_slots_by_hard * max_days_cap
        if hard.get("max_weekly_hours", True):
            max_slots_hard = min(max_slots_hard, int(round(c * 60 / slot_minutes * weeks_equivalent)))
        per_employee_max_slots.append(max_slots_hard)
    total_max_feasible_slots = sum(per_employee_max_slots)
    hard_debug_summary = {
        "total_required_hours": total_required_slots * slot_minutes / 60.0,
        "total_contract_hours": computed_monthly_capacity_hours,
        "weekly_hours_total": weekly_hours_total,
        "weeks_equivalent": weeks_equivalent,
        "computed_monthly_capacity": computed_monthly_capacity_hours,
        "required_slots_per_day": required_slots_per_day,
        "max_possible_slots_per_employee": per_employee_max_slots,
        "max_feasible_hours_under_hard": total_max_feasible_slots * slot_minutes / 60.0,
        "theoretical_margin_hours": (total_max_feasible_slots - total_required_slots) * slot_minutes / 60.0,
        "hard_constraints": {
            "max_weekly_hours": hard.get("max_weekly_hours", True),
            "max_days_per_week": max_days_week,
            "max_daily_minutes": max_daily_min,
            "rest_between_days_minutes": rest_min,
            "weekly_rest_minutes": weekly_rest_min,
            "require_qualified_optician": require_optician,
            "min_daily_minutes": min_daily_min,
        },
    }
    deep_debug_checks = []
    if deep_debug_mode:
        window_minutes = end_time_minutes - start_time_minutes
        earliest_end = start_time_minutes + slot_minutes
        latest_start = end_time_minutes - slot_minutes
        max_next_day_gap = (24 * 60 - earliest_end) + latest_start
        for e in range(num_employees):
            unavailable_days = set()
            if unavailabilities:
                for entry in unavailabilities:
                    if len(entry) == 2 and entry[0] == e:
                        unavailable_days.add(entry[1])
                    elif len(entry) == 3 and entry[0] == e:
                        # Une indisponibilité partielle n'annule pas la journée.
                        continue
            available_days = num_days - len(unavailable_days)
            max_theoretical_days = available_days
            if rest_min > max_next_day_gap:
                max_theoretical_days = min(available_days, (num_days + 1) // 2)
            weekly_cap_over_4w = max_days_week * 4
            deep_debug_checks.append(
                {
                    "employee": employees[e],
                    "available_days": available_days,
                    "max_theoretical_days_rest_block": max_theoretical_days,
                    "max_days_per_week_x4": weekly_cap_over_4w,
                    "potential_inconsistency": max_theoretical_days < weekly_cap_over_4w,
                    "rest_minutes": rest_min,
                    "single_block_per_day": bool(hard.get("single_contiguous_block_per_day", True)),
                    "schedule_window_minutes": window_minutes,
                }
            )
    if debug_mode:
        logger.info("=== HARD DIAGNOSIS ===")
        logger.info(f"weekly_hours_total: {weekly_hours_total:.2f}")
        logger.info(f"weeks_equivalent: {weeks_equivalent:.4f}")
        logger.info(f"computed_monthly_capacity: {computed_monthly_capacity_hours:.2f}")
        for key, value in hard_debug_summary["hard_constraints"].items():
            logger.info(f"HARD {key}: {value}")
        logger.info(f"Required weekly hours: {hard_debug_summary['total_required_hours']:.2f}")
        logger.info(f"Total contract hours: {hard_debug_summary['total_contract_hours']:.2f}")
        logger.info(
            "Max feasible under hard constraints: "
            f"{hard_debug_summary['max_feasible_hours_under_hard']:.2f}"
        )
        logger.info(
            "Theoretical margin before solve: "
            f"{hard_debug_summary['theoretical_margin_hours']:.2f}h"
        )
        logger.info(f"Required slots per day: {required_slots_per_day}")
        logger.info(f"Max possible slots per employee: {per_employee_max_slots}")
    slot_weights = _build_slot_weights(
        num_slots,
        start_time_minutes,
        slot_minutes,
        config.get("hourly_demand_weights", {}),
    )

    x = {}
    for e in range(num_employees):
        for d in range(num_days):
            for s in range(num_slots):
                x[(e, d, s)] = model.NewBoolVar(f"x_{e}_{d}_{s}")
                if d in closed_day_set:
                    model.Add(x[(e, d, s)] == 0)

    add_contract_minimum_constraint(
        model,
        x,
        num_employees,
        num_days,
        num_slots,
        contracts,
        slot_minutes,
    )

    if isinstance(min_staff_per_day, (list, tuple)) and len(min_staff_per_day) == num_days:
        adjusted_min_staff_per_day = [
            0 if d in closed_day_set else min_staff_per_day[d]
            for d in range(num_days)
        ]
        add_min_coverage(model, x, num_employees, num_days, num_slots, adjusted_min_staff_per_day)
    else:
        adjusted_min_staff_per_day = [
            0 if d in closed_day_set else min_staff
            for d in range(num_days)
        ]
        add_min_coverage(model, x, num_employees, num_days, num_slots, adjusted_min_staff_per_day)
    if hard.get("max_weekly_hours", True):
        add_max_weekly_hours(model, x, num_employees, num_days, num_slots, contracts, slot_minutes)
    # max_daily_hours is now a soft constraint (penalized in objective)
    if min_daily_min > 0:
        add_min_daily_work_duration(model, x, num_employees, num_days, num_slots,
                                    slot_minutes, min_daily_minutes=min_daily_min)
    relax_single_block_for_test = bool(config.get("relax_single_block_for_test", False))
    if hard.get("single_contiguous_block_per_day", True) and not relax_single_block_for_test:
        add_single_contiguous_block_per_day(model, x, num_employees, num_days, num_slots)
    add_max_days_per_week(model, x, num_employees, num_days, num_slots, max_days=max_days_week)
    if require_optician and roles is not None:
        add_qualified_optician_coverage(
            model,
            x,
            num_employees,
            num_days,
            num_slots,
            roles,
            closed_days=closed_day_indices,
        )
    if unavailabilities:
        add_unavailabilities(model, x, unavailabilities, num_slots)
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
                                                employees=employees)
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
        penalties = add_contiguity_preference(model, x, num_employees, num_days, num_slots,
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
    if w_days_concentration_penalty > 0:
        penalties = add_days_concentration_penalty(
            model,
            x,
            num_employees,
            num_days,
            num_slots,
            target_days=days_concentration_target_days,
            weight=w_days_concentration_penalty,
        )
        all_penalties.extend(penalties)
        phase2_penalties.extend(penalties)
        penalty_groups["days_concentration"] = penalties
    if w_long_day_requirement > 0:
        penalties = add_long_day_requirement_penalty(
            model,
            x,
            num_employees,
            num_days,
            num_slots,
            slot_minutes,
            threshold_minutes=420,
            min_long_days=1,
            weight=w_long_day_requirement,
        )
        all_penalties.extend(penalties)
        phase2_penalties.extend(penalties)
        penalty_groups["long_day_requirement"] = penalties
    if w_non_template_penalty > 0:
        penalties = add_non_template_penalty(
            model,
            x,
            num_employees,
            num_days,
            num_slots,
            start_time_minutes,
            end_time_minutes,
            slot_minutes,
            shift_templates=shift_templates,
            weight=w_non_template_penalty,
            template_deviation_weight=w_template_deviation,
            shift_type_presence_weight=w_shift_type_presence,
        )
        all_penalties.extend(penalties)
        phase2_penalties.extend(penalties)
        penalty_groups["non_template"] = penalties
    if w_hourly_demand > 0:
        penalties = add_hourly_demand_reward(
            model,
            x,
            num_employees,
            num_days,
            num_slots,
            slot_weights=slot_weights,
            reward_weight=w_hourly_demand,
        )
        all_penalties.extend(penalties)
        phase2_penalties.extend(penalties)
        penalty_groups["hourly_demand"] = penalties
    if w_max_daily_penalty > 0:
        penalties = add_max_daily_hours_penalty(model, x, num_employees, num_days, num_slots,
                                                slot_minutes,
                                                max_daily_minutes=max_daily_min,
                                                weight=w_max_daily_penalty)
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
                                              weight=w_weekly_fairness)
        all_penalties.extend(penalties)
        phase2_penalties.extend(penalties)
        penalty_groups["weekly_hours_fairness"] = penalties
    if w_close_fairness > 0:
        penalties = add_close_fairness(model, x, num_employees, num_days, num_slots,
                                       weight=w_close_fairness)
        all_penalties.extend(penalties)
        phase2_penalties.extend(penalties)
        penalty_groups["close_fairness"] = penalties
    if w_late_fairness > 0:
        late_threshold = sched.get("late_threshold_minutes", end_time_minutes - slot_minutes)
        penalties = add_late_days_fairness(
            model,
            x,
            num_employees,
            num_days,
            num_slots,
            start_time_minutes,
            slot_minutes,
            late_threshold_minutes=late_threshold,
            weight=w_late_fairness,
        )
        all_penalties.extend(penalties)
        phase2_penalties.extend(penalties)
        penalty_groups["late_fairness"] = penalties
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

    deep_debug_report = None
    if deep_debug_mode:
        try:
            with open("debug_model.pbtxt", "w") as f:
                f.write(str(model))
            logger.info("Deep debug: exported model to debug_model.pbtxt")
        except Exception as exc:
            logger.error("Deep debug: failed to export debug_model.pbtxt: %s", exc)

        critical_bounds = _collect_named_var_bounds(
            model,
            prefixes=["worked_days_week_", "late_days_month_"],
        )
        total_worked_slots_bounds = []
        contract_minimum_bounds = []
        for e in range(num_employees):
            ub_slots = num_days * num_slots
            lb_contract = 0
            if contracts[e] > 0:
                lb_contract = int((contracts[e] * 60 + slot_minutes - 1) // slot_minutes)
            total_worked_slots_bounds.append(
                {
                    "employee": employees[e],
                    "name": f"total_worked_slots_emp_{e}",
                    "min": 0,
                    "max": ub_slots,
                }
            )
            contract_minimum_bounds.append(
                {
                    "employee": employees[e],
                    "min_required_slots": lb_contract,
                    "max_possible_slots": ub_slots,
                    "potential_inconsistency": lb_contract > ub_slots,
                }
            )

        first_linear_contradiction = _find_first_linear_domain_contradiction(model)
        if first_linear_contradiction:
            logger.error(
                "Deep debug: first linear contradiction at constraint #%s",
                first_linear_contradiction["constraint_index"],
            )
        else:
            logger.info("Deep debug: no static linear contradiction detected before solve.")

        logger.info("Deep debug variable bounds: worked_days_week=%s", len(critical_bounds["worked_days_week_"]))
        logger.info("Deep debug variable bounds: late_days_month=%s", len(critical_bounds["late_days_month_"]))
        logger.info("Deep debug synthetic bounds: total_worked_slots=%s", total_worked_slots_bounds)
        logger.info("Deep debug contract minimum check=%s", contract_minimum_bounds)
        for item in deep_debug_checks:
            logger.info("Deep debug employee check: %s", item)

        deep_debug_report = {
            "exported_model_file": "debug_model.pbtxt",
            "num_variables": num_variables,
            "num_constraints": num_constraints,
            "critical_bounds": {
                "worked_days_week": critical_bounds["worked_days_week_"],
                "late_days_month": critical_bounds["late_days_month_"],
                "total_worked_slots": total_worked_slots_bounds,
                "contract_minimum": contract_minimum_bounds,
            },
            "employee_theoretical_checks": deep_debug_checks,
            "first_linear_domain_contradiction": first_linear_contradiction,
        }

    def build_solver():
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max_time
        solver.parameters.num_search_workers = num_workers
        solver.parameters.random_seed = 42
        solver.parameters.log_search_progress = True if deep_debug_mode else log_search_progress
        solver.parameters.cp_model_presolve = True
        solver.parameters.log_to_stdout = True if deep_debug_mode else debug_solver_logs
        solver.parameters.linearization_level = 1
        solver.parameters.search_branching = cp_model.AUTOMATIC_SEARCH
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

    status_name = solver.StatusName(status) if solver is not None else "UNKNOWN"

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
        "total_internal_hours": 0.0,
        "objective_value": obj_val,
        "objective_breakdown": objective_breakdown,
    }
    metrics["best_bound"] = solver.BestObjectiveBound() if solver is not None else None
    metrics["wall_time"] = solver.WallTime() if solver is not None else solver_wall_time
    metrics["num_conflicts"] = solver.NumConflicts() if solver is not None else None
    metrics["num_branches"] = solver.NumBranches() if solver is not None else None
    if hard_debug_mode:
        hard_debug_report = _run_hard_debug_diagnosis(
            employees=employees,
            days=days,
            contracts=contracts,
            config=config,
            roles=roles,
            unavailabilities=unavailabilities,
            previous_month_stats=previous_month_stats,
        )
        metrics["hard_debug_mode_report"] = hard_debug_report
        first = hard_debug_report.get("first_feasible_after_disabling")
        if first:
            logger.info(
                "HARD debug first feasible: disabled=%s active=%s status=%s",
                first["disabled"],
                first["active"],
                first["status"],
            )
        else:
            logger.info("HARD debug: no feasible combination found.")
    if debug_mode:
        metrics["hard_debug"] = hard_debug_summary
    if deep_debug_mode and deep_debug_report is not None:
        metrics["deep_debug"] = deep_debug_report

    if warnings:
        metrics["warnings"] = warnings

    logger.info(f"Solver: status={status_name}, time={solver_wall_time}s, gap={gap}%")

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"error": "Aucune solution trouvée par le solveur.", "metrics": metrics}

    schedule = {}
    coverage_slots_per_day = {}
    for e in range(num_employees):
        emp_name = employees[e]
        schedule[emp_name] = {"days": {}, "total_hours": 0.0}
        coverage_slots_per_day[emp_name] = {}
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
                coverage_slots_per_day[emp_name][days[d]] = slots_worked

    planning_matrix = {
        "slot_minutes": slot_minutes,
        "num_slots": num_slots,
        "days": days,
        "employees": {
            employees[e]: {
                "contract_hours": contracts[e] if e < len(contracts) else 0,
                "coverage_slots_per_day": coverage_slots_per_day.get(employees[e], {}),
                "internal_slots_per_day": {},
            }
            for e in range(num_employees)
        },
    }
    kpi = compute_global_kpi(planning_matrix, employees, config)

    return {
        "schedule": schedule,
        "metrics": metrics,
        "internal_hours_per_employee": {emp: 0.0 for emp in employees},
        "internal_hours_per_day": {emp: {} for emp in employees},
        "coverage_slots_per_day": coverage_slots_per_day,
        "internal_slots_per_day": {emp: {} for emp in employees},
        "kpi": kpi,
    }
