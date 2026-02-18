import sys
import time
from src.validation import validate_global_feasibility
from src.model_builder_v1 import build_and_solve_v1, _sum_ranges_hours
from src.hard_constraints import get_weeks


def test_feasible_simple():
    employees = ["Alice", "Bob", "Charlie"]
    days = ["Lun", "Mar", "Mer"]
    contracts = [30, 30, 30]
    config = {
        "start_time_minutes": 9 * 60,
        "end_time_minutes": 18 * 60,
        "min_staff_per_slot": 1
    }

    validate_global_feasibility(employees, contracts, days, config)

    result = build_and_solve_v1(employees, days, contracts, config)
    assert "error" not in result, f"Le solveur a échoué : {result}"
    assert "schedule" in result
    print("TEST 1 OK : cas faisable simple → planning généré")


def test_impossible_insufficient_hours():
    employees = ["Alice"]
    days = ["Lun", "Mar", "Mer", "Jeu", "Ven"]
    contracts = [5]
    config = {
        "start_time_minutes": 9 * 60,
        "end_time_minutes": 18 * 60,
        "min_staff_per_slot": 1
    }

    try:
        validate_global_feasibility(employees, contracts, days, config)
        assert False, "Aurait dû lever une ValueError"
    except ValueError as e:
        assert "Impossible structurellement" in str(e)
        print("TEST 2 OK : cas impossible (A < B) → échec AVANT solveur")


def test_limit_case_exact_match():
    employees = ["Alice", "Bob"]
    days = ["Lun"]
    config = {
        "start_time_minutes": 9 * 60,
        "end_time_minutes": 13 * 60,
        "min_staff_per_slot": 1
    }

    required_hours = 4 * 1
    contracts = [required_hours, 0]

    validate_global_feasibility(employees, contracts, days, config)

    result = build_and_solve_v1(employees, days, contracts, config)
    assert "error" not in result, f"Le solveur a échoué sur cas limite : {result}"
    print("TEST 3 OK : cas limite (A == B) → planning généré")


def _verify_hours_coherence(result):
    assert "schedule" in result
    for emp_name, emp_data in result["schedule"].items():
        sum_daily = 0.0
        for day_name, day_info in emp_data["days"].items():
            ranges_hours = _sum_ranges_hours(day_info["ranges"])
            assert abs(ranges_hours - day_info["hours"]) < 1e-9, (
                f"Incohérence {emp_name} {day_name}: "
                f"somme plages={ranges_hours}h != hours={day_info['hours']}h"
            )
            sum_daily += day_info["hours"]
        assert abs(sum_daily - emp_data["total_hours"]) < 1e-9, (
            f"Incohérence total {emp_name}: "
            f"somme jours={sum_daily}h != total_hours={emp_data['total_hours']}h"
        )


def test_hours_coherence_standard():
    employees = ["Alice", "Bob", "Charlie"]
    days = ["Lun", "Mar", "Mer", "Jeu", "Ven"]
    contracts = [35, 35, 35]
    config = {
        "start_time_minutes": 9 * 60 + 30,
        "end_time_minutes": 19 * 60 + 30,
        "min_staff_per_slot": 1
    }
    validate_global_feasibility(employees, contracts, days, config)
    result = build_and_solve_v1(employees, days, contracts, config)
    assert "error" not in result
    _verify_hours_coherence(result)
    print("TEST 4 OK : cohérence heures — scénario standard 3 employés 5 jours")


def test_hours_coherence_many_employees():
    employees = ["A", "B", "C", "D", "E", "F"]
    days = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"]
    contracts = [40, 20, 40, 40, 39, 30]
    config = {
        "start_time_minutes": 9 * 60 + 30,
        "end_time_minutes": 20 * 60 + 15,
        "min_staff_per_slot": 1
    }
    validate_global_feasibility(employees, contracts, days, config)
    result = build_and_solve_v1(employees, days, contracts, config)
    assert "error" not in result
    _verify_hours_coherence(result)
    print("TEST 5 OK : cohérence heures — scénario 6 employés 6 jours contrats variés")


