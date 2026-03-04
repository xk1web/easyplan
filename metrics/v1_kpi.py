from __future__ import annotations

from typing import Dict, Tuple

from model.weekly_model import WeeklyModelArtifacts


def compute_v1_kpi(
    artifacts: WeeklyModelArtifacts,
    x_values: Dict[Tuple[int, int, int], int],
) -> Dict[str, float]:
    slot_hours = artifacts.slot_minutes / 60.0

    total_contract_hours = float(sum(artifacts.contracts_hours))

    required_slots = 0
    planned_slots = 0
    overstaff_slots = 0
    undercoverage_slots = 0

    for d in range(artifacts.num_days):
        required = int(artifacts.min_staff_per_day[d])
        for s in range(artifacts.num_slots):
            assigned = sum(
                int(x_values.get((e, d, s), 0))
                for e in range(artifacts.num_employees)
            )
            required_slots += required
            planned_slots += assigned
            overstaff_slots += max(0, assigned - required)
            undercoverage_slots += max(0, required - assigned)

    total_required_hours = required_slots * slot_hours
    total_planned_hours = planned_slots * slot_hours
    surstaffing_net = overstaff_slots * slot_hours
    sous_couverture_nette = undercoverage_slots * slot_hours
    taux_tension = 0.0
    if total_required_hours > 0:
        taux_tension = (sous_couverture_nette / total_required_hours) * 100.0

    return {
        "total_heures_contractuelles": round(total_contract_hours, 2),
        "total_heures_requises_couverture": round(total_required_hours, 2),
        "total_heures_planifiees": round(total_planned_hours, 2),
        "surstaffing_net": round(surstaffing_net, 2),
        "sous_couverture_nette": round(sous_couverture_nette, 2),
        "taux_tension_percent": round(taux_tension, 2),
    }
