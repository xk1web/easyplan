from ortools.sat.python import cp_model


def add_monthly_hours_balancing(model, x, num_employees, num_days, num_slots,
                                contracts, slot_minutes, weight=10,
                                previous_month_stats=None, long_term_equity_weight=0.0,
                                employees=None, internal=None):
    penalties = []

    total_contract = sum(contracts)
    if total_contract == 0:
        return penalties

    total_available_slots = num_days * num_slots

    for e in range(num_employees):
        emp_slots = sum(
            x[(e, d, s)] + (internal[(e, d, s)] if internal is not None else 0)
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
                                weight_under=None, weight_over=None, internal=None):
    penalties = []
    deviation_terms = []

    if weight_under is None:
        weight_under = weight * 5
    if weight_over is None:
        weight_over = weight

    for e in range(num_employees):
        if contracts[e] <= 0:
            continue

        contract_slots_e = int(round(contracts[e] * 60 / slot_minutes))
        contract_slots_e = min(contract_slots_e, num_days * num_slots)

        emp_slots = sum(
            x[(e, d, s)] + (internal[(e, d, s)] if internal is not None else 0)
            for d in range(num_days)
            for s in range(num_slots)
        )

        under = model.NewIntVar(0, num_days * num_slots, f"contract_under_{e}")
        over = model.NewIntVar(0, num_days * num_slots, f"contract_over_{e}")
        model.Add(emp_slots - contract_slots_e == over - under)

        deviation = model.NewIntVar(0, num_days * num_slots, f"contract_dev_{e}")
        model.Add(deviation == under + over)
        deviation_terms.append(deviation)

        if weight_under > 0:
            penalties.append((under, weight_under))
        if weight_over > 0:
            penalties.append((over, weight_over))

    return penalties, deviation_terms


def add_contract_minimum_constraint(
    model,
    x,
    num_employees,
    num_days,
    num_slots,
    contracts,
    slot_minutes,
):
    """
    Enforce that each employee works at least their weekly contract hours.
    No prorata by num_days.
    """

    for e in range(num_employees):
        if contracts[e] <= 0:
            continue

        contract_minutes_e = int(contracts[e] * 60)

        daily_worked_slots = [
            cp_model.LinearExpr.Sum(
                [
                    x[(e, d, s)]
                    for s in range(num_slots)
                ]
            )
            for d in range(num_days)
        ]
        total_worked_slots = cp_model.LinearExpr.Sum(daily_worked_slots)
        model.Add(total_worked_slots * slot_minutes >= contract_minutes_e)


def add_max_daily_hours_penalty(model, x, num_employees, num_days, num_slots,
                                slot_minutes, max_daily_minutes=600, weight=20, internal=None):
    penalties = []
    max_daily_slots = max_daily_minutes // slot_minutes
    for e in range(num_employees):
        for d in range(num_days):
            daily_slots = sum(
                x[(e, d, s)] + (internal[(e, d, s)] if internal is not None else 0)
                for s in range(num_slots)
            )
            excess = model.NewIntVar(0, num_slots, f"max_daily_excess_{e}_{d}")
            model.Add(excess >= daily_slots - max_daily_slots)
            penalties.append((excess, weight))
    return penalties


def add_overstaffing_penalty(model, x, num_employees, num_days, num_slots,
                             min_staff_per_slot, min_staff_per_day=None, weight=1):
    penalties = []
    use_day_list = isinstance(min_staff_per_day, (list, tuple)) and len(min_staff_per_day) == num_days
    for d in range(num_days):
        required = min_staff_per_day[d] if use_day_list else min_staff_per_slot
        for s in range(num_slots):
            assigned = sum(x[(e, d, s)] for e in range(num_employees))
            excess = model.NewIntVar(0, num_employees, f"overstaff_{d}_{s}")
            model.Add(excess >= assigned - required)
            penalties.append((excess, weight))
    return penalties


def add_target_staffing_penalty(model, x, num_employees, num_days, num_slots,
                                target_staff_per_slot, weight=5):
    penalties = []
    for d in range(num_days):
        for s in range(num_slots):
            assigned = sum(x[(e, d, s)] for e in range(num_employees))
            shortfall = model.NewIntVar(0, num_employees, f"understaff_{d}_{s}")
            model.Add(shortfall >= target_staff_per_slot - assigned)
            penalties.append((shortfall, weight))
    return penalties