def test_hours_coherence_min_staff_2():
    employees = ["A", "B", "C", "D"]
    days = ["Lun", "Mar", "Mer"]
    contracts = [35, 35, 35, 35]
    config = {
        "start_time_minutes": 9 * 60,
        "end_time_minutes": 17 * 60,
        "min_staff_per_slot": 2
    }
    validate_global_feasibility(employees, contracts, days, config)
    result = build_and_solve_v1(employees, days, contracts, config)
    assert "error" not in result
    _verify_hours_coherence(result)
    for emp_name, emp_data in result["schedule"].items():
        assert emp_data["total_hours"] <= 35, (
            f"{emp_name} dépasse contrat: {emp_data['total_hours']}h > 35h"
        )
    print("TEST 6 OK : cohérence heures — min_staff=2, vérif contrat respecté")


def test_hours_coherence_single_slot():
    employees = ["Alice", "Bob"]
    days = ["Lun"]
    contracts = [1, 1]
    config = {
        "start_time_minutes": 9 * 60,
        "end_time_minutes": 9 * 60 + 15,
        "min_staff_per_slot": 1
    }
    validate_global_feasibility(employees, contracts, days, config)
    result = build_and_solve_v1(employees, days, contracts, config)
    assert "error" not in result
    _verify_hours_coherence(result)
    assigned = [
        emp for emp, data in result["schedule"].items()
        if data["days"]
    ]
    assert len(assigned) >= 1
    for emp_name, emp_data in result["schedule"].items():
        for day_name, day_info in emp_data["days"].items():
            assert len(day_info["ranges"]) == 1
            assert day_info["hours"] == 0.25
    print("TEST 7 OK : cohérence heures — cas un seul créneau 15 min")


def test_rest_between_days():
    employees = ["Alice", "Bob"]
    days = ["Lun", "Mar"]
    contracts = [24, 24]
    config = {
        "start_time_minutes": 6 * 60,
        "end_time_minutes": 23 * 60,
        "min_staff_per_slot": 1
    }
    validate_global_feasibility(employees, contracts, days, config)
    result = build_and_solve_v1(employees, days, contracts, config)
    assert "error" not in result
    _verify_hours_coherence(result)
    from src.model_builder_v1 import _hhmm_to_minutes
    for emp_name, emp_data in result["schedule"].items():
        if "Lun" in emp_data["days"] and "Mar" in emp_data["days"]:
            lun_ranges = emp_data["days"]["Lun"]["ranges"]
            mar_ranges = emp_data["days"]["Mar"]["ranges"]
            last_end_lun = max(_hhmm_to_minutes(r["end"]) for r in lun_ranges)
            first_start_mar = min(_hhmm_to_minutes(r["start"]) for r in mar_ranges)
            rest = (24 * 60 - last_end_lun) + first_start_mar
            assert rest >= 660, (
                f"{emp_name}: repos={rest}min < 660min (11h) "
                f"fin Lun={last_end_lun}, début Mar={first_start_mar}"
            )
    print("TEST 8 OK : repos 11h entre journées respecté (horaires larges 6h-23h)")


def test_optician_coverage():
    employees = ["Alice", "Bob", "Charlie"]
    days = ["Lun", "Mar"]
    contracts = [20, 20, 20]
    roles = ["opticien", "vendeur", "vendeur"]
    config = {
        "start_time_minutes": 9 * 60,
        "end_time_minutes": 18 * 60,
        "min_staff_per_slot": 1
    }
    validate_global_feasibility(employees, contracts, days, config)
    result = build_and_solve_v1(employees, days, contracts, config, roles=roles)
    assert "error" not in result
    _verify_hours_coherence(result)
    alice_data = result["schedule"]["Alice"]
    for day in days:
        assert day in alice_data["days"], (
            f"Alice (opticien) doit travailler {day} — seul opticien"
        )
    print("TEST 10 OK : présence opticien diplômé garantie (RULE 5.1)")


