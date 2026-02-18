# Planning Engine — Moteur Métier

## Overview
Moteur de génération de planning (Python + OR-Tools CP-SAT) pour magasins d'optique.
Convention collective optique-lunetterie (IDCC 1431).
Approche incrémentale : stabilisation heures → hard constraints → soft constraints → config.

## Project Architecture
- `src/` — Source code directory
- `src/validation.py` — Validation structurelle de faisabilité (heures disponibles vs requises)
- `src/model_builder_v1.py` — Modèle CP-SAT avec reconstruction plages contigües + cohérence heures
- `src/ai_runner.py` — Point d'entrée principal : pipeline validate → build → solve → return
- `src/tests.py` — 7 tests automatisés (faisabilité + cohérence heures)
- `src/app.py` — Serveur HTTP (utilise ancien scheduler.py, non modifié)
- `src/ai_client.py` — Configuration client OpenAI (non modifié)
- `scheduler.py` — Ancien scheduler (conservé, non utilisé par V1)
- `src/scheduler_v2.py` — Ancien scheduler V2 (conservé, non utilisé par V1)

## Schedule Output Schema (V1)
```json
{
  "schedule": {
    "EmployeeName": {
      "total_hours": 9.5,
      "days": {
        "Lun": {
          "ranges": [
            {"start": "09:30", "end": "12:00"},
            {"start": "14:00", "end": "18:00"}
          ],
          "hours": 6.5
        }
      }
    }
  }
}
```

## Pipeline V1
1. `validate_global_feasibility` — vérifie A >= B avant solveur
2. `build_and_solve_v1` — modèle CP-SAT avec hard constraints
3. Extraction planning avec plages contigües + assertion cohérence interne

## Hard Constraints V1
- Couverture minimale par créneau (min_staff_per_slot)
- Somme heures employé <= heures contractuelles
- Pas d'objectif d'optimisation (à venir étape 3)

## Tests (7)
1. Cas faisable simple
2. Cas impossible (A < B) → échec avant solveur
3. Cas limite (A == B)
4. Cohérence heures — 3 employés 5 jours
5. Cohérence heures — 6 employés 6 jours contrats variés
6. Cohérence heures — min_staff=2 + vérif contrat
7. Cohérence heures — cas un seul créneau 15 min

## Running
```bash
cd src && python ai_runner.py
```

## Tests
```bash
cd src && python tests.py
```

## User Preferences
- Méthode incrémentale stricte : une seule règle à la fois
- Tests après chaque modification
- Fiabilité > performance > élégance
- Ne pas anticiper les phases suivantes
- Résumé après chaque étape

## Recent Changes
- 2026-02-18: Étape 1 — Cohérence heures stabilisée
  - Reconstruction plages contigües (pas min/max)
  - Assertion interne model_hours == display_hours
  - total_hours par employé
  - 4 nouveaux tests de cohérence (tests 4-7)
  - Schema schedule changé : schedule[emp]["days"][day] au lieu de schedule[emp][day]
- 2026-02-17: Stabilisation V1 minimale — validation.py, model_builder_v1.py, pipeline propre, 3 tests
- 2026-02-15: Initial project setup with basic HTTP server
