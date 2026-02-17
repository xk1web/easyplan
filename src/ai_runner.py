from validation import validate_global_feasibility
from model_builder_v1 import build_and_solve_v1

employees = ["Alice", "Bob", "Charlie", "David", "Eve", "Frank"]
days = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"]
contracts = [40, 20, 40, 40, 39, 30]
roles = ["opticien", "vendeur", "opticien", "opticien", "vendeur", "opticien"]

config = {
    "start_time_minutes": 9 * 60 + 30,
    "end_time_minutes": 20 * 60 + 15,
    "min_staff_per_slot": 1
}

print("=" * 40)
print("PIPELINE V1 MINIMALE")
print("=" * 40)

print("\n1. Validation structurelle...")
try:
    validate_global_feasibility(employees, contracts, days, config)
    print("   OK : faisabilité structurelle validée.")
except ValueError as e:
    print(f"   ÉCHEC : {e}")
    exit(1)

print("\n2. Construction modèle V1 + résolution...")
result = build_and_solve_v1(employees, days, contracts, config)

print("\n" + "=" * 40)
print("RÉSULTAT")
print("=" * 40)

if "error" in result:
    print(f"Erreur solveur : {result['error']}")
else:
    for emp, planning in result["schedule"].items():
        print(f"\n{emp} :")
        for day, info in planning.items():
            print(f"  {day} : {info['start']} → {info['end']} ({info['hours']}h)")
