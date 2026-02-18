# Planning Engine — Moteur Métier Optique

## Overview
Moteur de génération de planning (Python + OR-Tools CP-SAT) pour magasins d'optique.
Convention collective optique-lunetterie (IDCC 1431).
Approche incrémentale : stabilisation heures → hard constraints → soft constraints → config → validation légale.

## Project Architecture
- `src/` — Source code directory
- `src/model_builder_v1.py` — Modèle CP-SAT principal : variables, extraction résultats, plages contigües
- `src/hard_constraints.py` — Contraintes dures : couverture, max hebdo/journalier, repos 11h, opticien diplômé, absences
- `src/soft_constraints.py` — Contraintes souples : équilibrage heures, équité samedis, contiguité (transitions)
- `src/validation.py` — Validation structurelle et légale (faisabilité, rôles, cohérence données)
- `src/config.py` — Chargement config JSON hiérarchique avec valeurs par défaut
- `src/ai_runner.py` — Point d'entrée principal : pipeline validate → build → solve → display
- `src/tests.py` — 15 tests automatisés
- `src/app.py` — Serveur HTTP (utilise ancien scheduler.py, non modifié)
- `src/ai_client.py` — Configuration client OpenAI (non modifié)
- `scheduler.py` — Ancien scheduler (conservé, non utilisé par V1)

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

## Configuration (JSON hiérarchique)
```json
{
  "store_name": "MonMagasin",
  "schedule": {
    "start_time_minutes": 570,
    "end_time_minutes": 1215,
    "slot_minutes": 15,
    "min_staff_per_slot": 1
  },
  "hard_constraints": {
    "max_weekly_minutes": 2640,
    "max_daily_minutes": 600,
    "rest_between_days_minutes": 660,
    "require_qualified_optician": true
  },
  "soft_weights": {
    "hours_balancing": 10,
    "saturday_fairness": 5,
    "contiguity": 3
  }
}
```
Rétro-compatible avec format plat (clés à la racine).

## Hard Constraints
- Couverture minimale par créneau (min_staff_per_slot)
- Heures hebdo ≤ contrat (max_weekly_minutes)
- Durée journalière ≤ 10h (max_daily_minutes, IDCC 1431)
- Repos inter-journalier ≥ 11h (min_rest_between_days_minutes)
- Présence opticien diplômé obligatoire (RULE 5.1)
- Absences (journées complètes ou créneaux spécifiques)

## Soft Constraints (objectif pondéré)
- Équilibrage heures entre employés (weight_balance)
- Équité samedis (weight_saturday_fairness)
- Contiguité plages horaires via pénalités de transition (weight_contiguity)

## Validation Légale
- Faisabilité structurelle (heures disponibles ≥ heures requises)
- Cohérence données (longueurs employés/contrats/rôles)
- Vérification présence opticien dans l'équipe
- Contrats non négatifs
- Capacité journalière suffisante

## Tests (15)
1. Cas faisable simple
2. Cas impossible (A < B) → échec avant solveur
3. Cas limite (A == B)
4-7. Cohérence heures (3 emp/5j, 6 emp/6j, min_staff=2, créneau unique)
8. Repos 11h inter-journalier
9. Durée max journalière 10h
10. Présence opticien diplômé
11. Contiguité des plages horaires
12. Absence journée complète
13. Absence créneau spécifique
14. Validation : aucun opticien → rejet
15. Validation : longueurs incohérentes → rejet

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
- 2026-02-18: Étape 6 — Validation légale enrichie
  - validate_global_feasibility étendu : rôles, cohérence longueurs, contrats négatifs, capacité
  - 2 nouveaux tests (14-15), 15/15 passent
- 2026-02-18: Étape 5 — Absences (journées complètes + créneaux)
- 2026-02-18: Étape 4 — Config JSON hiérarchique, poids paramétrables
- 2026-02-18: Étape 2-3 — Hard + soft constraints, objectif pondéré
- 2026-02-18: Étape 1 — Cohérence heures stabilisée
- 2026-02-17: Stabilisation V1 minimale
- 2026-02-15: Initial project setup
