from __future__ import annotations

import os
from typing import Any, Dict, List, Literal, Optional, Union

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core.v1_weekly_engine import run_weekly_v1_engine


app = FastAPI(
    title="EasyPlan API",
    description="Moteur V1 hebdomadaire strict (IDCC 1431)",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://easyplan-ochre.vercel.app",
        "https://easyplan-git-codex-v1-weekly-stable-matthieu-le-nys-projects.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


class PreviousMonthStats(BaseModel):
    total_hours: Optional[Dict[str, float]] = Field(default=None)
    saturdays_worked: Optional[Dict[str, int]] = Field(default=None)


class PlanningRequest(BaseModel):
    employees: List[str] = Field(..., min_length=1)
    contracts: List[float] = Field(..., min_length=1)
    roles: List[str] = Field(..., min_length=1)
    days: List[str] = Field(..., min_length=1)
    constraints: Optional[List[Dict[str, Any]]] = Field(default=None)
    unavailabilities: Optional[List[List[int]]] = Field(default=[])
    config: Optional[Dict[str, Any]] = Field(default=None)
    previous_month_stats: Optional[PreviousMonthStats] = Field(default=None)
    manual_overrides: Optional[List[Dict[str, Any]]] = Field(default=None)
    manual_override_mode: Literal["soft", "strict"] = Field(default="soft")


class SolverMetrics(BaseModel):
    num_variables: int
    num_constraints: int
    solver_wall_time: float
    solve_time_seconds: Optional[float] = None
    solver_status: str
    gap_percent: Optional[float] = None
    warnings: Optional[List[str]] = None
    objective_value: Optional[float] = None
    total_internal_hours: Optional[float] = None


class TimeRange(BaseModel):
    start: str
    end: str


class DaySchedule(BaseModel):
    ranges: List[TimeRange]
    hours: float


class EmployeeSchedule(BaseModel):
    days: Dict[str, DaySchedule]
    total_hours: float


class PlanningResponse(BaseModel):
    status: str
    schedule: Optional[Dict[str, EmployeeSchedule]] = None
    solver_time: float
    solve_time_seconds: Optional[float] = None
    metrics: Optional[SolverMetrics] = None
    kpi: Optional[Dict[str, float]] = None
    error: Optional[str] = None
    total_overtime_used_hours: Optional[float] = None
    capacity_total_hours: Optional[float] = None
    coverage_total_hours: Optional[float] = None
    hours_per_employee: Optional[Dict[str, float]] = None
    suggestions: Optional[List[str]] = None
    classification: Optional[str] = None
    explanation: Optional[Dict[str, Any]] = None
    infeasibility_reasons: Optional[List[Dict[str, Any]]] = None
    overrides_applied: Optional[List[Dict[str, Any]]] = None
    overrides_rejected: Optional[List[Dict[str, Any]]] = None


class AdjustPlanningRequest(PlanningRequest):
    contract_overrides: Optional[Dict[str, float]] = Field(default=None)
    overtime_max: Optional[int] = Field(default=None)
    coverage_overrides: Optional[Dict[int, int]] = Field(default=None)
    employee: Optional[str] = Field(default=None)
    day: Optional[str] = Field(default=None)
    new_status: Optional[Literal["working", "off", "unavailable"]] = Field(default=None)


class SimulatePlanningRequest(BaseModel):
    employees: List[str] = Field(..., min_length=1)
    contracts: List[float] = Field(..., min_length=1)
    roles: List[str] = Field(..., min_length=1)
    constraints: Optional[List[Dict[str, Any]]] = Field(default=None)
    opening_hours: Dict[str, Any]
    opening_days: Optional[List[str]] = Field(default=None)
    min_staff: Union[int, List[int], Dict[str, int]]


class SimulatePlanningResponse(BaseModel):
    schedule: Optional[Dict[str, EmployeeSchedule]] = None
    kpi_summary: Optional[Dict[str, Any]] = None
    explanation: Optional[Dict[str, Any]] = None


@app.get("/")
def root_status() -> Dict[str, str]:
    return {"status": "ok", "engine": "easyplan-v1-weekly-strict"}


def _prepare_config(base_config: dict, request_config: Optional[Dict[str, Any]]) -> dict:
    config = {}

    if request_config:
        config.update(request_config)

    # V1 strict configuration
    config["soft_weights"] = {}
    config["long_term_equity_weight"] = 0
    config["fast_solve"] = False

    return config


def _response_from_engine_output(
    output: Dict[str, Any],
    *,
    overrides_applied: Optional[List[Dict[str, Any]]] = None,
    overrides_rejected: Optional[List[Dict[str, Any]]] = None,
) -> PlanningResponse:
    return PlanningResponse(
        status=output.get("status", "timeout"),
        schedule=output.get("schedule"),
        solver_time=output.get("solver_time", 0.0),
        solve_time_seconds=output.get("solve_time_seconds"),
        metrics=output.get("metrics"),
        kpi=output.get("kpi"),
        error=output.get("error"),
        hours_per_employee=output.get("hours_per_employee"),
        suggestions=None,
        classification=None,
        explanation=output.get("explanation"),
        infeasibility_reasons=output.get("infeasibility_reasons"),
        overrides_applied=overrides_applied,
        overrides_rejected=overrides_rejected,
    )


def _merge_manual_overrides(
    base_constraints: Optional[List[Dict[str, Any]]],
    manual_overrides: Optional[List[Dict[str, Any]]],
    *,
    mode: Literal["soft", "strict"],
) -> List[Dict[str, Any]]:
    constraints = list(base_constraints or [])
    overrides = manual_overrides or []
    for override in overrides:
        employee = override.get("employee")
        day = override.get("day")
        status = override.get("new_status")
        if not employee or not day or status not in ("working", "off", "unavailable"):
            continue
        constraints = [
            c
            for c in constraints
            if not (
                c.get("type") in ("day_status", "manual_override_preference")
                and c.get("employee") == employee
                and c.get("day") == day
            )
        ]
        if mode == "strict":
            constraints.append(
                {
                    "type": "day_status",
                    "employee": employee,
                    "day": day,
                    "status": status,
                }
            )
        else:
            constraints.append(
                {
                    "type": "manual_override_preference",
                    "employee": employee,
                    "day": day,
                    "status": status,
                }
            )
    return constraints


def _evaluate_manual_overrides(
    schedule: Optional[Dict[str, Any]],
    overrides: Optional[List[Dict[str, Any]]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not overrides:
        return [], []
    if schedule is None:
        return [], [
            {
                **override,
                "reason": "Aucune solution faisable avec les contraintes hard actuelles.",
            }
            for override in overrides
        ]

    applied: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for override in overrides:
        employee = override.get("employee")
        day = override.get("day")
        status = override.get("new_status")
        if not employee or not day or status not in ("working", "off", "unavailable"):
            rejected.append({**override, "reason": "Override invalide (employee/day/status)."})
            continue

        day_data = ((schedule.get(employee) or {}).get("days") or {}).get(day)
        is_working = bool(day_data and len(day_data.get("ranges", [])) > 0)
        wants_working = status == "working"

        if wants_working == is_working:
            applied.append(override)
        else:
            rejected.append(
                {
                    **override,
                    "reason": "Incompatible avec contraintes hard (repos legal, couverture ou qualification).",
                }
            )

    return applied, rejected


def _parse_hhmm_to_minutes(value: str) -> int:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"Heure invalide: {value}")
    hours = int(parts[0])
    minutes = int(parts[1])
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        raise ValueError(f"Heure invalide: {value}")
    return hours * 60 + minutes


WEEKDAY_ORDER = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def _normalize_opening_days(opening_days: Optional[List[str]]) -> List[str]:
    if opening_days is None:
        return list(WEEKDAY_ORDER)

    normalized_days: List[str] = []
    for day in opening_days:
        normalized = str(day).strip().lower()
        if normalized not in WEEKDAY_ORDER:
            raise ValueError(f"Jour d'ouverture invalide: {day}")
        if normalized not in normalized_days:
            normalized_days.append(normalized)

    if not normalized_days:
        raise ValueError("Au moins un jour d'ouverture est requis.")

    return normalized_days


def _build_simulation_days_and_config(request: SimulatePlanningRequest) -> tuple[List[str], Dict[str, Any]]:
    config = _prepare_config({}, None)
    schedule_cfg = config.setdefault("schedule", {})
    normalized_opening_days = _normalize_opening_days(request.opening_days)

    opening_hours = request.opening_hours or {}
    reserved_keys = {"open", "close", "start_time_minutes", "end_time_minutes", "opening_days", "closed_weekdays"}
    day_keys = [key for key in opening_hours.keys() if key not in reserved_keys]

    if day_keys:
        days = day_keys
        first_day_conf = opening_hours.get(days[0], {}) or {}
        open_time = first_day_conf.get("open")
        close_time = first_day_conf.get("close")
        if open_time is not None and close_time is not None:
            schedule_cfg["start_time_minutes"] = _parse_hhmm_to_minutes(str(open_time))
            schedule_cfg["end_time_minutes"] = _parse_hhmm_to_minutes(str(close_time))
    else:
        days = [f"J{i}" for i in range(7)]
        if "start_time_minutes" in opening_hours and "end_time_minutes" in opening_hours:
            schedule_cfg["start_time_minutes"] = int(opening_hours["start_time_minutes"])
            schedule_cfg["end_time_minutes"] = int(opening_hours["end_time_minutes"])
        elif "open" in opening_hours and "close" in opening_hours:
            schedule_cfg["start_time_minutes"] = _parse_hhmm_to_minutes(str(opening_hours["open"]))
            schedule_cfg["end_time_minutes"] = _parse_hhmm_to_minutes(str(opening_hours["close"]))
        config["closed_weekdays"] = [
            weekday_idx
            for weekday_idx, weekday_name in enumerate(WEEKDAY_ORDER)
            if weekday_name not in normalized_opening_days
        ]

    min_staff = request.min_staff
    if isinstance(min_staff, int):
        schedule_cfg["min_staff_per_slot"] = int(min_staff)
    elif isinstance(min_staff, list):
        if len(min_staff) != len(days):
            raise ValueError("min_staff (liste) doit avoir la meme longueur que les jours.")
        schedule_cfg["min_staff_per_day"] = [int(v) for v in min_staff]
    elif isinstance(min_staff, dict):
        if not day_keys:
            raise ValueError("min_staff (dict) requiert opening_hours avec jours explicites.")
        schedule_cfg["min_staff_per_day"] = [int(min_staff.get(day, 1)) for day in days]
    else:
        raise ValueError("Format min_staff non supporte.")

    return days, config


@app.post("/generate-planning", response_model=PlanningResponse)
def generate_planning(request: PlanningRequest) -> PlanningResponse:
    payload = request.model_dump()
    print("API INPUT DEBUG")
    print("payload opening hours:", payload.get("opening_hours"))

    config = _prepare_config({}, request.config)
    unavailabilities = [tuple(u) for u in request.unavailabilities] if request.unavailabilities else []

    try:
        merged_constraints = _merge_manual_overrides(
            request.constraints,
            request.manual_overrides,
            mode=request.manual_override_mode,
        )
        output = run_weekly_v1_engine(
            employees=request.employees,
            contracts=request.contracts,
            roles=request.roles,
            constraints=merged_constraints,
            days=request.days,
            config=config,
            unavailabilities=unavailabilities,
        )
    except ValueError as exc:
        return PlanningResponse(
            status="validation_error",
            schedule=None,
            solver_time=0.0,
            metrics=None,
            kpi=None,
            error=str(exc),
            explanation={"summary": str(exc), "details": []},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur solveur: {exc}")

    overrides_applied, overrides_rejected = _evaluate_manual_overrides(
        output.get("schedule"),
        request.manual_overrides,
    )
    return _response_from_engine_output(
        output,
        overrides_applied=overrides_applied,
        overrides_rejected=overrides_rejected,
    )


@app.post("/adjust-planning", response_model=PlanningResponse)
def adjust_planning(request: AdjustPlanningRequest) -> PlanningResponse:
    payload = request.model_dump()
    print("API INPUT DEBUG")
    print("payload opening hours:", payload.get("opening_hours"))

    config = _prepare_config({}, request.config)

    employees = list(request.employees)
    contracts = list(request.contracts)

    constraints = _merge_manual_overrides(
        request.constraints,
        request.manual_overrides,
        mode=request.manual_override_mode,
    )
    if request.employee and request.day and request.new_status:
        constraints.append(
            {
                "type": "day_status",
                "employee": request.employee,
                "day": request.day,
                "status": request.new_status,
            }
        )

    if request.contract_overrides:
        for name, new_contract in request.contract_overrides.items():
            if name in employees:
                idx = employees.index(name)
                contracts[idx] = float(new_contract)

    if request.coverage_overrides:
        schedule_cfg = config.setdefault("schedule", {})
        base_min_staff = int(schedule_cfg.get("min_staff_per_slot", 1))
        min_staff_per_day = [base_min_staff for _ in range(len(request.days))]
        for day_idx, min_staff_day in request.coverage_overrides.items():
            if 0 <= day_idx < len(min_staff_per_day):
                min_staff_per_day[day_idx] = int(min_staff_day)
        schedule_cfg["min_staff_per_day"] = min_staff_per_day

    unavailabilities = [tuple(u) for u in request.unavailabilities] if request.unavailabilities else []

    try:
        output = run_weekly_v1_engine(
            employees=employees,
            contracts=contracts,
            roles=request.roles,
            constraints=constraints,
            days=request.days,
            config=config,
            unavailabilities=unavailabilities,
        )
    except ValueError as exc:
        return PlanningResponse(
            status="validation_error",
            schedule=None,
            solver_time=0.0,
            metrics=None,
            kpi=None,
            error=str(exc),
            explanation={"summary": str(exc), "details": []},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur solveur: {exc}")

    overrides_applied, overrides_rejected = _evaluate_manual_overrides(
        output.get("schedule"),
        request.manual_overrides,
    )
    return _response_from_engine_output(
        output,
        overrides_applied=overrides_applied,
        overrides_rejected=overrides_rejected,
    )


@app.post("/simulate-planning", response_model=SimulatePlanningResponse)
def simulate_planning(request: SimulatePlanningRequest) -> SimulatePlanningResponse:
    try:
        days, config = _build_simulation_days_and_config(request)
        output = run_weekly_v1_engine(
            employees=request.employees,
            contracts=request.contracts,
            roles=request.roles,
            constraints=request.constraints,
            days=days,
            config=config,
            unavailabilities=[],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur solveur: {exc}")

    return SimulatePlanningResponse(
        schedule=output.get("schedule"),
        kpi_summary=output.get("kpi_summary"),
        explanation=output.get("explanation"),
    )


frontend_path = "frontend/dist"

if os.path.exists(frontend_path):
    app.mount("/assets", StaticFiles(directory=f"{frontend_path}/assets"), name="assets")


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    index_path = os.path.join(frontend_path, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "frontend not built"}
