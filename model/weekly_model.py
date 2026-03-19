from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ortools.sat.python import cp_model

from utils.time_slots import (
    HIDDEN_BREAK_MINUTES,
    HIDDEN_BREAK_THRESHOLD_MINUTES,
    generate_opening_slots,
)

try:
    from config.store_config import BASE_MIN_STAFF
except Exception:
    store_cfg: Dict[str, object] = {}
    store_cfg_path = Path(__file__).resolve().parents[1] / "config" / "store_config.py"
    exec(store_cfg_path.read_text(encoding="utf-8"), store_cfg)
    BASE_MIN_STAFF = int(store_cfg["BASE_MIN_STAFF"])

MIN_SHIFT_SLOTS = 8
SHORT_SHIFT_WEIGHT = 50
LONG_SHIFT_WEIGHT = 50


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
    default_min_staff = int(schedule.get("min_staff_per_slot", BASE_MIN_STAFF))
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
                f"Duree contractuelle {hours}h incompatible avec des slots de {slot_minutes} minutes."
            )
        slots.append(slot_count)
    return slots


def _resolve_constraint_day_index(day_value: Any, days: List[str]) -> Optional[int]:
    if day_value is None:
        return None

    day_str = str(day_value)
    if day_str in days:
        return days.index(day_str)

    weekday_order = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]
    normalized = day_str.strip().lower()
    if len(days) == 7 and normalized in weekday_order:
        return weekday_order.index(normalized)

    return None


