from scheduler_v2 import generate_schedule_v2

employees = ["Alice", "Bob", "Charlie", "David", "Eve", "Frank"]

# SEMAINE MAGASIN (6 jours typique optique)
days = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"]

contracts = [40, 20, 40, 40, 39, 30]
roles = ["opticien", "vendeur", "opticien", "opticien", "vendeur", "opticien"]

config = {
    "max_hours_per_day": 9,
    "min_daily_hours_general": 4,
    "short_day_threshold": 6,
    "min_staff_per_hour": 1
}



# ============================
# ANALYSE STRUCTURELLE
# ============================

weekly_open_hours = 11 * len(days)  # 9h → 20h = 11h
required_hours = weekly_open_hours * config["min_staff_per_hour"]
total_available = sum(contracts)

print("\nAnalyse structurelle :")
print("Heures nécessaires :", required_hours)
print("Heures disponibles :", total_available)

if total_available < required_hours:
    print("⚠ Sous-effectif structurel :", required_hours - total_available, "h")

# ============================
# LANCEMENT SOLVEUR
# ============================

relax_used = 0

print("\nTentative niveau strict...")

result = generate_schedule_v2(
    employees,
    days,
    contracts,
    roles,
    config,
    relax_level=0
)

if "error" in result:
    relax_used = 1
    print("Relâchement niveau 1...")
    result = generate_schedule_v2(
        employees,
        days,
        contracts,
        roles,
        config,
        relax_level=1
    )

if "error" in result:
    relax_used = 2
    print("Relâchement niveau 2...")
    result = generate_schedule_v2(
        employees,
        days,
        contracts,
        roles,
        config,
        relax_level=2
    )

print("\n==============================")
print("RÉSULTAT FINAL")
print("==============================")

if "error" in result:
    print("Impossible de produire un planning avec la structure actuelle.")
else:
    print(result["schedule"])

    print("\nAnalyse qualitative :")

    if relax_used == 0:
        print("Structure saine. Planning obtenu sans compromis.")
    elif relax_used == 1:
        print("Structure légèrement tendue.")
    elif relax_used == 2:
        print("Structure contractuelle tendue.")
