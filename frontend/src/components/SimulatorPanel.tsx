import { useEffect, useMemo, useState } from "react";
import KpiPanel from "./KpiPanel";
import PlanningGrid from "./PlanningGrid";

type EmployeeEntry = {
  name: string;
  contract: number;
  role: string;
};

type TimeRange = {
  start: string;
  end: string;
};

type DaySchedule = {
  ranges: TimeRange[];
  hours: number;
};

type EmployeeSchedule = {
  days: Record<string, DaySchedule>;
  total_hours: number;
};

type ManagerConstraint = {
  type: "unavailability";
  employee: string;
  day: string;
} | {
  type: "day_status";
  employee: string;
  day: string;
  status: "working" | "off" | "unavailable";
} | {
  type: "prefer_morning";
  employee: string;
  day?: string;
} | {
  type: "avoid_closing";
  employee: string;
  day?: string;
} | {
  type: "extra_staff_day";
  day: string;
  extra_staff: number;
};

type SimulateResponse = {
  schedule?: Record<string, EmployeeSchedule> | null;
  kpi_summary?: Record<string, unknown> | null;
  explanation?: {
    global_analysis?: {
      message?: string;
    };
    constraints?: string[];
  } | null;
};

type GeneratePlanningResponse = {
  schedule?: Record<string, EmployeeSchedule> | null;
  kpi?: Record<string, unknown> | null;
  explanation?: Record<string, unknown> | null;
  error?: string | null;
};

const API_BASE_URL = import.meta.env.VITE_API_URL ?? import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const buildUrl = (path: string) => {
  const base = API_BASE_URL.endsWith("/") ? API_BASE_URL.slice(0, -1) : API_BASE_URL;
  return `${base}${path}`;
};

const parseErrorMessage = async (response: Response) => {
  try {
    const data = (await response.json()) as { detail?: string };
    if (typeof data.detail === "string") {
      return data.detail;
    }
  } catch {
    // ignore parse errors
  }
  return `HTTP ${response.status} ${response.statusText}`.trim();
};

const INITIAL_EMPLOYEES: EmployeeEntry[] = [{ name: "Employee 1", contract: 35, role: "opticien" }];
const INITIAL_MIN_STAFF = 1;
const INITIAL_OPENING_OPEN = "09:00";
const INITIAL_OPENING_CLOSE = "17:00";
const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const INITIAL_OPENING_DAYS = [...DAYS];
const DAY_LABELS: Record<string, string> = {
  monday: "Lundi",
  tuesday: "Mardi",
  wednesday: "Mercredi",
  thursday: "Jeudi",
  friday: "Vendredi",
  saturday: "Samedi",
  sunday: "Dimanche",
};

const getNumber = (source: Record<string, unknown> | null | undefined, keys: string[]) => {
  if (!source) {
    return 0;
  }
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
  }
  return 0;
};

const hhmmToMinutes = (value: string) => {
  const [hours, minutes] = value.split(":").map(Number);
  if (Number.isNaN(hours) || Number.isNaN(minutes)) {
    return 0;
  }
  return (hours * 60) + minutes;
};

