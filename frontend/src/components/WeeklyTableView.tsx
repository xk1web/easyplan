import type { EmployeeSchedule } from "../types/planning";

type WeeklyTableViewProps = {
  schedule: Record<string, EmployeeSchedule>;
  days: string[];
};

const formatDayLabel = (day: string) => {
  const date = new Date(`${day}T00:00:00`);
  if (Number.isNaN(date.getTime())) {
    return day;
  }

  const weekday = new Intl.DateTimeFormat("fr-FR", { weekday: "short" })
    .format(date)
    .replace(".", "");
  const capitalizedWeekday = weekday.charAt(0).toUpperCase() + weekday.slice(1);
  const formattedDate = new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "2-digit",
  }).format(date);

  return `${capitalizedWeekday} ${formattedDate}`;
};

const WeeklyTableView = ({ schedule, days }: WeeklyTableViewProps) => {
  return (
    <table className="table weekly-table">
      <thead>
        <tr>
          <th>Employé</th>
          {days.map((day) => (
            <th key={day}>{formatDayLabel(day)}</th>
          ))}
          <th>Total</th>
        </tr>
      </thead>
      <tbody>
        {Object.entries(schedule).map(([employeeName, employeeData]) => (
          <tr key={employeeName}>
            <td>{employeeName}</td>
            {days.map((day) => {
              const dayData = employeeData.days[day];
              const isWorking = Boolean(dayData && dayData.ranges.length > 0);
              const content = isWorking
                ? dayData!.ranges.map((range) => `${range.start}\u2013${range.end}`).join(", ")
                : "OFF";

              return (
                <td key={`${employeeName}-${day}`} className={isWorking ? "working" : "off"}>
                  {content}
                </td>
              );
            })}
            <td>{employeeData.total_hours.toFixed(2)}h</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};

export default WeeklyTableView;