def test_max_daily_hours():
    employees = ["Alice", "Bob"]
    days = ["Lun"]
    contracts = [20, 20]
    config = {
        "start_time_minutes": 6 * 60,
        "end_time_minutes": 22 * 60,
        "min_staff_per_slot": 1
    }
    validate_global_feasibility(employees, contracts, days, config)
    result = build_and_solve_v1(employees, days, contracts, config)
    assert "error" not in result
    _verify_hours_coherence(result)
    for emp_name, emp_data in result["schedule"].items():
        for day_name, day_info in emp_data["days"].items():
            assert day_info["hours"] <= 10.0, (
                f"{emp_name} {day_name}: {day_info['hours']}h > 10h max journalier"
            )
    print("TEST 9 OK : durée max journalière 10h respectée (amplitude 16h)")


def test_unavailability_full_day():
    employees = ["Alice", "Bob", "Charlie"]
    days = ["Lun", "Mar"]
    contracts = [20, 20, 20]
    config = {
        "start_time_minutes": 9 * 60,
        "end_time_minutes": 18 * 60,
        "min_staff_per_slot": 1
    }
    unavailabilities = [(0, 0)]
    validate_global_feasibility(employees, contracts, days, config)
    result = build_and_solve_v1(employees, days, contracts, config,
                                 unavailabilities=unavailabilities)
    assert "error" not in result
    _verify_hours_coherence(result)
    alice_data = result["schedule"]["Alice"]
    assert "Lun" not in alice_data["days"], (
        "Alice devrait être absente le Lun"
    )
    print("TEST 12 OK : absence journée complète respectée")


def test_unavailability_slot():
    employees = ["Alice", "Bob"]
    days = ["Lun"]
    contracts = [10, 10]
    config = {
        "start_time_minutes": 9 * 60,
        "end_time_minutes": 13 * 60,
        "min_staff_per_slot": 1
    }
    unavailabilities = [(0, 0, 0)]
    validate_global_feasibility(employees, contracts, days, config)
    result = build_and_solve_v1(employees, days, contracts, config,
                                 unavailabilities=unavailabilities)
    assert "error" not in result
    _verify_hours_coherence(result)
    alice_data = result["schedule"]["Alice"]
    if "Lun" in alice_data["days"]:
        from src.model_builder_v1 import _hhmm_to_minutes
        for r in alice_data["days"]["Lun"]["ranges"]:
            assert _hhmm_to_minutes(r["start"]) > 9 * 60, (
                "Alice ne devrait pas travailler au créneau 09:00"
            )
    print("TEST 13 OK : absence créneau spécifique respectée")


def test_validation_no_optician():
    employees = ["Alice", "Bob"]
    contracts = [20, 20]
    days = ["Lun"]
    roles = ["vendeur", "vendeur"]
    config = {
        "start_time_minutes": 9 * 60,
        "end_time_minutes": 18 * 60,
        "min_staff_per_slot": 1
    }
    try:
        validate_global_feasibility(employees, contracts, days, config, roles=roles)
        assert False, "Aurait dû lever ValueError (pas d'opticien)"
    except ValueError as e:
        assert "opticien" in str(e).lower()
        print("TEST 14 OK : validation refuse — aucun opticien diplômé")


def test_validation_mismatched_lengths():
    employees = ["Alice", "Bob"]
    contracts = [20]
    days = ["Lun"]
    config = {
        "start_time_minutes": 9 * 60,
        "end_time_minutes": 18 * 60,
        "min_staff_per_slot": 1
    }
    try:
        validate_global_feasibility(employees, contracts, days, config)
        assert False, "Aurait dû lever ValueError (longueurs différentes)"
    except ValueError as e:
        assert "Incohérence" in str(e)
        print("TEST 15 OK : validation refuse — employés != contrats")


