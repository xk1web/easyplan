export type TimeRange = {
  start: string;
  end: string;
};

export type DaySchedule = {
  ranges: TimeRange[];
  hours: number;
};

export type EmployeeSchedule = {
  days: Record<string, DaySchedule>;
  total_hours: number;
};

export type EmployeeEntry = {
  name: string;
  contract: number;
  role: string;
};

export type ManualPlanningAnalysisInput = {
  schedule: Record<string, EmployeeSchedule>;
  employees: EmployeeEntry[];
  dayKeys: string[];
  openingDays: string[];
  openingOpen: string;
  openingClose: string;
  minStaff: number;
  dayLabels?: Record<string, string>;
};

export type ManualPlanningAnalysis = {
  summary: string[];
  employeeAlerts: string[];
  dayAlerts: string[];
  allAlerts: string[];
  problematicCells: Record<string, boolean>;
  contractsUnderCount: number;
  contractsOverCount: number;
  unsecuredOpenings: number;
  unsecuredClosings: number;
  noOpticianOpenings: number;
  noOpticianClosings: number;
};

const DEFAULT_WEEKDAYS = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
];

const FRENCH_DAY_KEY_TO_WEEKDAY: Record<string, string> = {
  lun: "monday",
  mar: "tuesday",
  mer: "wednesday",
  jeu: "thursday",
  ven: "friday",
  sam: "saturday",
  dim: "sunday",
};

const HIDDEN_BREAK_THRESHOLD_MINUTES = 6 * 60;
const HIDDEN_BREAK_MINUTES = 60;

const toMinutes = (hhmm: string): number => {
  const [hours, minutes] = hhmm.split(":").map(Number);
  if (Number.isNaN(hours) || Number.isNaN(minutes)) return 0;
  return (hours * 60) + minutes;
};

const effectiveMinutesFromRanges = (ranges: TimeRange[]): number => {
  const presence = ranges.reduce((sum, range) => {
    const start = toMinutes(range.start);
    const end = toMinutes(range.end);
    if (end <= start) return sum;
    return sum + (end - start);
  }, 0);
  if (presence > HIDDEN_BREAK_THRESHOLD_MINUTES) {
    return Math.max(0, presence - HIDDEN_BREAK_MINUTES);
  }
  return Math.max(0, presence);
};

const formatSignedMinutes = (minutesDelta: number): string => {
  const sign = minutesDelta > 0 ? "+" : "-";
  const absMinutes = Math.abs(minutesDelta);
  const hours = Math.floor(absMinutes / 60);
  const minutes = absMinutes % 60;
  return `${sign}${hours}h${String(minutes).padStart(2, "0")}`;
};

const resolveWeekdayFromDayKey = (dayKey: string): string | null => {
  const normalized = String(dayKey).trim().toLowerCase();
  if (DEFAULT_WEEKDAYS.includes(normalized)) {
    return normalized;
  }
  const generic = normalized.match(/^j(\d)$/);
  if (generic) {
    const idx = Number(generic[1]);
    return DEFAULT_WEEKDAYS[idx] ?? null;
  }
  return FRENCH_DAY_KEY_TO_WEEKDAY[normalized] ?? null;
};

const isPresentAtMinute = (ranges: TimeRange[], minute: number): boolean => (
  ranges.some((range) => {
    const start = toMinutes(range.start);
    const end = toMinutes(range.end);
    return start <= minute && minute < end;
  })
);

