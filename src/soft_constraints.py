from ortools.sat.python import cp_model


def add_monthly_hours_balancing(model, x, num_employees, num_days, num_slots,
                                contracts, slot_minutes, weight=10,
                                previous_month_stats=None, long_term_equity_weight=0.0,
                                employees=None):
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

        if previous_month_stats and long_term_equity_weight > 0 and employees:
            prev_hours = previous_month_stats.get("total_hours", {})
            emp_name = employees[e] if e < len(employees) else None
            if emp_name and emp_name in prev_hours:
                prev_h = prev_hours[emp_name]
                expected_prev = contracts[e]
                delta_hours = prev_h - expected_prev
                delta_slots = int(delta_hours * 60 / slot_minutes * long_term_equity_weight)
                target_slots = max(0, target_slots - delta_slots)

        over = model.NewIntVar(0, num_days * num_slots, f"month_bal_over_{e}")
        under = model.NewIntVar(0, num_days * num_slots, f"month_bal_under_{e}")
        model.Add(emp_slots - target_slots == over - under)

        penalties.append((over, weight))
        penalties.append((under, weight))

    return penalties


def add_saturday_fairness(model, x, num_employees, num_days, num_slots,
                          days, slot_minutes, weight=5,
                          previous_month_stats=None, long_term_equity_weight=0.0,
                          employees=None):
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
        base_penalty_weight = weight

        if previous_month_stats and long_term_equity_weight > 0 and employees:
            prev_sats = previous_month_stats.get("saturdays_worked", {})
            emp_name = employees[e] if e < len(employees) else None
            if emp_name and emp_name in prev_sats:
                avg_prev_sats = sum(prev_sats.values()) / max(len(prev_sats), 1)
                emp_prev_sats = prev_sats[emp_name]
                if emp_prev_sats > avg_prev_sats:
                    extra = int((emp_prev_sats - avg_prev_sats) * long_term_equity_weight * weight)
                    base_penalty_weight = weight + extra

        penalty = model.NewIntVar(0, 1, f"sat_pen_{e}")
        model.Add(penalty >= sat_counts[e] * num_employees - total_sats)
        penalties.append((penalty, base_penalty_weight))

    return penalties


def add_contiguity_preference(model, x, num_employees, num_days, num_slots,
                              slot_minutes, weight=3):
    penalties = []
    for e in range(num_employees):
        for d in range(num_days):
            gap_reopens = []
            for s in range(1, num_slots):
                sb = model.NewBoolVar(f"sb_{e}_{d}_{s}")
                model.AddBoolOr([sb, x[(e, d, s)].Not(), x[(e, d, s - 1)]])
                model.AddHint(sb, 0)
                gap_reopens.append(sb)

            excess = model.NewIntVar(0, num_slots, f"excess_{e}_{d}")
            model.Add(excess >= x[(e, d, 0)] + sum(gap_reopens) - 1)
            model.AddHint(excess, 0)
            penalties.append((excess, weight))
    return penalties
