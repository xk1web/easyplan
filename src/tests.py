import sys
from validation import validate_global_feasibility
from model_builder_v1 import build_and_solve_v1


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


if __name__ == "__main__":
    passed = 0
    failed = 0

    for test_fn in [test_feasible_simple, test_impossible_insufficient_hours, test_limit_case_exact_match]:
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
