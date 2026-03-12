from typing import Dict, List, Any


def explain_planning(result: Dict[str, Any], employees: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyse le résultat du solveur et produit une explication métier du planning.

    Parameters
    ----------
    result : dict
        sortie du moteur (hours_per_employee, kpi, etc.)
    employees : list
        liste des employés avec contrat hebdomadaire

    Returns
    -------
    dict
        {
            employee_analysis,
            coverage_analysis,
            global_analysis
        }
    """

    employee_analysis = _analyze_employees(result, employees)
    coverage_analysis = _analyze_coverage(result, employees)
    global_analysis = _global_message(coverage_analysis)

    return {
        "employee_analysis": employee_analysis,
        "coverage_analysis": coverage_analysis,
        "global_analysis": global_analysis,
    }

def _analyze_employees(result: Dict[str, Any], employees: List[Dict[str, Any]]) -> List[Dict[str, Any]]:

    hours_per_employee = result.get("hours_per_employee", {})

    analysis = []

    for emp in employees:

        emp_id = emp["id"]
        contract = emp["contract_hours"]

        planned = hours_per_employee.get(emp_id, 0.0)

        delta = round(planned - contract, 2)

        if delta < -0.25:
            status = "under_contract"
            cause = "volume ouverture insuffisant"

        elif delta > 0.25:
            status = "over_contract"
            cause = "contrainte couverture élevée"

        else:
            status = "balanced"
            cause = "équilibre planning"

        analysis.append({
            "employee_id": emp_id,
            "contract_hours": contract,
            "planned_hours": planned,
            "delta_hours": delta,
            "status": status,
            "probable_cause": cause
        })

    return analysis

def _analyze_coverage(result: Dict[str, Any], employees: List[Dict[str, Any]]) -> Dict[str, Any]:

    kpi = result.get("kpi", {})

    total_required = kpi.get("total_heures_requises_couverture", 0.0)

    total_contract = sum(emp["contract_hours"] for emp in employees)

    if total_contract == 0:
        tension = 0.0
    else:
        tension = round(total_required / total_contract, 2)

    if tension > 1.05:
        status = "understaffed"
    elif tension < 0.95:
        status = "overstaffed"
    else:
        status = "balanced"

    return {
        "total_required_hours": total_required,
        "total_contract_hours": total_contract,
        "tension_rate": tension,
        "coverage_status": status
    }

def _global_message(coverage: Dict[str, Any]) -> Dict[str, str]:

    required = coverage["total_required_hours"]
    contract = coverage["total_contract_hours"]

    delta = round(required - contract, 2)

    if delta > 0:
        msg = (
            f"Les contrats ne permettent pas de couvrir totalement l'ouverture. "
            f"{delta} heures de sous-couverture apparaissent."
        )

    elif delta < 0:
        msg = (
            f"Le volume contractuel dépasse le besoin d'ouverture. "
            f"{abs(delta)} heures de surstaffing structurel."
        )

    else:
        msg = "Le volume contractuel correspond exactement au besoin d'ouverture."

    return {"message": msg}

"""
Exemple d'utilisation

result = run_weekly_v1_engine(...)
employees = [{"id": "E1", "contract_hours": 35}, {"id": "E2", "contract_hours": 35}]
explanation = explain_planning(result, employees)
print(explanation["global_analysis"]["message"])
"""
