import { useState } from "react";
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

type SimulateResponse = {
  schedule?: Record<string, EmployeeSchedule> | null;
  kpi_summary?: Record<string, unknown> | null;
  explanation?: {
    global_analysis?: {
      message?: string;
    };
  } | null;
};

type GeneratePlanningResponse = {
  schedule?: Record<string, EmployeeSchedule> | null;
  error?: string | null;
};

const API_BASE_URL = "http://localhost:8001";

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
  const [loading, setLoading] = useState(false);
  const [loadingGenerate, setLoadingGenerate] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [schedule, setSchedule] = useState<Record<string, EmployeeSchedule>>({});
  const [kpi, setKpi] = useState<Record<string, unknown>>({});
  const [explanation, setExplanation] = useState<SimulateResponse["explanation"]>({});
  const [generatedSchedule, setGeneratedSchedule] = useState<Record<string, EmployeeSchedule> | null>(null);

  const tensionRate = getNumber(kpi, ["tension_rate", "taux_tension_percent"]);
  const totalContractHours = getNumber(kpi, ["total_contract_hours", "total_heures_contractuelles"]);
  const totalRequiredHours = getNumber(kpi, ["total_required_hours", "total_heures_requises_couverture"]);
  const hasKpiSummary = Object.keys(kpi).length > 0;
  const planningImpossible = totalContractHours < totalRequiredHours;
  const surstaffingHours = Math.max(0, totalContractHours - totalRequiredHours);
  const canGeneratePlanning = hasKpiSummary && !planningImpossible;

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

  const simulatePlanning = async () => {
    setLoading(true);
    try {
      const payload = {
        employees: employees.map((employee) => employee.name),
        contracts: employees.map((employee) => employee.contract),
        roles: employees.map((employee) => employee.role),
        min_staff: minStaff,
        opening_hours: {
          open: openingOpen,
          close: openingClose,
        },
      };

      setError(null);
      const response = await fetch("http://localhost:8000/simulate-planning", {
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
    setError(null);
    setSchedule({});
    setKpi({});
    setExplanation({});
    setGeneratedSchedule(null);
  };

  const generatePlanning = async () => {
    setLoadingGenerate(true);
    try {
      const payload = {
        employees: employees.map((employee) => employee.name),
        contracts: employees.map((employee) => employee.contract),
        roles: employees.map((employee) => employee.role),
        days: ["J0", "J1", "J2", "J3", "J4", "J5", "J6"],
        unavailabilities: [],
        config: {
          schedule: {
            start_time_minutes: hhmmToMinutes(openingOpen),
            end_time_minutes: hhmmToMinutes(openingClose),
            min_staff_per_slot: minStaff,
          },
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
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(message);
      setGeneratedSchedule(null);
    } finally {
      setLoadingGenerate(false);
    }
  };

  return (
    <section className="panel">
      <h2>Simulator Panel</h2>

      <div className="panel__stack">
        {employees.map((employee, index) => (
          <div key={`sim-employee-${index}`} className="card panel__grid">
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
              onClick={() => removeEmployee(index)}
              disabled={employees.length === 1 || loading}
            >
              Supprimer
            </button>
          </div>
        ))}

        <div className="panel__actions">
          <button type="button" onClick={addEmployee} disabled={loading}>
            Ajouter employe
          </button>
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

        <div className="panel__actions">
          <button type="button" className="button--primary" onClick={simulatePlanning} disabled={loading}>
            {loading ? "Simulation..." : "Simuler"}
          </button>
          <button type="button" onClick={resetScenario} disabled={loading}>
            Reset scenario
          </button>
        </div>
      </div>

      {error ? <p style={{ color: "#b42318" }}>{error}</p> : null}

      <div className="decision-section">
        <h3>KPI</h3>
        <KpiPanel kpiSummary={kpi} />
        {hasKpiSummary && planningImpossible ? <p style={{ color: "#b42318" }}>Sous-effectif</p> : null}
        {hasKpiSummary && surstaffingHours > 0 ? (
          <p style={{ color: "#b54708" }}>Surstaffing estime : {surstaffingHours.toFixed(2)} heures</p>
        ) : null}
        {hasKpiSummary ? (
          <div className="panel__actions">
            <button
              type="button"
              className="button--primary"
              onClick={generatePlanning}
              disabled={loadingGenerate || !canGeneratePlanning}
            >
              {loadingGenerate ? "Generation..." : "Generer le planning"}
            </button>
          </div>
        ) : null}
      </div>

      <div className="decision-section">
        <h3>Planning</h3>
        <PlanningGrid schedule={generatedSchedule ?? schedule} />
      </div>

      <div className="decision-section">
        <h3>Explication</h3>
        <p>{explanation?.global_analysis?.message ?? "Aucun message."}</p>
      </div>
    </section>
  );
};

export default SimulatorPanel;
