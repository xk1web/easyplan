from typing import List, Optional


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

    total_required_slots = num_slots * num_days * min_staff
    total_required_hours = total_required_slots * slot_minutes / 60

    # contracts[] is interpreted as full weekly contractual hours (no scaling).
    total_available_hours = sum(contracts)

    if total_available_hours < total_required_hours:
        raise ValueError(
            f"Impossible structurellement : heures disponibles insuffisantes. "
            f"Disponible = {total_available_hours}h, "
            f"Requis = {total_required_hours}h"
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
