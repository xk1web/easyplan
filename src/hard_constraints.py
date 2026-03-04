from ortools.sat.python import cp_model


def get_weeks(num_days):
    weeks = []
    start = 0
    while start < num_days:
        end = min(start + 7, num_days)
        weeks.append(list(range(start, end)))
        start = end
    return weeks


def add_min_coverage(model, x, num_employees, num_days, num_slots, min_staff):
    is_list = isinstance(min_staff, (list, tuple))
    for d in range(num_days):
        required = min_staff[d] if is_list else min_staff
        for s in range(num_slots):
            model.Add(
                sum(x[(e, d, s)] for e in range(num_employees)) >= required
            )


def add_max_weekly_hours(model, x, num_employees, num_days, num_slots, contracts, slot_minutes, internal=None):
    weeks = get_weeks(num_days)
    for e in range(num_employees):
        weekly_hours = contracts[e]
        max_slots = weekly_hours * 60 // slot_minutes
        print(
            "Employee", e,
            "weekly_hours:", weekly_hours,
            "slot_minutes:", slot_minutes,
            "computed max_slots:", max_slots
        )
        for week_days in weeks:
            week_slots = sum(
                x[(e, d, s)] + (internal[(e, d, s)] if internal is not None else 0)
                for d in week_days
                for s in range(num_slots)
            )
            model.Add(week_slots <= max_slots)


def add_max_days_per_week(model, x, num_employees, num_days, num_slots, max_days=6, work=None):
    weeks = get_weeks(num_days)
    for e in range(num_employees):
        for week_days in weeks:
            day_worked_vars = []
            for d in week_days:
                worked = model.NewBoolVar(f"day_worked_{e}_{d}")
                daily_slots = sum((work or x)[(e, d, s)] for s in range(num_slots))
                model.Add(daily_slots >= 1).OnlyEnforceIf(worked)
                model.Add(daily_slots == 0).OnlyEnforceIf(worked.Not())
                day_worked_vars.append(worked)
            week_idx = week_days[0] // 7
            worked_days_week = model.NewIntVar(0, len(week_days), f"worked_days_week_{e}_{week_idx}")
            model.Add(worked_days_week == sum(day_worked_vars))
            model.Add(worked_days_week <= max_days)


def _build_prefix_sums(model, x, e, d, num_slots, name_prefix):
    prefix = []
    for s in range(num_slots):
        p = model.NewIntVar(0, num_slots, f"{name_prefix}_{e}_{d}_{s}")
        if s == 0:
            model.Add(p == x[(e, d, s)])
        else:
            model.Add(p == prefix[s - 1] + x[(e, d, s)])
        prefix.append(p)
    return prefix


def _build_prefix_sums_work(model, work, e, d, num_slots, name_prefix):
    prefix = []
    for s in range(num_slots):
        p = model.NewIntVar(0, num_slots, f"{name_prefix}_{e}_{d}_{s}")
        if s == 0:
            model.Add(p == work[(e, d, s)])
        else:
            model.Add(p == prefix[s - 1] + work[(e, d, s)])
        prefix.append(p)
    return prefix


def add_weekly_rest_35h(model, x, num_employees, num_days, num_slots,
                        start_time_minutes, slot_minutes, rest_minutes=2100, work=None):
    if rest_minutes <= 0:
        return

    prefix_cache = {}

    def get_prefix(e, d):
        key = (e, d)
        if key not in prefix_cache:
            if work is None:
                prefix_cache[key] = _build_prefix_sums(
                    model, x, e, d, num_slots, "pref_weekly_rest"
                )
            else:
                prefix_cache[key] = _build_prefix_sums_work(
                    model, work, e, d, num_slots, "pref_weekly_rest"
                )
        return prefix_cache[key]

    for e in range(num_employees):
        for d in range(num_days - 2):
            d_mid = d + 1
            d_after = d + 2

            has_work_mid = model.NewBoolVar(f"work_mid_{e}_{d_mid}")
            mid_slots = sum((work or x)[(e, d_mid, s)] for s in range(num_slots))
            model.Add(mid_slots >= 1).OnlyEnforceIf(has_work_mid)
            model.Add(mid_slots == 0).OnlyEnforceIf(has_work_mid.Not())

            prefix_after = get_prefix(e, d_after)

            for s_end in range(num_slots):
                end_minutes = start_time_minutes + (s_end + 1) * slot_minutes
                needed = rest_minutes - (48 * 60 - end_minutes) - start_time_minutes
                if needed <= 0:
                    continue
                earliest_slot = (needed + slot_minutes - 1) // slot_minutes
                if earliest_slot <= 0:
                    continue
                t = earliest_slot - 1
                if t >= num_slots:
                    t = num_slots - 1
                model.Add(prefix_after[t] == 0).OnlyEnforceIf(
                    [(work or x)[(e, d, s_end)], has_work_mid.Not()]
                )


