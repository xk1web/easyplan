import EmployeeLoadTable from "./EmployeeLoadTable";
import StatusBadge from "./StatusBadge";
import type { PlanningResponse } from "../types/planning";

type PlanningViewProps = {
  result: PlanningResponse | null;
};

const PlanningView = ({ result }: PlanningViewProps) => {
  if (!result) {
    return (
      <section className="panel">
        <h2>Planning View</h2>
        <p>No planning data yet.</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2>Planning View</h2>
      <div className="panel__stack">
        <div>
          Status: <StatusBadge status={result.status} />
        </div>
        <div>Classification: {result.classification ?? "N/A"}</div>
        <div>Suggestions: {result.suggestions?.join(", ") || "None"}</div>
        <div>Coverage (hours): {result.coverage_total_hours ?? "N/A"}</div>
        <div>Capacity (hours): {result.capacity_total_hours ?? "N/A"}</div>
        <div>Overtime used (hours): {result.total_overtime_used_hours ?? "N/A"}</div>
      </div>

      <EmployeeLoadTable hoursPerEmployee={result.hours_per_employee ?? {}} />
    </section>
  );
};

export default PlanningView;
