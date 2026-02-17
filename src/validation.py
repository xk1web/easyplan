from typing import List


def validate_global_feasibility(
    employees: List[str],
    contracts: List[int],
    days: List[str],
    config: dict
) -> None:
    slot_minutes = 15
    start_time_minutes = config.get("start_time_minutes", 9 * 60 + 30)
    end_time_minutes = config.get("end_time_minutes", 20 * 60 + 15)
    min_staff = config.get("min_staff_per_slot", 1)

    num_slots = (end_time_minutes - start_time_minutes) // slot_minutes
    num_days = len(days)

    total_required_slots = num_slots * num_days * min_staff
    total_required_hours = total_required_slots * slot_minutes / 60

    total_available_hours = sum(contracts)

    if total_available_hours < total_required_hours:
        raise ValueError(
            f"Impossible structurellement : heures disponibles insuffisantes. "
            f"Disponible = {total_available_hours}h, "
            f"Requis = {total_required_hours}h"
        )
