import logging
from datetime import date, timedelta
from typing import List, Optional


logger = logging.getLogger(__name__)


def validate_global_feasibility(
    employees: List[str],
    contracts: List[int],
    days: List[str],
    config: dict,
    roles: Optional[List[str]] = None,
    unavailabilities: Optional[List] = None
) -> None:
    sched = config.get("schedule", config)
    slot_minutes = sched.get("slot_minutes", 15)
    start_time_minutes = sched.get("start_time_minutes", 9 * 60 + 30)
    end_time_minutes = sched.get("end_time_minutes", 20 * 60 + 15)
    staffing = config.get("staffing", {})
    min_staff = staffing.get("min_staff_per_slot", sched.get("min_staff_per_slot", 1))

    hard = config.get("hard_constraints", {})
    max_daily_min = hard.get("max_daily_minutes", 600)

    num_slots = (end_time_minutes - start_time_minutes) // slot_minutes
    num_days = len(days)
    weeks_equivalent = num_days / 7.0
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
    open_days_count = num_days - len(closed_day_indices)

    min_staff_per_day = sched.get("min_staff_per_day")
    if isinstance(min_staff_per_day, (list, tuple)) and len(min_staff_per_day) == num_days:
        total_required_slots = 0
        for d in range(num_days):
            if d in closed_day_indices:
                continue
            total_required_slots += int(min_staff_per_day[d]) * num_slots
    else:
        total_required_slots = num_slots * open_days_count * min_staff
    total_required_hours = total_required_slots * slot_minutes / 60

    weekly_hours_total = sum(contracts)
    total_available_hours = weekly_hours_total * weeks_equivalent
    margin_hours = total_available_hours - total_required_hours

    debug_cfg = config.get("debug_diagnosis", {})
    if debug_cfg.get("enabled", False):
        logger.info("=== STRUCTURAL VALIDATION DEBUG ===")
        logger.info(f"num_days: {num_days}")
        logger.info(f"start_date: {start_date_str}")
        logger.info(f"closed_day_indices: {closed_day_indices}")
        logger.info(f"open_days_count: {open_days_count}")
        for d in range(min(10, num_days)):
            current_date = (start_date + timedelta(days=d)).isoformat() if start_date is not None else None
            weekday_index = (start_date + timedelta(days=d)).weekday() if start_date is not None else (d % 7)
            logger.info(
                "day_debug day_index=%s current_date=%s weekday_index=%s is_closed=%s",
                d,
                current_date,
                weekday_index,
                weekday_index in closed_weekdays,
            )
        logger.info(f"weekly_hours_total: {weekly_hours_total:.2f}")
        logger.info(f"weeks_equivalent: {weeks_equivalent:.4f}")
        logger.info(f"computed_monthly_capacity: {total_available_hours:.2f}")
        logger.info(f"required_hours recalculated: {total_required_hours:.2f}")
        logger.info(f"margin_hours: {margin_hours:.2f}")

    if total_available_hours < total_required_hours:
        raise ValueError(
            f"Impossible structurellement : heures disponibles insuffisantes. "
            f"Disponible = {total_available_hours:.1f}h, "
            f"Requis = {total_required_hours:.1f}h, "
            f"Margin = {margin_hours:.1f}h"
        )

    daily_open_hours = (end_time_minutes - start_time_minutes) / 60
    if max_daily_min / 60 < daily_open_hours and len(employees) * max_daily_min / 60 < daily_open_hours * min_staff:
        raise ValueError(
            f"Impossible : avec max {max_daily_min / 60}h/jour/employé et "
            f"{len(employees)} employés, impossible de couvrir "
            f"{daily_open_hours}h d'ouverture avec {min_staff} personne(s) min."
        )

    for i, contract in enumerate(contracts):
        if contract < 0:
            raise ValueError(
                f"Contrat invalide pour {employees[i]} : {contract}h (négatif)"
            )

    if roles is not None:
        optician_count = sum(1 for r in roles if r == "opticien")
        if optician_count == 0 and hard.get("require_qualified_optician", True):
            raise ValueError(
                "Aucun opticien diplômé dans l'équipe — "
                "RULE 5.1 : au moins un opticien requis pendant l'ouverture."
            )

    if len(employees) != len(contracts):
        raise ValueError(
            f"Incohérence : {len(employees)} employés mais {len(contracts)} contrats."
        )

    if roles is not None and len(roles) != len(employees):
        raise ValueError(
            f"Incohérence : {len(employees)} employés mais {len(roles)} rôles."
        )
