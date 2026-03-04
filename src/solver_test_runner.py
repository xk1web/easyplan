import json
from typing import Any, Dict, List, Optional

from src.config import load_config
from src.validation import validate_global_feasibility
# LEGACY ENGINE - DO NOT USE
# from src.model_builder_v1 import build_and_solve_v1


def _deep_merge(base: Dict[str, Any], overrides: Dict[str, Any]) -> None:
    for key, value in overrides.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _compute_coverage_hours(config: dict, num_days: int) -> float:
    sched = config.get("schedule", config)
    slot_minutes = sched.get("slot_minutes", 15)
    start_time_minutes = sched.get("start_time_minutes", 9 * 60 + 30)
    end_time_minutes = sched.get("end_time_minutes", 20 * 60 + 15)
    min_staff = sched.get("min_staff_per_slot", 1)
    min_staff_per_day = sched.get("min_staff_per_day")
    num_slots = (end_time_minutes - start_time_minutes) // slot_minutes
    if isinstance(min_staff_per_day, (list, tuple)) and len(min_staff_per_day) == num_days:
        total_required_slots = sum(min_staff_per_day) * num_slots
    else:
        total_required_slots = num_days * num_slots * min_staff
    return total_required_slots * slot_minutes / 60.0


def _compute_capacity_hours(contracts: List[int], num_days: int) -> float:
    return sum(contracts) * (num_days / 7.0)


def _compute_capacity_with_overtime_hours(contracts: List[int], num_days: int, config: dict) -> float:
    sched = config.get("schedule", config)
    slot_minutes = sched.get("slot_minutes", 15)
    hard = config.get("hard_constraints", {})
    overtime_slots = hard.get("contract_overtime_slots", 0)
    full_weeks = num_days // 7
    base = _compute_capacity_hours(contracts, num_days)
    extra = len(contracts) * full_weeks * overtime_slots * slot_minutes / 60.0
    return base + extra


def _compute_suggestions(contracts: List[int], num_days: int, config: dict) -> List[str]:
    coverage_total_hours = _compute_coverage_hours(config, num_days)
    capacity_with_overtime = _compute_capacity_with_overtime_hours(contracts, num_days, config)
    suggestions = []
    if capacity_with_overtime < coverage_total_hours:
        suggestions.append("Augmenter l’overtime autorisé ou réduire la couverture minimale.")
    elif config.get("hard_constraints", {}).get("contract_overtime_slots", 0) > 0:
        suggestions.append("Overtime autorisé insuffisant : ajuster contrats ou couverture.")
    return suggestions


def _estimate_overtime_distribution(
    employees: List[str],
    contracts: List[int],
    num_days: int,
    schedule: Dict[str, Any],
) -> Dict[str, float]:
    # Approximation: overtime = max(0, total_hours - target_hours_prorated)
    # Note: this is not the exact solver overtime variable, but provides a consistent heuristic.
    distribution = {}
    for i, emp in enumerate(employees):
        target_hours = contracts[i] * (num_days / 7.0)
        total_hours = schedule[emp]["total_hours"] if emp in schedule else 0.0
        distribution[emp] = max(0.0, total_hours - target_hours)
    return distribution


def run_dataset(dataset: Dict[str, Any]) -> Dict[str, Any]:
    payload = dataset["payload"]
    config = load_config()
    if payload.get("config"):
        _deep_merge(config, payload["config"])

    unavailabilities = payload.get("unavailabilities") or []

    try:
        validate_global_feasibility(
            employees=payload["employees"],
            contracts=payload["contracts"],
            days=payload["days"],
            config=config,
            roles=payload["roles"],
            unavailabilities=unavailabilities,
        )
    except Exception as e:
        return {
            "name": dataset["name"],
            "status": "validation_error",
            "error": str(e),
        }

    result = build_and_solve_v1(
        employees=payload["employees"],
        days=payload["days"],
        contracts=payload["contracts"],
        config=config,
        roles=payload["roles"],
        unavailabilities=unavailabilities,
        previous_month_stats=None,
    )

    metrics = result.get("metrics") or {}
    schedule = result.get("schedule")

    overtime_used_slots = metrics.get("total_overtime_used_slots")
    overtime_used_hours = None
    if overtime_used_slots is not None:
        sched = config.get("schedule", config)
        slot_minutes = sched.get("slot_minutes", 15)
        overtime_used_hours = overtime_used_slots * slot_minutes / 60.0

    overtime_distribution = None
    if schedule:
        overtime_distribution = _estimate_overtime_distribution(
            payload["employees"], payload["contracts"], len(payload["days"]), schedule
        )

    return {
        "name": dataset["name"],
        "solver_status": metrics.get("solver_status"),
        "objective_value": None,  # not exposed by build_and_solve_v1
        "total_overtime_used_hours": overtime_used_hours,
        "overtime_distribution": overtime_distribution,
        "coverage_total": _compute_coverage_hours(config, len(payload["days"])),
        "capacity_total": _compute_capacity_hours(payload["contracts"], len(payload["days"])),
        "suggestions": _compute_suggestions(payload["contracts"], len(payload["days"]), config),
        "error": result.get("error"),
    }


def compare_suggestions(actual: List[str], expected: List[str]) -> List[str]:
    missing = [s for s in expected if s not in actual]
    extra = [s for s in actual if s not in expected]
    issues = []
    if missing:
        issues.append(f"Missing suggestions: {missing}")
    if extra:
        issues.append(f"Unexpected suggestions: {extra}")
    return issues


def main() -> None:
    datasets = [
        {
            "name": "example_feasible_tight",
            "payload": {
                "employees": ["E1", "E2", "E3", "E4"],
                "contracts": [35, 35, 30, 28],
                "roles": ["opticien", "vendeur", "vendeur", "opticien"],
                "days": ["J0", "J1", "J2", "J3", "J4", "J5"],
                "unavailabilities": [],
                "config": {
                    "schedule": {
                        "start_time_minutes": 540,
                        "end_time_minutes": 1140,
                        "slot_minutes": 60,
                        "min_staff_per_slot": 2,
                    },
                    "hard_constraints": {
                        "contract_hours_mode": "hard",
                        "contract_overtime_slots": 2,
                        "max_days_per_week": 6,
                        "max_daily_minutes": 600,
                        "rest_between_days_minutes": 660,
                        "weekly_rest_minutes": 2100,
                        "require_qualified_optician": True,
                    },
                    "soft_weights": {
                        "hours_balancing": 0,
                        "saturday_fairness": 0,
                        "contiguity": 3,
                        "weekly_hours_fairness": 4,
                        "close_fairness": 3,
                        "amplitude_fairness": 2,
                        "contract_target": 0,
                    },
                },
            },
            "expected_suggestions": [],
        },
    ]

    report = {"total": len(datasets), "issues": []}

    for ds in datasets:
        result = run_dataset(ds)
        expected = ds.get("expected_suggestions", [])
        actual = result.get("suggestions") or []
        issues = compare_suggestions(actual, expected)
        if result.get("objective_value") is None:
            issues.append("objective_value not available from build_and_solve_v1")
        if issues:
            report["issues"].append(
                {
                    "name": ds["name"],
                    "issues": issues,
                    "result": result,
                }
            )

        print(json.dumps(result, ensure_ascii=False))

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
