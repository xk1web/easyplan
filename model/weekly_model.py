from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ortools.sat.python import cp_model
from model.shift_templates import SHIFT_TEMPLATES, build_template_slots
from utils.time_slots import time_to_slot

try:
    from config.store_config import BASE_MIN_STAFF, EVENING_BOOST, EVENING_PEAK_HOUR, SATURDAY_BOOST
except Exception:
    # Fallback loader when a non-package module named "config" shadows local config/.
    store_cfg: Dict[str, object] = {}
    store_cfg_path = Path(__file__).resolve().parents[1] / "config" / "store_config.py"
    exec(store_cfg_path.read_text(encoding="utf-8"), store_cfg)
    BASE_MIN_STAFF = int(store_cfg["BASE_MIN_STAFF"])
    EVENING_PEAK_HOUR = str(store_cfg["EVENING_PEAK_HOUR"])
    EVENING_BOOST = int(store_cfg["EVENING_BOOST"])
    SATURDAY_BOOST = int(store_cfg["SATURDAY_BOOST"])


@dataclass
class WeeklyModelArtifacts:
    model: cp_model.CpModel
    x: Dict[Tuple[int, int, int], cp_model.IntVar]
    num_employees: int
    num_days: int
    num_slots: int
    slot_minutes: int
    start_time_minutes: int
    end_time_minutes: int
    min_staff_per_day: List[int]
    contracts_hours: List[float]
    contracts_slots: List[int]
    employees: List[str]
    days: List[str]


def _resolve_closed_day_indices(config: dict, num_days: int) -> List[int]:
    closed_weekdays = set(config.get("closed_weekdays", []))
    start_date_str = config.get("start_date")
    start_date = None
    if isinstance(start_date_str, str):
        try:
            start_date = date.fromisoformat(start_date_str)
        except ValueError:
            start_date = None

    closed = []
    for day_idx in range(num_days):
        if start_date is not None:
            weekday_index = (start_date + timedelta(days=day_idx)).weekday()
        else:
            weekday_index = day_idx % 7
        if weekday_index in closed_weekdays:
            closed.append(day_idx)
    return closed


def _add_rest_11h_constraints(
    model: cp_model.CpModel,
    x: Dict[Tuple[int, int, int], cp_model.IntVar],
    num_employees: int,
    num_days: int,
    num_slots: int,
    start_time_minutes: int,
    slot_minutes: int,
    rest_minutes: int,
) -> None:
    if rest_minutes <= 0:
        return

    for e in range(num_employees):
        for d in range(num_days - 1):
            for s_end in range(num_slots):
                end_minutes = start_time_minutes + (s_end + 1) * slot_minutes
                for s_next in range(num_slots):
                    start_next_minutes = start_time_minutes + s_next * slot_minutes
                    rest = (24 * 60 - end_minutes) + start_next_minutes
                    if rest < rest_minutes:
                        model.Add(x[(e, d, s_end)] + x[(e, d + 1, s_next)] <= 1)


def _add_weekly_rest_35h_constraints(
    model: cp_model.CpModel,
    x: Dict[Tuple[int, int, int], cp_model.IntVar],
    num_employees: int,
    num_days: int,
    num_slots: int,
    start_time_minutes: int,
    slot_minutes: int,
    rest_minutes: int,
) -> None:
    if rest_minutes <= 0:
        return

    week_minutes = num_days * 24 * 60
    if week_minutes < rest_minutes:
        return

    slot_intervals: List[Tuple[int, int, int, int]] = []
    for d in range(num_days):
        day_offset = d * 24 * 60
        for s in range(num_slots):
            abs_start = day_offset + start_time_minutes + s * slot_minutes
            abs_end = abs_start + slot_minutes
            slot_intervals.append((d, s, abs_start, abs_end))

    candidate_starts = range(0, week_minutes - rest_minutes + 1, slot_minutes)
    for e in range(num_employees):
        flags = []
        for idx, window_start in enumerate(candidate_starts):
            window_end = window_start + rest_minutes
            flag = model.NewBoolVar(f"weekly_rest_35h_{e}_{idx}")
            for d, s, slot_start, slot_end in slot_intervals:
                if slot_end <= window_start or slot_start >= window_end:
                    continue
                model.Add(x[(e, d, s)] == 0).OnlyEnforceIf(flag)
            flags.append(flag)

        if flags:
            model.Add(sum(flags) >= 1)