export const analyzeManualPlanning = ({
  schedule,
  employees,
  dayKeys,
  openingDays,
  openingOpen,
  openingClose,
  minStaff,
  dayLabels = {},
}: ManualPlanningAnalysisInput): ManualPlanningAnalysis => {
  const employeeAlerts: string[] = [];
  const dayAlerts: string[] = [];
  const allAlerts: string[] = [];
  const problematicCells: Record<string, boolean> = {};

  let contractsUnderCount = 0;
  let contractsOverCount = 0;
  let unsecuredOpenings = 0;
  let unsecuredClosings = 0;
  let noOpticianOpenings = 0;
  let noOpticianClosings = 0;

  const roleByEmployee = Object.fromEntries(employees.map((employee) => [employee.name, employee.role]));
  const employeeNames = employees.map((employee) => employee.name);

  for (const employee of employees) {
    const employeeSchedule = schedule[employee.name];
    if (!employeeSchedule) continue;

    const plannedMinutes = Object.values(employeeSchedule.days).reduce(
      (sum, dayData) => sum + effectiveMinutesFromRanges(dayData.ranges ?? []),
      0,
    );
    const contractMinutes = Math.max(0, Math.round(employee.contract * 60));
    const delta = plannedMinutes - contractMinutes;
    if (delta < 0) {
      contractsUnderCount += 1;
      employeeAlerts.push(`${employee.name} : contrat non atteint (${formatSignedMinutes(delta)})`);
      allAlerts.push(`${employee.name} : contrat non atteint (${formatSignedMinutes(delta)})`);
      for (const dayKey of dayKeys) {
        problematicCells[`${employee.name}__${dayKey}`] = true;
      }
    } else if (delta > 0) {
      contractsOverCount += 1;
      employeeAlerts.push(`${employee.name} : contrat depasse (${formatSignedMinutes(delta)})`);
      allAlerts.push(`${employee.name} : contrat depasse (${formatSignedMinutes(delta)})`);
      for (const dayKey of dayKeys) {
        problematicCells[`${employee.name}__${dayKey}`] = true;
      }
    }

    for (const dayKey of dayKeys) {
      const ranges = employeeSchedule.days[dayKey]?.ranges ?? [];
      const ordered = [...ranges].sort((a, b) => toMinutes(a.start) - toMinutes(b.start));
      for (let i = 0; i < ordered.length - 1; i += 1) {
        if (toMinutes(ordered[i].end) > toMinutes(ordered[i + 1].start)) {
          const dayLabel = dayLabels[resolveWeekdayFromDayKey(dayKey) ?? dayKey] ?? dayKey;
          const msg = `${employee.name} - ${dayLabel} : chevauchement d'horaires`;
          employeeAlerts.push(msg);
          allAlerts.push(msg);
          problematicCells[`${employee.name}__${dayKey}`] = true;
          break;
        }
      }
    }
  }

  const openMinute = toMinutes(openingOpen);
  const closeMinute = Math.max(openMinute, toMinutes(openingClose) - 1);

  for (const dayKey of dayKeys) {
    const weekday = resolveWeekdayFromDayKey(dayKey);
    if (weekday && !openingDays.includes(weekday)) {
      continue;
    }
    const dayLabel = dayLabels[weekday ?? dayKey] ?? dayKey;

    const countAt = (minute: number) => {
      let staff = 0;
      let opticians = 0;
      for (const employeeName of employeeNames) {
        const ranges = schedule[employeeName]?.days?.[dayKey]?.ranges ?? [];
        if (!isPresentAtMinute(ranges, minute)) continue;
        staff += 1;
        if (roleByEmployee[employeeName] === "opticien") {
          opticians += 1;
        }
      }
      return { staff, opticians };
    };

    const openingCoverage = countAt(openMinute);
    const closingCoverage = countAt(closeMinute);

    if (openingCoverage.staff < minStaff) {
      unsecuredOpenings += 1;
      if (openingCoverage.staff === 0) {
        dayAlerts.push(`${dayLabel} ouverture : aucun employe present (0/${minStaff})`);
        allAlerts.push(`${dayLabel} ouverture : aucun employe present (0/${minStaff})`);
      } else {
        dayAlerts.push(`${dayLabel} ouverture : couverture insuffisante (${openingCoverage.staff}/${minStaff})`);
        allAlerts.push(`${dayLabel} ouverture : couverture insuffisante (${openingCoverage.staff}/${minStaff})`);
      }
      for (const employeeName of employeeNames) {
        problematicCells[`${employeeName}__${dayKey}`] = true;
      }
    }
    if (closingCoverage.staff < minStaff) {
      unsecuredClosings += 1;
      if (closingCoverage.staff === 0) {
        dayAlerts.push(`${dayLabel} fermeture : aucun employe present (0/${minStaff})`);
        allAlerts.push(`${dayLabel} fermeture : aucun employe present (0/${minStaff})`);
      } else {
        dayAlerts.push(`${dayLabel} fermeture : couverture insuffisante (${closingCoverage.staff}/${minStaff})`);
        allAlerts.push(`${dayLabel} fermeture : couverture insuffisante (${closingCoverage.staff}/${minStaff})`);
      }
      for (const employeeName of employeeNames) {
        problematicCells[`${employeeName}__${dayKey}`] = true;
      }
    }

    if (openingCoverage.staff > 0 && openingCoverage.opticians === 0) {
      noOpticianOpenings += 1;
      dayAlerts.push(`${dayLabel} ouverture : aucun opticien diplome present`);
      allAlerts.push(`${dayLabel} ouverture : aucun opticien diplome present`);
      for (const employeeName of employeeNames) {
        problematicCells[`${employeeName}__${dayKey}`] = true;
      }
    }
    if (closingCoverage.staff > 0 && closingCoverage.opticians === 0) {
      noOpticianClosings += 1;
      dayAlerts.push(`${dayLabel} fermeture : aucun opticien diplome present`);
      allAlerts.push(`${dayLabel} fermeture : aucun opticien diplome present`);
      for (const employeeName of employeeNames) {
        problematicCells[`${employeeName}__${dayKey}`] = true;
      }
    }

    // Also inspect intermediate open slots (1h step) for qualification gaps.
    let missingOpticianInDay = false;
    let missingStaffInDay = false;
    for (let minute = openMinute; minute <= closeMinute; minute += 60) {
      const coverage = countAt(minute);
      if (coverage.staff === 0) {
        missingStaffInDay = true;
      } else if (coverage.opticians === 0) {
        missingOpticianInDay = true;
      }
    }
    if (missingStaffInDay) {
      const msg = `${dayLabel} : au moins un creneau ouvert sans personnel`;
      dayAlerts.push(msg);
      allAlerts.push(msg);
      for (const employeeName of employeeNames) {
        problematicCells[`${employeeName}__${dayKey}`] = true;
      }
    }
    if (missingOpticianInDay) {
      const msg = `${dayLabel} : personnel present mais sans opticien sur au moins un creneau`;
      dayAlerts.push(msg);
      allAlerts.push(msg);
      for (const employeeName of employeeNames) {
        problematicCells[`${employeeName}__${dayKey}`] = true;
      }
    }
  }

  const summary: string[] = [];
  const contractsNotRespected = contractsUnderCount + contractsOverCount;
  if (contractsNotRespected > 0) {
    summary.push(`${contractsNotRespected} contrat(s) non respecte(s)`);
  }
  if (unsecuredOpenings + unsecuredClosings > 0) {
    summary.push(`${unsecuredOpenings + unsecuredClosings} ouverture(s)/fermeture(s) non securisee(s)`);
  }
  if (noOpticianOpenings + noOpticianClosings > 0) {
    summary.push(`${noOpticianOpenings + noOpticianClosings} ouverture(s)/fermeture(s) sans opticien diplome`);
  }
  if (summary.length === 0) {
    summary.push("Aucune alerte critique detectee");
  }

  return {
    summary,
    employeeAlerts,
    dayAlerts,
    allAlerts,
    problematicCells,
    contractsUnderCount,
    contractsOverCount,
    unsecuredOpenings,
    unsecuredClosings,
    noOpticianOpenings,
    noOpticianClosings,
  };
};
