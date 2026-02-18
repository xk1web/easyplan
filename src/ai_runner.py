import sys
from src.config import load_config
from src.validation import validate_global_feasibility
from src.model_builder_v1 import build_and_solve_v1

employees = ["Alice", "Bob", "Charlie", "David", "Eve", "Frank"]
days = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"]
contracts = [40, 20, 40, 40, 39, 30]
roles = ["opticien", "vendeur", "opticien", "opticien", "vendeur", "opticien"]

config = load_config()

unavailabilities = [
    (1, 5),
]

print("=" * 40)
print("MOTEUR DE PLANNING — OPTIQUE")
print("=" * 40)

print(f"\nMagasin : {config.get('store_name', 'défaut')}")
print(f"Employés : {len(employees)}")
print(f"Jours : {', '.join(days)}")

print("\n1. Validation structurelle et légale...")
try:
    validate_global_feasibility(employees, contracts, days, config, roles=roles)
    print("   OK : faisabilité validée.")
except ValueError as e:
    print(f"   ÉCHEC : {e}")
    sys.exit(1)

print("\n2. Construction modèle + résolution...")
result = build_and_solve_v1(
    employees, days, contracts, config,
    roles=roles, unavailabilities=unavailabilities
)

print("\n" + "=" * 40)
print("RÉSULTAT")
print("=" * 40)

if "error" in result:
    print(f"Erreur solveur : {result['error']}")
else:
    for emp, emp_data in result["schedule"].items():
        contract_idx = employees.index(emp)
        print(f"\n{emp} ({roles[contract_idx]}) — {emp_data['total_hours']}h / {contracts[contract_idx]}h contrat :")
        for day, info in emp_data["days"].items():
            ranges_str = ", ".join(
                f"{r['start']}→{r['end']}" for r in info["ranges"]
            )
            print(f"  {day} : {ranges_str} ({info['hours']}h)")
