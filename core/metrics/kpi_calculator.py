from __future__ import annotations

from typing import Any, Dict


def calculate_kpi(result: Dict[str, Any]) -> Dict[str, float]:
    """Build business KPIs from a solver result payload.

    The function is pure and only reads the given ``result`` dictionary.
    """
    kpi = result.get("kpi", {})
    explanation = result.get("explanation", {})
    coverage = explanation.get("coverage_analysis", {}) if isinstance(explanation, dict) else {}

    total_contract_hours = _pick_float(
        kpi,
        coverage,
        keys=("total_contract_hours", "total_heures_contractuelles"),
    )
    total_required_hours = _pick_float(
        kpi,
        coverage,
        keys=("total_required_hours", "total_heures_requises_couverture"),
    )

    hours_per_employee = result.get("hours_per_employee", {})
    total_planned_hours = _sum_hours(hours_per_employee)
    if total_planned_hours == 0.0:
        total_planned_hours = _pick_float(kpi, keys=("total_planned_hours", "total_heures_planifiees"))

    surstaffing_hours = max(0.0, total_planned_hours - total_required_hours)
    undercoverage_hours = max(0.0, total_required_hours - total_planned_hours)
    if total_contract_hours > 0:
        tension_rate = round(total_required_hours / total_contract_hours, 2)
    else:
        tension_rate = 0.0

    return {
        "total_contract_hours": round(total_contract_hours, 2),
        "total_required_hours": round(total_required_hours, 2),
        "total_planned_hours": round(total_planned_hours, 2),
        "surstaffing_hours": round(surstaffing_hours, 2),
        "undercoverage_hours": round(undercoverage_hours, 2),
        "tension_rate": tension_rate,
    }


def _pick_float(*sources: Any, keys: tuple[str, ...]) -> float:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = source.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return 0.0


def _sum_hours(hours_per_employee: Any) -> float:
    if not isinstance(hours_per_employee, dict):
        return 0.0
    total = 0.0
    for value in hours_per_employee.values():
        try:
            total += float(value)
        except (TypeError, ValueError):
            continue
    return total