def test_soft_contiguity():
    employees = ["Alice", "Bob", "Charlie"]
    days = ["Lun", "Mar", "Mer"]
    contracts = [20, 20, 20]
    config = {
        "start_time_minutes": 9 * 60,
        "end_time_minutes": 18 * 60,
        "min_staff_per_slot": 1
    }
    validate_global_feasibility(employees, contracts, days, config)
    result = build_and_solve_v1(employees, days, contracts, config)
    assert "error" not in result
    _verify_hours_coherence(result)
    for emp_name, emp_data in result["schedule"].items():
        for day_name, day_info in emp_data["days"].items():
            assert len(day_info["ranges"]) <= 3, (
                f"{emp_name} {day_name}: {len(day_info['ranges'])} plages "
                f"— trop fragmenté"
            )
    print("TEST 11 OK : soft contiguité — plages peu fragmentées")


def test_weekly_structuring():
    weeks = get_weeks(31)
    assert len(weeks) == 5
    assert weeks[0] == [0, 1, 2, 3, 4, 5, 6]
    assert weeks[1] == [7, 8, 9, 10, 11, 12, 13]
    assert weeks[4] == [28, 29, 30]

    weeks_28 = get_weeks(28)
    assert len(weeks_28) == 4
    assert all(len(w) == 7 for w in weeks_28)

    weeks_6 = get_weeks(6)
    assert len(weeks_6) == 1
    assert weeks_6[0] == [0, 1, 2, 3, 4, 5]
    print("TEST 16 OK : découpage en semaines correct")


def test_max_6_days_per_week():
    employees = ["Alice", "Bob", "Charlie"]
    days = [f"J{i}" for i in range(7)]
    contracts = [40, 40, 40]
    config = {
        "schedule": {
            "start_time_minutes": 9 * 60,
            "end_time_minutes": 17 * 60,
            "slot_minutes": 30,
            "min_staff_per_slot": 1
        },
        "hard_constraints": {
            "max_weekly_hours": True,
            "max_days_per_week": 6,
            "max_daily_minutes": 600,
            "rest_between_days_minutes": 660,
            "require_qualified_optician": False
        },
        "soft_weights": {
            "hours_balancing": 10,
            "saturday_fairness": 0,
            "contiguity": 0
        },
        "solver": {"max_time_seconds": 30}
    }
    result = build_and_solve_v1(employees, days, contracts, config)
    assert "error" not in result, f"Solveur échoué: {result}"
    for emp_name, emp_data in result["schedule"].items():
        days_worked = len(emp_data["days"])
        assert days_worked <= 6, (
            f"{emp_name} travaille {days_worked} jours, max 6"
        )
    print("TEST 17 OK : max 6 jours travaillés par semaine respecté")


def test_metrics_present():
    employees = ["Alice", "Bob"]
    days = ["Lun", "Mar"]
    contracts = [20, 20]
    config = {
        "start_time_minutes": 9 * 60,
        "end_time_minutes": 17 * 60,
        "min_staff_per_slot": 1
    }
    result = build_and_solve_v1(employees, days, contracts, config)
    assert "error" not in result
    assert "metrics" in result
    m = result["metrics"]
    assert "num_variables" in m
    assert "num_constraints" in m
    assert "solver_wall_time" in m
    assert "solver_status" in m
    assert m["num_variables"] > 0
    assert m["num_constraints"] > 0
    assert m["solver_status"] in ("OPTIMAL", "FEASIBLE")
    print("TEST 18 OK : métriques solveur présentes et valides")


