import { useEffect, useMemo, useState } from "react";
import KpiPanel from "./KpiPanel";
import PlanningGrid from "./PlanningGrid";
import { analyzeManualPlanning } from "../utils/manualPlanningAnalysis";

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
  status?: string;
  schedule?: Record<string, EmployeeSchedule> | null;
  kpi?: Record<string, unknown> | null;
  explanation?: Record<string, unknown> | null;
  error?: string | null;
  infeasibility_reasons?: Array<{
    code: string;
    title: string;
    message: string;
    details?: Record<string, unknown>;
  }> | null;
};

type InfeasibilityReason = NonNullable<GeneratePlanningResponse["infeasibility_reasons"]>[number];

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
const LOCAL_DRAFT_STORAGE_KEY = "easyplan_manual_draft_v1";

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

const recomputeEmployeeTotalHours = (employeeSchedule: EmployeeSchedule): number => (
  Object.values(employeeSchedule.days).reduce((sum, dayData) => {
    if (!dayData?.ranges?.length) return sum;
    return sum + effectiveWorkedHoursFromRanges(dayData.ranges);
  }, 0)
);

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
  const [infeasibilityReasons, setInfeasibilityReasons] = useState<
    NonNullable<GeneratePlanningResponse["infeasibility_reasons"]>
  >([]);
  const [isManualEditMode, setIsManualEditMode] = useState(false);
  const [editedCellStatuses, setEditedCellStatuses] = useState<Record<string, "working" | "off" | "unavailable">>({});
  const [constraints, setConstraints] = useState<ManagerConstraint[]>([]);
  const [constraintEmployee, setConstraintEmployee] = useState(INITIAL_EMPLOYEES[0]?.name ?? "");
  const [constraintDay, setConstraintDay] = useState("monday");
  const [constraintType, setConstraintType] = useState<"unavailability" | "prefer_morning" | "avoid_closing" | "extra_staff_day">("unavailability");
  const [constraintExtraStaff, setConstraintExtraStaff] = useState(1);
  const [saveNotice, setSaveNotice] = useState<string | null>(null);
  const [localSaveState, setLocalSaveState] = useState<"idle" | "dirty" | "saved">("idle");

  const tensionRate = getNumber(kpi, ["tension_rate", "taux_tension_percent"]);
  const totalContractHours = getNumber(kpi, ["total_contract_hours", "total_heures_contractuelles"]);
  const totalRequiredHours = getNumber(kpi, ["total_required_hours", "total_heures_requises_couverture"]);
  const hasKpiSummary = Object.keys(kpi).length > 0;
  const planningImpossibleFromSimulation = totalContractHours < totalRequiredHours;
  const surstaffingHoursFromSimulation = Math.max(0, totalContractHours - totalRequiredHours);
  const canGeneratePlanning = hasKpiSummary && !planningImpossibleFromSimulation;
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
    : planningImpossibleFromSimulation
      ? "Sous-effectif"
      : surstaffingHoursFromSimulation > 0
        ? "Surstaffing"
        : "Equilibre";

  const reasonDetails = (reason: InfeasibilityReason): string[] => {
    const details = reason.details ?? {};
    if (reason.code === "NO_OPTICIAN_AVAILABLE") {
      const days = Array.isArray(details.days) ? details.days : [];
      if (days.length > 0) {
        return [`Jours impactes: ${days.map((day) => DAY_LABELS[String(day)] ?? String(day)).join(", ")}`];
      }
    }
    if (reason.code === "OPEN_DAY_NOT_COVERABLE") {
      const rows = Array.isArray(details.days) ? details.days : [];
      return rows.slice(0, 3).map((row) => {
        const day = String((row as Record<string, unknown>).day ?? "");
        const required = Number((row as Record<string, unknown>).required ?? 0);
        const maxAvailable = Number((row as Record<string, unknown>).max_available_assignments ?? 0);
        return `${DAY_LABELS[day] ?? day}: requis=${required}, max disponible=${maxAvailable}`;
      });
    }
    if (reason.code === "FIXED_OFF_INCOMPATIBLE") {
      const rows = Array.isArray(details.sample_constraints) ? details.sample_constraints : [];
      return rows.slice(0, 3).map((row) => {
        const item = row as Record<string, unknown>;
        const employee = String(item.employee ?? "");
        const day = String(item.day ?? "");
        const type = String(item.type ?? "");
        const status = String(item.status ?? "");
        const suffix = status ? ` (${status})` : "";
        return `${employee} - ${DAY_LABELS[day] ?? day} - ${type}${suffix}`;
      });
    }
    if (reason.code === "INSUFFICIENT_CAPACITY") {
      const rows = Array.isArray(details.employees_below_contract) ? details.employees_below_contract : [];
      return rows.slice(0, 3).map((row) => {
        const item = row as Record<string, unknown>;
        const employee = String(item.employee ?? "");
        const contractMinutes = Number(item.contract_minutes ?? 0);
        const maxPossibleMinutes = Number(item.max_possible_minutes ?? 0);
        return `${employee}: contrat=${(contractMinutes / 60).toFixed(1)}h, max possible=${(maxPossibleMinutes / 60).toFixed(1)}h`;
      });
    }
    return [];
  };

  const actionHints = useMemo(() => {
    const hints: string[] = [];
    const codes = new Set(infeasibilityReasons.map((reason) => reason.code));
    if (codes.has("NO_OPTICIAN_AVAILABLE")) {
      hints.push("Verifier les indisponibilites/off des opticiens sur les jours impactes.");
    }
    if (codes.has("OPEN_DAY_NOT_COVERABLE")) {
      hints.push("Ajuster le minimum journalier, les jours d'ouverture, ou les indisponibilites fixes.");
    }
    if (codes.has("FIXED_OFF_INCOMPATIBLE")) {
      hints.push("Retirer ou assouplir au moins une contrainte OFF/indisponibilite parmi celles listees.");
    }
    if (codes.has("INSUFFICIENT_CAPACITY")) {
      hints.push("Augmenter la capacite contractuelle ou reduire les indisponibilites bloquantes.");
    }
    if (hints.length === 0 && infeasibilityReasons.length > 0) {
      hints.push("Verifier les contraintes manager puis relancer une simulation.");
    }
    return hints;
  }, [infeasibilityReasons]);

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
      setSaveNotice(null);
      setLocalSaveState("idle");
      setInfeasibilityReasons([]);
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
      setInfeasibilityReasons([]);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(message);
      setSchedule({});
      setKpi({});
      setExplanation({});
      setInfeasibilityReasons([]);
      setSaveNotice(null);
      setLocalSaveState("idle");
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
    setInfeasibilityReasons([]);
    setSaveNotice(null);
    setLocalSaveState("idle");
    setConstraints([]);
    setConstraintEmployee(INITIAL_EMPLOYEES[0]?.name ?? "");
    setConstraintDay("monday");
    setConstraintType("unavailability");
    setConstraintExtraStaff(1);
  };

  const activePlanning = editedPlanning ?? generatedPlanning ?? schedule;
  const canEditLocally = Boolean(generatedPlanning || editedPlanning);
  const openingDurationHours = Math.max(0, (hhmmToMinutes(openingClose) - hhmmToMinutes(openingOpen)) / 60);
  const localKpiSummary = useMemo(() => {
    if (!activePlanning || Object.keys(activePlanning).length === 0) return null;

    const totalPlannedHours = Object.values(activePlanning).reduce(
      (sum, employeeSchedule) => sum + recomputeEmployeeTotalHours(employeeSchedule),
      0,
    );
    const totalContractHoursLocal = employees.reduce((sum, employee) => sum + Math.max(0, employee.contract || 0), 0);
    const totalRequiredHoursLocal = DAYS.reduce((sum, day) => {
      if (!openingDays.includes(day)) return sum;
      return sum + (minStaff * openingDurationHours);
    }, 0);
    const undercoverage = Math.max(0, totalRequiredHoursLocal - totalPlannedHours);
    const surstaffing = Math.max(0, totalPlannedHours - totalRequiredHoursLocal);
    const tension = totalContractHoursLocal > 0 ? totalRequiredHoursLocal / totalContractHoursLocal : 0;

    return {
      total_contract_hours: totalContractHoursLocal,
      total_required_hours: totalRequiredHoursLocal,
      total_planned_hours: totalPlannedHours,
      undercoverage_hours: undercoverage,
      surstaffing_hours: surstaffing,
      tension_rate: tension,
    };
  }, [activePlanning, employees, minStaff, openingDays, openingDurationHours]);
  const displayedKpi = isManualEditMode ? (localKpiSummary ?? kpi) : kpi;
  const displayedTotalContractHours = getNumber(displayedKpi, ["total_contract_hours", "total_heures_contractuelles"]);
  const displayedTotalRequiredHours = getNumber(displayedKpi, ["total_required_hours", "total_heures_requises_couverture"]);
  const planningImpossible = displayedTotalContractHours < displayedTotalRequiredHours;
  const surstaffingHours = Math.max(0, displayedTotalContractHours - displayedTotalRequiredHours);

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
  const localModifiedCount = useMemo(
    () => Object.keys(modifiedCells).length,
    [modifiedCells],
  );
  const localSaveLabel = localSaveState === "saved"
    ? "Sauvegarde locale: OK"
    : localSaveState === "dirty"
      ? "Sauvegarde locale: en attente"
      : "Sauvegarde locale: non demarree";

  const manualAnalysis = useMemo(() => {
    if (!isManualEditMode || !editedPlanning || dayKeys.length === 0) return null;
    return analyzeManualPlanning({
      schedule: editedPlanning,
      employees,
      dayKeys,
      openingDays,
      openingOpen,
      openingClose,
      minStaff,
      dayLabels: DAY_LABELS,
    });
  }, [dayKeys, editedPlanning, employees, isManualEditMode, minStaff, openingClose, openingDays, openingOpen]);
  const localWarnings = manualAnalysis?.allAlerts ?? [];
  const localEmployeeAlerts = manualAnalysis?.employeeAlerts ?? [];
  const localDayAlerts = manualAnalysis?.dayAlerts ?? [];
  const localSummary = manualAnalysis?.summary ?? [];
  const problematicCells = manualAnalysis?.problematicCells ?? {};
  const localImpactMessage = useMemo(() => {
    if (!isManualEditMode || !generatedPlanning || !editedPlanning) return null;

    const generatedHours = Object.values(generatedPlanning).reduce(
      (sum, employeeSchedule) => sum + recomputeEmployeeTotalHours(employeeSchedule),
      0,
    );
    const editedHours = Object.values(editedPlanning).reduce(
      (sum, employeeSchedule) => sum + recomputeEmployeeTotalHours(employeeSchedule),
      0,
    );
    const deltaHours = editedHours - generatedHours;
    const deltaLabel = deltaHours > 0 ? `+${deltaHours.toFixed(1)}h` : `${deltaHours.toFixed(1)}h`;

    if (Math.abs(deltaHours) < 1e-6 && localWarnings.length === 0) {
      return "Impact de vos changements: rien de critique.";
    }
    if (Math.abs(deltaHours) < 1e-6) {
      return `Impact de vos changements: heures stables, ${localWarnings.length} point(s) a verifier.`;
    }
    return `Impact de vos changements: ${deltaLabel} au planning, ${localWarnings.length} point(s) a verifier.`;
  }, [editedPlanning, generatedPlanning, isManualEditMode, localWarnings.length]);
  const activeAlertCount = infeasibilityReasons.length > 0 ? infeasibilityReasons.length : localWarnings.length;
  const managerStatusLabel = infeasibilityReasons.length > 0
    ? "Infeasible"
    : planningImpossible
      ? "Sous-effectif"
      : surstaffingHours > 0
        ? "Surstaffing"
        : "Stable";
  const kpiSourceLabel = isManualEditMode ? "KPI locaux (édition)" : "KPI solveur";

  const recomputeTotalHours = (employeeSchedule: EmployeeSchedule): number => (
    recomputeEmployeeTotalHours(employeeSchedule)
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
      setSaveNotice(null);
      const response = await fetch(buildUrl("/generate-planning"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error(await parseErrorMessage(response));
      }
      const data = (await response.json()) as GeneratePlanningResponse;
      if (data.status === "infeasible") {
        // Keep current local planning context so manual editing stays available.
        setIsManualEditMode(Boolean(editedPlanning ?? generatedPlanning));
        setInfeasibilityReasons(data.infeasibility_reasons ?? []);
        setError(data.error ?? "Planning infeasible avec les contraintes hard actuelles.");
        return;
      }
      if (data.error) {
        throw new Error(data.error);
      }
      const nextPlanning = data.schedule ?? null;
      setGeneratedPlanning(nextPlanning);
      setEditedPlanning(nextPlanning);
      setEditedCellStatuses({});
      setIsManualEditMode(false);
      setInfeasibilityReasons([]);
      setSaveNotice(null);
      setLocalSaveState("idle");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(`Impossible de regenerer le planning avec les modifications manuelles: ${message}`);
      setSaveNotice(null);
      setLocalSaveState("idle");
    } finally {
      setLoadingGenerate(false);
    }
  };

  const adjustPlanningCell = (payload: { employee: string; day: string; new_status: "working" | "off" | "unavailable" }) => {
    if (!isManualEditMode || !editedPlanning) {
      setError("Generez un planning avant de le modifier.");
      return;
    }
    setError(null);
    setSaveNotice(null);
    setLocalSaveState("dirty");
    setEditedPlanning((prev) => applyStatusToEditedPlanning(prev, payload));
    setEditedCellStatuses((prev) => ({ ...prev, [`${payload.employee}__${payload.day}`]: payload.new_status }));
  };

  const adjustPlanningTime = (payload: { employee: string; day: string; start: string; end: string }) => {
    if (!isManualEditMode || !editedPlanning) {
      return;
    }
    setEditedPlanning((prev) => applyTimeToEditedPlanning(prev, payload));
    setEditedCellStatuses((prev) => ({ ...prev, [`${payload.employee}__${payload.day}`]: "working" }));
    setSaveNotice(null);
    setLocalSaveState("dirty");
  };

  const swapEmployeeDays = (payload: { employee: string; sourceDay: string; targetDay: string }) => {
    if (!isManualEditMode || !editedPlanning) {
      return;
    }
    if (payload.sourceDay === payload.targetDay) {
      return;
    }

    setError(null);
    setSaveNotice(null);
    setLocalSaveState("dirty");
    setEditedPlanning((prev) => {
      if (!prev) return prev;
      const employeeSchedule = prev[payload.employee];
      if (!employeeSchedule) return prev;

      const nextDays = { ...employeeSchedule.days };
      const source = employeeSchedule.days[payload.sourceDay];
      const target = employeeSchedule.days[payload.targetDay];

      if (target) {
        nextDays[payload.sourceDay] = target;
      } else {
        delete nextDays[payload.sourceDay];
      }

      if (source) {
        nextDays[payload.targetDay] = source;
      } else {
        delete nextDays[payload.targetDay];
      }

      const nextSchedule = {
        ...employeeSchedule,
        days: nextDays,
        total_hours: recomputeTotalHours({ ...employeeSchedule, days: nextDays }),
      };

      return {
        ...prev,
        [payload.employee]: nextSchedule,
      };
    });
    setEditedCellStatuses((prev) => {
      const next = { ...prev };
      const sourceKey = `${payload.employee}__${payload.sourceDay}`;
      const targetKey = `${payload.employee}__${payload.targetDay}`;
      const sourceStatus = prev[sourceKey];
      const targetStatus = prev[targetKey];
      if (targetStatus) {
        next[sourceKey] = targetStatus;
      } else {
        delete next[sourceKey];
      }
      if (sourceStatus) {
        next[targetKey] = sourceStatus;
      } else {
        delete next[targetKey];
      }
      return next;
    });
  };

  const saveLocalEdits = () => {
    if (!editedPlanning) return;
    const snapshot = JSON.parse(JSON.stringify(editedPlanning)) as Record<string, EmployeeSchedule>;
    setGeneratedPlanning(snapshot);
    setEditedPlanning(snapshot);
    setEditedCellStatuses({});
    setError(null);
    setSaveNotice("Modifications enregistrees localement.");
    setLocalSaveState("saved");
    try {
      localStorage.setItem(LOCAL_DRAFT_STORAGE_KEY, JSON.stringify(snapshot));
    } catch {
      // Ignore storage errors.
    }
  };

  const resetFromGeneratedPlanning = () => {
    setEditedPlanning(generatedPlanning);
    setEditedCellStatuses({});
    setError(null);
    setSaveNotice(null);
    setLocalSaveState("idle");
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
      setSaveNotice(null);
      setLocalSaveState("idle");
      const response = await fetch(buildUrl("/generate-planning"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error(await parseErrorMessage(response));
      }
      const data = (await response.json()) as GeneratePlanningResponse;
      if (data.status === "infeasible") {
        setGeneratedPlanning(null);
        setEditedPlanning(null);
        setEditedCellStatuses({});
        setIsManualEditMode(false);
        setInfeasibilityReasons(data.infeasibility_reasons ?? []);
        setError(data.error ?? "Planning infeasible avec les contraintes hard actuelles.");
        return;
      }
      if (data.error) {
        throw new Error(data.error);
      }
      const nextPlanning = data.schedule ?? null;
      setGeneratedPlanning(nextPlanning);
      setEditedPlanning(nextPlanning);
      setEditedCellStatuses({});
      setIsManualEditMode(false);
      setInfeasibilityReasons([]);
      setSaveNotice(null);
      setLocalSaveState("idle");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(message);
      setGeneratedPlanning(null);
      setEditedPlanning(null);
      setEditedCellStatuses({});
      setInfeasibilityReasons([]);
      setSaveNotice(null);
      setLocalSaveState("idle");
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
          {canEditLocally ? (
            <button
              type="button"
              className="button--ghost"
              onClick={() => {
                if (!editedPlanning && generatedPlanning) {
                  setEditedPlanning(generatedPlanning);
                }
                setIsManualEditMode((prev) => !prev);
              }}
              disabled={loadingGenerate || loading}
            >
              {isManualEditMode ? "Quitter mode edition" : "Mode edition"}
            </button>
          ) : null}
          {generatedPlanning ? (
            <button
              type="button"
              className="button--ghost"
              onClick={saveLocalEdits}
              disabled={loadingGenerate || loading || !isManualEditMode || !editedPlanning}
            >
              Sauvegarder modifs locales
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
      {hasKpiSummary ? (
        <div className="card">
          <p className="hint-text">
            <strong>Résumé manager:</strong> Statut {managerStatusLabel} | {kpiSourceLabel} | {localModifiedCount} modif locale(s) | {activeAlertCount} alerte(s) | {localSaveLabel}
          </p>
          {localImpactMessage ? <p className="hint-text">{localImpactMessage}</p> : null}
          {saveNotice ? <p className="hint-text">{saveNotice}</p> : null}
        </div>
      ) : null}

      {error ? <p className="alert alert--error">{error}</p> : null}
      {infeasibilityReasons.length > 0 ? (
        <div className="card">
          <h4>Diagnostic infeasibility</h4>
          <ul className="list-clean">
            {infeasibilityReasons.map((reason, index) => (
              <li key={`${reason.code}-${index}`}>
                <strong>{reason.title}:</strong> {reason.message}
                {reasonDetails(reason).length > 0 ? (
                  <div className="hint-text">
                    {reasonDetails(reason).join(" | ")}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
          {actionHints.length > 0 ? (
            <>
              <h4>Actions recommandees</h4>
              <ul className="list-clean">
                {actionHints.map((hint, index) => (
                  <li key={`hint-${index}`}>{hint}</li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      ) : null}

      <div className="decision-section">
        <h3>KPI</h3>
        <KpiPanel kpiSummary={displayedKpi} />
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
        {isManualEditMode && localSummary.length > 0 ? (
          <div className="card">
            <p className="alert alert--warning">Synthese locale</p>
            <ul className="list-clean">
              {localSummary.map((item, index) => (
                <li key={`local-summary-${index}`}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {isManualEditMode && localEmployeeAlerts.length > 0 ? (
          <div className="card">
            <p className="alert alert--warning">Points critiques par employe</p>
            <ul className="list-clean">
              {localEmployeeAlerts.map((warning, index) => (
                <li key={`local-employee-warning-${index}`}>{warning}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {isManualEditMode && localDayAlerts.length > 0 ? (
          <div className="card">
            <p className="alert alert--warning">Points critiques par jour</p>
            <ul className="list-clean">
              {localDayAlerts.map((warning, index) => (
                <li key={`local-day-warning-${index}`}>{warning}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {isManualEditMode && localWarnings.length > 0 ? (
          <div className="card">
            <p className="alert alert--warning">
              Alertes actives ({localWarnings.length})
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
          problematicCells={problematicCells}
          onCellStatusChange={adjustPlanningCell}
          onCellTimeChange={adjustPlanningTime}
          onSwapDays={swapEmployeeDays}
        />
      </div>
    </section>
  );
};

export default SimulatorPanel;