def add_hourly_demand_reward(
    model,
    x,
    num_employees,
    num_days,
    num_slots,
    slot_weights,
    reward_weight=1,
):
    """
    Reward coverage on high-demand slots.
    Returned terms use negative coefficients so they reduce the minimization objective.
    """
    penalties = []
    if reward_weight <= 0:
        return penalties

    for d in range(num_days):
        for s in range(num_slots):
            slot_w = slot_weights[s] if s < len(slot_weights) else 1
            if slot_w <= 0:
                continue
            coverage_count = model.NewIntVar(0, num_employees, f"demand_cov_{d}_{s}")
            model.Add(coverage_count == sum(x[(e, d, s)] for e in range(num_employees)))
            penalties.append((coverage_count, -int(reward_weight * slot_w)))
    return penalties


def add_days_concentration_penalty(
    model,
    x,
    num_employees,
    num_days,
    num_slots,
    target_days=5,
    weight=3,
):
    penalties = []
    for e in range(num_employees):
        worked_day_vars = []
        for d in range(num_days):
            worked_day = model.NewBoolVar(f"worked_day_{e}_{d}")
            daily_slots = sum(x[(e, d, s)] for s in range(num_slots))
            model.Add(daily_slots >= 1).OnlyEnforceIf(worked_day)
            model.Add(daily_slots == 0).OnlyEnforceIf(worked_day.Not())
            worked_day_vars.append(worked_day)

        total_worked_days = sum(worked_day_vars)
        penalty_days = model.NewIntVar(0, num_days, f"penalty_days_{e}")
        model.Add(penalty_days >= total_worked_days - target_days)
        penalties.append((penalty_days, weight))

    return penalties


