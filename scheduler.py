from ortools.sat.python import cp_model


def generate_schedule(
    employees,
    days,
    unavailable,
    contracts,
    coverage_per_day,
    roles,
    required_opticians_per_day,
    preferences
):
    hours_per_day = 8

    # ----------------------------
    # PRÉ-CHECK CAPACITÉ GLOBALE
    # ----------------------------

    max_capacity = 0
    for e in range(len(employees)):
        max_days = contracts[e] // hours_per_day
        max_capacity += max_days

    total_required = sum(coverage_per_day)

    if max_capacity < total_required:
        return {
            "error": "Impossible schedule",
            "reason": f"Demanded shifts ({total_required}) exceed maximum capacity ({max_capacity})."
        }

    # ----------------------------
    # SOLVEUR
    # ----------------------------

    model = cp_model.CpModel()
    work = {}

    for e in range(len(employees)):
        for d in range(len(days)):
            work[(e, d)] = model.NewBoolVar(f"work_{e}_{d}")

    # Contraintes contractuelles
    for e in range(len(employees)):
        target_hours = contracts[e]

        max_days = target_hours // hours_per_day
        min_days = max_days - 1 if max_days > 0 else 0

        total_days = sum(work[(e, d)] for d in range(len(days)))

        model.Add(total_days <= max_days)
        model.Add(total_days >= min_days)

    # Couverture variable
    for d in range(len(days)):
        required = coverage_per_day[d]
        model.Add(
            sum(work[(e, d)] for e in range(len(employees)))
            >= required
        )

    # Qualification
    for d in range(len(days)):
        model.Add(
            sum(
                work[(e, d)]
                for e in range(len(employees))
                if roles[e] == "opticien"
            )
            >= required_opticians_per_day
        )

    # Indisponibilités (hard)
    for (emp_index, day_index) in unavailable:
        model.Add(work[(emp_index, day_index)] == 0)

    # ----------------------------
    # SOFT CONSTRAINTS (préférences)
    # ----------------------------

    penalties = []

    for (emp_index, day_index) in preferences:
        penalty = model.NewBoolVar(f"penalty_{emp_index}_{day_index}")
        model.Add(work[(emp_index, day_index)] == 1).OnlyEnforceIf(penalty)
        penalties.append(penalty)

    # Objectif : minimiser shifts + pénalités
    model.Minimize(
        sum(work[(e, d)] for e in range(len(employees)) for d in range(len(days)))
        + sum(penalties)
    )

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        schedule = {}
        for e in range(len(employees)):
            schedule[employees[e]] = []
            for d in range(len(days)):
                if solver.Value(work[(e, d)]) == 1:
                    schedule[employees[e]].append(days[d])
        return schedule
    else:
        return {"error": "No solution found by solver"}
