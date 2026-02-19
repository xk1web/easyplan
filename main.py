import time
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from src.config import load_config
from src.validation import validate_global_feasibility
from src.model_builder_v1 import build_and_solve_v1
from src.suggestion_engine import (
    compute_coverage_hours,
    compute_capacity_hours,
    compute_capacity_with_overtime_hours,
    classify_result,
    generate_suggestions,
)

app = FastAPI(
    title="Planning Engine API",
    description="Moteur de génération de planning pour magasins d'optique (CP-SAT)",
    version="2.0.0",
)


class PreviousMonthStats(BaseModel):
    total_hours: Optional[Dict[str, float]] = Field(default=None)
    saturdays_worked: Optional[Dict[str, int]] = Field(default=None)


class PlanningRequest(BaseModel):
    employees: List[str] = Field(..., min_length=1)
    contracts: List[int] = Field(..., min_length=1)
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


class PlanningResponse(BaseModel):
    status: str
    schedule: Optional[Dict[str, Any]] = None
    solver_time: float
    solve_time_seconds: Optional[float] = None
    metrics: Optional[SolverMetrics] = None
    error: Optional[str] = None
    total_overtime_used_hours: Optional[float] = None
    capacity_total_hours: Optional[float] = None
    coverage_total_hours: Optional[float] = None
    hours_per_employee: Optional[Dict[str, float]] = None
    suggestions: Optional[List[str]] = None
    classification: Optional[str] = None


class AdjustPlanningRequest(PlanningRequest):
    contract_overrides: Optional[Dict[str, int]] = Field(default=None)
    overtime_max: Optional[int] = Field(default=None)
    coverage_overrides: Optional[Dict[int, int]] = Field(default=None)


@app.get("/")
def health():
    return {"status": "ok", "engine": "planning-optique-v2"}


