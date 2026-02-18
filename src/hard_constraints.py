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
    for d in range(num_days):
        for s in range(num_slots):
            model.Add(
                sum(x[(e, d, s)] for e in range(num_employees)) >= min_staff
            )


def add_max_weekly_hours(model, x, num_employees, num_days, num_slots, contracts, slot_minutes):
    weeks = get_weeks(num_days)
    for e in range(num_employees):
        max_slots = contracts[e] * 60 // slot_minutes
        for week_days in weeks:
            week_slots = sum(
                x[(e, d, s)]
                for d in week_days
                for s in range(num_slots)
            )
            model.Add(week_slots <= max_slots)


def add_max_days_per_week(model, x, num_employees, num_days, num_slots, max_days=6):
    weeks = get_weeks(num_days)
    for e in range(num_employees):
        for week_days in weeks:
            day_worked_vars = []
            for d in week_days:
                worked = model.NewBoolVar(f"day_worked_{e}_{d}")
                daily_slots = sum(x[(e, d, s)] for s in range(num_slots))
                model.Add(daily_slots >= 1).OnlyEnforceIf(worked)
                model.Add(daily_slots == 0).OnlyEnforceIf(worked.Not())
                day_worked_vars.append(worked)
            model.Add(sum(day_worked_vars) <= max_days)


def add_weekly_rest_35h(model, x, num_employees, num_days, num_slots,
                        start_time_minutes, slot_minutes, rest_minutes=2100):
    for e in range(num_employees):
        for d in range(num_days - 2):
            d_mid = d + 1
            d_after = d + 2
            has_work_mid = model.NewBoolVar(f"work_mid_{e}_{d_mid}")
            mid_slots = sum(x[(e, d_mid, s)] for s in range(num_slots))
            model.Add(mid_slots >= 1).OnlyEnforceIf(has_work_mid)
            model.Add(mid_slots == 0).OnlyEnforceIf(has_work_mid.Not())
            for s_end in range(num_slots):
                end_minutes = start_time_minutes + (s_end + 1) * slot_minutes
                for s_start in range(num_slots):
                    start_next = start_time_minutes + s_start * slot_minutes
                    gap = (24 * 60 - end_minutes) + 24 * 60 + start_next
                    if gap < rest_minutes:
                        model.AddBoolOr([
                            x[(e, d, s_end)].Not(),
                            x[(e, d_after, s_start)].Not(),
                            has_work_mid
                        ])


def add_max_daily_hours(model, x, num_employees, num_days, num_slots,
                        slot_minutes, max_daily_minutes=600):
    max_daily_slots = max_daily_minutes // slot_minutes
    for e in range(num_employees):
        for d in range(num_days):
            daily_slots = sum(x[(e, d, s)] for s in range(num_slots))
            model.Add(daily_slots <= max_daily_slots)


def add_qualified_optician_coverage(model, x, num_employees, num_days, num_slots, roles):
    optician_indices = [e for e in range(num_employees) if roles[e] == "opticien"]
    if not optician_indices:
        raise ValueError("Aucun opticien diplômé dans l'équipe — RULE 5.1 impossible.")
    for d in range(num_days):
        for s in range(num_slots):
            model.Add(
                sum(x[(e, d, s)] for e in optician_indices) >= 1
            )


def add_unavailabilities(model, x, unavailabilities, num_slots):
    for entry in unavailabilities:
        if len(entry) == 3:
            emp_idx, day_idx, slot_idx = entry
            model.Add(x[(emp_idx, day_idx, slot_idx)] == 0)
        elif len(entry) == 2:
            emp_idx, day_idx = entry
            for s in range(num_slots):
                model.Add(x[(emp_idx, day_idx, s)] == 0)


def add_rest_between_days(model, x, num_employees, num_days, num_slots,
                          start_time_minutes, slot_minutes, rest_minutes=660):
    for e in range(num_employees):
        for d in range(num_days - 1):
            for s_end in range(num_slots):
                end_minutes = start_time_minutes + (s_end + 1) * slot_minutes
                for s_start in range(num_slots):
                    start_next = start_time_minutes + s_start * slot_minutes
                    gap = (24 * 60 - end_minutes) + start_next
                    if gap < rest_minutes:
                        model.AddBoolOr([
                            x[(e, d, s_end)].Not(),
                            x[(e, d + 1, s_start)].Not()
                        ])
