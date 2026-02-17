from ortools.sat.python import cp_model


def generate_schedule_v2(
    employees,
    days,
    contracts,
    roles,
    config,
    relax_level=0
):

    model = cp_model.CpModel()
    penalties = []

    # ============================
    # BASE TEMPORELLE (15 MINUTES)
    # ============================

    slot_minutes = 15
    start_time_minutes = 9 * 60 + 30     # 9h30
    end_time_minutes = 20 * 60 + 15      # 20h15

    num_slots = (end_time_minutes - start_time_minutes) // slot_minutes

    # ============================
    # PARAMÈTRES
    # ============================

    max_hours_per_day = config["max_hours_per_day"]
    max_slots_per_day = max_hours_per_day * 4

    min_daily_hours = config["min_daily_hours_general"]
    min_daily_slots = min_daily_hours * 4

    short_threshold_hours = config["short_day_threshold"]
    short_threshold_slots = short_threshold_hours * 4

    min_staff = config.get("min_staff_per_hour", 1)

    # ============================
    # VARIABLES
    # ============================

    start = {}
    duration = {}
    works = {}

    for e in range(len(employees)):
        for d in range(len(days)):

            start[(e, d)] = model.NewIntVar(0, num_slots - 1, f"start_{e}_{d}")
            duration[(e, d)] = model.NewIntVar(0, max_slots_per_day, f"dur_{e}_{d}")
            works[(e, d)] = model.NewBoolVar(f"works_{e}_{d}")
            # Lien strict works <-> duration

            # Si ne travaille pas → durée = 0
            model.Add(duration[(e, d)] == 0).OnlyEnforceIf(works[(e, d)].Not())

            # Si travaille → durée >= min_daily
            model.Add(duration[(e, d)] >= min_daily_slots).OnlyEnforceIf(works[(e, d)])

            # Si durée < min_daily → alors ne travaille pas
            model.Add(duration[(e, d)] < min_daily_slots).OnlyEnforceIf(works[(e, d)].Not())

            # Cohérence temporelle
            model.Add(start[(e, d)] + duration[(e, d)] <= num_slots)


    # ============================
    # CONTRATS HEBDO (HARD)
    # ============================

    for e in range(len(employees)):
        model.Add(
            sum(duration[(e, d)] for d in range(len(days)))
            == contracts[e] * 4
        )

    # ============================
    # MAX 6 JOURS CONSÉCUTIFS (HARD)
    # ============================

    for e in range(len(employees)):
        for d in range(len(days) - 6):
            model.Add(
                sum(works[(e, d+i)] for i in range(7)) <= 6
            )


    # ============================
    # OPTICIEN OPEN / CLOSE (HARD)
    # ============================

  #  open_close_penalties = []

  #  for d in range(len(days)):

   #     open_present = []
    #    close_present = []

     #   for e in range(len(employees)):

      #      if roles[e] != "opticien":
       #         continue

        #    open_flag = model.NewBoolVar(f"open_{e}_{d}")
         #   close_flag = model.NewBoolVar(f"close_{e}_{d}")

            # ouverture = premier slot (9h30)
          #  model.Add(start[(e, d)] == 0).OnlyEnforceIf(open_flag)
           # model.Add(start[(e, d)] != 0).OnlyEnforceIf(open_flag.Not())

            # fermeture = dernier slot (20h15)
            #model.Add(start[(e, d)] + duration[(e, d)] == num_slots).OnlyEnforceIf(close_flag)
         #   model.Add(start[(e, d)] + duration[(e, d)] != num_slots).OnlyEnforceIf(close_flag.Not())

          #  open_present.append(open_flag)
           # close_present.append(close_flag)

            # éviter open + close même jour
           # both_flag = model.NewBoolVar(f"open_close_{e}_{d}")
           # model.AddBoolAnd([open_flag, close_flag]).OnlyEnforceIf(both_flag)
           # model.AddBoolOr([open_flag.Not(), close_flag.Not()]).OnlyEnforceIf(both_flag.Not())

            #open_close_penalties.append(both_flag)

      #  model.Add(sum(open_present) >= 1)
       # model.Add(sum(close_present) >= 1)

   # penalties.append(sum(open_close_penalties) * 20)

    # ============================
    # SHORT DAYS (SOFT)
    # ============================

    for e in range(len(employees)):

        short_flags = []

        for d in range(len(days)):

            short_flag = model.NewBoolVar(f"short_{e}_{d}")

            model.Add(duration[(e, d)] > 0).OnlyEnforceIf(short_flag)
            model.Add(duration[(e, d)] < short_threshold_slots).OnlyEnforceIf(short_flag)
            model.Add(duration[(e, d)] >= short_threshold_slots).OnlyEnforceIf(short_flag.Not())

            short_flags.append(short_flag)

        total_short = sum(short_flags)

        if contracts[e] > 25 and relax_level == 0:
            model.Add(total_short <= 1)

        penalties.append(total_short * (10 - relax_level * 2))

    # ============================
    # OBJECTIF
    # ============================

    if penalties:
        model.Minimize(sum(penalties))

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"error": "No feasible solution found"}

    # ============================
    # EXTRACTION
    # ============================

    schedule = {}

    for e in range(len(employees)):
        schedule[employees[e]] = {}

        for d in range(len(days)):

            dur = solver.Value(duration[(e, d)])

            if dur > 0:

                s = solver.Value(start[(e, d)])

                start_minutes = start_time_minutes + s * slot_minutes
                end_minutes = start_minutes + dur * slot_minutes

                schedule[employees[e]][days[d]] = {
                    "start": f"{start_minutes//60:02d}:{start_minutes%60:02d}",
                    "end": f"{end_minutes//60:02d}:{end_minutes%60:02d}",
                    "hours": dur / 4
                }

    return {"schedule": schedule}
