import sys
from validation import validate_global_feasibility
from model_builder_v1 import build_and_solve_v1, _sum_ranges_hours


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
