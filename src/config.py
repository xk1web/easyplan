import json
import os

DEFAULT_CONFIG = {
    "store_name": "default",
    "schedule": {
        "start_time_minutes": 570,
        "end_time_minutes": 1215,
        "slot_minutes": 15,
        "min_staff_per_slot": 1
    },
    "hard_constraints": {
        "max_weekly_hours": True,
        "max_daily_minutes": 600,
        "rest_between_days_minutes": 660,
        "require_qualified_optician": True
    },
    "soft_weights": {
        "hours_balancing": 10,
        "saturday_fairness": 5,
        "contiguity": 3
    },
    "solver": {
        "max_time_seconds": 30
    }
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
