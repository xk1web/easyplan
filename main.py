import time
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from src.config import load_config
from src.validation import validate_global_feasibility
from src.model_builder_v1 import build_and_solve_v1

app = FastAPI(
    title="Planning Engine API",
    description="Moteur de génération de planning pour magasins d'optique (CP-SAT)",
    version="1.0.0",
)


class PlanningRequest(BaseModel):
    employees: List[str] = Field(..., min_length=1)
    contracts: List[int] = Field(..., min_length=1)
    roles: List[str] = Field(..., min_length=1)
    days: List[str] = Field(..., min_length=1)
    unavailabilities: Optional[List[List[int]]] = Field(default=[])
    config: Optional[Dict[str, Any]] = Field(default=None)


class PlanningResponse(BaseModel):
    status: str
    schedule: Optional[Dict[str, Any]] = None
    solver_time: float
    error: Optional[str] = None


@app.get("/")
def health():
    return {"status": "ok", "engine": "planning-optique-v1"}


@app.post("/generate-planning", response_model=PlanningResponse)
def generate_planning(request: PlanningRequest):
    config = load_config()
    if request.config:
        from src.config import _deep_merge
        _deep_merge(config, request.config)

    unavailabilities = [tuple(u) for u in request.unavailabilities] if request.unavailabilities else []

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
        raise HTTPException(status_code=422, detail=str(e))

    t0 = time.time()
    try:
        result = build_and_solve_v1(
            employees=request.employees,
            days=request.days,
            contracts=request.contracts,
            config=config,
            roles=request.roles,
            unavailabilities=unavailabilities,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur solveur : {str(e)}")
    solver_time = round(time.time() - t0, 3)

    if "error" in result:
        return PlanningResponse(
            status="infeasible",
            schedule=None,
            solver_time=solver_time,
            error=result["error"],
        )

    return PlanningResponse(
        status="optimal",
        schedule=result["schedule"],
        solver_time=solver_time,
    )
