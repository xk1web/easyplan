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


def add_contract_target_penalty(model, x, num_employees, num_days, num_slots,
                                contracts, slot_minutes, weight=50,
                                weight_under=None, weight_over=None):
    penalties = []

    if weight_under is None:
        weight_under = weight
    if weight_over is None:
        weight_over = weight

    for e in range(num_employees):
        if contracts[e] <= 0:
            continue

        contract_slots_e = int(round(contracts[e] * 60 / slot_minutes * (num_days / 7.0)))
        contract_slots_e = min(contract_slots_e, num_days * num_slots)

        emp_slots = sum(
            x[(e, d, s)]
            for d in range(num_days)
            for s in range(num_slots)
        )

        under = model.NewIntVar(0, num_days * num_slots, f"contract_under_{e}")
        over = model.NewIntVar(0, num_days * num_slots, f"contract_over_{e}")
        model.Add(emp_slots - contract_slots_e == over - under)

        if weight_under > 0:
            penalties.append((under, weight_under))
        if weight_over > 0:
            penalties.append((over, weight_over))

    return penalties


def _get_weeks(num_days):
    weeks = []
    start = 0
    while start < num_days:
        end = min(start + 7, num_days)
        weeks.append(list(range(start, end)))
        start = end
    return weeks


def add_weekly_hours_fairness(model, x, num_employees, num_days, num_slots,
                              contracts, slot_minutes, weight=5,
                              weight_under=None, weight_over=None):
    penalties = []

    if weight_under is None:
        weight_under = weight
    if weight_over is None:
        weight_over = weight

    weeks = _get_weeks(num_days)
    for e in range(num_employees):
        weekly_target_slots = contracts[e] * 60 / slot_minutes
        for w_idx, week_days in enumerate(weeks):
            target_slots = int(round(weekly_target_slots * len(week_days) / 7.0))
            target_slots = min(target_slots, len(week_days) * num_slots)

            week_slots = sum(
                x[(e, d, s)]
                for d in week_days
                for s in range(num_slots)
            )

            under = model.NewIntVar(0, len(week_days) * num_slots, f"week_under_{e}_{w_idx}")
            over = model.NewIntVar(0, len(week_days) * num_slots, f"week_over_{e}_{w_idx}")
            model.Add(week_slots - target_slots == over - under)

            if weight_under > 0:
                penalties.append((under, weight_under))
            if weight_over > 0:
                penalties.append((over, weight_over))

    return penalties


def add_close_fairness(model, x, num_employees, num_days, num_slots, weight=5):
    penalties = []
    if num_slots <= 0:
        return penalties

    last_slot = num_slots - 1
    close_counts = []
    for e in range(num_employees):
        close_slots = sum(x[(e, d, last_slot)] for d in range(num_days))
        close_counts.append(close_slots)

    total_close = sum(close_counts)

    for e in range(num_employees):
        penalty = model.NewIntVar(0, num_days, f"close_pen_{e}")
        model.Add(penalty >= close_counts[e] * num_employees - total_close)
        penalties.append((penalty, weight))

    return penalties


def _daily_amplitude_slots(model, x, e, d, num_slots):
    start_candidates = []
    end_candidates = []

    for s in range(num_slots):
        sc = model.NewIntVar(0, num_slots, f"amp_start_c_{e}_{d}_{s}")
        model.Add(sc == s).OnlyEnforceIf(x[(e, d, s)])
        model.Add(sc == num_slots).OnlyEnforceIf(x[(e, d, s)].Not())
        start_candidates.append(sc)

        ec = model.NewIntVar(0, num_slots, f"amp_end_c_{e}_{d}_{s}")
        model.Add(ec == s + 1).OnlyEnforceIf(x[(e, d, s)])
        model.Add(ec == 0).OnlyEnforceIf(x[(e, d, s)].Not())
        end_candidates.append(ec)

    start = model.NewIntVar(0, num_slots, f"amp_start_{e}_{d}")
    end = model.NewIntVar(0, num_slots, f"amp_end_{e}_{d}")
    model.AddMinEquality(start, start_candidates)
    model.AddMaxEquality(end, end_candidates)

    amp_raw = model.NewIntVar(-num_slots, num_slots, f"amp_raw_{e}_{d}")
    model.Add(amp_raw == end - start)
    amp = model.NewIntVar(0, num_slots, f"amp_{e}_{d}")
    zero = model.NewConstant(0)
    model.AddMaxEquality(amp, [amp_raw, zero])
    return amp


def add_amplitude_fairness(model, x, num_employees, num_days, num_slots, weight=3):
    penalties = []
    total_amplitudes = []

    for e in range(num_employees):
        day_amps = []
        for d in range(num_days):
            day_amps.append(_daily_amplitude_slots(model, x, e, d, num_slots))
        total_amp = model.NewIntVar(0, num_days * num_slots, f"amp_total_{e}")
        model.Add(total_amp == sum(day_amps))
        total_amplitudes.append(total_amp)

    total_all = sum(total_amplitudes)

    for e in range(num_employees):
        penalty = model.NewIntVar(0, num_days * num_slots, f"amp_pen_{e}")
        model.Add(penalty >= total_amplitudes[e] * num_employees - total_all)
        penalties.append((penalty, weight))

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