@app.post("/generate-planning", response_model=PlanningResponse)
def generate_planning(request: PlanningRequest):
    config = load_config()
    if request.config:
        from src.config import _deep_merge
        _deep_merge(config, request.config)

    unavailabilities = [tuple(u) for u in request.unavailabilities] if request.unavailabilities else []

    prev_stats = None
    if request.previous_month_stats:
        prev_stats = {}
        if request.previous_month_stats.total_hours:
            prev_stats["total_hours"] = request.previous_month_stats.total_hours
        if request.previous_month_stats.saturdays_worked:
            prev_stats["saturdays_worked"] = request.previous_month_stats.saturdays_worked

    validation_error = None
    try:
        validate_global_feasibility(
            employees=request.employees,
            contracts=request.contracts,
            days=request.days,
            config=config,
            roles=request.roles,
            unavailabilities=unavailabilities,
        )
    except ValueError as e:
        validation_error = str(e)

    result = {}
    solver_time = 0.0
    if validation_error is None:
        t0 = time.time()
        try:
            result = build_and_solve_v1(
                employees=request.employees,
                days=request.days,
                contracts=request.contracts,
                config=config,
                roles=request.roles,
                unavailabilities=unavailabilities,
                previous_month_stats=prev_stats,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erreur solveur : {str(e)}")
        solver_time = round(time.time() - t0, 3)

    metrics_data = result.get("metrics") if result else None
    metrics = SolverMetrics(**metrics_data) if metrics_data else None
    coverage_total_hours = compute_coverage_hours(config, len(request.days))
    capacity_total_hours = compute_capacity_hours(request.contracts, len(request.days))
    capacity_with_overtime = compute_capacity_with_overtime_hours(request.contracts, len(request.days), config)
    hours_per_employee = None
    total_overtime_used_hours = None
    if metrics and metrics.total_overtime_used_slots is not None:
        sched = config.get("schedule", config)
        slot_minutes = sched.get("slot_minutes", 15)
        total_overtime_used_hours = metrics.total_overtime_used_slots * slot_minutes / 60.0

    classification = classify_result(
        validation_error=validation_error,
        solver_status=metrics.solver_status if metrics else None,
        coverage_total_hours=coverage_total_hours,
        capacity_total_hours=capacity_total_hours,
        capacity_with_overtime_hours=capacity_with_overtime,
        total_overtime_used_hours=total_overtime_used_hours,
    )
    hard = config.get("hard_constraints", {})
    suggestions, _reason_codes = generate_suggestions(
        classification=classification,
        coverage_total_hours=coverage_total_hours,
        capacity_total_hours=capacity_total_hours,
        capacity_with_overtime_hours=capacity_with_overtime,
        total_overtime_used_hours=total_overtime_used_hours,
        require_optician=hard.get("require_qualified_optician", True),
        rest_between_days_minutes=hard.get("rest_between_days_minutes", 660),
        max_days_per_week=hard.get("max_days_per_week", 6),
        has_unavailabilities=bool(unavailabilities),
        hours_per_employee=hours_per_employee,
        contracts=request.contracts,
        inequity_threshold_ratio=config.get("inequity_threshold_ratio", 0.2),
        solver_status=metrics.solver_status if metrics else None,
    )

    if validation_error is not None:
        return PlanningResponse(
            status="validation_error",
            schedule=None,
            solver_time=solver_time,
            solve_time_seconds=metrics.solver_wall_time if metrics else None,
            metrics=metrics,
            error=validation_error,
            total_overtime_used_hours=total_overtime_used_hours,
            capacity_total_hours=capacity_total_hours,
            coverage_total_hours=coverage_total_hours,
            hours_per_employee=hours_per_employee,
            suggestions=suggestions or None,
            classification=classification,
        )

    if "error" in result:
        return PlanningResponse(
            status="infeasible",
            schedule=None,
            solver_time=solver_time,
            solve_time_seconds=metrics.solver_wall_time if metrics else None,
            metrics=metrics,
            error=result["error"],
            total_overtime_used_hours=total_overtime_used_hours,
            capacity_total_hours=capacity_total_hours,
            coverage_total_hours=coverage_total_hours,
            hours_per_employee=hours_per_employee,
            suggestions=suggestions or None,
            classification=classification,
        )

    hours_per_employee = {
        emp: data["total_hours"] for emp, data in result["schedule"].items()
    }

    return PlanningResponse(
        status=metrics.solver_status.lower() if metrics else "optimal",
        schedule=result["schedule"],
        solver_time=solver_time,
        solve_time_seconds=metrics.solver_wall_time if metrics else None,
        metrics=metrics,
        total_overtime_used_hours=total_overtime_used_hours,
        capacity_total_hours=capacity_total_hours,
        coverage_total_hours=coverage_total_hours,
        hours_per_employee=hours_per_employee,
        suggestions=suggestions or None,
        classification=classification,
    )


@app.post("/adjust-planning", response_model=PlanningResponse)
def adjust_planning(request: AdjustPlanningRequest):
    config = load_config()
    if request.config:
        from src.config import _deep_merge
        _deep_merge(config, request.config)

    employees = list(request.employees)
    contracts = list(request.contracts)
    if request.contract_overrides:
        for name, new_contract in request.contract_overrides.items():
            if name in employees:
                idx = employees.index(name)
                contracts[idx] = new_contract

    if request.overtime_max is not None:
        config.setdefault("hard_constraints", {})
        config["hard_constraints"]["contract_overtime_slots"] = request.overtime_max

    if request.coverage_overrides:
        sched = config.get("schedule", config)
        min_staff = sched.get("min_staff_per_slot", 1)
        min_staff_per_day = [min_staff for _ in range(len(request.days))]
        for day_idx, min_staff_day in request.coverage_overrides.items():
            if 0 <= day_idx < len(min_staff_per_day):
                min_staff_per_day[day_idx] = min_staff_day
        sched["min_staff_per_day"] = min_staff_per_day

    unavailabilities = [tuple(u) for u in request.unavailabilities] if request.unavailabilities else []

    prev_stats = None
    if request.previous_month_stats:
        prev_stats = {}
        if request.previous_month_stats.total_hours:
            prev_stats["total_hours"] = request.previous_month_stats.total_hours
        if request.previous_month_stats.saturdays_worked:
            prev_stats["saturdays_worked"] = request.previous_month_stats.saturdays_worked

    validation_error = None
    try:
        validate_global_feasibility(
            employees=employees,
            contracts=contracts,
            days=request.days,
            config=config,
            roles=request.roles,
            unavailabilities=unavailabilities,
        )
    except ValueError as e:
        validation_error = str(e)

    result = {}
    solver_time = 0.0
    if validation_error is None:
        t0 = time.time()
        try:
            result = build_and_solve_v1(
                employees=employees,
                days=request.days,
                contracts=contracts,
                config=config,
                roles=request.roles,
                unavailabilities=unavailabilities,
                previous_month_stats=prev_stats,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erreur solveur : {str(e)}")
        solver_time = round(time.time() - t0, 3)

    metrics_data = result.get("metrics") if result else None
    metrics = SolverMetrics(**metrics_data) if metrics_data else None
    coverage_total_hours = compute_coverage_hours(config, len(request.days))
    capacity_total_hours = compute_capacity_hours(contracts, len(request.days))
    capacity_with_overtime = compute_capacity_with_overtime_hours(contracts, len(request.days), config)
    hours_per_employee = None
    total_overtime_used_hours = None
    if metrics and metrics.total_overtime_used_slots is not None:
        sched = config.get("schedule", config)
        slot_minutes = sched.get("slot_minutes", 15)
        total_overtime_used_hours = metrics.total_overtime_used_slots * slot_minutes / 60.0

    classification = classify_result(
        validation_error=validation_error,
        solver_status=metrics.solver_status if metrics else None,
        coverage_total_hours=coverage_total_hours,
        capacity_total_hours=capacity_total_hours,
        capacity_with_overtime_hours=capacity_with_overtime,
        total_overtime_used_hours=total_overtime_used_hours,
    )
    hard = config.get("hard_constraints", {})
    suggestions, _reason_codes = generate_suggestions(
        classification=classification,
        coverage_total_hours=coverage_total_hours,
        capacity_total_hours=capacity_total_hours,
        capacity_with_overtime_hours=capacity_with_overtime,
        total_overtime_used_hours=total_overtime_used_hours,
        require_optician=hard.get("require_qualified_optician", True),
        rest_between_days_minutes=hard.get("rest_between_days_minutes", 660),
        max_days_per_week=hard.get("max_days_per_week", 6),
        has_unavailabilities=bool(unavailabilities),
        hours_per_employee=hours_per_employee,
        contracts=contracts,
        inequity_threshold_ratio=config.get("inequity_threshold_ratio", 0.2),
        solver_status=metrics.solver_status if metrics else None,
    )

    if validation_error is not None:
        return PlanningResponse(
            status="validation_error",
            schedule=None,
            solver_time=solver_time,
            solve_time_seconds=metrics.solver_wall_time if metrics else None,
            metrics=metrics,
            error=validation_error,
            total_overtime_used_hours=total_overtime_used_hours,
            capacity_total_hours=capacity_total_hours,
            coverage_total_hours=coverage_total_hours,
            hours_per_employee=hours_per_employee,
            suggestions=suggestions or None,
            classification=classification,
        )

    if "error" in result:
        return PlanningResponse(
            status="infeasible",
            schedule=None,
            solver_time=solver_time,
            solve_time_seconds=metrics.solver_wall_time if metrics else None,
            metrics=metrics,
            error=result["error"],
            total_overtime_used_hours=total_overtime_used_hours,
            capacity_total_hours=capacity_total_hours,
            coverage_total_hours=coverage_total_hours,
            hours_per_employee=hours_per_employee,
            suggestions=suggestions or None,
            classification=classification,
        )

    hours_per_employee = {
        emp: data["total_hours"] for emp, data in result["schedule"].items()
    }

    return PlanningResponse(
        status=metrics.solver_status.lower() if metrics else "optimal",
        schedule=result["schedule"],
        solver_time=solver_time,
        solve_time_seconds=metrics.solver_wall_time if metrics else None,
        metrics=metrics,
        total_overtime_used_hours=total_overtime_used_hours,
        capacity_total_hours=capacity_total_hours,
        coverage_total_hours=coverage_total_hours,
        hours_per_employee=hours_per_employee,
        suggestions=suggestions or None,
        classification=classification,
    )
