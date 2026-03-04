from typing import Any, Dict, List


def _slots_count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, list):
        return len(value)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def compute_global_kpi(planning_matrix, employees: List[str], config: Dict[str, Any]) -> Dict[str, float]:
    """
    Compute global KPI values from planning data without solver dependencies.

    Expected planning_matrix shape (flexible):
    {
      "slot_minutes": int,
      "days": [iso_day, ...],
      "employees": {
        "Alice": {
          "contract_hours": 39,
          "coverage_slots_per_day": {"2026-02-28": [0, 1, ...]},
          "internal_slots_per_day": {"2026-02-28": [10, 11, ...]},
        },
      }
    }
    """
    sched = config.get("schedule", config)
    staffing = config.get("staffing", {})
    slot_minutes = planning_matrix.get("slot_minutes", sched.get("slot_minutes", 15))
    slot_hours = slot_minutes / 60.0

    employee_rows = planning_matrix.get("employees", planning_matrix)
    days = planning_matrix.get("days")
    if not days:
        day_set = set()
        for emp_name in employees:
            emp_row = employee_rows.get(emp_name, {}) if isinstance(employee_rows, dict) else {}
            cov_days = emp_row.get("coverage_slots_per_day", {}).keys()
            int_days = emp_row.get("internal_slots_per_day", {}).keys()
            day_set.update(cov_days)
            day_set.update(int_days)
        days = sorted(day_set)

    total_contracted_hours = 0.0
    total_coverage_slots = 0
    total_internal_slots = 0
    coverage_by_day = {d: 0 for d in days}

    for idx, emp_name in enumerate(employees):
        emp_row = employee_rows.get(emp_name, {}) if isinstance(employee_rows, dict) else {}
        contract_hours = emp_row.get("contract_hours")
        if contract_hours is None:
            cfg_contracts = config.get("contracts")
            if isinstance(cfg_contracts, list) and idx < len(cfg_contracts):
                contract_hours = cfg_contracts[idx]
            else:
                contract_hours = 0.0
        total_contracted_hours += float(contract_hours)

        cov_per_day = emp_row.get("coverage_slots_per_day", {})
        int_per_day = emp_row.get("internal_slots_per_day", {})

        for d in days:
            cov_slots = _slots_count(cov_per_day.get(d))
            int_slots = _slots_count(int_per_day.get(d))
            total_coverage_slots += cov_slots
            total_internal_slots += int_slots
            coverage_by_day[d] = coverage_by_day.get(d, 0) + cov_slots

    total_coverage_hours = total_coverage_slots * slot_hours
    total_internal_hours = 0.0
    total_worked_hours = total_coverage_hours

    min_staff = staffing.get("min_staff_per_slot")
    target_staff = staffing.get("target_staff_per_slot")
    num_slots = planning_matrix.get("num_slots")
    if num_slots is None and total_coverage_slots >= 0 and len(days) > 0:
        max_covered = max(coverage_by_day.values()) if coverage_by_day else 0
        num_slots = max_covered
    num_slots = int(num_slots or 0)

    coverage_gap_slots = 0
    if min_staff is not None and num_slots > 0:
        for d in days:
            required = int(min_staff) * num_slots
            observed = coverage_by_day.get(d, 0)
            coverage_gap_slots += max(0, required - observed)

    overstaff_slots = 0
    if target_staff is not None and num_slots > 0:
        for d in days:
            allowed = int(target_staff) * num_slots
            observed = coverage_by_day.get(d, 0)
            overstaff_slots += max(0, observed - allowed)

    return {
        "total_contracted_hours": total_contracted_hours,
        "total_worked_hours": total_worked_hours,
        "total_internal_hours": total_internal_hours,
        "total_coverage_hours": total_coverage_hours,
        "coverage_gap": coverage_gap_slots * slot_hours,
        "overstaff_hours": overstaff_slots * slot_hours,
    }
