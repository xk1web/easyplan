from ortools.sat.python import cp_model

def generate_schedule(employees, days):
    model = cp_model.CpModel()

    # Variable : work[e][d] = 1 si employé e travaille le jour d
    work = {}
    for e in range(len(employees)):
        for d in range(len(days)):
            work[(e, d)] = model.NewBoolVar(f"work_{e}_{d}")

    # Contrainte : max 4 jours par employé
    for e in range(len(employees)):
        model.Add(sum(work[(e, d)] for d in range(len(days))) <= 4)

    # Contrainte : au moins 2 employés par jour
    for d in range(len(days)):
        model.Add(sum(work[(e, d)] for e in range(len(employees))) >= 2)

    # Exemple : Alice ne travaille pas mardi
    model.Add(work[(0, 1)] == 0)

    # Ancien planning simulé
    previous_schedule = {
        (0, 0): 1,
        (1, 1): 1,
        (2, 2): 1
    }

    change_penalties = []

    for e in range(len(employees)):
        for d in range(len(days)):
            previous = previous_schedule.get((e, d), 0)
            diff = model.NewBoolVar(f"diff_{e}_{d}")
            model.Add(work[(e, d)] != previous).OnlyEnforceIf(diff)
            model.Add(work[(e, d)] == previous).OnlyEnforceIf(diff.Not())
            change_penalties.append(diff)

    model.Minimize(sum(change_penalties))

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


if __name__ == "__main__":
    employees = ["Alice", "Bob", "Charlie"]
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    result = generate_schedule(employees, days)
    print(result)