def add_min_daily_work_duration(model, x, num_employees, num_days, num_slots,
                                slot_minutes, min_daily_minutes=240, work=None):
    if min_daily_minutes <= 0:
        return
    min_daily_slots = min_daily_minutes // slot_minutes
    for e in range(num_employees):
        for d in range(num_days):
            day_worked = model.NewBoolVar(f"min_dur_worked_{e}_{d}")
            daily_slots = sum((work or x)[(e, d, s)] for s in range(num_slots))
            model.Add(daily_slots >= 1).OnlyEnforceIf(day_worked)
            model.Add(daily_slots == 0).OnlyEnforceIf(day_worked.Not())
            model.Add(daily_slots >= min_daily_slots).OnlyEnforceIf(day_worked)


def add_single_contiguous_block_per_day(model, x, num_employees, num_days, num_slots, work=None):
    activity = work or x
    for e in range(num_employees):
        for d in range(num_days):
            start_flags = []
            for s in range(1, num_slots):
                start_flag = model.NewBoolVar(f"start_flag_{e}_{d}_{s}")
                # start_flag_s = 1 iff activity[s] == 1 and activity[s-1] == 0
                model.Add(start_flag <= activity[(e, d, s)])
                model.Add(start_flag <= 1 - activity[(e, d, s - 1)])
                model.Add(start_flag >= activity[(e, d, s)] - activity[(e, d, s - 1)])
                start_flags.append(start_flag)

            starts_count = activity[(e, d, 0)] + sum(start_flags)
            model.Add(starts_count <= 1)


def add_max_daily_hours(model, x, num_employees, num_days, num_slots,
                        slot_minutes, max_daily_minutes=600, work=None):
    max_daily_slots = max_daily_minutes // slot_minutes
    for e in range(num_employees):
        for d in range(num_days):
            daily_slots = sum((work or x)[(e, d, s)] for s in range(num_slots))
            model.Add(daily_slots <= max_daily_slots)


def add_qualified_optician_coverage(model, x, num_employees, num_days, num_slots, roles, closed_days=None):
    optician_indices = [e for e in range(num_employees) if roles[e] == "opticien"]
    if not optician_indices:
        raise ValueError("Aucun opticien diplômé dans l'équipe — RULE 5.1 impossible.")
    closed_days_set = set(closed_days or [])
    opening_slot = 0
    closing_slot = num_slots - 1
    for d in range(num_days):
        if d in closed_days_set:
            continue
        model.Add(sum(x[(e, d, opening_slot)] for e in optician_indices) >= 1)
        model.Add(sum(x[(e, d, closing_slot)] for e in optician_indices) >= 1)


def add_unavailabilities(model, x, unavailabilities, num_slots, internal=None):
    for entry in unavailabilities:
        if len(entry) == 3:
            emp_idx, day_idx, slot_idx = entry
            model.Add(x[(emp_idx, day_idx, slot_idx)] == 0)
            if internal is not None:
                model.Add(internal[(emp_idx, day_idx, slot_idx)] == 0)
        elif len(entry) == 2:
            emp_idx, day_idx = entry
            for s in range(num_slots):
                model.Add(x[(emp_idx, day_idx, s)] == 0)
                if internal is not None:
                    model.Add(internal[(emp_idx, day_idx, s)] == 0)


def add_rest_between_days(model, x, num_employees, num_days, num_slots,
                          start_time_minutes, slot_minutes, rest_minutes=660, work=None):
    if rest_minutes <= 0:
        return

    prefix_cache = {}

    def get_prefix(e, d):
        key = (e, d)
        if key not in prefix_cache:
            if work is None:
                prefix_cache[key] = _build_prefix_sums(
                    model, x, e, d, num_slots, "pref_daily_rest"
                )
            else:
                prefix_cache[key] = _build_prefix_sums_work(
                    model, work, e, d, num_slots, "pref_daily_rest"
                )
        return prefix_cache[key]

    for e in range(num_employees):
        for d in range(num_days - 1):
            prefix_next = get_prefix(e, d + 1)
            for s_end in range(num_slots):
                end_minutes = start_time_minutes + (s_end + 1) * slot_minutes
                needed = rest_minutes - (24 * 60 - end_minutes) - start_time_minutes
                if needed <= 0:
                    continue
                earliest_slot = (needed + slot_minutes - 1) // slot_minutes
                if earliest_slot <= 0:
                    continue
                t = earliest_slot - 1
                if t >= num_slots:
                    t = num_slots - 1
                model.Add(prefix_next[t] == 0).OnlyEnforceIf((work or x)[(e, d, s_end)])