def _resolve_min_staff_per_day(schedule: dict, num_days: int, closed_days: List[int]) -> List[int]:
    default_min_staff = int(schedule.get("min_staff_per_slot", 1))
    min_staff_per_day = schedule.get("min_staff_per_day")

    if isinstance(min_staff_per_day, (list, tuple)) and len(min_staff_per_day) == num_days:
        values = [int(v) for v in min_staff_per_day]
    else:
        values = [default_min_staff for _ in range(num_days)]

    for d in closed_days:
        values[d] = 0

    return values


def _contracts_to_slots(contracts: List[float], slot_minutes: int) -> List[int]:
    slots = []
    for hours in contracts:
        raw_minutes = float(hours) * 60.0
        slot_count = int(round(raw_minutes / slot_minutes))
        if abs(slot_count * slot_minutes - raw_minutes) > 1e-6:
            raise ValueError(
                f"Durée contractuelle {hours}h incompatible avec des slots de {slot_minutes} minutes."
            )
        slots.append(slot_count)
    return slots


def build_weekly_model(
    *,
    employees: List[str],
    contracts: List[float],
    roles: List[str],
    days: List[str],
    config: dict,
    unavailabilities: Optional[List[Tuple[int, ...]]] = None,
) -> WeeklyModelArtifacts:
    if len(days) != 7:
        raise ValueError("V1 strict: le planning doit contenir exactement 7 jours.")
    if len(employees) != len(contracts):
        raise ValueError("Incohérence: nombre d'employés différent du nombre de contrats.")
    if len(roles) != len(employees):
        raise ValueError("Incohérence: nombre de rôles différent du nombre d'employés.")

    for emp_name, contract in zip(employees, contracts):
        if contract < 0:
            raise ValueError(f"Contrat négatif interdit pour {emp_name}: {contract}h")
        if contract > 35:
            raise ValueError(f"Contrat > 35h non autorisé en V1 pour {emp_name}: {contract}h")

    schedule = config.get("schedule", config)
    hard = config.get("hard_constraints", {})
    print("SHIFT_TEMPLATES_LOADED", len(SHIFT_TEMPLATES))

    slot_minutes = int(schedule.get("slot_minutes", 15))
    start_time_minutes = int(schedule.get("start_time_minutes", 9 * 60 + 30))
    end_time_minutes = int(schedule.get("end_time_minutes", 20 * 60 + 15))

    if end_time_minutes <= start_time_minutes:
        raise ValueError("Configuration invalide: end_time_minutes doit être > start_time_minutes.")

    opening_minutes = end_time_minutes - start_time_minutes
    if opening_minutes % slot_minutes != 0:
        raise ValueError("Fenêtre horaire incompatible avec slot_minutes.")

    num_employees = len(employees)
    num_days = len(days)
    num_slots = opening_minutes // slot_minutes
    evening_peak_slot = time_to_slot(
        EVENING_PEAK_HOUR,
        start_time_minutes=start_time_minutes,
        slot_minutes=slot_minutes,
    )

    try:
        template_slots = build_template_slots(
            start_time_minutes, end_time_minutes, slot_minutes=slot_minutes
        )
    except ValueError:
        # Keep model solvable for narrow store windows while template library is >= 6h.
        template_slots = {}
    if not template_slots:
        template_slots = {"FULL_OPEN_FALLBACK": list(range(num_slots))}
    templates = list(template_slots.keys())
    print("TEMPLATES_USED", templates)
    print("TEMPLATE_DRIVEN_SLOTS_ENABLED")
    template_duration_slots = {t: len(template_slots[t]) for t in templates}
    full_templates = [t for t in ["FULL_OPEN", "FULL_LATE", "FULL_EARLY"] if t in templates]
    closing_templates = [t for t in ["CLOSING_LONG", "FULL_LATE"] if t in templates]
    short_templates = [t for t in ["SHORT_AM", "SHORT_PM", "SHORT_MID"] if t in templates]

    max_daily_minutes = int(hard.get("max_daily_minutes", 600))
    if max_daily_minutes > 600:
        max_daily_minutes = 600
    max_daily_slots = max_daily_minutes // slot_minutes

    max_days_per_week = min(6, int(hard.get("max_days_per_week", 6)))
    rest_between_days_minutes = int(hard.get("rest_between_days_minutes", 660))
    weekly_rest_minutes = int(hard.get("weekly_rest_minutes", 2100))
    require_optician = bool(hard.get("require_qualified_optician", True))

    closed_days = _resolve_closed_day_indices(config, num_days)
    min_staff_per_day = _resolve_min_staff_per_day(schedule, num_days, closed_days)

    optician_indices = [idx for idx, role in enumerate(roles) if role == "opticien"]
    if require_optician and not optician_indices:
        raise ValueError("Aucun opticien diplômé disponible (contrainte hard active).")

    contracts_slots = _contracts_to_slots(contracts, slot_minutes)

    model = cp_model.CpModel()
    x: Dict[Tuple[int, int, int], cp_model.IntVar] = {}

    for e in range(num_employees):
        for d in range(num_days):
            for s in range(num_slots):
                var = model.NewBoolVar(f"x_{e}_{d}_{s}")
                x[(e, d, s)] = var
                if d in closed_days:
                    model.Add(var == 0)

    shift = {}
    for e in range(num_employees):
        for d in range(num_days):
            for t in templates:
                shift[(e, d, t)] = model.NewBoolVar(f"shift_{e}_{d}_{t}")
    print("SHIFT_VARIABLES_CREATED")

    for e in range(num_employees):
        for d in range(num_days):
            model.Add(sum(shift[(e, d, t)] for t in templates) <= 1)

    # Soft constraints: weekly distribution of shift types.
    soft_penalties = []
    for e in range(num_employees):
        full_days = sum(
            shift[(e, d, t)]
            for d in range(num_days)
            for t in full_templates
        ) if full_templates else 0
        closing_days = sum(
            shift[(e, d, t)]
            for d in range(num_days)
            for t in closing_templates
        ) if closing_templates else 0
        short_days = sum(
            shift[(e, d, t)]
            for d in range(num_days)
            for t in short_templates
        ) if short_templates else 0

        full_violation = model.NewIntVar(0, 7, f"full_violation_{e}")
        closing_violation = model.NewIntVar(0, 7, f"closing_violation_{e}")
        short_violation = model.NewIntVar(0, 7, f"short_violation_{e}")

        model.Add(full_days <= 3 + full_violation)
        model.Add(closing_days <= 3 + closing_violation)
        model.Add(short_days >= 1 - short_violation)

        soft_penalties.append(full_violation * 5)
        soft_penalties.append(closing_violation * 3)
        soft_penalties.append(short_violation * 2)
    print("SHIFT_DISTRIBUTION_CONSTRAINTS_ENABLED")

    for e in range(num_employees):
        closing_streak_violation = model.NewIntVar(0, num_days, f"closing_streak_violation_{e}")
        for d in range(num_days - 1):
            closing_shift_d = sum(shift[(e, d, t)] for t in closing_templates) if closing_templates else 0
            closing_shift_next = sum(shift[(e, d + 1, t)] for t in closing_templates) if closing_templates else 0
            model.Add(closing_shift_d + closing_shift_next <= 1 + closing_streak_violation)
        soft_penalties.append(closing_streak_violation * 4)
    print("CLOSING_ROTATION_ENABLED")

    saturday_index = 5
    if saturday_index < num_days:
        for e in range(num_employees):
            saturday_work = sum(
                shift[(e, saturday_index, t)]
                for t in templates
            )
            saturday_violation = model.NewIntVar(0, 2, f"saturday_violation_{e}")
            model.Add(saturday_work <= 1 + saturday_violation)
            soft_penalties.append(saturday_violation * 4)
    print("SATURDAY_BALANCING_ENABLED")

    for e in range(num_employees):
        for d in range(num_days):
            for t in templates:
                for s in template_slots[t]:
                    model.Add(x[(e, d, s)] >= shift[(e, d, t)])

    covering_templates_by_slot = {}
    for s in range(num_slots):
        covering_templates_by_slot[s] = [t for t in templates if s in template_slots[t]]

    for e in range(num_employees):
        for d in range(num_days):
            for s in range(num_slots):
                covering_templates = covering_templates_by_slot[s]
                if covering_templates:
                    model.Add(
                        x[(e, d, s)] <= sum(shift[(e, d, t)] for t in covering_templates)
                    )
                else:
                    model.Add(x[(e, d, s)] == 0)

    # Enforce a single contiguous work block per employee per day.
    for e in range(num_employees):
        for d in range(num_days):
            starts = []
            for s in range(num_slots):
                start = model.NewBoolVar(f"start_{e}_{d}_{s}")
                if s == 0:
                    model.Add(start >= x[(e, d, s)])
                else:
                    model.Add(start >= x[(e, d, s)] - x[(e, d, s - 1)])
                starts.append(start)
            model.Add(sum(starts) <= 1)
    print("CONTIGUOUS_SHIFT_CONSTRAINT_ENABLED")

    for entry in unavailabilities or []:
        if len(entry) == 2:
            emp_idx, day_idx = entry
            for s in range(num_slots):
                model.Add(x[(emp_idx, day_idx, s)] == 0)
        elif len(entry) == 3:
            emp_idx, day_idx, slot_idx = entry
            model.Add(x[(emp_idx, day_idx, slot_idx)] == 0)

    for d in range(num_days):
        for s in range(num_slots):
            required_staff = BASE_MIN_STAFF
            if s >= evening_peak_slot:
                required_staff += EVENING_BOOST
            if d == saturday_index:
                required_staff += SATURDAY_BOOST
            if d in closed_days:
                required_staff = 0

            coverage = sum(x[(e, d, s)] for e in range(num_employees))
            model.Add(coverage >= required_staff)
            if require_optician and required_staff > 0:
                model.Add(sum(x[(e, d, s)] for e in optician_indices) >= 1)
    print("OPTICAL_TRAFFIC_CURVE_ENABLED")

    worked_day = {}
    target_hours_slots = int(round(sum(contracts_slots) / max(1, num_employees)))
    for e in range(num_employees):
        total_week_slots = []
        for d in range(num_days):
            hours_worked = sum(
                shift[(e, d, t)] * template_duration_slots[t]
                for t in templates
            )
            model.Add(hours_worked <= max_daily_slots)
            total_week_slots.append(hours_worked)

            day_flag = model.NewBoolVar(f"worked_day_{e}_{d}")
            worked_day[(e, d)] = day_flag
            model.Add(hours_worked >= 1).OnlyEnforceIf(day_flag)
            model.Add(hours_worked == 0).OnlyEnforceIf(day_flag.Not())

        hours_employee = sum(total_week_slots)
        model.Add(hours_employee == contracts_slots[e])
        model.Add(sum(worked_day[(e, d)] for d in range(num_days)) <= max_days_per_week)

        diff_hours = model.NewIntVar(0, 40 * 60 // slot_minutes, f"diff_hours_{e}")
        model.Add(hours_employee - target_hours_slots <= diff_hours)
        model.Add(target_hours_slots - hours_employee <= diff_hours)
        soft_penalties.append(diff_hours * 2)
    print("TEAM_BALANCING_ENABLED")

    _add_rest_11h_constraints(
        model=model,
        x=x,
        num_employees=num_employees,
        num_days=num_days,
        num_slots=num_slots,
        start_time_minutes=start_time_minutes,
        slot_minutes=slot_minutes,
        rest_minutes=rest_between_days_minutes,
    )
    _add_weekly_rest_35h_constraints(
        model=model,
        x=x,
        num_employees=num_employees,
        num_days=num_days,
        num_slots=num_slots,
        start_time_minutes=start_time_minutes,
        slot_minutes=slot_minutes,
        rest_minutes=weekly_rest_minutes,
    )

    model.Minimize(sum(soft_penalties))

    return WeeklyModelArtifacts(
        model=model,
        x=x,
        num_employees=num_employees,
        num_days=num_days,
        num_slots=num_slots,
        slot_minutes=slot_minutes,
        start_time_minutes=start_time_minutes,
        end_time_minutes=end_time_minutes,
        min_staff_per_day=min_staff_per_day,
        contracts_hours=[float(c) for c in contracts],
        contracts_slots=contracts_slots,
        employees=employees,
        days=days,
    )
