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
  editMode?: boolean;
  onCellStatusChange?: (payload: {
    employee: string;
    day: string;
    new_status: "working" | "off" | "unavailable";
  }) => void;
  onCellTimeChange?: (payload: {
    employee: string;
    day: string;
    start: string;
    end: string;
  }) => void;
  cellStatuses?: Record<string, "working" | "off" | "unavailable">;
  modifiedCells?: Record<string, boolean>;
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

const PlanningGrid = ({
  schedule,
  editMode = false,
  onCellStatusChange,
  onCellTimeChange,
  cellStatuses,
  modifiedCells,
}: PlanningGridProps) => {
  if (!schedule || Object.keys(schedule).length === 0) {
    return <p className="empty-state">Aucun planning disponible pour le moment.</p>;
  }

  const dayKeys = resolveDayKeys(schedule);

  return (
    <div className="table-wrapper">
      <table className="table weekly-table">
        <thead>
          <tr>
            <th>Employé</th>
            {DAY_LABELS.map((label) => (
              <th key={label}>{label}</th>
            ))}
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(schedule).map(([employeeName, employeeSchedule]) => (
            <tr key={employeeName}>
              <td className="table__employee">{employeeName}</td>
              {dayKeys.map((dayKey, index) => {
                const dayData = employeeSchedule.days[dayKey];
                const isWorking = Boolean(dayData && dayData.ranges.length > 0);
                const key = `${employeeName}__${dayKey}`;
                const currentStatus = cellStatuses?.[key] ?? (isWorking ? "working" : "off");
                const firstRange = dayData?.ranges?.[0];
                const shift = currentStatus === "off"
                  ? "OFF"
                  : currentStatus === "unavailable"
                    ? "INDISPO"
                    : isWorking
                      ? dayData!.ranges.map((range) => `${range.start}-${range.end}`).join(", ")
                      : "WORKING (manuel)";
                const isModified = Boolean(modifiedCells?.[key]);

                return (
                  <td
                    key={`${employeeName}-${DAY_LABELS[index]}`}
                    className={isModified ? "planning-cell planning-cell--modified" : "planning-cell"}
                  >
                    <div
                      style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}
                      draggable={editMode}
                      data-dnd-cell={key}
                    >
                      <span>{shift}</span>
                      {editMode ? (
                        <>
                          <select
                            aria-label={`Modifier ${employeeName} ${DAY_LABELS[index]}`}
                            value={currentStatus}
                            onChange={(event) => {
                              const value = event.target.value as "working" | "off" | "unavailable";
                              onCellStatusChange?.({
                                employee: employeeName,
                                day: dayKey,
                                new_status: value,
                              });
                            }}
                            style={{ maxWidth: "140px" }}
                          >
                            <option value="working">Working</option>
                            <option value="off">Off</option>
                            <option value="unavailable">Unavailable</option>
                          </select>
                          {currentStatus === "working" ? (
                            <>
                              <input
                                type="time"
                                value={firstRange?.start ?? "09:00"}
                                onChange={(event) => {
                                  onCellTimeChange?.({
                                    employee: employeeName,
                                    day: dayKey,
                                    start: event.target.value,
                                    end: firstRange?.end ?? "17:00",
                                  });
                                }}
                                style={{ width: "120px" }}
                              />
                              <input
                                type="time"
                                value={firstRange?.end ?? "17:00"}
                                onChange={(event) => {
                                  onCellTimeChange?.({
                                    employee: employeeName,
                                    day: dayKey,
                                    start: firstRange?.start ?? "09:00",
                                    end: event.target.value,
                                  });
                                }}
                                style={{ width: "120px" }}
                              />
                            </>
                          ) : null}
                        </>
                      ) : null}
                    </div>
                  </td>
                );
              })}
              <td>{employeeSchedule.total_hours.toFixed(1)}h</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default PlanningGrid;
