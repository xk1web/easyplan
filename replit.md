# Planning Engine — API REST Production V2

## Overview
API REST de génération de planning mensuel (Python + FastAPI + OR-Tools CP-SAT) pour magasins d'optique.
Convention collective optique-lunetterie (IDCC 1431).
Supporte 1 mois complet (28-31 jours), structuration hebdomadaire, équité mensuelle, injection statistiques mois précédent.
Portable et déployable sur n'importe quelle infrastructure (Railway, Render, VPS, Docker, AWS).

## Project Architecture
```
.
├── main.py                      — API FastAPI v2 (point d'entrée)
├── requirements.txt             — Dépendances minimales
├── Dockerfile                   — Image Docker production
├── src/
│   ├── __init__.py              — Package Python
│   ├── model_builder_v1.py      — Modèle CP-SAT : variables, extraction résultats, métriques solveur
│   ├── hard_constraints.py      — Contraintes dures : couverture, max hebdo/semaine, 6j max, repos 11h/35h, opticien, absences
│   ├── soft_constraints.py      — Contraintes souples : équité mensuelle, équité samedis (+ long-terme), contiguité
│   ├── validation.py            — Validation structurelle et légale
│   ├── config.py                — Config JSON hiérarchique avec valeurs par défaut (fast_solve, long_term_equity_weight)
│   ├── ai_runner.py             — Script CLI standalone
│   └── tests.py                 — 22 tests automatisés
├── frontend/                    — Frontend de test minimal (Vite + React)
│   ├── index.html               — Point d'entrée HTML
│   ├── package.json             — Dépendances Node.js
│   ├── vite.config.js           — Config Vite (proxy vers backend :8000)
│   └── src/
│       ├── main.jsx             — Entrée React
│       └── App.jsx              — Formulaire + appel API + affichage résultats
├── scheduler.py                 — Ancien scheduler (conservé, non utilisé)
└── src/app.py                   — Ancien serveur HTTP (conservé, non utilisé)
```

## API Endpoints

### GET /
Health check.
```json
{"status": "ok", "engine": "planning-optique-v2"}
```

### POST /generate-planning
Génère un planning mensuel optimisé.

**Body JSON :**
```json
{
  "employees": ["Alice", "Bob", "Charlie"],
  "contracts": [35, 39, 40],
  "roles": ["opticien", "vendeur", "opticien"],
  "days": ["J0", "J1", ..., "J27"],
  "unavailabilities": [],
  "config": {
    "schedule": { "min_staff_per_slot": 2 },
    "solver": { "max_time_seconds": 60 },
    "fast_solve": false,
    "long_term_equity_weight": 0.3
  },
  "previous_month_stats": {
    "total_hours": { "Alice": 152, "Bob": 160, "Charlie": 140 },
    "saturdays_worked": { "Alice": 2, "Bob": 4, "Charlie": 1 }
  }
}
```

**Réponse :**
```json
{
  "status": "optimal",
  "schedule": { ... },
  "solver_time": 6.8,
  "metrics": {
    "num_variables": 5900,
    "num_constraints": 2050,
    "solver_wall_time": 6.5,
    "solver_status": "OPTIMAL",
    "gap_percent": 0.0,
    "warnings": []
  },
  "error": null
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
    "max_days_per_week": 6,
    "max_daily_minutes": 600,
    "rest_between_days_minutes": 660,
    "weekly_rest_minutes": 2100,
    "require_qualified_optician": true
  },
  "soft_weights": {
    "hours_balancing": 10,
    "saturday_fairness": 5,
    "contiguity": 3,
    "contract_target_under": 8,
    "contract_target_over": 12
  },
  "solver": {
    "max_time_seconds": 30
  },
  "long_term_equity_weight": 0.3,
  "fast_solve": false
}
```

## Hard Constraints (par semaine de 7 jours)
- Couverture minimale par créneau (min_staff_per_slot)
- Heures hebdo ≤ contrat **par semaine** (max_weekly_hours) — découpage automatique en blocs de 7 jours
- Max 6 jours travaillés **par semaine** (max_days_per_week)
- Durée journalière ≤ 10h (max_daily_minutes, IDCC 1431)
- Repos inter-journalier ≥ 11h (rest_between_days_minutes)
- Repos hebdomadaire 35h consécutives (contrainte explicite sur triplets de jours + max 6j/semaine)
- Présence opticien diplômé obligatoire (RULE 5.1)
- Absences (journées complètes ou créneaux spécifiques)

