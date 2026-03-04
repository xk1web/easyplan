from __future__ import annotations

from typing import Dict, List


def build_v1_explanation(*, solver_status: str, kpi: Dict[str, float]) -> Dict[str, List[str] | str]:
    if solver_status == "INFEASIBLE":
        summary = "Aucun planning conforme n'a ete trouve (INFEASIBLE)."
    elif solver_status == "UNKNOWN":
        summary = "Resolution interrompue avant preuve de faisabilite (timeout)."
    elif solver_status == "FEASIBLE":
        summary = "Un planning conforme a ete trouve (FEASIBLE)."
    elif solver_status == "OPTIMAL":
        summary = "Un planning conforme a ete trouve (OPTIMAL)."
    else:
        summary = f"Statut solveur: {solver_status}."

    details = [
        f"Heures contractuelles totales: {kpi.get('total_heures_contractuelles', 0.0)}h",
        f"Heures de couverture requises: {kpi.get('total_heures_requises_couverture', 0.0)}h",
        f"Heures planifiees: {kpi.get('total_heures_planifiees', 0.0)}h",
        f"Surstaffing net: {kpi.get('surstaffing_net', 0.0)}h",
        f"Sous-couverture nette: {kpi.get('sous_couverture_nette', 0.0)}h",
        f"Taux de tension: {kpi.get('taux_tension_percent', 0.0)}%",
    ]

    return {
        "summary": summary,
        "details": details,
    }
