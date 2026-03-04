from typing import Dict, List

from src.config import load_config
# LEGACY ENGINE - DO NOT USE
# from src.model_builder_v1 import build_and_solve_v1


def _build_case(num_employees: int) -> Dict:
    config = load_config()
    config["solver_max_time_seconds"] = 45
    config["solver_num_workers"] = 8
    config["solver_log_search_progress"] = True
    config["hard_constraints"]["max_days_per_week"] = 5

    employees = [f"E{i+1}" for i in range(num_employees)]
    contracts = [35 for _ in range(num_employees)]
    roles = ["opticien"] + ["vendeur" for _ in range(num_employees - 1)]
    days = [f"D{i+1}" for i in range(28)]

    return {
        "employees": employees,
        "contracts": contracts,
        "roles": roles,
        "days": days,
        "config": config,
    }


def _classify(metrics: Dict, timeout: float) -> str:
    status = metrics.get("solver_status")
    branches = metrics.get("num_branches") or 0
    wall_time = metrics.get("wall_time") or 0.0

    if status == "UNKNOWN" and branches > 500_000:
        return "Probable explosion combinatoire."
    if status == "UNKNOWN" and branches < 20_000:
        return "Blocage structurel ou mauvais branching (peu d'exploration)."
    if status in ("FEASIBLE", "OPTIMAL") and wall_time >= timeout * 0.9:
        return "Modèle solvable mais peu guidé (temps proche timeout)."
    if status in ("FEASIBLE", "OPTIMAL"):
        return "Résolution saine sur ce scénario."
    return "Diagnostic indéterminé avec ces métriques."


def _one_optimization(diags: List[str]) -> str:
    if any("explosion combinatoire" in d for d in diags):
        return "Optimisation ciblée: ajouter une stratégie de décision explicite (AddDecisionStrategy) sur les variables x, jour par jour."
    if any("peu d'exploration" in d for d in diags):
        return "Optimisation ciblée: imposer un warm-start (AddHint) avec un planning glouton simple pour fournir une première solution."
    if any("peu guidé" in d for d in diags):
        return "Optimisation ciblée: activer une phase objective en 2 étapes plus agressive (feasibility-first puis optimisation) pour converger plus vite."
    return "Optimisation ciblée: ajouter un warm-start glouton minimal pour améliorer l'orientation initiale du solveur."


def run_case(num_employees: int) -> str:
    case = _build_case(num_employees)
    result = build_and_solve_v1(
        employees=case["employees"],
        days=case["days"],
        contracts=case["contracts"],
        config=case["config"],
        roles=case["roles"],
    )
    metrics = result.get("metrics") or {}

    print(f"\n=== Benchmark {num_employees} employés ===")
    print("Status:", metrics.get("solver_status"))
    print("Wall time:", metrics.get("wall_time"))
    print("Branches:", metrics.get("num_branches"))
    print("Conflicts:", metrics.get("num_conflicts"))
    print("Best bound:", metrics.get("best_bound"))
    print("Objective:", metrics.get("objective_value"))

    diagnosis = _classify(metrics, case["config"]["solver_max_time_seconds"])
    print("Diagnostic:", diagnosis)
    return diagnosis


def main() -> None:
    diagnoses = []
    for n in [6, 8, 10]:
        diagnoses.append(run_case(n))

    print("\n=== Synthèse ===")
    print("Cause probable dominante:", diagnoses[-1])
    print(_one_optimization(diagnoses))


if __name__ == "__main__":
    main()
