from ortools.sat.python import cp_model

def generate_schedule():
    model = cp_model.CpModel()

    employees = ["Alice", "Bob", "Charlie"]
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    # Variable : work[e][d] = 1 si employé e travaille le jour d
    work = {}
    for e in range(len(employees)):
        for d in range(len(days)):
            work[(e, d)] = model.NewBoolVar(f"work_{e}_{d}")

    # Contrainte : max 3 jours par employé
    for e in range(len(employees)):
        model.Add(sum(work[(e, d)] for d in range(len(days))) <= 3)

    # Contrainte : Alice ne travaille pas mardi
    model.Add(work[(0, 1)] == 0)

    # Objectif simple : maximiser le nombre total de jours travaillés
    model.Maximize(
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

if __name__ == "__main__":
    result = generate_schedule()
    print(result)
