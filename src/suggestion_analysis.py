import json
from typing import Any, Dict, List, Optional

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


def _deep_merge(base: Dict[str, Any], overrides: Dict[str, Any]) -> None:
    for key, value in overrides.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def run_dataset(dataset: Dict[str, Any]) -> Dict[str, Any]:
    payload = dataset["payload"]
    config = load_config()
    if payload.get("config"):
        _deep_merge(config, payload["config"])

    unavailabilities = payload.get("unavailabilities") or []

    validation_error = None
    try:
        validate_global_feasibility(
            employees=payload["employees"],
            contracts=payload["contracts"],
            days=payload["days"],
            config=config,
            roles=payload.get("roles"),
            unavailabilities=unavailabilities,
        )
    except Exception as e:
        validation_error = str(e)

    result: Dict[str, Any] = {}
    if validation_error is None:
        result = build_and_solve_v1(
            employees=payload["employees"],
            days=payload["days"],
            contracts=payload["contracts"],
            config=config,
            roles=payload.get("roles"),
            unavailabilities=unavailabilities,
            previous_month_stats=None,
        )

    metrics = result.get("metrics") if result else None

    coverage_total_hours = compute_coverage_hours(config, len(payload["days"]))
    capacity_total_hours = compute_capacity_hours(payload["contracts"], len(payload["days"]))
    capacity_with_overtime_hours = compute_capacity_with_overtime_hours(
        payload["contracts"], len(payload["days"]), config
    )

    total_overtime_used_hours = None
    if metrics and metrics.get("total_overtime_used_slots") is not None:
        sched = config.get("schedule", config)
        slot_minutes = sched.get("slot_minutes", 15)
        total_overtime_used_hours = metrics["total_overtime_used_slots"] * slot_minutes / 60.0

    classification = classify_result(
        validation_error=validation_error,
        solver_status=metrics.get("solver_status") if metrics else None,
        coverage_total_hours=coverage_total_hours,
        capacity_total_hours=capacity_total_hours,
        capacity_with_overtime_hours=capacity_with_overtime_hours,
        total_overtime_used_hours=total_overtime_used_hours,
    )

    hard = config.get("hard_constraints", {})
    hours_per_employee = None
    if result.get("schedule"):
        hours_per_employee = {
            emp: data.get("total_hours", 0.0) for emp, data in result["schedule"].items()
        }
    suggestions, reason_codes = generate_suggestions(
        classification=classification,
        coverage_total_hours=coverage_total_hours,
        capacity_total_hours=capacity_total_hours,
        capacity_with_overtime_hours=capacity_with_overtime_hours,
        total_overtime_used_hours=total_overtime_used_hours,
        require_optician=hard.get("require_qualified_optician", True),
        rest_between_days_minutes=hard.get("rest_between_days_minutes", 660),
        max_days_per_week=hard.get("max_days_per_week", 6),
        has_unavailabilities=bool(unavailabilities),
        hours_per_employee=hours_per_employee,
        contracts=payload["contracts"],
        inequity_threshold_ratio=config.get("inequity_threshold_ratio", 0.2),
        solver_status=metrics.get("solver_status") if metrics else None,
    )

    return {
        "name": dataset["name"],
        "solver_status": metrics.get("solver_status") if metrics else None,
        "classification": classification,
        "coverage_total_hours": coverage_total_hours,
        "capacity_total_hours": capacity_total_hours,
        "capacity_with_overtime_hours": capacity_with_overtime_hours,
        "total_overtime_used_hours": total_overtime_used_hours,
        "objective_value": metrics.get("objective_value") if metrics else None,
        "objective_breakdown": metrics.get("objective_breakdown") if metrics else None,
        "suggestions": suggestions,
        "reason_codes": reason_codes,
        "error": validation_error or result.get("error"),
    }


