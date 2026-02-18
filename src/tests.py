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
    from model_builder_v1 import _hhmm_to_minutes
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
        from model_builder_v1 import _hhmm_to_minutes
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