def add_daily_balance_penalty(
    model,
    x,
    contracts,
    num_employees,
    num_days,
    num_slots,
    slot_minutes,
    target_days=5,
    tolerance_minutes=60,
    weight=4,
):
    penalties = []
    if weight <= 0 or target_days <= 0:
        return penalties
    tolerance_slots = max(0, (tolerance_minutes + slot_minutes - 1) // slot_minutes)

    for e in range(num_employees):
        target_daily_slots = int(round((contracts[e] * 60 / slot_minutes) / target_days))
        for d in range(num_days):
            daily_slots = sum(x[(e, d, s)] for s in range(num_slots))
            worked_day = model.NewBoolVar(f"daily_balance_worked_day_{e}_{d}")
            model.Add(daily_slots >= 1).OnlyEnforceIf(worked_day)
            model.Add(daily_slots == 0).OnlyEnforceIf(worked_day.Not())

            raw_deviation = model.NewIntVar(0, num_slots, f"daily_balance_raw_deviation_{e}_{d}")
            model.Add(raw_deviation >= daily_slots - target_daily_slots)
            model.Add(raw_deviation >= target_daily_slots - daily_slots)
            model.Add(raw_deviation == 0).OnlyEnforceIf(worked_day.Not())

            effective_deviation = model.NewIntVar(0, num_slots, f"daily_balance_effective_deviation_{e}_{d}")
            model.Add(effective_deviation >= raw_deviation - tolerance_slots)
            model.Add(effective_deviation >= 0)
            model.Add(effective_deviation == 0).OnlyEnforceIf(worked_day.Not())
            penalties.append((effective_deviation, weight))

    return penalties


def add_long_day_requirement_penalty(
    model,
    x,
    num_employees,
    num_days,
    num_slots,
    slot_minutes,
    threshold_minutes=420,
    min_long_days=1,
    weight=5,
):
    penalties = []
    if weight <= 0 or threshold_minutes <= 0 or min_long_days <= 0:
        return penalties

    threshold_slots = max(1, threshold_minutes // slot_minutes)

    for e in range(num_employees):
        long_day_flags = []
        for d in range(num_days):
            daily_slots = sum(x[(e, d, s)] for s in range(num_slots))
            is_long_day = model.NewBoolVar(f"is_long_day_{e}_{d}")
            model.Add(daily_slots >= threshold_slots).OnlyEnforceIf(is_long_day)
            model.Add(daily_slots <= threshold_slots - 1).OnlyEnforceIf(is_long_day.Not())
            long_day_flags.append(is_long_day)

        total_long_days = model.NewIntVar(0, num_days, f"total_long_days_{e}")
        model.Add(total_long_days == sum(long_day_flags))

        shortage = model.NewIntVar(0, min_long_days, f"long_day_shortage_{e}")
        model.Add(shortage >= min_long_days - total_long_days)
        penalties.append((shortage, weight))

    return penalties


def add_non_template_penalty(
    model,
    x,
    num_employees,
    num_days,
    num_slots,
    start_time_minutes,
    end_time_minutes,
    slot_minutes,
    shift_templates,
    weight=3,
    template_deviation_weight=1,
    shift_type_presence_weight=2,
):
    penalties = []
    if weight <= 0 or not isinstance(shift_templates, list):
        return penalties

    valid_templates = []
    for template in shift_templates:
        if not isinstance(template, dict):
            continue
        try:
            t_name = str(template.get("name", "")).strip().lower()
            t_start = int(template.get("start"))
            t_end = int(template.get("end"))
        except (TypeError, ValueError):
            continue
        if t_end <= t_start:
            continue
        if t_start < start_time_minutes or t_end > end_time_minutes:
            continue
        if (t_start - start_time_minutes) % slot_minutes != 0:
            continue
        if (t_end - start_time_minutes) % slot_minutes != 0:
            continue

        start_slot = (t_start - start_time_minutes) // slot_minutes
        end_slot = (t_end - start_time_minutes) // slot_minutes
        if start_slot < 0 or end_slot > num_slots or end_slot <= start_slot:
            continue
        valid_templates.append((t_name, start_slot, end_slot))

    if not valid_templates:
        return penalties

    for e in range(num_employees):
        shift_choices_by_template = [[] for _ in valid_templates]
        for d in range(num_days):
            daily_slots = sum(x[(e, d, s)] for s in range(num_slots))
            worked_day = model.NewBoolVar(f"tpl_worked_day_{e}_{d}")
            model.Add(daily_slots >= 1).OnlyEnforceIf(worked_day)
            model.Add(daily_slots == 0).OnlyEnforceIf(worked_day.Not())
            daily_minutes = model.NewIntVar(0, num_slots * slot_minutes, f"daily_minutes_{e}_{d}")
            model.Add(daily_minutes == daily_slots * slot_minutes)

            shift_choices = []
            duration_deviations = []
            for t_idx, (_, start_slot, end_slot) in enumerate(valid_templates):
                choice = model.NewBoolVar(f"shift_choice_{e}_{d}_{t_idx}")
                shift_choices.append(choice)
                shift_choices_by_template[t_idx].append(choice)
                for s in range(num_slots):
                    expected = 1 if start_slot <= s < end_slot else 0
                    model.Add(x[(e, d, s)] == expected).OnlyEnforceIf(choice)

                template_minutes = (end_slot - start_slot) * slot_minutes
                deviation_t = model.NewIntVar(
                    0,
                    num_slots * slot_minutes,
                    f"template_duration_deviation_{e}_{d}_{t_idx}",
                )
                model.Add(deviation_t >= daily_minutes - template_minutes)
                model.Add(deviation_t >= template_minutes - daily_minutes)
                duration_deviations.append(deviation_t)

            model.Add(sum(shift_choices) <= 1)

            matched_template = model.NewBoolVar(f"matched_template_{e}_{d}")
            model.AddMaxEquality(matched_template, shift_choices)

            non_template = model.NewIntVar(0, 1, f"non_template_penalty_{e}_{d}")
            model.Add(non_template >= worked_day - matched_template)
            model.Add(non_template <= worked_day)
            model.Add(non_template <= 1 - matched_template)
            penalties.append((non_template, weight))

            if template_deviation_weight > 0:
                min_duration_deviation = model.NewIntVar(
                    0,
                    num_slots * slot_minutes,
                    f"min_template_duration_deviation_{e}_{d}",
                )
                model.AddMinEquality(min_duration_deviation, duration_deviations)
                template_deviation = model.NewIntVar(
                    0,
                    num_slots * slot_minutes,
                    f"template_deviation_{e}_{d}",
                )
                model.Add(template_deviation == min_duration_deviation).OnlyEnforceIf(worked_day)
                model.Add(template_deviation == 0).OnlyEnforceIf(worked_day.Not())
                penalties.append((template_deviation, template_deviation_weight))

        for t_idx, (template_name, _, _) in enumerate(valid_templates):
            count_shift_type = model.NewIntVar(0, num_days, f"count_shift_type_{e}_{t_idx}")
            model.Add(count_shift_type == sum(shift_choices_by_template[t_idx]))

            if shift_type_presence_weight > 0 and template_name in ("closing", "morning"):
                shortage = model.NewIntVar(0, 1, f"{template_name}_shortage_{e}")
                model.Add(shortage >= 1 - count_shift_type)
                penalties.append((shortage, shift_type_presence_weight))

    return penalties


def add_internal_hours_penalty(model, internal, num_employees, num_days, num_slots, weight=1):
    penalties = []
    for e in range(num_employees):
        for d in range(num_days):
            for s in range(num_slots):
                penalties.append((internal[(e, d, s)], weight))
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
                              weight_under=None, weight_over=None, internal=None):
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
                x[(e, d, s)] + (internal[(e, d, s)] if internal is not None else 0)
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


def add_late_days_fairness(
    model,
    x,
    num_employees,
    num_days,
    num_slots,
    start_time_minutes,
    slot_minutes,
    late_threshold_minutes,
    weight=5,
):
    penalties = []
    if num_employees <= 0 or num_days <= 0 or num_slots <= 0:
        return penalties

    late_slot_indices = []
    for s in range(num_slots):
        slot_end = start_time_minutes + (s + 1) * slot_minutes
        if slot_end > late_threshold_minutes:
            late_slot_indices.append(s)

    if not late_slot_indices:
        return penalties

    late_days_month_vars = []
    for e in range(num_employees):
        closing_flags = []
        for d in range(num_days):
            closing_flag = model.NewBoolVar(f"closing_flag_{e}_{d}")
            late_slots = sum(x[(e, d, s)] for s in late_slot_indices)
            model.Add(late_slots >= 1).OnlyEnforceIf(closing_flag)
            model.Add(late_slots == 0).OnlyEnforceIf(closing_flag.Not())
            closing_flags.append(closing_flag)

        late_days_month = model.NewIntVar(0, num_days, f"late_days_month_{e}")
        model.Add(late_days_month == sum(closing_flags))
        late_days_month_vars.append(late_days_month)

    max_late_days = model.NewIntVar(0, num_days, "max_late_days_month")
    min_late_days = model.NewIntVar(0, num_days, "min_late_days_month")
    for e in range(num_employees):
        model.Add(max_late_days >= late_days_month_vars[e])
        model.Add(min_late_days <= late_days_month_vars[e])

    fairness_gap = model.NewIntVar(0, num_days, "fairness_gap")
    model.Add(fairness_gap == max_late_days - min_late_days)
    penalties.append((fairness_gap, weight))

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


def add_contiguity_preference(model, activity, num_employees, num_days, num_slots,
                              slot_minutes, weight=3):
    penalties = []
    for e in range(num_employees):
        for d in range(num_days):
            gap_reopens = []
            for s in range(1, num_slots):
                sb = model.NewBoolVar(f"sb_{e}_{d}_{s}")
                model.AddBoolOr([sb, activity[(e, d, s)].Not(), activity[(e, d, s - 1)]])
                model.AddHint(sb, 0)
                gap_reopens.append(sb)

            excess = model.NewIntVar(0, num_slots, f"excess_{e}_{d}")
            # Number of 0->1 transitions equals number of contiguous worked segments.
            # Penalize only above two segments to keep a light flexibility.
            model.Add(excess >= activity[(e, d, 0)] + sum(gap_reopens) - 2)
            model.AddHint(excess, 0)
            penalties.append((excess, weight))
    return penalties
