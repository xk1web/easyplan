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

type PlanningGridProps = {
  schedule?: Record<string, EmployeeSchedule> | null;
};

const DAY_LABELS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"] as const;
const DAY_KEYS_FRENCH = ["LUN", "MAR", "MER", "JEU", "VEN", "SAM", "DIM"] as const;
const DAY_KEYS_GENERIC = ["J0", "J1", "J2", "J3", "J4", "J5", "J6"] as const;

const resolveDayKeys = (schedule: Record<string, EmployeeSchedule>) => {
  const allKeys = new Set<string>();
  Object.values(schedule).forEach((employeeSchedule) => {
    Object.keys(employeeSchedule.days).forEach((key) => allKeys.add(key));
  });

  if (DAY_KEYS_FRENCH.every((key) => allKeys.has(key))) {
    return [...DAY_KEYS_FRENCH];
  }
  if (DAY_KEYS_GENERIC.every((key) => allKeys.has(key))) {
    return [...DAY_KEYS_GENERIC];
  }

  const fallback = Array.from(allKeys).sort((a, b) => a.localeCompare(b)).slice(0, 7);
  while (fallback.length < 7) {
    fallback.push(`J${fallback.length}`);
  }
  return fallback;
};

const PlanningGrid = ({ schedule }: PlanningGridProps) => {
  if (!schedule || Object.keys(schedule).length === 0) {
    return <p>Aucun planning.</p>;
  }

  const dayKeys = resolveDayKeys(schedule);

  return (
    <table className="table weekly-table">
      <thead>
        <tr>
          <th>Employe</th>
          {DAY_LABELS.map((label) => (
            <th key={label}>{label}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {Object.entries(schedule).map(([employeeName, employeeSchedule]) => (
          <tr key={employeeName}>
            <td>{employeeName}</td>
            {dayKeys.map((dayKey, index) => {
              const dayData = employeeSchedule.days[dayKey];
              if (!dayData || dayData.ranges.length === 0) {
                return <td key={`${employeeName}-${DAY_LABELS[index]}`}>—</td>;
              }
              const shift = dayData.ranges.map((range) => `${range.start}-${range.end}`).join(", ");
              return <td key={`${employeeName}-${DAY_LABELS[index]}`}>{shift}</td>;
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
};

export default PlanningGrid;
