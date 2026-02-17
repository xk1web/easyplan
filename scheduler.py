from ortools.sat.python import cp_model


def generate_schedule(
    employees,
    days,
    unavailable,
    contracts,
    roles,
    preferences,
    previous_assignments,
    config,
    employee_preferences
):
    model = cp_model.CpModel()

    max_hours_per_day = config["max_hours_per_day"]
    preferred_daily_hours = config["preferred_daily_hours"]
    penalty_long_day = config["penalty_long_day"]
    required_open = config["required_open"]
    required_close = config["required_close"]

    # ----------------------------
    # MIN SHIFT RULE
    # ----------------------------

    def get_min_shift(contract_hours):
        for rule in sorted(config["min_shift_rules"],
                           key=lambda x: x["min_contract"],
                           reverse=True):
            if contract_hours >= rule["min_contract"]:
                return rule["min_hours"]
        return 4

    # ----------------------------
    # VARIABLES
    # ----------------------------

    hours = {}
    works = {}
    open_shift = {}
    close_shift = {}

    for e in range(len(employees)):
        for d in range(len(days)):
            hours[(e, d)] = model.NewIntVar(
                0,
                max_hours_per_day,
                f"hours_{e}_{d}"
            )

            works[(e, d)] = model.NewBoolVar(f"works_{e}_{d}")
            open_shift[(e, d)] = model.NewBoolVar(f"open_{e}_{d}")
            close_shift[(e, d)] = model.NewBoolVar(f"close_{e}_{d}")

            # lien heures ↔ travaille
            model.Add(hours[(e, d)] > 0).OnlyEnforceIf(works[(e, d)])
            model.Add(hours[(e, d)] == 0).OnlyEnforceIf(works[(e, d)].Not())
            # minimum général si on travaille
            min_daily = config["min_daily_hours_general"]
            model.Add(hours[(e, d)] >= min_daily).OnlyEnforceIf(works[(e, d)])


            # pas open + close le même jour
            model.Add(open_shift[(e, d)] + close_shift[(e, d)] <= 1)

            # si open/close → travaille
            model.Add(works[(e, d)] == 1).OnlyEnforceIf(open_shift[(e, d)])
            model.Add(works[(e, d)] == 1).OnlyEnforceIf(close_shift[(e, d)])

            # min heures si shift assigné
            min_shift = get_min_shift(contracts[e])
            model.Add(hours[(e, d)] >= min_shift).OnlyEnforceIf(open_shift[(e, d)])
            model.Add(hours[(e, d)] >= min_shift).OnlyEnforceIf(close_shift[(e, d)])

    # ----------------------------
    # CONTRATS (Hard)
    # ----------------------------

    for e in range(len(employees)):
        model.Add(
            sum(hours[(e, d)] for d in range(len(days))) == contracts[e]
        )

    # ----------------------------
    # INDISPONIBILITÉS (Hard)
    # ----------------------------

    for (e, d) in unavailable:
        model.Add(hours[(e, d)] == 0)

    # ----------------------------
    # COUVERTURE OPEN/CLOSE (Hard)
    # ----------------------------

    for d in range(len(days)):
        model.Add(
            sum(open_shift[(e, d)] for e in range(len(employees)))
            >= required_open
        )
        model.Add(
            sum(close_shift[(e, d)] for e in range(len(employees)))
            >= required_close
        )

    # ----------------------------
    # QUALIFICATION : OPTICIEN OBLIGATOIRE OPEN/CLOSE
    # ----------------------------

    for d in range(len(days)):
        model.Add(
            sum(open_shift[(e, d)]
                for e in range(len(employees))
                if roles[e] == "opticien")
            >= 1
        )

        model.Add(
            sum(close_shift[(e, d)]
                for e in range(len(employees))
                if roles[e] == "opticien")
            >= 1
        )


    # ----------------------------
    # SOFT CONSTRAINTS
    # ----------------------------

    penalties = []

    # préférences jours
    for (e, d, weight) in preferences:
        penalties.append(works[(e, d)] * weight)

    # pénalité journées trop longues
    for e in range(len(employees)):
        for d in range(len(days)):
            excess = model.NewIntVar(0, max_hours_per_day,
                                     f"excess_{e}_{d}")
            model.Add(hours[(e, d)] - preferred_daily_hours <= excess)
            model.Add(excess >= 0)
            penalties.append(excess * penalty_long_day)

    # préférences shifts employé
    for e in range(len(employees)):
        emp_pref = employee_preferences.get(e, {})
        avoid = emp_pref.get("avoid_shifts", [])

        for d in range(len(days)):
            if "open" in avoid:
                penalties.append(open_shift[(e, d)] * 5)
            if "close" in avoid:
                penalties.append(close_shift[(e, d)] * 5)

    # ----------------------------
    # SOFT : ÉQUITÉ OPEN/CLOSE
    # ----------------------------

    equity_weight = config["equity_weight"]

    for e in range(len(employees)):
        total_open = sum(open_shift[(e, d)] for d in range(len(days)))
        total_close = sum(close_shift[(e, d)] for d in range(len(days)))

        diff = model.NewIntVar(0, len(days), f"diff_open_close_{e}")
        model.AddAbsEquality(diff, total_open - total_close)

        penalties.append(diff * equity_weight)
    # ----------------------------
    # SOFT : CLOSE → OPEN LENDMAIN
    # ----------------------------

    rest_penalty_weight = config["rest_penalty_weight"]

    for e in range(len(employees)):
        for d in range(len(days) - 1):

            close_today = close_shift[(e, d)]
            open_next = open_shift[(e, d + 1)]

            violation = model.NewBoolVar(f"rest_violation_{e}_{d}")

            model.Add(close_today + open_next == 2).OnlyEnforceIf(violation)
            model.Add(close_today + open_next != 2).OnlyEnforceIf(violation.Not())

            penalties.append(violation * rest_penalty_weight)


    total_penalty = sum(penalties)

    # ----------------------------
    # OBJECTIF
    # ----------------------------

    model.Minimize(total_penalty)

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"error": "No solution"}



    # ----------------------------
    # EXTRACTION
    # ----------------------------

    schedule = {}

    for e in range(len(employees)):
        schedule[employees[e]] = {}
        for d in range(len(days)):
            h = solver.Value(hours[(e, d)])
            if h > 0:
                schedule[employees[e]][days[d]] = {
                    "hours": h,
                    "open": solver.Value(open_shift[(e, d)]),
                    "close": solver.Value(close_shift[(e, d)])
                }

    return schedule