const SimulatorPanel = () => {
  const [employees, setEmployees] = useState<EmployeeEntry[]>(INITIAL_EMPLOYEES);
  const [minStaff, setMinStaff] = useState<number>(INITIAL_MIN_STAFF);
  const [openingOpen, setOpeningOpen] = useState(INITIAL_OPENING_OPEN);
  const [openingClose, setOpeningClose] = useState(INITIAL_OPENING_CLOSE);
  const [openingDays, setOpeningDays] = useState<string[]>(INITIAL_OPENING_DAYS);
  const [loading, setLoading] = useState(false);
  const [loadingGenerate, setLoadingGenerate] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [schedule, setSchedule] = useState<Record<string, EmployeeSchedule>>({});
  const [kpi, setKpi] = useState<Record<string, unknown>>({});
  const [explanation, setExplanation] = useState<SimulateResponse["explanation"]>({});
  const [generatedSchedule, setGeneratedSchedule] = useState<Record<string, EmployeeSchedule> | null>(null);
  const [generatedKpi, setGeneratedKpi] = useState<Record<string, unknown> | null>(null);
  const [generatedExplanation, setGeneratedExplanation] = useState<Record<string, unknown> | null>(null);
  const [generatedPlanningPayload, setGeneratedPlanningPayload] = useState<Record<string, unknown> | null>(null);
  const [cellStatuses, setCellStatuses] = useState<Record<string, "working" | "off" | "unavailable">>({});
  const [constraints, setConstraints] = useState<ManagerConstraint[]>([]);
  const [constraintEmployee, setConstraintEmployee] = useState(INITIAL_EMPLOYEES[0]?.name ?? "");
  const [constraintDay, setConstraintDay] = useState("monday");
  const [constraintType, setConstraintType] = useState<"unavailability" | "prefer_morning" | "avoid_closing" | "extra_staff_day">("unavailability");
  const [constraintExtraStaff, setConstraintExtraStaff] = useState(1);

  const tensionRate = getNumber(kpi, ["tension_rate", "taux_tension_percent"]);
  const totalContractHours = getNumber(kpi, ["total_contract_hours", "total_heures_contractuelles"]);
  const totalRequiredHours = getNumber(kpi, ["total_required_hours", "total_heures_requises_couverture"]);
  const hasKpiSummary = Object.keys(kpi).length > 0;
  const planningImpossible = totalContractHours < totalRequiredHours;
  const surstaffingHours = Math.max(0, totalContractHours - totalRequiredHours);
  const canGeneratePlanning = hasKpiSummary && !planningImpossible;
  const explanationConstraints = explanation?.constraints ?? [];
  const closedWeekdayIndices = useMemo(
    () =>
      DAYS.reduce<number[]>((acc, day, idx) => {
        if (!openingDays.includes(day)) {
          acc.push(idx);
        }
        return acc;
      }, []),
    [openingDays],
  );
  const totalContractHoursInput = useMemo(
    () => employees.reduce((acc, employee) => acc + Math.max(0, employee.contract || 0), 0),
    [employees],
  );
  const simulationStatus = !hasKpiSummary
    ? "Aucune simulation"
    : planningImpossible
      ? "Sous-effectif"
      : surstaffingHours > 0
        ? "Surstaffing"
        : "Equilibre";

  useEffect(() => {
    if (employees.length === 0) {
      setConstraintEmployee("");
      return;
    }
    const hasSelectedEmployee = employees.some((employee) => employee.name === constraintEmployee);
    if (!hasSelectedEmployee) {
      setConstraintEmployee(employees[0].name);
    }
  }, [constraintEmployee, employees]);

  const updateEmployee = (index: number, key: keyof EmployeeEntry, value: string | number) => {
    setEmployees((prev) =>
      prev.map((employee, idx) => {
        if (idx !== index) {
          return employee;
        }
        return { ...employee, [key]: value };
      }),
    );
  };

  const addEmployee = () => {
    setEmployees((prev) => [
      ...prev,
      { name: `Employee ${prev.length + 1}`, contract: 35, role: "opticien" },
    ]);
  };

  const removeEmployee = (index: number) => {
    setEmployees((prev) => prev.filter((_, idx) => idx !== index));
  };

  const toggleOpeningDay = (day: string) => {
    setOpeningDays((prev) => {
      if (prev.includes(day)) {
        if (prev.length === 1) {
          return prev;
        }
        return prev.filter((entry) => entry !== day);
      }
      return [...prev, day];
    });
  };

  const removeConstraint = (index: number) => {
    setConstraints((prev) => prev.filter((_, idx) => idx !== index));
  };

  const addConstraint = () => {
    if (constraintType === "extra_staff_day") {
      setConstraints((prev) => [
        ...prev,
        {
          type: "extra_staff_day",
          day: constraintDay,
          extra_staff: Math.max(1, Math.floor(constraintExtraStaff)),
        },
      ]);
      return;
    }

    if (!constraintEmployee) return;

    if (constraintType === "unavailability") {
      setConstraints((prev) => [
        ...prev,
        { type: "unavailability", employee: constraintEmployee, day: constraintDay },
      ]);
      return;
    }
    if (constraintType === "prefer_morning") {
      setConstraints((prev) => [...prev, { type: "prefer_morning", employee: constraintEmployee, day: constraintDay }]);
      return;
    }
    setConstraints((prev) => [...prev, { type: "avoid_closing", employee: constraintEmployee, day: constraintDay }]);
  };

  const formatConstraint = (constraint: ManagerConstraint) => {
    if (constraint.type === "extra_staff_day") {
      return `${DAY_LABELS[constraint.day] ?? constraint.day} - renfort (+${constraint.extra_staff})`;
    }
    if (constraint.type === "unavailability") {
      return `${constraint.employee} - indisponible ${DAY_LABELS[constraint.day] ?? constraint.day}`;
    }
    if (constraint.type === "day_status") {
      const statusLabel = constraint.status === "working" ? "travaille" : constraint.status === "off" ? "repos" : "indisponible";
      return `${constraint.employee} - ${DAY_LABELS[constraint.day] ?? constraint.day} -> ${statusLabel}`;
    }
    if (constraint.type === "prefer_morning") {
      return constraint.day
        ? `${constraint.employee} - prefere le matin (${DAY_LABELS[constraint.day] ?? constraint.day})`
        : `${constraint.employee} - prefere le matin`;
    }
    if (constraint.day) {
      return `${constraint.employee} - eviter fermeture (${DAY_LABELS[constraint.day] ?? constraint.day})`;
    }
    return `${constraint.employee} - eviter fermeture`;
  };

  const simulatePlanning = async () => {
    setLoading(true);
    try {
      const payload = {
        employees: employees.map((employee) => employee.name),
        contracts: employees.map((employee) => employee.contract),
        roles: employees.map((employee) => employee.role),
        constraints,
        min_staff: minStaff,
        opening_hours: {
          open: openingOpen,
          close: openingClose,
        },
        opening_days: openingDays,
      };

      setError(null);
      const response = await fetch(buildUrl("/simulate-planning"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(await parseErrorMessage(response));
      }

      const data = (await response.json()) as SimulateResponse;
      setSchedule(data.schedule || {});
      setKpi(data.kpi_summary || {});
      setExplanation(data.explanation || {});
      setGeneratedSchedule(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(message);
      setSchedule({});
      setKpi({});
      setExplanation({});
    } finally {
      setLoading(false);
    }
  };

  const resetScenario = () => {
    setEmployees(INITIAL_EMPLOYEES);
    setMinStaff(INITIAL_MIN_STAFF);
    setOpeningOpen(INITIAL_OPENING_OPEN);
    setOpeningClose(INITIAL_OPENING_CLOSE);
    setOpeningDays(INITIAL_OPENING_DAYS);
    setError(null);
    setSchedule({});
    setKpi({});
    setExplanation({});
    setGeneratedSchedule(null);
    setGeneratedKpi(null);
    setGeneratedExplanation(null);
    setGeneratedPlanningPayload(null);
    setCellStatuses({});
    setConstraints([]);
    setConstraintEmployee(INITIAL_EMPLOYEES[0]?.name ?? "");
    setConstraintDay("monday");
    setConstraintType("unavailability");
    setConstraintExtraStaff(1);
  };

  const upsertDayStatusConstraint = (
    current: ManagerConstraint[],
    next: { employee: string; day: string; status: "working" | "off" | "unavailable" },
  ): ManagerConstraint[] => {
    const withoutSame = current.filter(
      (c) => !(c.type === "day_status" && c.employee === next.employee && c.day === next.day),
    );
    return [
      ...withoutSame,
      { type: "day_status" as const, employee: next.employee, day: next.day, status: next.status },
    ];
  };

  const generatePlanning = async () => {
    setLoadingGenerate(true);
    try {
      const payload = {
        employees: employees.map((employee) => employee.name),
        contracts: employees.map((employee) => employee.contract),
        roles: employees.map((employee) => employee.role),
        constraints,
        days: ["J0", "J1", "J2", "J3", "J4", "J5", "J6"],
        unavailabilities: [],
        config: {
          schedule: {
            start_time_minutes: hhmmToMinutes(openingOpen),
            end_time_minutes: hhmmToMinutes(openingClose),
            min_staff_per_slot: minStaff,
          },
          closed_weekdays: closedWeekdayIndices,
        },
      };

      setError(null);
      setGeneratedPlanningPayload(payload);
      const response = await fetch(buildUrl("/generate-planning"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error(await parseErrorMessage(response));
      }
      const data = (await response.json()) as GeneratePlanningResponse;
      if (data.error) {
        throw new Error(data.error);
      }
      setGeneratedSchedule(data.schedule ?? null);
      setGeneratedKpi(data.kpi ?? null);
      setGeneratedExplanation(data.explanation ?? null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(message);
      setGeneratedSchedule(null);
      setGeneratedKpi(null);
      setGeneratedExplanation(null);
    } finally {
      setLoadingGenerate(false);
    }
  };

  const adjustPlanningCell = async (payload: { employee: string; day: string; new_status: "working" | "off" | "unavailable" }) => {
    if (!generatedPlanningPayload) {
      setError("Generez un planning avant de le modifier.");
      return;
    }

    setLoadingGenerate(true);
    try {
      const body = { ...generatedPlanningPayload, employee: payload.employee, day: payload.day, new_status: payload.new_status };
      setError(null);
      const response = await fetch(buildUrl("/adjust-planning"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        throw new Error(await parseErrorMessage(response));
      }
      const data = (await response.json()) as GeneratePlanningResponse;
      if (data.error) {
        throw new Error(data.error);
      }

      setGeneratedSchedule(data.schedule ?? null);
      setGeneratedKpi(data.kpi ?? null);
      setGeneratedExplanation(data.explanation ?? null);

      setCellStatuses((prev) => ({ ...prev, [`${payload.employee}__${payload.day}`]: payload.new_status }));
      setConstraints((prev) => upsertDayStatusConstraint(prev, { employee: payload.employee, day: payload.day, status: payload.new_status }));
      setGeneratedPlanningPayload((prev) => {
        if (!prev) return prev;
        const currentConstraints = (prev as { constraints?: ManagerConstraint[] }).constraints ?? [];
        return { ...(prev as object), constraints: upsertDayStatusConstraint(currentConstraints, { employee: payload.employee, day: payload.day, status: payload.new_status }) };
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(message);
    } finally {
      setLoadingGenerate(false);
    }
  };

  const loadDemoStore = async () => {
    setLoadingGenerate(true);
    try {
      const payload = {
        employees: ["Alice", "Bob", "Chloe", "David"],
        contracts: [35, 35, 28, 24],
        roles: ["opticien", "opticien", "vendeur", "opticien"],
        constraints: [
          { type: "unavailability", employee: "Alice", day: "monday" },
          { type: "prefer_morning", employee: "Bob", day: "wednesday" },
          { type: "avoid_closing", employee: "David", day: "friday" },
        ],
        days: ["J0", "J1", "J2", "J3", "J4", "J5", "J6"],
        unavailabilities: [],
        config: {
          schedule: {
            start_time_minutes: 9 * 60,
            end_time_minutes: 18 * 60,
            min_staff_per_slot: 1,
          },
          closed_weekdays: [6],
        },
      };

      setError(null);
      const response = await fetch(buildUrl("/generate-planning"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error(await parseErrorMessage(response));
      }
      const data = (await response.json()) as GeneratePlanningResponse;
      if (data.error) {
        throw new Error(data.error);
      }
      setGeneratedSchedule(data.schedule ?? null);
      setGeneratedKpi(data.kpi ?? null);
      setGeneratedExplanation(data.explanation ?? null);
      setGeneratedPlanningPayload(payload);
      setCellStatuses({});
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(message);
      setGeneratedSchedule(null);
      setGeneratedKpi(null);
      setGeneratedExplanation(null);
    } finally {
      setLoadingGenerate(false);
    }
  };

  return (
    <section className="panel simulator">
      <div className="simulator__header">
        <div>
          <p className="simulator__eyebrow">Parametrage</p>
          <h2>Construire un scenario de planning</h2>
          <p className="simulator__description">
            Configurez vos ressources, simulez la couverture puis lancez la generation finale.
          </p>
        </div>
        <div className="simulator__stats">
          <div className="mini-stat">
            <span>Equipe</span>
            <strong>{employees.length}</strong>
          </div>
          <div className="mini-stat">
            <span>Contrats hebdo</span>
            <strong>{totalContractHoursInput.toFixed(1)}h</strong>
          </div>
          <div className="mini-stat">
            <span>Jours ouverts</span>
            <strong>{openingDays.length}/7</strong>
          </div>
          <div className="mini-stat">
            <span>Tension</span>
            <strong>{hasKpiSummary ? tensionRate.toFixed(2) : "--"}</strong>
          </div>
          <div className="mini-stat">
            <span>Status simulation</span>
            <strong>{simulationStatus}</strong>
          </div>
        </div>
      </div>

      <div className="panel-section">
        <div className="panel-section__title">
          <span>1</span>
          <h3>Equipe</h3>
        </div>
        <div className="panel__stack">
          {employees.map((employee, index) => (
            <div key={`sim-employee-${index}`} className="card panel__grid employee-card">
              <label>
                Employe
                <input
                  value={employee.name}
                  onChange={(event) => updateEmployee(index, "name", event.target.value)}
                />
              </label>
              <label>
                Contrat hebdo (h)
                <input
                  type="number"
                  min={0}
                  step={1}
                  value={employee.contract}
                  onChange={(event) => updateEmployee(index, "contract", Number(event.target.value))}
                />
              </label>
              <label>
                Role
                <select
                  value={employee.role}
                  onChange={(event) => updateEmployee(index, "role", event.target.value)}
                >
                  <option value="opticien">opticien</option>
                  <option value="vendeur">vendeur</option>
                </select>
              </label>
              <button
                type="button"
                className="button--ghost"
                onClick={() => removeEmployee(index)}
                disabled={employees.length === 1 || loading || loadingGenerate}
              >
                Supprimer
              </button>
            </div>
          ))}
          <div className="panel__actions">
            <button type="button" onClick={addEmployee} disabled={loading || loadingGenerate}>
              Ajouter employe
            </button>
          </div>
        </div>
      </div>

      <div className="panel-section">
        <div className="panel-section__title">
          <span>2</span>
          <h3>Parametres d'ouverture</h3>
        </div>
        <div className="card panel__grid">
          <label>
            Min staff
            <input
              type="number"
              min={0}
              step={1}
              value={minStaff}
              onChange={(event) => setMinStaff(Number(event.target.value))}
            />
          </label>
          <label>
            Ouverture
            <input type="time" value={openingOpen} onChange={(event) => setOpeningOpen(event.target.value)} />
          </label>
          <label>
            Fermeture
            <input
              type="time"
              value={openingClose}
              onChange={(event) => setOpeningClose(event.target.value)}
            />
          </label>
        </div>
        <div className="card day-toggle-panel">
          <p>Jours d'ouverture</p>
          <div className="day-toggle-grid">
            {DAYS.map((day) => {
              const isOpen = openingDays.includes(day);
              return (
                <button
                  key={`opening-day-${day}`}
                  type="button"
                  className={isOpen ? "day-toggle day-toggle--active" : "day-toggle"}
                  onClick={() => toggleOpeningDay(day)}
                  disabled={isOpen && openingDays.length === 1}
                >
                  {DAY_LABELS[day] ?? day}
                </button>
              );
            })}
          </div>
          <p className="hint-text">
            {openingDays.length === 7
              ? "Magasin ouvert 7/7."
              : `Fermeture: ${DAYS.filter((day) => !openingDays.includes(day)).map((day) => DAY_LABELS[day]).join(", ")}`}
          </p>
        </div>
      </div>

      <div className="panel-section">
        <div className="panel-section__title">
          <span>3</span>
          <h3>Contraintes manager</h3>
        </div>
        <div className="card panel__grid">
          <label>
            Employee
            <select
              value={constraintEmployee}
              onChange={(event) => setConstraintEmployee(event.target.value)}
              disabled={constraintType === "extra_staff_day"}
            >
              {employees.map((employee, index) => (
                <option key={`constraint-employee-${index}`} value={employee.name}>
                  {employee.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Day
            <select
              value={constraintDay}
              onChange={(event) => setConstraintDay(event.target.value)}
              disabled={false}
            >
              {DAYS.map((day) => (
                <option key={`constraint-day-${day}`} value={day}>
                  {DAY_LABELS[day] ?? day}
                </option>
              ))}
            </select>
          </label>
          <label>
            Type
            <select
              value={constraintType}
              onChange={(event) => setConstraintType(
                event.target.value as "unavailability" | "prefer_morning" | "avoid_closing" | "extra_staff_day",
              )}
            >
              <option value="unavailability">unavailability</option>
              <option value="prefer_morning">prefer_morning</option>
              <option value="avoid_closing">avoid_closing</option>
              <option value="extra_staff_day">extra_staff_day</option>
            </select>
          </label>
          {constraintType === "extra_staff_day" ? (
            <label>
              Extra staff
              <input
                type="number"
                min={1}
                step={1}
                value={constraintExtraStaff}
                onChange={(event) => setConstraintExtraStaff(Number(event.target.value))}
              />
            </label>
          ) : null}
          <button type="button" onClick={addConstraint} disabled={loading || loadingGenerate || employees.length === 0}>
            Ajouter contrainte
          </button>
        </div>
        {constraints.length > 0 ? (
          <div className="constraint-list">
            {constraints.map((constraint, index) => (
              <div key={`manager-constraint-${index}`} className="constraint-item">
                <span>{formatConstraint(constraint)}</span>
                <button type="button" className="button--ghost" onClick={() => removeConstraint(index)}>
                  Retirer
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className="empty-state">Aucune contrainte ajoutee.</p>
        )}
      </div>

      <div className="panel-section">
        <div className="panel-section__title">
          <span>4</span>
          <h3>Simulation et generation</h3>
        </div>
        <div className="panel__actions">
          <button type="button" className="button--primary" onClick={simulatePlanning} disabled={loading || loadingGenerate}>
            {loading ? "Simulation..." : "Simuler"}
          </button>
          <button type="button" onClick={resetScenario} disabled={loading || loadingGenerate}>
            Reinitialiser
          </button>
          {hasKpiSummary ? (
            <button
              type="button"
              className="button--primary-alt"
              onClick={generatePlanning}
              disabled={loadingGenerate || loading || !canGeneratePlanning}
            >
              {loadingGenerate ? "Generation..." : "Generer le planning"}
            </button>
          ) : null}
          <button type="button" className="button--ghost" onClick={loadDemoStore} disabled={loadingGenerate || loading}>
            Load demo store
          </button>
        </div>
        {!hasKpiSummary ? (
          <p className="hint-text">Lancez d'abord une simulation pour activer la generation finale.</p>
        ) : null}
      </div>

      {error ? <p className="alert alert--error">{error}</p> : null}

      <div className="decision-section">
        <h3>KPI</h3>
        <KpiPanel kpiSummary={kpi} />
        {hasKpiSummary && planningImpossible ? (
          <p className="alert alert--error">Sous-effectif detecte: les heures contractuelles sont insuffisantes.</p>
        ) : null}
        {hasKpiSummary && surstaffingHours > 0 ? (
          <p className="alert alert--warning">Surstaffing estime: {surstaffingHours.toFixed(2)} heures</p>
        ) : null}
        {explanationConstraints.length > 0 ? (
          <>
            <h4>Contraintes prises en compte</h4>
            <ul className="list-clean">
              {explanationConstraints.map((constraint, index) => (
                <li key={`constraint-${index}`}>{constraint}</li>
              ))}
            </ul>
          </>
        ) : null}
      </div>

      <div className="decision-section">
        <h3>Planning</h3>
        <PlanningGrid
          schedule={generatedSchedule ?? schedule}
          cellStatuses={cellStatuses}
          onCellStatusChange={adjustPlanningCell}
        />
      </div>

      <div className="decision-section">
        <h3>Explication</h3>
        <p>{explanation?.global_analysis?.message ?? "Aucun message."}</p>
      </div>
    </section>
  );
};

export default SimulatorPanel;
