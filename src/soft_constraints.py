from ortools.sat.python import cp_model


def add_hours_balancing(model, x, num_employees, num_days, num_slots,
                        contracts, slot_minutes, weight=10):
    penalties = []

    total_contract = sum(contracts)
    if total_contract == 0:
        return penalties

    total_available_slots = num_days * num_slots

    for e in range(num_employees):
        emp_slots = sum(
            x[(e, d, s)]
            for d in range(num_days)
            for s in range(num_slots)
        )
        target_slots = int(contracts[e] / total_contract * total_available_slots)

        over = model.NewIntVar(0, num_days * num_slots, f"bal_over_{e}")
        under = model.NewIntVar(0, num_days * num_slots, f"bal_under_{e}")
        model.Add(emp_slots - target_slots == over - under)

        penalties.append((over, weight))
        penalties.append((under, weight))

    return penalties


def add_saturday_fairness(model, x, num_employees, num_days, num_slots,
                          days, slot_minutes, weight=5):
    penalties = []
    saturday_indices = [i for i, d in enumerate(days) if d.lower().startswith("sam")]
    if not saturday_indices:
        return penalties

    sat_counts = []
    for e in range(num_employees):
        sat_slots = sum(
            x[(e, d, s)]
            for d in saturday_indices
            for s in range(num_slots)
        )
        has_sat = model.NewBoolVar(f"has_sat_{e}")
        model.Add(sat_slots >= 1).OnlyEnforceIf(has_sat)
        model.Add(sat_slots == 0).OnlyEnforceIf(has_sat.Not())
        sat_counts.append(has_sat)

    total_sats = sum(sat_counts)
    for e in range(num_employees):
        penalty = model.NewIntVar(0, 1, f"sat_pen_{e}")
        model.Add(penalty >= sat_counts[e] * num_employees - total_sats)
        penalties.append((penalty, weight))

    return penalties


def add_contiguity_preference(model, x, num_employees, num_days, num_slots,
                              slot_minutes, weight=3):
    penalties = []
    for e in range(num_employees):
        for d in range(num_days):
            for s in range(num_slots - 1):
                transition = model.NewBoolVar(f"trans_{e}_{d}_{s}")
                diff = model.NewIntVar(-1, 1, f"diff_{e}_{d}_{s}")
                model.Add(diff == x[(e, d, s)] - x[(e, d, s + 1)])
                model.AddAbsEquality(transition, diff)
                penalties.append((transition, weight))
    return penalties
