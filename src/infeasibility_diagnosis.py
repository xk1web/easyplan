import copy
import io
import json
import logging
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Dict, List, Optional, Tuple

from src.config import load_config
# LEGACY ENGINE - DO NOT USE
# from src.model_builder_v1 import build_and_solve_v1
from src.validation import validate_global_feasibility


logging.basicConfig(level=logging.INFO, format="%(message)s")


def _deep_merge(base: Dict[str, Any], overrides: Dict[str, Any]) -> None:
    for key, value in overrides.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _make_days(num_days: int) -> List[str]:
    week = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
    return [week[i % 7] for i in range(num_days)]


def _build_base_config(min_staff: int, optician_required: bool, rest_11h: bool) -> Dict[str, Any]:
    cfg = load_config()
    overrides = {
        "schedule": {
            "start_time_minutes": 10 * 60,
            "end_time_minutes": 19 * 60,
            "slot_minutes": 15,
            "min_staff_per_slot": min_staff,
        },
        "hard_constraints": {
            "max_days_per_week": 5,
            "require_qualified_optician": optician_required,
            "rest_between_days_minutes": 660 if rest_11h else 0,
        },
        "debug_diagnosis": {
            "enabled": True,
            "solver_logs": False,
        },
        "solver": {
            "max_time_seconds": 8,
        },
    }
    _deep_merge(cfg, overrides)
    return cfg


def _build_people(num_employees: int, optician_required: bool) -> Tuple[List[str], List[int], List[str]]:
    employees = [f"E{i+1}" for i in range(num_employees)]
    contracts = [35 for _ in range(num_employees)]
    if optician_required:
        roles = ["opticien"] + ["vendeur" for _ in range(num_employees - 1)]
    else:
        roles = ["vendeur" for _ in range(num_employees)]
    return employees, contracts, roles