def build_weekly_model(
    *,
    employees: List[str],
    contracts: List[float],
    roles: List[str],
    days: List[str],
    config: dict,
    unavailabilities: Optional[List[Tuple[int, ...]]] = None,
    constraints: Optional[List[Dict[str, Any]]] = None,
) -> WeeklyModelArtifacts:
    if len(days) != 7:
        raise ValueError("V1 strict: le planning doit contenir exactement 7 jours.")
    if len(employees) != len(contracts):
        raise ValueError("Incoherence: nombre d'employes different du nombre de contrats.")
    if len(roles) != len(employees):
        raise ValueError("Incoherence: nombre de roles different du nombre d'employes.")

    for emp_name, contract in zip(employees, contracts):
        if contract < 0:
            raise ValueError(f"Contrat negatif interdit pour {emp_name}: {contract}h")
        if contract > 35:
            raise ValueError(f"Contrat > 35h non autorise en V1 pour {emp_name}: {contract}h")

    schedule = config.get("schedule", config)
    hard = config.get("hard_constraints", {})
    soft_weights = config.get("soft_weights", {})

    slot_minutes = int(schedule.get("slot_minutes", 15))
    start_time_minutes = int(schedule.get("start_time_minutes", 9 * 60 + 30))
    end_time_minutes = int(schedule.get("end_time_minutes", 20 * 60 + 15))

    if end_time_minutes <= start_time_minutes:
        raise ValueError("Configuration invalide: end_time_minutes doit etre > start_time_minutes.")

    opening_minutes = end_time_minutes - start_time_minutes
    if opening_minutes % slot_minutes != 0:
        raise ValueError("Fenetre horaire incompatible avec slot_minutes.")

    num_employees = len(employees)
    num_days = len(days)
    num_slots = len(
        generate_opening_slots(
            open_time=start_time_minutes,
            close_time=end_time_minutes,
            slot_minutes=slot_minutes,
        )
    )

    rest_between_days_minutes = int(hard.get("rest_between_days_minutes", 660))
    weekly_rest_minutes = int(hard.get("weekly_rest_minutes", 2100))
    require_optician = bool(hard.get("require_qualified_optician", True))
    configured_min_shift_minutes = int(hard.get("min_shift_minutes", 360))
    effective_min_shift_minutes = min(configured_min_shift_minutes, opening_minutes)
    min_day_slots = (effective_min_shift_minutes + slot_minutes - 1) // slot_minutes
    max_day_slots = (600 + slot_minutes - 1) // slot_minutes

    closed_days = _resolve_closed_day_indices(config, num_days)
    min_staff_per_day = _resolve_min_staff_per_day(schedule, num_days, closed_days)

    optician_indices = [idx for idx, role in enumerate(roles) if role == "opticien"]
    if require_optician and not optician_indices:
        raise ValueError("Aucun opticien diplome disponible (contrainte hard active).")

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

    employee_index = {
        (employee["name"] if isinstance(employee, dict) and "name" in employee else employee): i
        for i, employee in enumerate(employees)
    }
    for c in constraints or []:
        if c.get("type") == "extra_staff_day":
            day_idx = _resolve_constraint_day_index(c.get("day"), days)
            extra_staff = int(c.get("extra_staff", 1))
            if day_idx is not None and day_idx not in closed_days and extra_staff > 0:
                min_staff_per_day[day_idx] += extra_staff

    for c in constraints or []:
        if c.get("type") == "unavailability":
            emp = c.get("employee")
            day = c.get("day")
            day_idx = _resolve_constraint_day_index(day, days)
            if emp in employee_index and day_idx is not None:
                print("UNAVAILABILITY APPLIED:", emp, day)
                e = employee_index[emp]
                d = day_idx
                for s in range(num_slots):
                    model.Add(x[(e, d, s)] == 0)

    for c in constraints or []:
        if c.get("type") == "day_status":
            emp = c.get("employee")
            day = c.get("day")
            status = str(c.get("status") or "").strip().lower()
            day_idx = _resolve_constraint_day_index(day, days)

            if emp not in employee_index:
                raise ValueError(f"Contrainte day_status invalide: employe inconnu: {emp}")
            if day_idx is None:
                raise ValueError(f"Contrainte day_status invalide: jour inconnu: {day}")
            if day_idx in closed_days:
                raise ValueError(f"Contrainte day_status invalide: jour ferme: {day}")

            e = employee_index[emp]
            d = day_idx

            if status in ("off", "unavailable"):
                for s in range(num_slots):
                    model.Add(x[(e, d, s)] == 0)
            elif status == "working":
                model.Add(sum(x[(e, d, s)] for s in range(num_slots)) >= min_day_slots)
            else:
                raise ValueError(f"Contrainte day_status invalide: status inconnu: {status}")

    # HARD: span maximal journalier (10h) via premier et dernier slot travailles.
    max_day_slots = (600 + slot_minutes - 1) // slot_minutes
    for e in range(num_employees):
        for d in range(num_days):
            first_slot_e_d = model.NewIntVar(0, num_slots - 1, f"first_slot_{e}_{d}")
            last_slot_e_d = model.NewIntVar(0, num_slots - 1, f"last_slot_{e}_{d}")

            first_candidates = []
            last_candidates = []
            for s in range(num_slots):
                first_candidate = model.NewIntVar(0, num_slots - 1, f"first_candidate_{e}_{d}_{s}")
                model.Add(first_candidate == s).OnlyEnforceIf(x[(e, d, s)])
                model.Add(first_candidate == num_slots - 1).OnlyEnforceIf(x[(e, d, s)].Not())
                first_candidates.append(first_candidate)

                last_candidate = model.NewIntVar(0, num_slots - 1, f"last_candidate_{e}_{d}_{s}")
                model.Add(last_candidate == s).OnlyEnforceIf(x[(e, d, s)])
                model.Add(last_candidate == 0).OnlyEnforceIf(x[(e, d, s)].Not())
                last_candidates.append(last_candidate)

            model.AddMinEquality(first_slot_e_d, first_candidates)
            model.AddMaxEquality(last_slot_e_d, last_candidates)

            day_worked = model.NewBoolVar(f"day_worked_span_{e}_{d}")
            day_slots = sum(x[(e, d, s)] for s in range(num_slots))
            model.Add(day_slots >= 1).OnlyEnforceIf(day_worked)
            model.Add(day_slots == 0).OnlyEnforceIf(day_worked.Not())
            model.Add(last_slot_e_d - first_slot_e_d <= max_day_slots).OnlyEnforceIf(day_worked)

    # HARD: 1 bloc continu par employe et par jour.
    start_vars: Dict[Tuple[int, int, int], cp_model.IntVar] = {}
    for e in range(num_employees):
        for d in range(num_days):
            starts = []
            for s in range(num_slots):
                start = model.NewBoolVar(f"start_{e}_{d}_{s}")
                start_vars[(e, d, s)] = start
                if s == 0:
                    model.Add(start == x[(e, d, s)])
                else:
                    model.Add(start >= x[(e, d, s)] - x[(e, d, s - 1)])
                    model.Add(start <= x[(e, d, s)])
                    model.Add(start <= 1 - x[(e, d, s - 1)])
                starts.append(start)
            model.Add(sum(starts) <= 1)

    # HARD: longueur minimale de shift (plafonnee par la duree d'ouverture du jour).
    for e in range(num_employees):
        for d in range(num_days):
            for s in range(num_slots):
                start_var = start_vars[(e, d, s)]
                print(
                    "[DEBUG MAX DAY]",
                    "employee=", e,
                    "day=", d,
                    "start_slot=", s,
                    "max_day_slots=", max_day_slots,
                )
                remaining = num_slots - s
                if remaining < min_day_slots:
                    model.Add(start_var == 0)
                    continue

                valid_slots = []
                for k in range(min_day_slots):
                    if s + k < num_slots:
                        valid_slots.append(x[(e, d, s + k)])

                if valid_slots:
                    model.Add(sum(valid_slots) >= min_day_slots * start_var)
                for k in range(max_day_slots + 1, num_slots - s):
                    model.Add(x[(e, d, s + k)] == 0).OnlyEnforceIf(start_var)

    # Unavailabilities.
    for entry in unavailabilities or []:
        if len(entry) == 2:
            emp_idx, day_idx = entry
            for s in range(num_slots):
                model.Add(x[(emp_idx, day_idx, s)] == 0)
        elif len(entry) == 3:
            emp_idx, day_idx, slot_idx = entry
            model.Add(x[(emp_idx, day_idx, slot_idx)] == 0)

    # HARD: contrat hebdomadaire strict sur temps effectif
    # (pause invisible deduite si shift > 6h).
    min_slots_for_break = (HIDDEN_BREAK_THRESHOLD_MINUTES // slot_minutes) + 1
    worked_minutes_per_employee: Dict[int, cp_model.IntVar] = {}
    for e in range(num_employees):
        effective_minutes_by_day = []
        for d in range(num_days):
            day_slots = model.NewIntVar(0, num_slots, f"day_slots_{e}_{d}")
            model.Add(day_slots == sum(x[(e, d, s)] for s in range(num_slots)))

            has_hidden_break = model.NewBoolVar(f"has_hidden_break_{e}_{d}")
            model.Add(day_slots >= min_slots_for_break).OnlyEnforceIf(has_hidden_break)
            model.Add(day_slots <= min_slots_for_break - 1).OnlyEnforceIf(has_hidden_break.Not())

            day_effective_minutes = model.NewIntVar(0, num_slots * slot_minutes, f"day_effective_minutes_{e}_{d}")
            model.Add(day_effective_minutes == day_slots * slot_minutes - has_hidden_break * HIDDEN_BREAK_MINUTES)
            effective_minutes_by_day.append(day_effective_minutes)

        worked_minutes = model.NewIntVar(0, num_days * num_slots * slot_minutes, f"worked_minutes_{e}")
        model.Add(worked_minutes == sum(effective_minutes_by_day))
        model.Add(worked_minutes == contracts_slots[e] * slot_minutes)
        worked_minutes_per_employee[e] = worked_minutes

    # HARD: minimum staff journalier global (garde-fou metier).
    for d in range(num_days):
        if d in closed_days:
            continue
        model.Add(sum(x[(e, d, s)] for e in range(num_employees) for s in range(num_slots)) >= min_staff_per_day[d])

    soft_penalties = []
    target_shift_slots = min_day_slots
    short_shift_vars: Dict[Tuple[int, int], cp_model.IntVar] = {}
    long_shift_vars: Dict[Tuple[int, int], cp_model.IntVar] = {}

    for e in range(num_employees):
        for d in range(num_days):
            shift_length = sum(x[(e, d, s)] for s in range(num_slots))
            short_shift = model.NewIntVar(0, target_shift_slots, f"short_shift_{e}_{d}")
            model.Add(short_shift >= target_shift_slots - shift_length)
            short_shift_vars[(e, d)] = short_shift
            long_shift = model.NewIntVar(0, num_slots, f"long_shift_{e}_{d}")
            model.Add(long_shift >= shift_length - max_day_slots)
            long_shift_vars[(e, d)] = long_shift
    soft_penalties.append(
        SHORT_SHIFT_WEIGHT * sum(short_shift_vars[(e, d)] for e in range(num_employees) for d in range(num_days))
    )
    soft_penalties.append(
        LONG_SHIFT_WEIGHT * sum(long_shift_vars[(e, d)] for e in range(num_employees) for d in range(num_days))
    )

    # Structured constraints: prefer_morning (soft). Penalise les shifts qui commencent apres 12h.
    preference_weight = int(soft_weights.get("preference_weight", 20))
    noon_minutes = 12 * 60
    noon_slot = max(0, (noon_minutes - start_time_minutes + slot_minutes - 1) // slot_minutes)
    penalty_preference_vars: List[cp_model.IntVar] = []
    for constraint in constraints or []:
        if constraint.get("type") != "prefer_morning":
            continue
        employee = constraint.get("employee")
        if employee not in employee_index:
            continue
        emp_idx = employee_index[employee]
        day_idx = _resolve_constraint_day_index(constraint.get("day"), days)
        target_days = [day_idx] if day_idx is not None else list(range(num_days))
        for d in target_days:
            late_starts = [start_vars[(emp_idx, d, s)] for s in range(noon_slot, num_slots)]
            if not late_starts:
                continue
            penalty_preference = model.NewIntVar(0, 1, f"penalty_preference_{emp_idx}_{d}")
            model.Add(penalty_preference == sum(late_starts))
            penalty_preference_vars.append(penalty_preference)
    if penalty_preference_vars:
        soft_penalties.append(preference_weight * sum(penalty_preference_vars))

    # Structured constraints: avoid_closing (soft). Penalise les shifts terminant a l'heure de fermeture.
    avoid_closing_weight = int(soft_weights.get("avoid_closing_weight", 20))
    avoid_closing_vars: List[cp_model.IntVar] = []
    if num_slots > 0:
        closing_slot_idx = num_slots - 1
        for constraint in constraints or []:
            if constraint.get("type") != "avoid_closing":
                continue
            employee = constraint.get("employee")
            if employee not in employee_index:
                continue
            emp_idx = employee_index[employee]
            day_idx = _resolve_constraint_day_index(constraint.get("day"), days)
            target_days = [day_idx] if day_idx is not None else list(range(num_days))
            for d in target_days:
                avoid_closing_vars.append(x[(emp_idx, d, closing_slot_idx)])
    if avoid_closing_vars:
        soft_penalties.append(avoid_closing_weight * sum(avoid_closing_vars))

    # SOFT: couverture par slot.
    coverage_weight = int(soft_weights.get("coverage_weight", 10))
    for d in range(num_days):
        required_staff = min_staff_per_day[d]
        for s in range(num_slots):
            coverage = sum(x[(e, d, s)] for e in range(num_employees))
            understaff = model.NewIntVar(0, required_staff, f"understaff_{d}_{s}")
            model.Add(coverage + understaff >= required_staff)
            soft_penalties.append(understaff * coverage_weight)
            # HARD: opticien present pendant ouverture quand staff requis.
            if require_optician and required_staff > 0:
                model.Add(sum(x[(e, d, s)] for e in optician_indices) >= 1)

    # SOFT: equilibrage leger du nombre de jours travailles.
    balance_weight = int(soft_weights.get("light_balance_weight", 1))
    worked_days = []
    for e in range(num_employees):
        worked_day_vars = []
        for d in range(num_days):
            worked_day = model.NewBoolVar(f"worked_day_{e}_{d}")
            shift_length = sum(x[(e, d, s)] for s in range(num_slots))
            model.Add(shift_length >= min_day_slots * worked_day)
            model.Add(shift_length <= num_slots * worked_day)
            worked_day_vars.append(worked_day)
        days_count = model.NewIntVar(0, num_days, f"worked_days_count_{e}")
        model.Add(days_count == sum(worked_day_vars))
        worked_days.append(days_count)

    max_days = model.NewIntVar(0, num_days, "max_worked_days")
    min_days = model.NewIntVar(0, num_days, "min_worked_days")
    for e in range(num_employees):
        model.Add(worked_days[e] <= max_days)
        model.Add(worked_days[e] >= min_days)
    spread_days = model.NewIntVar(0, num_days, "spread_worked_days")
    model.Add(spread_days == max_days - min_days)
    soft_penalties.append(spread_days * balance_weight)

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

    model.Minimize(sum(soft_penalties) if soft_penalties else 0)

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