def test_fast_solve_mode():
    employees = ["Alice", "Bob", "Charlie"]
    days = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"]
    contracts = [35, 35, 35]
    config_normal = {
        "schedule": {
            "start_time_minutes": 9 * 60,
            "end_time_minutes": 18 * 60,
            "slot_minutes": 30,
            "min_staff_per_slot": 1
        },
        "hard_constraints": {
            "max_weekly_hours": True,
            "max_daily_minutes": 600,
            "rest_between_days_minutes": 660,
            "require_qualified_optician": False
        },
        "soft_weights": {
            "hours_balancing": 10,
            "saturday_fairness": 5,
            "contiguity": 3
        },
        "solver": {"max_time_seconds": 30},
        "fast_solve": False
    }
    config_fast = dict(config_normal)
    config_fast["fast_solve"] = True

    result_fast = build_and_solve_v1(employees, days, contracts, config_fast)
    assert "error" not in result_fast
    assert "metrics" in result_fast
    print("TEST 19 OK : fast_solve mode fonctionne")


def test_previous_month_stats():
    employees = ["Alice", "Bob", "Charlie"]
    days = ["Lun", "Mar", "Mer", "Jeu", "Ven"]
    contracts = [35, 35, 35]
    config = {
        "schedule": {
            "start_time_minutes": 9 * 60,
            "end_time_minutes": 18 * 60,
            "slot_minutes": 30,
            "min_staff_per_slot": 1
        },
        "hard_constraints": {
            "max_weekly_hours": True,
            "max_daily_minutes": 600,
            "rest_between_days_minutes": 660,
            "require_qualified_optician": False
        },
        "soft_weights": {
            "hours_balancing": 10,
            "saturday_fairness": 0,
            "contiguity": 0
        },
        "solver": {"max_time_seconds": 30},
        "long_term_equity_weight": 0.3
    }
    prev_stats = {
        "total_hours": {"Alice": 160, "Bob": 130, "Charlie": 140},
        "saturdays_worked": {"Alice": 4, "Bob": 1, "Charlie": 2}
    }
    result = build_and_solve_v1(employees, days, contracts, config,
                                 previous_month_stats=prev_stats)
    assert "error" not in result
    _verify_hours_coherence(result)
    print("TEST 20 OK : previous_month_stats accepté et traité")


def test_performance_warnings():
    employees = [f"Emp{i}" for i in range(12)]
    days = [f"J{i}" for i in range(5)]
    contracts = [35] * 12
    config = {
        "start_time_minutes": 9 * 60,
        "end_time_minutes": 14 * 60,
        "min_staff_per_slot": 1
    }
    result = build_and_solve_v1(employees, days, contracts, config)
    assert "metrics" in result
    assert "warnings" in result["metrics"]
    assert any(">10" in w for w in result["metrics"]["warnings"])
    print("TEST 21 OK : warning >10 employés affiché")


def test_monthly_planning_10_employees():
    employees = [f"Emp{i}" for i in range(10)]
    days = [f"J{i}" for i in range(28)]
    contracts = [35, 39, 40, 35, 20, 30, 35, 40, 39, 25]
    roles = ["opticien", "vendeur", "opticien", "vendeur", "vendeur",
             "opticien", "vendeur", "opticien", "vendeur", "opticien"]
    config = {
        "schedule": {
            "start_time_minutes": 9 * 60 + 30,
            "end_time_minutes": 19 * 60 + 30,
            "slot_minutes": 30,
            "min_staff_per_slot": 2
        },
        "hard_constraints": {
            "max_weekly_hours": True,
            "max_days_per_week": 6,
            "max_daily_minutes": 600,
            "rest_between_days_minutes": 660,
            "require_qualified_optician": True
        },
        "soft_weights": {
            "hours_balancing": 10,
            "saturday_fairness": 0,
            "contiguity": 0
        },
        "solver": {"max_time_seconds": 60},
        "fast_solve": True
    }
    t0 = time.time()
    result = build_and_solve_v1(employees, days, contracts, config, roles=roles)
    elapsed = time.time() - t0
    assert "error" not in result, f"Solveur échoué pour 10x28: {result.get('error')}"
    _verify_hours_coherence(result)
    m = result["metrics"]
    print(f"TEST 22 OK : 10 employés × 28 jours résolu en {elapsed:.1f}s "
          f"({m['num_variables']} vars, {m['num_constraints']} contraintes, "
          f"status={m['solver_status']})")