## Soft Constraints (objectif pondéré)
- **Équité mensuelle** : une seule variable over/under par employé pour tout le mois (remplace l'ancien équilibrage proportionnel hebdomadaire)
- Équité samedis (saturday_fairness) avec ajustement long-terme via previous_month_stats
- Contiguité plages horaires via pénalités de transition (contiguity)

## Injection Statistiques Mois Précédent
- Champ `previous_month_stats` dans la requête API
- `total_hours`: heures travaillées par employé le mois précédent → ajuste le target mensuel
- `saturdays_worked`: samedis travaillés → pénalise ceux qui en ont fait beaucoup
- Coefficient paramétrable : `long_term_equity_weight` (défaut 0.3)

## Mode Fast Solve
- Activable via `config.fast_solve: true`
- Désactive contiguité et équité samedi
- Réduit significativement le nombre de variables et contraintes
- Recommandé pour scénarios >10 employés ou >28 jours

## Performance Safeguards
- Warning automatique si >10 employés
- Warning automatique si >35 jours
- Métriques solveur incluses dans chaque réponse

## Tests (22)
```bash
python -m src.tests
```

## RAPPORT FINAL — Phase 6

### Impact en nombre de variables
- Variables principales : E × D × S (employés × jours × créneaux)
  - 10 employés × 28 jours × 20 créneaux (slot 30min, 10h ouverture) = **5 600 variables booléennes**
  - 10 employés × 31 jours × 43 créneaux (slot 15min, 10h45 ouverture) = **13 330 variables booléennes**
- Variables auxiliaires Phase 1 : E × W × jours/semaine pour day_worked (max 6j) = ~10 × 5 × 7 = 350
- Variables auxiliaires Phase 2 : 2 × E = 20 (over/under mensuel, remplace l'ancien par semaine)
- Variables auxiliaires contiguité (refonte blocs v2) : E × D × (S-1) BoolVar (gap_reopens) + E × D IntVar (excess) ≈ 10 × 30 × 20 + 300 = 6 300 (désactivable via fast_solve)
- **Total estimé avec slot 30min, normal** : ~13 200 variables, ~9 130 contraintes (mesuré 10×30)
- **Total estimé avec slot 30min, fast** : ~6 160 variables, ~2 570 contraintes (mesuré 10×28)
- **Total estimé avec slot 15min** : ~19 000 variables, ~12 000 contraintes

### Complexité estimée
- Complexité linéaire en nombre de jours : O(E × D × S)
- Pas de croissance exponentielle introduite par les phases
- Phase 1 (semaines) : découpage O(D/7), contraintes O(E × W × S) — linéaire
- Phase 2 (équité mensuelle) : 2 variables par employé — O(E), réduit vs ancien
- Phase 3 (stats précédentes) : ajustement constant par employé — O(E)
- Phase 4 (métriques) : lecture seule post-solve — O(1)
- Phase 5 (safeguards) : vérification O(1), fast_solve réduit le modèle

### Comportement attendu à 10 employés × 30 jours
- Avec slot 30min, min_staff=2, fast_solve=true : résolution en **5-7 secondes** (mesuré : 5.9s pour 10×28)
- Avec slot 30min, min_staff=2, fast_solve=false (contiguité ON) : résolution en **~14 secondes** (mesuré : 14.2s pour 10×30, gap 1.21%)
- Avec slot 15min, min_staff=2, fast_solve=true : résolution en **15-30 secondes**
- Status OPTIMAL ou FEASIBLE (gap <2%) atteignable avec max_time_seconds=15

### Limites restantes
1. **Repos 35h** : appliqué via contrainte sur triplets de jours (d, d+1, d+2) : si le gap spanning un jour off < 35h, le jour off ne peut pas être le jour de repos. Combiné avec max 6j/semaine, force au moins un bloc de repos >= 35h. N'utilise pas de fenêtre glissante de 7 jours.
2. **Découpage semaines** : blocs fixes de 7 jours depuis le jour 0, ne tient pas compte du jour de la semaine réel (lundi, mardi, etc.)
3. **Previous month stats** : mapping par nom d'employé. Les employés absents des stats précédentes ne sont pas ajustés.
4. **Contiguité** : refonte v2 par blocs (SAT clauses + excess IntVar + hints), scalable à 10×30 en <15s, fast_solve la désactive
5. **Pas de planification multi-mois** : chaque appel est indépendant, la continuité inter-mois passe uniquement par previous_month_stats
6. **Slot 15min** : à 10 employés × 31 jours, le modèle contient ~19 000 variables — le solveur peut ne pas trouver l'optimal dans le timeout

### Temps solveur estimé
| Scénario | Variables | Contraintes | Temps estimé | Status |
|----------|-----------|-------------|--------------|--------|
| 6 emp × 6j, slot 15min | ~1 600 | ~800 | <2s | OPTIMAL |
| 10 emp × 28j, slot 30min, fast | ~6 160 | ~2 570 | ~6s | OPTIMAL |
| 10 emp × 30j, slot 30min, normal | ~13 200 | ~9 130 | ~14s | FEASIBLE (gap <2%) |
| 10 emp × 28j, slot 15min, fast | ~12 500 | ~4 500 | ~20s | FEASIBLE |
| 10 emp × 31j, slot 15min, normal | ~19 000 | ~12 000 | 30-60s | FEASIBLE |

## User Preferences
- Méthode incrémentale stricte : une seule règle à la fois
- Tests après chaque modification
- Fiabilité > performance > élégance
- Ne pas anticiper les phases suivantes
- Résumé après chaque étape

## Workflows
- **Backend API** : `uvicorn main:app --host 0.0.0.0 --port 8000 --reload` (port 8000)
- **Frontend** : `cd frontend && npm run dev` (port 5000, proxy /generate-planning → localhost:8000)

## Recent Changes
- 2026-02-18: Ajout pénalité soft contract_target — incite chaque employé à atteindre son contrat sans le dépasser
  - weight_under=8 (en dessous du contrat), weight_over=12 (dépassement, pénalisé plus fort)
  - Calcul automatique du target en slots selon la durée de la période (weeks_in_period = num_days / 7)
  - Désactivé en fast_solve, poids configurables via soft_weights
- 2026-02-18: Refonte contiguité v2 — Modélisation par blocs (SAT clauses + excess + hints)
  - Ancien : AddAbsEquality + IntVar diff → 12 000 vars, 12 000 contraintes contiguité, timeout
  - Nouveau : AddBoolOr (SAT clause) + excess IntVar + AddHint → 6 300 vars, 6 300 contraintes contiguité
  - Résultat mesuré 10×30 normal : 14.2s, FEASIBLE, gap 1.21%, max 3 plages/jour
  - 22/22 tests passent
- 2026-02-18: V2 — Implémentation 6 phases :
  - Phase 1 : Structuration hebdomadaire (get_weeks, max_weekly_hours par semaine, max 6j/semaine, repos 35h)
  - Phase 2 : Équité mensuelle (add_monthly_hours_balancing, 1 over/under par employé)
  - Phase 3 : Injection previous_month_stats (total_hours, saturdays_worked, long_term_equity_weight)
  - Phase 4 : Métriques solveur (num_variables, num_constraints, solver_wall_time, solver_status, gap_percent)
  - Phase 5 : Safeguards (warnings >10 emp/>35 jours, fast_solve mode)
  - Phase 6 : Rapport final documenté
  - 22/22 tests passent (dont 10 emp × 28 jours en 6.8s)
- 2026-02-18: V1 — API REST production-ready
- 2026-02-18: Étape 6 — Validation légale enrichie
- 2026-02-18: Étape 5 — Absences
- 2026-02-18: Étape 4 — Config JSON hiérarchique
- 2026-02-18: Étape 2-3 — Hard + soft constraints
- 2026-02-18: Étape 1 — Cohérence heures stabilisée
- 2026-02-17: Stabilisation V1 minimale
- 2026-02-15: Initial project setup
