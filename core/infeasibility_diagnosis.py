from __future__ import annotations

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


def _resolve_closed_days(config: Dict[str, Any], num_days: int) -> set[int]:
    closed = set()
    closed_weekdays = set(config.get("closed_weekdays", []))
    for d in range(num_days):
        weekday = d % 7
        if weekday in closed_weekdays:
            closed.add(d)
    return closed


def _resolve_min_staff_per_day(schedule: Dict[str, Any], num_days: int, closed_days: set[int]) -> List[int]:
    default_min_staff = int(schedule.get("min_staff_per_slot", 1))
    configured = schedule.get("min_staff_per_day")
    if isinstance(configured, (list, tuple)) and len(configured) == num_days:
        values = [int(v) for v in configured]
    else:
        values = [default_min_staff for _ in range(num_days)]
    for d in closed_days:
        values[d] = 0
    return values


def _effective_minutes_from_slots(slot_count: int, slot_minutes: int) -> int:
    presence = slot_count * slot_minutes
    if presence > HIDDEN_BREAK_THRESHOLD_MINUTES:
        return max(0, presence - HIDDEN_BREAK_MINUTES)
    return max(0, presence)


def diagnose_infeasibility(
    *,
    employees: List[str],
    roles: List[str],
    contracts: List[float],
    days: List[str],
    config: Dict[str, Any],
    constraints: Optional[List[Dict[str, Any]]] = None,
    unavailabilities: Optional[List[Tuple[int, ...]]] = None,
) -> List[Dict[str, Any]]:
    schedule = config.get("schedule", config)
    hard = config.get("hard_constraints", {})

    slot_minutes = int(schedule.get("slot_minutes", 15))
    start_time_minutes = int(schedule.get("start_time_minutes", 9 * 60 + 30))
    end_time_minutes = int(schedule.get("end_time_minutes", 20 * 60 + 15))
    opening_minutes = max(0, end_time_minutes - start_time_minutes)
    num_slots = opening_minutes // slot_minutes if slot_minutes > 0 else 0
    num_days = len(days)

    closed_days = _resolve_closed_days(config, num_days)
    min_staff_per_day = _resolve_min_staff_per_day(schedule, num_days, closed_days)
    require_optician = bool(hard.get("require_qualified_optician", True))
    optician_indices = [idx for idx, role in enumerate(roles) if role == "opticien"]

    availability = [[[True for _ in range(num_slots)] for _ in range(num_days)] for _ in employees]

    employee_index = {name: idx for idx, name in enumerate(employees)}

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
        if ctype == "day_status":
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

    reasons: List[Dict[str, Any]] = []

    # 1) Opticien qualification impossible on an open day/slot.
    if require_optician:
        no_optician_slots: List[Dict[str, Any]] = []
        for d in range(num_days):
            if d in closed_days or min_staff_per_day[d] <= 0:
                continue
            for s in range(num_slots):
                opt_count = sum(1 for e in optician_indices if availability[e][d][s])
                if opt_count == 0:
                    no_optician_slots.append({"day": days[d], "slot": s})
                    break
        if no_optician_slots:
            days_without_optician = sorted({item["day"] for item in no_optician_slots})
            reasons.append(
                {
                    "code": "NO_OPTICIAN_AVAILABLE",
                    "title": "Aucun opticien diplome disponible",
                    "message": (
                        "Au moins un jour ouvert ne dispose d'aucun opticien disponible, "
                        "alors que la presence d'un opticien est une contrainte hard."
                    ),
                    "details": {"days": days_without_optician},
                }
            )

    # 2) Open day not coverable against hard daily minimum staff.
    uncovered_days: List[Dict[str, Any]] = []
    for d in range(num_days):
        if d in closed_days:
            continue
        max_daily_assignments = sum(
            sum(1 for s in range(num_slots) if availability[e][d][s]) for e in range(len(employees))
        )
        required_daily_assignments = int(min_staff_per_day[d])
        if max_daily_assignments < required_daily_assignments:
            uncovered_days.append(
                {
                    "day": days[d],
                    "required": required_daily_assignments,
                    "max_available_assignments": max_daily_assignments,
                }
            )
    if uncovered_days:
        reasons.append(
            {
                "code": "OPEN_DAY_NOT_COVERABLE",
                "title": "Jour ouvert non couvrable",
                "message": "Le minimum journalier hard ne peut pas etre atteint sur certains jours ouverts.",
                "details": {"days": uncovered_days},
            }
        )

    # 3) Incompatibility from fixed off/unavailability constraints.
    fixed_off_constraints = [
        c
        for c in (constraints or [])
        if c.get("type") in ("unavailability", "day_status")
        and (
            c.get("type") == "unavailability"
            or str(c.get("status") or "").strip().lower() in ("off", "unavailable")
        )
    ]
    if fixed_off_constraints and (no_optician_slots if require_optician else uncovered_days):
        reasons.append(
            {
                "code": "FIXED_OFF_INCOMPATIBLE",
                "title": "Indisponibilites et jours OFF incompatibles",
                "message": (
                    "Les indisponibilites/jours OFF figes suppriment des affectations indispensables "
                    "pour respecter les contraintes hard."
                ),
                "details": {
                    "fixed_constraints_count": len(fixed_off_constraints),
                    "sample_constraints": fixed_off_constraints[:5],
                },
            }
        )

    # 4) Total capacity insufficiency against strict contract equalities.
    total_contract_minutes = int(round(sum(float(h) for h in contracts) * 60))
    total_max_effective_minutes = 0
    employees_below_contract: List[Dict[str, Any]] = []
    for e, name in enumerate(employees):
        emp_contract_minutes = int(round(float(contracts[e]) * 60))
        emp_max_effective = 0
        for d in range(num_days):
            day_available_slots = sum(1 for s in range(num_slots) if availability[e][d][s])
            emp_max_effective += _effective_minutes_from_slots(day_available_slots, slot_minutes)
        total_max_effective_minutes += emp_max_effective
        if emp_max_effective < emp_contract_minutes:
            employees_below_contract.append(
                {
                    "employee": name,
                    "contract_minutes": emp_contract_minutes,
                    "max_possible_minutes": emp_max_effective,
                }
            )

    if total_max_effective_minutes < total_contract_minutes or employees_below_contract:
        reasons.append(
            {
                "code": "INSUFFICIENT_CAPACITY",
                "title": "Capacite totale insuffisante",
                "message": (
                    "La capacite maximale compatible avec les indisponibilites est inferieure "
                    "aux heures contractuelles imposees en egalite stricte."
                ),
                "details": {
                    "total_contract_minutes": total_contract_minutes,
                    "max_possible_effective_minutes": total_max_effective_minutes,
                    "employees_below_contract": employees_below_contract,
                },
            }
        )

    if not reasons:
        reasons.append(
            {
                "code": "HARD_CONSTRAINTS_COMBINATION",
                "title": "Combinaison de contraintes hard",
                "message": (
                    "Aucune cause unique evidente detectee. L'infaisabilite provient probablement "
                    "de la combinaison des contraintes hard (repos, structure de shift, qualification, couverture)."
                ),
                "details": {},
            }
        )

    return reasons