def test_contract_driven_planning():
    employees = ["Emp0", "Emp1", "Emp2", "Emp3", "Emp4", "Emp5"]
    days = [f"J{i}" for i in range(30)]
    contracts = [35, 39, 35, 39, 35, 39]
    config = {
        "schedule": {
            "start_time_minutes": 9 * 60 + 30,
            "end_time_minutes": 19 * 60 + 30,
            "slot_minutes": 30,
            "min_staff_per_slot": 2
        },
        "hard_constraints": {
            "max_weekly_hours": True,
            "max_days_per_week": 6,
            "max_daily_minutes": 600,
            "rest_between_days_minutes": 660,
            "require_qualified_optician": False
        },
        "soft_weights": {
            "hours_balancing": 0,
            "saturday_fairness": 0,
            "contiguity": 0,
            "contract_target": 50
        },
        "solver": {"max_time_seconds": 60},
        "fast_solve": False
    }

    t0 = time.time()
    result = build_and_solve_v1(employees, days, contracts, config)
    elapsed = time.time() - t0
    assert "error" not in result, f"Solveur échoué: {result.get('error')}"
    _verify_hours_coherence(result)

    tolerance_slots = 2
    for i, emp in enumerate(employees):
        total_hours = result["schedule"][emp]["total_hours"]
        target_hours = contracts[i] * 30 / 7.0
        slot_minutes = 30
        tolerance_hours = tolerance_slots * slot_minutes / 60.0
        assert total_hours >= target_hours - tolerance_hours, (
            f"{emp} (contrat {contracts[i]}h/sem): {total_hours:.1f}h < "
            f"cible {target_hours:.1f}h - tolérance {tolerance_hours}h"
        )

    m = result["metrics"]
    print(f"TEST 23 OK : contract-driven planning — 6 emp × 30 jours, "
          f"slot 30min, min_staff=2")
    print(f"  Solve time: {elapsed:.2f}s, status={m['solver_status']}, "
          f"gap={m['gap_percent']}%")
    for i, emp in enumerate(employees):
        total = result["schedule"][emp]["total_hours"]
        target = contracts[i] * 30 / 7.0
        print(f"  {emp}: contrat={contracts[i]}h/sem, "
              f"cible={target:.1f}h, réel={total:.1f}h, "
              f"delta={total - target:+.1f}h")


if __name__ == "__main__":
    passed = 0
    failed = 0

    for test_fn in [
        test_feasible_simple,
        test_impossible_insufficient_hours,
        test_limit_case_exact_match,
        test_hours_coherence_standard,
        test_hours_coherence_many_employees,
        test_hours_coherence_min_staff_2,
        test_hours_coherence_single_slot,
        test_rest_between_days,
        test_max_daily_hours,
        test_optician_coverage,
        test_soft_contiguity,
        test_unavailability_full_day,
        test_unavailability_slot,
        test_validation_no_optician,
        test_validation_mismatched_lengths,
        test_weekly_structuring,
        test_max_6_days_per_week,
        test_metrics_present,
        test_fast_solve_mode,
        test_previous_month_stats,
        test_performance_warnings,
        test_monthly_planning_10_employees,
        test_contract_driven_planning,
    ]:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"ÉCHEC {test_fn.__name__} : {e}")
            failed += 1

    print(f"\n{'=' * 40}")
    print(f"Résultats : {passed} passés, {failed} échoués")

    if failed > 0:
        sys.exit(1)
    else:
        print("Tous les tests ont réussi.")
