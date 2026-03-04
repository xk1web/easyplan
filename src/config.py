import json
import os

DEFAULT_CONFIG = {
    "store_name": "default",
    "schedule": {
        "start_time_minutes": 570,
        "end_time_minutes": 1215,
        "slot_minutes": 15,
        "min_staff_per_slot": 1,
        "late_threshold_minutes": 1080
    },
    "hard_constraints": {
        "max_weekly_hours": True,
        "max_days_per_week": 5,
        "max_daily_minutes": 600,
        "rest_between_days_minutes": 660,
        "weekly_rest_minutes": 2100,
        "require_qualified_optician": True,
        "min_daily_minutes": 240
    },
    "soft_weights": {
        "hours_balancing": 0,
        "saturday_fairness": 5,
        "contiguity_penalty": 1,
        "contiguity": 3,
        "days_concentration_penalty": 3,
        "days_concentration_target_days": 5,
        "weight_daily_balance": 4,
        "daily_balance_tolerance_minutes": 60,
        "long_day_requirement": 7,
        "non_template_penalty": 1,
        "template_deviation_weight": 1,
        "shift_type_presence_penalty": 2,
        "hourly_demand_weight": 0.5,
        "late_fairness_penalty": 12,
        "contract_target": 50
    },
    "shift_templates": [
        {"name": "morning", "start": 570, "end": 990},
        {"name": "full", "start": 570, "end": 1080},
        {"name": "closing", "start": 720, "end": 1215}
    ],
    "hourly_demand_weights": {
        "09:30-12:00": 1,
        "12:00-14:00": 2,
        "14:00-18:00": 4
    },
    "closed_weekdays": [6],
    "solver": {
        "max_time_seconds": 30
    },
    "solver_max_time_seconds": 45,
    "solver_num_workers": 8,
    "solver_log_search_progress": True,
    "long_term_equity_weight": 0.3,
    "fast_solve": False
}


def load_config(json_path=None):
    config = dict(DEFAULT_CONFIG)
    for key in DEFAULT_CONFIG:
        if isinstance(DEFAULT_CONFIG[key], dict):
            config[key] = dict(DEFAULT_CONFIG[key])

    if json_path and os.path.exists(json_path):
        with open(json_path, "r") as f:
            overrides = json.load(f)
        _deep_merge(config, overrides)

    return config


def _deep_merge(base, overrides):
    for key, value in overrides.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
