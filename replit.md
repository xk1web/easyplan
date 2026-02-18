# Planning Engine — API REST Production

## Overview
API REST de génération de planning (Python + FastAPI + OR-Tools CP-SAT) pour magasins d'optique.
Convention collective optique-lunetterie (IDCC 1431).
Portable et déployable sur n'importe quelle infrastructure (Railway, Render, VPS, Docker, AWS).

## Project Architecture
```
.
├── main.py                      — API FastAPI (point d'entrée)
├── requirements.txt             — Dépendances minimales
├── Dockerfile                   — Image Docker production
├── src/
│   ├── __init__.py              — Package Python
│   ├── model_builder_v1.py      — Modèle CP-SAT : variables, extraction résultats, plages contigües
│   ├── hard_constraints.py      — Contraintes dures : couverture, max hebdo/journalier, repos 11h, opticien, absences
│   ├── soft_constraints.py      — Contraintes souples : équilibrage heures, équité samedis, contiguité
│   ├── validation.py            — Validation structurelle et légale
│   ├── config.py                — Config JSON hiérarchique avec valeurs par défaut
│   ├── ai_runner.py             — Script CLI standalone (pipeline validate → build → solve → display)
│   └── tests.py                 — 15 tests automatisés
├── scheduler.py                 — Ancien scheduler (conservé, non utilisé par V1)
└── src/app.py                   — Ancien serveur HTTP (conservé, non utilisé)
```

## API Endpoints

### GET /
Health check.
```json
{"status": "ok", "engine": "planning-optique-v1"}
```

### POST /generate-planning
Génère un planning optimisé.

**Body JSON :**
```json
{
  "employees": ["Alice", "Bob", "Charlie"],
  "contracts": [35, 39, 40],
  "roles": ["opticien", "vendeur", "opticien"],
  "days": ["Lun", "Mar", "Mer", "Jeu", "Ven"],
  "unavailabilities": [],
  "config": {
    "schedule": { "min_staff_per_slot": 1 },
    "solver": { "max_time_seconds": 10 }
  }
}
```

**Réponse :**
```json
{
  "status": "optimal | infeasible",
  "schedule": { ... },
  "solver_time": 2.5,
  "error": null
}
```

**Codes HTTP :**
- 200 : Planning généré (ou infaisable avec message)
- 422 : Validation échouée (données incohérentes, faisabilité impossible)
- 500 : Erreur solveur interne

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
    "max_weekly_hours": true,
    "max_daily_minutes": 600,
    "rest_between_days_minutes": 660,
    "require_qualified_optician": true
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
```

## Hard Constraints
- Couverture minimale par créneau (min_staff_per_slot)
- Heures hebdo ≤ contrat (max_weekly_hours)
- Durée journalière ≤ 10h (max_daily_minutes, IDCC 1431)
- Repos inter-journalier ≥ 11h (rest_between_days_minutes)
- Présence opticien diplômé obligatoire (RULE 5.1)
- Absences (journées complètes ou créneaux spécifiques)

## Soft Constraints (objectif pondéré)
- Équilibrage heures entre employés (hours_balancing)
- Équité samedis (saturday_fairness)
- Contiguité plages horaires via pénalités de transition (contiguity)

## Tests (15)
```bash
python -m src.tests
```

## Exécution locale
```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## Docker
```bash
docker build -t planning-api .
docker run -p 8000:8000 planning-api
```

## Déploiement
### Railway
1. Connecter le repo GitHub
2. Railway détecte automatiquement le Dockerfile
3. Déployer

### Render
1. Créer un Web Service
2. Start Command : `uvicorn main:app --host 0.0.0.0 --port $PORT`
3. Déployer

### Test curl
```bash
curl -X POST http://localhost:8000/generate-planning \
  -H "Content-Type: application/json" \
  -d '{
    "employees": ["Alice", "Bob"],
    "contracts": [35, 39],
    "roles": ["opticien", "vendeur"],
    "days": ["Lun", "Mar", "Mer"],
    "unavailabilities": [],
    "config": {}
  }'
```

## User Preferences
- Méthode incrémentale stricte : une seule règle à la fois
- Tests après chaque modification
- Fiabilité > performance > élégance
- Ne pas anticiper les phases suivantes
- Résumé après chaque étape

## Recent Changes
- 2026-02-18: Transformation en API REST production-ready
  - FastAPI avec endpoint POST /generate-planning
  - Modèles Pydantic pour validation entrée/sortie
  - requirements.txt minimal (fastapi, uvicorn, ortools)
  - Dockerfile minimal (python:3.11-slim)
  - Imports refactorisés en package Python (src.*)
  - Aucune dépendance Replit, 100% portable
  - 15/15 tests passent
- 2026-02-18: Étape 6 — Validation légale enrichie
- 2026-02-18: Étape 5 — Absences
- 2026-02-18: Étape 4 — Config JSON hiérarchique
- 2026-02-18: Étape 2-3 — Hard + soft constraints
- 2026-02-18: Étape 1 — Cohérence heures stabilisée
- 2026-02-17: Stabilisation V1 minimale
- 2026-02-15: Initial project setup
