from ortools.sat.python import cp_model


def add_min_coverage(model, x, num_employees, num_days, num_slots, min_staff):
    for d in range(num_days):
        for s in range(num_slots):
            model.Add(
                sum(x[(e, d, s)] for e in range(num_employees)) >= min_staff
            )


def add_max_weekly_hours(model, x, num_employees, num_days, num_slots, contracts, slot_minutes):
    for e in range(num_employees):
        total_slots = sum(
            x[(e, d, s)]
            for d in range(num_days)
            for s in range(num_slots)
        )
        max_slots = contracts[e] * 60 // slot_minutes
        model.Add(total_slots <= max_slots)


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
