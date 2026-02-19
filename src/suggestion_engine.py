from typing import Any, Dict, List, Optional, Tuple


def compute_coverage_hours(config: dict, num_days: int) -> float:
    sched = config.get("schedule", config)
    slot_minutes = sched.get("slot_minutes", 15)
    start_time_minutes = sched.get("start_time_minutes", 9 * 60 + 30)
    end_time_minutes = sched.get("end_time_minutes", 20 * 60 + 15)
    min_staff = sched.get("min_staff_per_slot", 1)
    min_staff_per_day = sched.get("min_staff_per_day")
    num_slots = (end_time_minutes - start_time_minutes) // slot_minutes
    if isinstance(min_staff_per_day, (list, tuple)) and len(min_staff_per_day) == num_days:
        total_required_slots = sum(min_staff_per_day) * num_slots
    else:
        total_required_slots = num_days * num_slots * min_staff
    return total_required_slots * slot_minutes / 60.0


def compute_capacity_hours(contracts: List[int], num_days: int) -> float:
    return sum(contracts) * (num_days / 7.0)


def compute_capacity_with_overtime_hours(contracts: List[int], num_days: int, config: dict) -> float:
    sched = config.get("schedule", config)
    slot_minutes = sched.get("slot_minutes", 15)
    hard = config.get("hard_constraints", {})
    overtime_slots = hard.get("contract_overtime_slots", 0)
    full_weeks = num_days // 7
    base = compute_capacity_hours(contracts, num_days)
    extra = len(contracts) * full_weeks * overtime_slots * slot_minutes / 60.0
    return base + extra


def classify_result(
    *,
    validation_error: Optional[str],
    solver_status: Optional[str],
    coverage_total_hours: float,
    capacity_total_hours: float,
    capacity_with_overtime_hours: float,
    total_overtime_used_hours: Optional[float],
) -> str:
    if validation_error:
        if capacity_total_hours < coverage_total_hours:
            return "infeasible_structural"
        return "infeasible_constraints"

    if solver_status in ("INFEASIBLE", "MODEL_INVALID"):
        if capacity_with_overtime_hours < coverage_total_hours:
            return "infeasible_structural"
        return "infeasible_constraints"

    if solver_status in ("FEASIBLE", "OPTIMAL"):
        if total_overtime_used_hours and total_overtime_used_hours > 0:
            return "feasible_with_tension"
        return "feasible_no_tension"

    return "unknown"


def generate_suggestions(
    *,
    classification: str,
    coverage_total_hours: float,
    capacity_total_hours: float,
    capacity_with_overtime_hours: float,
    total_overtime_used_hours: Optional[float],
    require_optician: bool,
    rest_between_days_minutes: int,
    max_days_per_week: int,
    has_unavailabilities: bool,
    hours_per_employee: Optional[Dict[str, float]],
    contracts: Optional[List[float]],
    inequity_threshold_ratio: float,
    solver_status: Optional[str],
) -> Tuple[List[str], List[str]]:
    suggestions: List[str] = []
    reason_codes_set = set()

    if classification == "infeasible_structural":
        reason_codes_set.add("capacity_below_coverage")
        suggestions.append("Augmenter la capacité (contrats/équipe) ou réduire la couverture minimale.")
        if capacity_with_overtime_hours < coverage_total_hours:
            reason_codes_set.add("overtime_insufficient")
            suggestions.append("Augmenter l’overtime autorisé si possible (ou revoir les contrats).")
        return suggestions, sorted(reason_codes_set)

    if classification == "infeasible_constraints":
        if require_optician:
            reason_codes_set.add("constraint_optician_required")
        if rest_between_days_minutes >= 660:
            reason_codes_set.add("constraint_rest_11h")
        if max_days_per_week < 7:
            reason_codes_set.add("constraint_max_days")
        if has_unavailabilities:
            reason_codes_set.add("constraint_unavailability")
        suggestions.append(
            "Infeasible lié aux contraintes : vérifier repos 11h, opticien requis, indisponibilités, max jours/horaires."
        )
        suggestions.append("Ajuster les indisponibilités ou augmenter la polyvalence/qualification si applicable.")
        return suggestions, sorted(reason_codes_set)

    if classification == "feasible_with_tension":
        reason_codes_set.add("overtime_used")
        suggestions.append("Planning faisable avec overtime : surveiller la charge et envisager un renfort." )
        if total_overtime_used_hours and total_overtime_used_hours > 0:
            reason_codes_set.add("overtime_used")
            suggestions.append("Rééquilibrer la charge ou ajuster les contrats pour réduire l’overtime.")
        if total_overtime_used_hours is not None:
            overtime_capacity = max(0.0, capacity_with_overtime_hours - capacity_total_hours)
            if overtime_capacity > 0 and total_overtime_used_hours >= overtime_capacity:
                reason_codes_set.add("overtime_saturated")
                suggestions.append("Overtime saturé : risque de sous-capacité si la demande augmente.")
        return suggestions, sorted(reason_codes_set)

    def _maybe_add_relative_inequity() -> None:
        if solver_status not in ("FEASIBLE", "OPTIMAL"):
            return
        if not hours_per_employee or not contracts:
            return
        ratios = []
        for idx, (emp, hours) in enumerate(hours_per_employee.items()):
            if idx >= len(contracts):
                continue
            contract_hours = contracts[idx]
            if contract_hours and contract_hours > 0:
                ratios.append(hours / contract_hours)
        if ratios:
            relative_gap = max(ratios) - min(ratios)
            if relative_gap > inequity_threshold_ratio:
                reason_codes_set.add("high_relative_inequity")
                suggestions.append("Répartition déséquilibrée par rapport aux contrats.")

    if classification == "feasible_no_tension":
        _maybe_add_relative_inequity()
        return suggestions, sorted(reason_codes_set)

    _maybe_add_relative_inequity()

    return suggestions, sorted(reason_codes_set)