def main() -> None:
    base_config = {
        "schedule": {
            "start_time_minutes": 9 * 60,
            "end_time_minutes": 17 * 60,
            "slot_minutes": 60,
            "min_staff_per_slot": 1,
        },
        "hard_constraints": {
            "contract_hours_mode": "hard",
            "contract_overtime_slots": 2,
            "max_days_per_week": 6,
            "max_daily_minutes": 600,
            "rest_between_days_minutes": 660,
            "weekly_rest_minutes": 2100,
            "require_qualified_optician": True,
            "min_daily_minutes": 0,
            "max_weekly_hours": True,
        },
        "soft_weights": {
            "hours_balancing": 5,
            "saturday_fairness": 5,
            "contiguity": 3,
            "weekly_hours_fairness": 4,
            "close_fairness": 3,
            "amplitude_fairness": 2,
            "contract_target": 50,
            "contract_overtime_penalty": 5,
        },
    }

    datasets = [
        {
            "name": "1_under_capacity_structural_validation",
            "payload": {
                "employees": ["E1", "E2"],
                "contracts": [20, 20],
                "roles": ["opticien", "vendeur"],
                "days": ["J1", "J2", "J3", "J4", "J5", "J6", "J7"],
                "unavailabilities": [],
                "config": {
                    **base_config,
                    "schedule": {
                        **base_config["schedule"],
                        "min_staff_per_slot": 1,
                        "start_time_minutes": 9 * 60,
                        "end_time_minutes": 17 * 60,
                    },
                },
            },
        },
        {
            "name": "2_under_capacity_even_with_overtime",
            "payload": {
                "employees": ["E1", "E2"],
                "contracts": [20, 20],
                "roles": ["opticien", "vendeur"],
                "days": ["J1", "J2", "J3", "J4", "J5", "J6", "J7"],
                "unavailabilities": [],
                "config": {
                    **base_config,
                    "schedule": {
                        **base_config["schedule"],
                        "start_time_minutes": 9 * 60,
                        "end_time_minutes": 18 * 60,
                        "min_staff_per_slot": 1,
                    },
                    "hard_constraints": {
                        **base_config["hard_constraints"],
                        "contract_overtime_slots": 2,
                    },
                },
            },
        },
        {
            "name": "3_infeasible_optician_required",
            "payload": {
                "employees": ["E1", "E2"],
                "contracts": [20, 20],
                "roles": ["vendeur", "vendeur"],
                "days": ["J1", "J2", "J3"],
                "unavailabilities": [],
                "config": {
                    **base_config,
                    "schedule": {
                        **base_config["schedule"],
                        "start_time_minutes": 9 * 60,
                        "end_time_minutes": 12 * 60,
                        "min_staff_per_slot": 1,
                    },
                    "hard_constraints": {
                        **base_config["hard_constraints"],
                        "require_qualified_optician": True,
                    },
                },
            },
        },
        {
            "name": "4_infeasible_rest_11h",
            "payload": {
                "employees": ["E1"],
                "contracts": [120],
                "roles": ["opticien"],
                "days": ["J1", "J2"],
                "unavailabilities": [],
                "config": {
                    **base_config,
                    "schedule": {
                        **base_config["schedule"],
                        "start_time_minutes": 6 * 60,
                        "end_time_minutes": 23 * 60,
                        "min_staff_per_slot": 1,
                    },
                    "hard_constraints": {
                        **base_config["hard_constraints"],
                        "rest_between_days_minutes": 660,
                        "max_daily_minutes": 1020,
                        "max_days_per_week": 2,
                        "contract_hours_mode": "off",
                    },
                },
            },
        },
        {
            "name": "5_feasible_no_tension",
            "payload": {
                "employees": ["E1", "E2"],
                "contracts": [35, 35],
                "roles": ["opticien", "opticien"],
                "days": ["J1", "J2", "J3", "J4", "J5"],
                "unavailabilities": [],
                "config": {
                    **base_config,
                    "schedule": {
                        **base_config["schedule"],
                        "start_time_minutes": 9 * 60,
                        "end_time_minutes": 19 * 60,
                        "min_staff_per_slot": 1,
                    },
                    "hard_constraints": {
                        **base_config["hard_constraints"],
                        "contract_overtime_slots": 0,
                    },
                },
            },
        },
        {
            "name": "6_feasible_with_overtime_used",
            "payload": {
                "employees": ["E1", "E2"],
                "contracts": [30, 30],
                "roles": ["opticien", "opticien"],
                "days": ["J1", "J2", "J3", "J4", "J5", "J6", "J7"],
                "unavailabilities": [],
                "config": {
                    **base_config,
                    "schedule": {
                        **base_config["schedule"],
                        "start_time_minutes": 9 * 60,
                        "end_time_minutes": 16 * 60,
                        "min_staff_per_slot": 1,
                        "min_staff_per_day": [2, 1, 1, 1, 1, 1, 2],
                    },
                    "hard_constraints": {
                        **base_config["hard_constraints"],
                        "contract_overtime_slots": 2,
                        "max_weekly_hours": False,
                    },
                },
            },
        },
        {
            "name": "7_feasible_with_overtime_saturated",
            "payload": {
                "employees": ["E1", "E2"],
                "contracts": [30, 30],
                "roles": ["opticien", "opticien"],
                "days": ["J1", "J2", "J3", "J4", "J5", "J6", "J7"],
                "unavailabilities": [],
                "config": {
                    **base_config,
                    "schedule": {
                        **base_config["schedule"],
                        "start_time_minutes": 9 * 60,
                        "end_time_minutes": 17 * 60,
                        "min_staff_per_slot": 1,
                        "min_staff_per_day": [2, 1, 1, 1, 1, 1, 1],
                    },
                    "hard_constraints": {
                        **base_config["hard_constraints"],
                        "contract_overtime_slots": 2,
                        "max_weekly_hours": False,
                    },
                },
            },
        },
        {
            "name": "8_high_inequity_feasible",
            "payload": {
                "employees": ["E1", "E2", "E3", "E4"],
                "contracts": [40, 30, 10, 10],
                "roles": ["opticien", "opticien", "vendeur", "vendeur"],
                "days": ["J1", "J2", "J3", "J4", "J5"],
                "unavailabilities": [],
                "config": base_config,
            },
        },
    ]

    results = [run_dataset(ds) for ds in datasets]
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
