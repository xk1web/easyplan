from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
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
        "http://localhost:5173",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PreviousMonthStats(BaseModel):
    total_hours: Optional[Dict[str, float]] = Field(default=None)
    saturdays_worked: Optional[Dict[str, int]] = Field(default=None)


class PlanningRequest(BaseModel):
    employees: List[str] = Field(..., min_length=1)
    contracts: List[float] = Field(..., min_length=1)
    roles: List[str] = Field(..., min_length=1)
    days: List[str] = Field(..., min_length=1)
    unavailabilities: Optional[List[List[int]]] = Field(default=[])
    config: Optional[Dict[str, Any]] = Field(default=None)
    previous_month_stats: Optional[PreviousMonthStats] = Field(default=None)


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


class AdjustPlanningRequest(PlanningRequest):
    contract_overrides: Optional[Dict[str, float]] = Field(default=None)
    overtime_max: Optional[int] = Field(default=None)
    coverage_overrides: Optional[Dict[int, int]] = Field(default=None)


@app.get("/")
def health() -> Dict[str, str]:
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


def _response_from_engine_output(output: Dict[str, Any]) -> PlanningResponse:
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
    )


@app.post("/generate-planning", response_model=PlanningResponse)
def generate_planning(request: PlanningRequest) -> PlanningResponse:
    payload = request.model_dump()
    print("API INPUT DEBUG")
    print("payload opening hours:", payload.get("opening_hours"))

    config = _prepare_config({}, request.config)
    unavailabilities = [tuple(u) for u in request.unavailabilities] if request.unavailabilities else []

    try:
        output = run_weekly_v1_engine(
            employees=request.employees,
            contracts=request.contracts,
            roles=request.roles,
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

    return _response_from_engine_output(output)


@app.post("/adjust-planning", response_model=PlanningResponse)
def adjust_planning(request: AdjustPlanningRequest) -> PlanningResponse:
    payload = request.model_dump()
    print("API INPUT DEBUG")
    print("payload opening hours:", payload.get("opening_hours"))

    config = _prepare_config({}, request.config)

    employees = list(request.employees)
    contracts = list(request.contracts)

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

    return _response_from_engine_output(output)
