from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from utils.time_slots import HIDDEN_BREAK_MINUTES, HIDDEN_BREAK_THRESHOLD_MINUTES

WEEKDAY_ORDER = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def _resolve_closed_day_indices(config: Dict[str, Any], num_days: int) -> List[int]:
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


def _resolve_day_index(day_value: Any, days: List[str]) -> Optional[int]:
    if day_value is None:
        return None
    day_str = str(day_value)
    if day_str in days:
        return days.index(day_str)
    normalized = day_str.strip().lower()
    if len(days) == 7 and normalized in WEEKDAY_ORDER:
        return WEEKDAY_ORDER.index(normalized)
    return None


def _max_consecutive_true(values: List[bool]) -> int:
    best = 0
    current = 0
    for value in values:
        if value:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def _effective_minutes_from_presence_slots(slot_count: int, slot_minutes: int) -> int:
    presence_minutes = slot_count * slot_minutes
    if presence_minutes > HIDDEN_BREAK_THRESHOLD_MINUTES:
        return max(0, presence_minutes - HIDDEN_BREAK_MINUTES)
    return max(0, presence_minutes)


def run_employee_feasibility_precheck(
    *,
    employees: List[str],
    contracts: List[float],
    days: List[str],
    config: Dict[str, Any],
    constraints: Optional[List[Dict[str, Any]]] = None,
    unavailabilities: Optional[List[Tuple[int, ...]]] = None,
) -> Dict[str, Any]:
    schedule = config.get("schedule", config)

    slot_minutes = int(schedule.get("slot_minutes", 15))
    start_time_minutes = int(schedule.get("start_time_minutes", 9 * 60 + 30))
    end_time_minutes = int(schedule.get("end_time_minutes", 20 * 60 + 15))
    opening_minutes = max(0, end_time_minutes - start_time_minutes)
    num_slots = opening_minutes // slot_minutes if slot_minutes > 0 else 0
    num_days = len(days)

    configured_min_shift_minutes = int(config.get("hard_constraints", {}).get("min_shift_minutes", 360))
    effective_min_shift_minutes = min(configured_min_shift_minutes, opening_minutes)
    min_day_slots = (effective_min_shift_minutes + slot_minutes - 1) // slot_minutes if slot_minutes > 0 else 0
    max_day_slots = (600 + slot_minutes - 1) // slot_minutes if slot_minutes > 0 else 0

    closed_days = set(_resolve_closed_day_indices(config, num_days))
    employee_index = {name: idx for idx, name in enumerate(employees)}
    availability = [[[True for _ in range(num_slots)] for _ in range(num_days)] for _ in employees]

    for d in closed_days:
        for e in range(len(employees)):
            for s in range(num_slots):
                availability[e][d][s] = False

    for c in constraints or []:
        ctype = c.get("type")
        day_idx = _resolve_day_index(c.get("day"), days)
        emp_name = c.get("employee")
        if day_idx is None or emp_name not in employee_index:
            continue
        e = employee_index[emp_name]
        if ctype == "unavailability":
            for s in range(num_slots):
                availability[e][day_idx][s] = False
        elif ctype == "day_status":
            status = str(c.get("status") or "").strip().lower()
            if status in ("off", "unavailable"):
                for s in range(num_slots):
                    availability[e][day_idx][s] = False

    for entry in unavailabilities or []:
        if len(entry) == 2:
            e, d = int(entry[0]), int(entry[1])
            if 0 <= e < len(employees) and 0 <= d < num_days:
                for s in range(num_slots):
                    availability[e][d][s] = False
        elif len(entry) == 3:
            e, d, s = int(entry[0]), int(entry[1]), int(entry[2])
            if 0 <= e < len(employees) and 0 <= d < num_days and 0 <= s < num_slots:
                availability[e][d][s] = False

    employee_diagnostics: List[Dict[str, Any]] = []
    unreachable_contracts: List[Dict[str, Any]] = []
    open_days_count = sum(1 for d in range(num_days) if d not in closed_days)

    for e, name in enumerate(employees):
        contract_minutes = int(round(float(contracts[e]) * 60))
        workable_open_days = 0
        blocked_open_days: List[str] = []
        max_possible_effective_minutes = 0

        for d in range(num_days):
            if d in closed_days:
                continue

            day_mask = availability[e][d]
            longest_block_slots = _max_consecutive_true(day_mask)
            max_assignable_slots = min(max_day_slots, longest_block_slots)

            if max_assignable_slots >= min_day_slots:
                workable_open_days += 1
                max_possible_effective_minutes += _effective_minutes_from_presence_slots(
                    max_assignable_slots, slot_minutes
                )
            else:
                blocked_open_days.append(days[d])

        diagnostic = {
            "employee": name,
            "contract_minutes": contract_minutes,
            "open_days_count": open_days_count,
            "workable_open_days": workable_open_days,
            "blocked_open_days": blocked_open_days,
            "max_possible_effective_minutes": max_possible_effective_minutes,
            "daily_max_presence_minutes": max_day_slots * slot_minutes,
        }
        employee_diagnostics.append(diagnostic)

        if max_possible_effective_minutes < contract_minutes:
            unreachable_contracts.append(diagnostic)

    return {
        "is_feasible": len(unreachable_contracts) == 0,
        "employees": employee_diagnostics,
        "unreachable_contracts": unreachable_contracts,
        "global": {
            "num_days": num_days,
            "open_days_count": open_days_count,
            "closed_days_count": len(closed_days),
            "closed_days": [days[d] for d in sorted(closed_days)],
            "slot_minutes": slot_minutes,
            "opening_minutes_per_day": opening_minutes,
            "min_shift_minutes": effective_min_shift_minutes,
            "max_daily_minutes": max_day_slots * slot_minutes,
        },
    }
