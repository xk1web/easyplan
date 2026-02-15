from ortools.sat.python import cp_model


def generate_schedule(employees, days, unavailable, contracts):
    model = cp_model.CpModel()

    work = {}

    for e in range(len(employees)):
        for d in range(len(days)):
            work[(e, d)] = model.NewBoolVar(f"work_{e}_{d}")

    # 1 jour = 8h
    hours_per_day = 8

    # Contrainte : respecter les heures contractuelles max
    for e in range(len(employees)):
        max_days = contracts[e] // hours_per_day
        model.Add(
            sum(work[(e, d)] for d in range(len(days))) <= max_days
        )

    # Contrainte : au moins 2 employés par jour
    for d in range(len(days)):
        model.Add(
            sum(work[(e, d)] for e in range(len(employees))) >= 2
        )

    # Indisponibilités
    for (emp_index, day_index) in unavailable:
        model.Add(work[(emp_index, day_index)] == 0)

    # Objectif simple : minimiser le total travaillé (pour éviter sur-remplissage)
    model.Minimize(
        sum(work[(e, d)] for e in range(len(employees)) for d in range(len(days)))
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
        return {"error": "No solution found"}
