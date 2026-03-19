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
const HIDDEN_BREAK_THRESHOLD_MINUTES = 6 * 60;
const HIDDEN_BREAK_MINUTES = 60;

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

const effectiveWorkedHoursFromRanges = (ranges: TimeRange[]): number => {
  const totalPresenceMinutes = ranges.reduce((sum, range) => {
    const start = hhmmToMinutes(range.start);
    const end = hhmmToMinutes(range.end);
    if (end <= start) return sum;
    return sum + (end - start);
  }, 0);
  const effectiveMinutes = totalPresenceMinutes > HIDDEN_BREAK_THRESHOLD_MINUTES
    ? totalPresenceMinutes - HIDDEN_BREAK_MINUTES
    : totalPresenceMinutes;
  return Math.max(0, effectiveMinutes / 60);
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
  const [generatedPlanning, setGeneratedPlanning] = useState<Record<string, EmployeeSchedule> | null>(null);
  const [editedPlanning, setEditedPlanning] = useState<Record<string, EmployeeSchedule> | null>(null);
  const [isManualEditMode, setIsManualEditMode] = useState(false);
  const [editedCellStatuses, setEditedCellStatuses] = useState<Record<string, "working" | "off" | "unavailable">>({});
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
      setGeneratedPlanning(null);
      setEditedPlanning(null);
      setEditedCellStatuses({});
      setIsManualEditMode(false);
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
    setGeneratedPlanning(null);
    setEditedPlanning(null);
    setEditedCellStatuses({});
    setIsManualEditMode(false);
    setConstraints([]);
    setConstraintEmployee(INITIAL_EMPLOYEES[0]?.name ?? "");
    setConstraintDay("monday");
    setConstraintType("unavailability");
    setConstraintExtraStaff(1);
  };

  const activePlanning = editedPlanning ?? generatedPlanning ?? schedule;

  const dayKeys = useMemo(() => {
    const keys = new Set<string>();
    Object.values(activePlanning).forEach((employeeSchedule) => {
      Object.keys(employeeSchedule.days).forEach((dayKey) => keys.add(dayKey));
    });
    if (keys.size === 0) {
      return ["J0", "J1", "J2", "J3", "J4", "J5", "J6"];
    }
    const ordered = Array.from(keys).sort((a, b) => a.localeCompare(b));
    while (ordered.length < 7) {
      ordered.push(`J${ordered.length}`);
    }
    return ordered.slice(0, 7);
  }, [activePlanning]);

  const getCellStatus = (
    planning: Record<string, EmployeeSchedule> | null | undefined,
    employee: string,
    day: string,
  ): "working" | "off" => {
    if (!planning) return "off";
    const dayData = planning[employee]?.days?.[day];
    return dayData && dayData.ranges.length > 0 ? "working" : "off";
  };

  const modifiedCells = useMemo(() => {
    if (!generatedPlanning || !editedPlanning) return {};
    const changed: Record<string, boolean> = {};
    for (const employee of Object.keys(generatedPlanning)) {
      for (const day of dayKeys) {
        const generatedDay = generatedPlanning[employee]?.days?.[day];
        const editedDay = editedPlanning[employee]?.days?.[day];
        const generatedStatus = generatedDay && generatedDay.ranges.length > 0 ? "working" : "off";
        const editedStatus = editedDay && editedDay.ranges.length > 0 ? "working" : "off";
        const generatedRange = generatedDay?.ranges?.[0];
        const editedRange = editedDay?.ranges?.[0];
        const hasTimeDiff = (generatedRange?.start ?? "") !== (editedRange?.start ?? "")
          || (generatedRange?.end ?? "") !== (editedRange?.end ?? "");
        if (generatedStatus !== editedStatus || hasTimeDiff) {
          changed[`${employee}__${day}`] = true;
        }
      }
    }
    return changed;
  }, [dayKeys, editedPlanning, generatedPlanning]);

  const localWarnings = useMemo(() => {
    if (!generatedPlanning || !editedPlanning) return [] as string[];
    const warnings: string[] = [];
    const contractByEmployee = Object.fromEntries(employees.map((employee) => [employee.name, employee.contract]));
    const roleByEmployee = Object.fromEntries(employees.map((employee) => [employee.name, employee.role]));

    for (const [employeeName, employeeSchedule] of Object.entries(editedPlanning)) {
      const contract = Number(contractByEmployee[employeeName] ?? 0);
      if (employeeSchedule.total_hours > contract + 1e-6) {
        warnings.push(`${employeeName}: contrat depasse (${employeeSchedule.total_hours.toFixed(1)}h > ${contract.toFixed(1)}h).`);
      }
    }

    for (const [employeeName, employeeSchedule] of Object.entries(editedPlanning)) {
      for (let i = 0; i < dayKeys.length - 1; i += 1) {
        const currentDay = employeeSchedule.days[dayKeys[i]];
        const nextDay = employeeSchedule.days[dayKeys[i + 1]];
        if (!currentDay?.ranges?.length || !nextDay?.ranges?.length) continue;
        const endCurrent = hhmmToMinutes(currentDay.ranges[currentDay.ranges.length - 1].end);
        const startNext = hhmmToMinutes(nextDay.ranges[0].start);
        const restMinutes = (24 * 60 - endCurrent) + startNext;
        if (restMinutes < 11 * 60) {
          warnings.push(`${employeeName}: repos < 11h entre ${dayKeys[i]} et ${dayKeys[i + 1]}.`);
        }
      }
    }

    for (const day of dayKeys) {
      let workingCount = 0;
      let opticianCount = 0;
      for (const [employeeName, employeeSchedule] of Object.entries(editedPlanning)) {
        const isWorking = Boolean(employeeSchedule.days[day]?.ranges?.length);
        if (!isWorking) continue;
        workingCount += 1;
        if (roleByEmployee[employeeName] === "opticien") {
          opticianCount += 1;
        }
      }
      if (workingCount < minStaff) {
        warnings.push(`${day}: sous-couverture (${workingCount}/${minStaff}).`);
      }
      if (workingCount > 0 && opticianCount === 0) {
        warnings.push(`${day}: absence d'opticien diplome.`);
      }
    }

    return warnings;
  }, [dayKeys, editedPlanning, employees, generatedPlanning, minStaff]);

  const recomputeTotalHours = (employeeSchedule: EmployeeSchedule): number => (
    Object.values(employeeSchedule.days).reduce((sum, dayData) => sum + dayData.hours, 0)
  );

  const applyStatusToEditedPlanning = (
    currentDraft: Record<string, EmployeeSchedule> | null,
    payload: { employee: string; day: string; new_status: "working" | "off" | "unavailable" },
  ): Record<string, EmployeeSchedule> | null => {
    if (!currentDraft || !currentDraft[payload.employee]) {
      return currentDraft;
    }
    const employeeSchedule = currentDraft[payload.employee];
    const nextDays = { ...employeeSchedule.days };
    const existingDay = nextDays[payload.day];

    if (payload.new_status === "off" || payload.new_status === "unavailable") {
      delete nextDays[payload.day];
    } else if (!existingDay) {
      nextDays[payload.day] = { ranges: [{ start: openingOpen, end: openingClose }], hours: effectiveWorkedHoursFromRanges([{ start: openingOpen, end: openingClose }]) };
    }

    const nextEmployeeSchedule: EmployeeSchedule = {
      ...employeeSchedule,
      days: nextDays,
      total_hours: recomputeTotalHours({ ...employeeSchedule, days: nextDays }),
    };

    return {
      ...currentDraft,
      [payload.employee]: nextEmployeeSchedule,
    };
  };

  const applyTimeToEditedPlanning = (
    currentDraft: Record<string, EmployeeSchedule> | null,
    payload: { employee: string; day: string; start: string; end: string },
  ): Record<string, EmployeeSchedule> | null => {
    if (!currentDraft || !currentDraft[payload.employee]) return currentDraft;
    const startMinutes = hhmmToMinutes(payload.start);
    const endMinutes = hhmmToMinutes(payload.end);
    if (endMinutes <= startMinutes) return currentDraft;

    const employeeSchedule = currentDraft[payload.employee];
    const nextDays = { ...employeeSchedule.days };
    nextDays[payload.day] = {
      ranges: [{ start: payload.start, end: payload.end }],
      hours: effectiveWorkedHoursFromRanges([{ start: payload.start, end: payload.end }]),
    };

    return {
      ...currentDraft,
      [payload.employee]: {
        ...employeeSchedule,
        days: nextDays,
        total_hours: recomputeTotalHours({ ...employeeSchedule, days: nextDays }),
      },
    };
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
      const nextPlanning = data.schedule ?? null;
      setGeneratedPlanning(nextPlanning);
      setEditedPlanning(nextPlanning);
      setEditedCellStatuses({});
      setIsManualEditMode(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(`Impossible de regenerer le planning avec les modifications manuelles: ${message}`);
    } finally {
      setLoadingGenerate(false);
    }
  };

  const adjustPlanningCell = (payload: { employee: string; day: string; new_status: "working" | "off" | "unavailable" }) => {
    if (!isManualEditMode || !generatedPlanning || !editedPlanning) {
      setError("Generez un planning avant de le modifier.");
      return;
    }
    setError(null);
    setEditedPlanning((prev) => applyStatusToEditedPlanning(prev, payload));
    setEditedCellStatuses((prev) => ({ ...prev, [`${payload.employee}__${payload.day}`]: payload.new_status }));
  };

  const adjustPlanningTime = (payload: { employee: string; day: string; start: string; end: string }) => {
    if (!isManualEditMode || !generatedPlanning || !editedPlanning) {
      return;
    }
    setEditedPlanning((prev) => applyTimeToEditedPlanning(prev, payload));
    setEditedCellStatuses((prev) => ({ ...prev, [`${payload.employee}__${payload.day}`]: "working" }));
  };

  const resetFromGeneratedPlanning = () => {
    setEditedPlanning(generatedPlanning);
    setEditedCellStatuses({});
    setError(null);
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
      const nextPlanning = data.schedule ?? null;
      setGeneratedPlanning(nextPlanning);
      setEditedPlanning(nextPlanning);
      setEditedCellStatuses({});
      setIsManualEditMode(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(message);
      setGeneratedPlanning(null);
      setEditedPlanning(null);
      setEditedCellStatuses({});
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
              {loadingGenerate ? "Generation..." : "Generer"}
            </button>
          ) : null}
          {generatedPlanning ? (
            <button
              type="button"
              className="button--ghost"
              onClick={() => setIsManualEditMode((prev) => !prev)}
              disabled={loadingGenerate || loading}
            >
              {isManualEditMode ? "Quitter mode edition" : "Mode edition"}
            </button>
          ) : null}
          {generatedPlanning ? (
            <button
              type="button"
              className="button--ghost"
              onClick={resetFromGeneratedPlanning}
              disabled={loadingGenerate || loading}
            >
              Reinitialiser depuis planning genere
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
        {generatedPlanning ? (
          <p className={isManualEditMode ? "alert alert--warning" : "hint-text"}>
            {isManualEditMode
              ? "Mode edition active: toutes les modifications sont locales (aucun appel backend)."
              : "Passez en mode edition pour modifier OFF/WORKING et horaires."}
          </p>
        ) : null}
        {isManualEditMode ? (
          <p className="hint-text">UX drag & drop prete: cellules rendues draggable (deplacement/resize a brancher ensuite).</p>
        ) : null}
        {localWarnings.length > 0 ? (
          <div className="card">
            <p className="alert alert--warning">
              Warnings locaux ({localWarnings.length}) : certaines modifications ne respectent pas les regles metier.
            </p>
            <ul className="list-clean">
              {localWarnings.map((warning, index) => (
                <li key={`local-warning-${index}`}>{warning}</li>
              ))}
            </ul>
          </div>
        ) : null}
        <PlanningGrid
          schedule={activePlanning}
          editMode={isManualEditMode}
          cellStatuses={editedCellStatuses}
          modifiedCells={modifiedCells}
          onCellStatusChange={adjustPlanningCell}
          onCellTimeChange={adjustPlanningTime}
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
