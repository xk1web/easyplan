import { useMemo, useState } from "react";
import EmployeeLoadTable from "./EmployeeLoadTable";
import StatusBadge from "./StatusBadge";
import WeeklyTableView from "./WeeklyTableView";
import type { PlanningResponse } from "../types/planning";

type PlanningViewProps = {
  result: PlanningResponse | null;
};

const PlanningView = ({ result }: PlanningViewProps) => {
  const [viewMode, setViewMode] = useState<"table" | "list">("table");
  const days = useMemo(() => {
    if (!result?.schedule) return [];
    const uniqueDays = new Set<string>();
    Object.values(result.schedule).forEach((employeeData) => {
      Object.keys(employeeData.days).forEach((day) => uniqueDays.add(day));
    });
    return Array.from(uniqueDays).sort((a, b) => a.localeCompare(b));
  }, [result?.schedule]);

  if (!result) {
    return (
      <section className="panel">
        <h2>Planning View</h2>
        <p>No planning data yet.</p>
      </section>
    );
  }

  const data = result;
  const isPlanningImpossible = data.classification === "infeasible_constraints";
  const displayedSuggestions = isPlanningImpossible
    ? [
        "Verifier les indisponibilites",
        "Augmenter le nombre d'opticiens",
        "Reduire les heures d'ouverture",
        "Autoriser 6 jours travailles",
      ]
    : (result.suggestions ?? []);
  const healthStatus = (() => {
    if (!data?.kpi) return "NEUTRAL";
    if (data.kpi.coverage_gap > 0) return "CRITICAL";
    if (data.kpi.overstaff_hours > 0) return "OVERSTAFF";
    return "OPTIMAL";
  })();

  return (
    <section className="panel">
      <h2>Planning View</h2>
      {data?.kpi && (
        <div style={{ padding: "12px", border: "1px solid #ccc", marginBottom: "16px" }}>
          <div>
            Planning status:{" "}
            <strong>
              {healthStatus === "CRITICAL" && "🔴 Under coverage"}
              {healthStatus === "OVERSTAFF" && "🟠 Overstaffed"}
              {healthStatus === "OPTIMAL" && "🟢 Balanced"}
            </strong>
          </div>
          <div>Contracted hours: {data.kpi.total_contracted_hours.toFixed(1)}h</div>
          <div>Worked hours: {data.kpi.total_worked_hours.toFixed(1)}h</div>
          <div>
            Contract utilization:{" "}
            {(
              (data.kpi.total_worked_hours /
                data.kpi.total_contracted_hours) *
              100
            ).toFixed(1)}
            %
          </div>
          <div>Internal hours: {data.kpi.total_internal_hours.toFixed(1)}h</div>
          <div>Coverage gap: {data.kpi.coverage_gap.toFixed(1)}h</div>
          <div>Overstaffing: {data.kpi.overstaff_hours.toFixed(1)}h</div>
        </div>
      )}
      <div className="panel__stack">
        <div>
          Status: <StatusBadge status={result.status} />
        </div>
        <div>
          Diagnostic:{" "}
          {isPlanningImpossible
            ? "Planning impossible avec les parametres actuels"
            : (result.classification ?? "N/A")}
        </div>
        <div>
          Suggestions:
          <ul>
            {displayedSuggestions.length > 0 ? (
              displayedSuggestions.map((suggestion, index) => (
                <li key={`${suggestion}-${index}`}>{suggestion}</li>
              ))
            ) : (
              <li>Aucune suggestion</li>
            )}
          </ul>
        </div>
        <div>
          Coverage (hours):{" "}
          {typeof result.coverage_total_hours === "number"
            ? result.coverage_total_hours.toFixed(1)
            : "N/A"}
        </div>
        <div>
          Capacity (hours):{" "}
          {typeof result.capacity_total_hours === "number"
            ? result.capacity_total_hours.toFixed(1)
            : "N/A"}
        </div>
        <div>
          Overtime used (hours):{" "}
          {typeof result.total_overtime_used_hours === "number"
            ? result.total_overtime_used_hours.toFixed(1)
            : "N/A"}
        </div>
      </div>

      <EmployeeLoadTable hoursPerEmployee={result.hours_per_employee ?? {}} />

      {result.schedule && (
        <div style={{ marginTop: "16px" }}>
          <h3>Weekly Details</h3>
          <div className="panel__actions">
            <button
              type="button"
              onClick={() => setViewMode("list")}
              disabled={viewMode === "list"}
            >
              Vue liste
            </button>
            <button
              type="button"
              onClick={() => setViewMode("table")}
              disabled={viewMode === "table"}
            >
              Vue tableau
            </button>
          </div>
          {viewMode === "table" ? (
            <WeeklyTableView schedule={result.schedule} days={days} />
          ) : (
            Object.entries(result.schedule).map(([employeeName, employeeData]) => {
              const orderedDays = Object.entries(employeeData.days).sort(([a], [b]) =>
                a.localeCompare(b),
              );
              return (
                <div
                  key={employeeName}
                  style={{
                    border: "1px solid #ccc",
                    padding: "12px",
                    marginBottom: "12px",
                    borderRadius: "8px",
                  }}
                >
                  <div style={{ fontWeight: 700, marginBottom: "8px" }}>
                    {employeeName} - total semaine: {employeeData.total_hours.toFixed(2)}h
                  </div>
                  {orderedDays.length === 0 ? (
                    <div>Aucun shift</div>
                  ) : (
                    orderedDays.map(([day, dayData]) => {
                      const ranges = dayData.ranges
                        .map((range) => `${range.start}-${range.end}`)
                        .join(", ");
                      return (
                        <div key={`${employeeName}-${day}`} style={{ marginBottom: "6px" }}>
                          <strong>{day}</strong> - plage(s): {ranges} - heures du jour:{" "}
                          {dayData.hours.toFixed(2)}h
                        </div>
                      );
                    })
                  )}
                </div>
              );
            })
          )}
        </div>
      )}
    </section>
  );
};

export default PlanningView;
