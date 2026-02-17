from typing import List, Dict, Optional
from ortools.sat.python import cp_model


def build_and_solve_v1(
    employees: List[str],
    days: List[str],
    contracts: List[int],
    config: dict
) -> Dict:
    model = cp_model.CpModel()

    slot_minutes = 15
    start_time_minutes = config.get("start_time_minutes", 9 * 60 + 30)
    end_time_minutes = config.get("end_time_minutes", 20 * 60 + 15)
    min_staff = config.get("min_staff_per_slot", 1)

    num_slots = (end_time_minutes - start_time_minutes) // slot_minutes
    num_employees = len(employees)
    num_days = len(days)

    x = {}
    for e in range(num_employees):
        for d in range(num_days):
            for s in range(num_slots):
                x[(e, d, s)] = model.NewBoolVar(f"x_{e}_{d}_{s}")

    for d in range(num_days):
        for s in range(num_slots):
            model.Add(
                sum(x[(e, d, s)] for e in range(num_employees)) >= min_staff
            )

    for e in range(num_employees):
        total_slots = sum(
            x[(e, d, s)]
            for d in range(num_days)
            for s in range(num_slots)
        )
        max_slots = contracts[e] * 60 // slot_minutes
        model.Add(total_slots <= max_slots)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"error": "Aucune solution trouvée par le solveur."}

    schedule = {}
    for e in range(num_employees):
        schedule[employees[e]] = {}
        for d in range(num_days):
            slots_worked = [
                s for s in range(num_slots)
                if solver.Value(x[(e, d, s)]) == 1
            ]
            if slots_worked:
                first = min(slots_worked)
                last = max(slots_worked)
                s_start = start_time_minutes + first * slot_minutes
                s_end = start_time_minutes + (last + 1) * slot_minutes
                schedule[employees[e]][days[d]] = {
                    "start": f"{s_start // 60:02d}:{s_start % 60:02d}",
                    "end": f"{s_end // 60:02d}:{s_end % 60:02d}",
                    "hours": len(slots_worked) * slot_minutes / 60
                }

    return {"schedule": schedule}