def _run_one(
    num_employees: int,
    min_staff: int,
    optician_required: bool,
    rest_11h: bool,
    num_days: int = 7,
    solver_logs: bool = False,
    custom_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    config = _build_base_config(min_staff, optician_required, rest_11h)
    if custom_config:
        _deep_merge(config, custom_config)
    config["debug_diagnosis"]["solver_logs"] = solver_logs

    employees, contracts, roles = _build_people(num_employees, optician_required)
    days = _make_days(num_days)

    validation_error = None
    try:
        validate_global_feasibility(
            employees=employees,
            contracts=contracts,
            days=days,
            config=config,
            roles=roles,
            unavailabilities=[],
        )
    except Exception as exc:
        validation_error = str(exc)

    if validation_error:
        return {
            "status": "VALIDATION_ERROR",
            "error": validation_error,
            "metrics": None,
            "config": config,
            "employees": employees,
            "contracts": contracts,
            "roles": roles,
            "days": days,
        }

    result = build_and_solve_v1(
        employees=employees,
        days=days,
        contracts=contracts,
        config=config,
        roles=roles,
        unavailabilities=[],
        previous_month_stats=None,
    )
    metrics = result.get("metrics", {})
    status = metrics.get("solver_status", "UNKNOWN")
    return {
        "status": status,
        "error": result.get("error"),
        "metrics": metrics,
        "config": config,
        "employees": employees,
        "contracts": contracts,
        "roles": roles,
        "days": days,
    }


def _progressive_relaxation(case: Dict[str, Any]) -> List[Tuple[str, str]]:
    steps: List[Tuple[str, Dict[str, Any]]] = [
        ("baseline", {}),
        (
            "templates",
            {
                "shift_templates": [],
                "soft_weights": {
                    "non_template_penalty": 0,
                    "template_deviation_weight": 0,
                    "shift_type_presence_penalty": 0,
                },
            },
        ),
        (
            "daily_balance",
            {
                "soft_weights": {
                    "weight_daily_balance": 0,
                }
            },
        ),
        (
            "fairness",
            {
                "soft_weights": {
                    "saturday_fairness": 0,
                    "weekly_hours_fairness": 0,
                    "close_fairness": 0,
                    "late_fairness_penalty": 0,
                    "amplitude_fairness": 0,
                    "days_concentration_penalty": 0,
                }
            },
        ),
        (
            "demand_reward",
            {
                "soft_weights": {
                    "hourly_demand_weight": 0,
                }
            },
        ),
    ]

    cumulative_overrides: Dict[str, Any] = {}
    outputs: List[Tuple[str, str]] = []
    for name, override in steps:
        _deep_merge(cumulative_overrides, copy.deepcopy(override))
        run = _run_one(
            num_employees=len(case["employees"]),
            min_staff=case["config"]["schedule"]["min_staff_per_slot"],
            optician_required=case["config"]["hard_constraints"]["require_qualified_optician"],
            rest_11h=case["config"]["hard_constraints"]["rest_between_days_minutes"] > 0,
            num_days=len(case["days"]),
            solver_logs=False,
            custom_config=cumulative_overrides,
        )
        outputs.append((name, run["status"]))
        if run["status"] in ("OPTIMAL", "FEASIBLE"):
            outputs.append(("feasible_after_removing", name))
            break
    return outputs


def _collect_solver_logs(case: Dict[str, Any]) -> List[str]:
    logs_io = io.StringIO()
    with redirect_stdout(logs_io), redirect_stderr(logs_io):
        _run_one(
            num_employees=len(case["employees"]),
            min_staff=case["config"]["schedule"]["min_staff_per_slot"],
            optician_required=case["config"]["hard_constraints"]["require_qualified_optician"],
            rest_11h=case["config"]["hard_constraints"]["rest_between_days_minutes"] > 0,
            num_days=len(case["days"]),
            solver_logs=True,
        )
    lines = logs_io.getvalue().splitlines()
    interesting = []
    keys = ("conflict", "infeas", "reduced", "presolve")
    for line in lines:
        l = line.lower()
        if any(k in l for k in keys):
            interesting.append(line)
    return interesting[:40]


def _hypothesis(case: Dict[str, Any], relaxation: List[Tuple[str, str]]) -> str:
    if case["status"] == "VALIDATION_ERROR":
        return "Infeasible avant solveur: validation globale échoue."
    hd = (case.get("metrics") or {}).get("hard_debug", {})
    margin = hd.get("theoretical_margin_hours")
    if isinstance(margin, (int, float)) and margin < 0:
        return "Capacité HARD insuffisante: heures requises > heures maximales théoriques."
    for step, status in relaxation:
        if step == "feasible_after_removing":
            return f"Espace de recherche trop contraint par softs, relâché à l'étape: {status}."
    return "Combinaison probable: max_days_per_week=5 + repos/qualification + objectifs soft restants."


def main() -> None:
    scenarios = []
    for n in [3, 4, 6, 8]:
        for min_staff in [1, 2]:
            for opt_req in [False, True]:
                for rest_11h in [False, True]:
                    scenarios.append((n, min_staff, opt_req, rest_11h))

    print("=== INFEASIBILITY DIAGNOSIS ===")
    first_infeasible = None
    detailed_results = []

    for n, min_staff, opt_req, rest_11h in scenarios:
        result = _run_one(
            num_employees=n,
            min_staff=min_staff,
            optician_required=opt_req,
            rest_11h=rest_11h,
            num_days=7,
            solver_logs=False,
        )
        hard_debug = (result.get("metrics") or {}).get("hard_debug", {})
        print(
            f"Scenario n={n}, min_staff={min_staff}, optician_required={opt_req}, rest_11h={rest_11h} "
            f"=> {result['status']}"
        )
        if hard_debug:
            print(
                f"  Requis: {hard_debug['total_required_hours']:.1f}h | "
                f"Disponible: {hard_debug['total_contract_hours']:.1f}h | "
                f"Max feasible under 5-day constraint: {hard_debug['max_feasible_hours_under_hard']:.1f}h | "
                f"Margin: {hard_debug['theoretical_margin_hours']:.1f}h"
            )

        detailed_results.append(result)
        if first_infeasible is None and result["status"] in ("INFEASIBLE", "VALIDATION_ERROR"):
            first_infeasible = result

    print("\n=== MINIMAL STRUCTURE CHECK (block + templates) ===")
    minimal_case = _run_one(
        num_employees=3,
        min_staff=1,
        optician_required=False,
        rest_11h=True,
        num_days=5,
    )
    print(f"Minimal 3 emp / 5 days / 10-19 / min_staff=1 => {minimal_case['status']}")
    if minimal_case["status"] in ("INFEASIBLE", "VALIDATION_ERROR"):
        print("Hypothesis: interaction structure (single block + templates) may be contracting search space.")

    if first_infeasible is None:
        print("\nNo infeasible scenario found in this grid.")
        return

    print("\n=== FIRST INFEASIBLE COMPLEXITY LEVEL ===")
    fi_cfg = first_infeasible["config"]
    print(
        json.dumps(
            {
                "employees": len(first_infeasible["employees"]),
                "min_staff": fi_cfg["schedule"]["min_staff_per_slot"],
                "optician_required": fi_cfg["hard_constraints"]["require_qualified_optician"],
                "rest_11h": fi_cfg["hard_constraints"]["rest_between_days_minutes"] > 0,
                "status": first_infeasible["status"],
                "error": first_infeasible["error"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\n=== PROGRESSIVE RELAXATION ===")
    relaxation = _progressive_relaxation(first_infeasible)
    for name, status in relaxation:
        if name == "feasible_after_removing":
            print(f"Feasible after removing: {status}")
        else:
            print(f"{name}: {status}")

    print("\n=== SOLVER CONFLICT / PRESOLVE LOG EXTRACT ===")
    log_lines = _collect_solver_logs(first_infeasible)
    if log_lines:
        for line in log_lines:
            print(line)
    else:
        print("No explicit conflicting-constraint lines found in solver logs.")

    print("\n=== HYPOTHESIS ===")
    print(_hypothesis(first_infeasible, relaxation))


if __name__ == "__main__":
    main()
