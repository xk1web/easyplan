# Planning Engine — V1 Minimale

## Overview
Moteur de génération de planning (Python + OR-Tools CP-SAT). V1 minimale strictement faisable.

## Project Architecture
- `src/` — Source code directory
- `src/validation.py` — Validation structurelle de faisabilité (heures disponibles vs requises)
- `src/model_builder_v1.py` — Modèle CP-SAT V1 minimal (hard constraints uniquement)
- `src/ai_runner.py` — Point d'entrée principal : pipeline validate → build → solve → return
- `src/tests.py` — 3 tests automatisés (faisable, impossible, limite)
- `src/app.py` — Serveur HTTP (non modifié)
- `src/ai_client.py` — Configuration client OpenAI (non modifié)
- `scheduler.py` — Ancien scheduler (conservé, non utilisé par V1)
- `src/scheduler_v2.py` — Ancien scheduler V2 (conservé, non utilisé par V1)

## Pipeline V1
1. `validate_global_feasibility` — vérifie A >= B avant solveur
2. `build_and_solve_v1` — modèle CP-SAT avec hard constraints uniquement
3. Extraction et retour du planning

## Hard Constraints V1
- Couverture minimale par créneau (min_staff_per_slot)
- Somme heures employé <= heures contractuelles
- Pas d'objectif d'optimisation

## Running
```bash
cd src && python ai_runner.py
```

## Tests
```bash
cd src && python tests.py
```

## Recent Changes
- 2026-02-17: Stabilisation V1 minimale — validation.py, model_builder_v1.py, pipeline propre, 3 tests
- 2026-02-15: Initial project setup with basic HTTP server
