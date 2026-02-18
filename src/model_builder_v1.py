from typing import List, Dict, Optional
from ortools.sat.python import cp_model


def _minutes_to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _hhmm_to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _build_contiguous_ranges(
    slots_worked: List[int],
    start_time_minutes: int,
    slot_minutes: int
) -> List[Dict[str, str]]:
    sorted_slots = sorted(slots_worked)
    ranges = []
    range_start = sorted_slots[0]
    prev = sorted_slots[0]

    for s in sorted_slots[1:]:
        if s == prev + 1:
            prev = s
        else:
            r_start = start_time_minutes + range_start * slot_minutes
            r_end = start_time_minutes + (prev + 1) * slot_minutes
            ranges.append({
                "start": _minutes_to_hhmm(r_start),
                "end": _minutes_to_hhmm(r_end)
            })
            range_start = s
            prev = s

    r_start = start_time_minutes + range_start * slot_minutes
    r_end = start_time_minutes + (prev + 1) * slot_minutes
    ranges.append({
        "start": _minutes_to_hhmm(r_start),
        "end": _minutes_to_hhmm(r_end)
    })

    return ranges


def _sum_ranges_hours(ranges: List[Dict[str, str]]) -> float:
    total_minutes = 0
    for r in ranges:
        total_minutes += _hhmm_to_minutes(r["end"]) - _hhmm_to_minutes(r["start"])
    return total_minutes / 60


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
        emp_name = employees[e]
        schedule[emp_name] = {"days": {}, "total_hours": 0.0}
        for d in range(num_days):
            slots_worked = [
                s for s in range(num_slots)
                if solver.Value(x[(e, d, s)]) == 1
            ]
            if slots_worked:
                ranges = _build_contiguous_ranges(
                    slots_worked, start_time_minutes, slot_minutes
                )
                model_hours = len(slots_worked) * slot_minutes / 60
                display_hours = _sum_ranges_hours(ranges)
                assert abs(model_hours - display_hours) < 1e-9, (
                    f"Incohérence heures {emp_name} {days[d]}: "
                    f"modèle={model_hours}h, affichage={display_hours}h"
                )
                schedule[emp_name]["days"][days[d]] = {
                    "ranges": ranges,
                    "hours": model_hours
                }
                schedule[emp_name]["total_hours"] += model_hours

    return {"schedule": schedule}
