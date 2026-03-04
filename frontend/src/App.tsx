import { useState } from "react";
import DecisionPanel from "./components/DecisionPanel";
import DiagnosticPanel from "./components/DiagnosticPanel";
import PlanningView from "./components/PlanningView";
import { generatePlanning } from "./api/planning";
import type { PlanningRequest, PlanningResponse } from "./types/planning";

type EmployeeInput = {
  name: string;
  weekly_hours: number;
  role: "opticien" | "vendeur";
};

const App = () => {
  const [coverageLevel, setCoverageLevel] = useState<"standard" | "high">("standard");
  const [planningPriority, setPlanningPriority] = useState<
    "team_balance" | "store_performance" | "strict_contracts"
  >("team_balance");
  const [opticianRequirement, setOpticianRequirement] = useState<"required" | "recommended">(
    "recommended",
  );
  const [employees, setEmployees] = useState<EmployeeInput[]>([
    { name: "Employee 1", weekly_hours: 35, role: "opticien" },
  ]);
  const [weekStartDate, setWeekStartDate] = useState("2026-03-02");
  const [numberOfDays, setNumberOfDays] = useState(28);
  const [openingStartTime, setOpeningStartTime] = useState("09:30");
  const [openingEndTime, setOpeningEndTime] = useState("20:15");

  const [planningResult, setPlanningResult] = useState<PlanningResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buildDays = () => {
    const startDate = new Date(weekStartDate);
    if (Number.isNaN(startDate.getTime())) {
      return [];
    }
    return Array.from({ length: numberOfDays }, (_, index) => {
      const date = new Date(startDate);
      date.setDate(startDate.getDate() + index);
      const isoDate = date.toISOString().split("T")[0];
      return isoDate;
    });
  };

  const hhmmToMinutes = (value: string) => {
    const [hours, minutes] = value.split(":").map(Number);
    if (Number.isNaN(hours) || Number.isNaN(minutes)) {
      return 0;
    }
    return (hours * 60) + minutes;
  };

  const buildPlanningPriorities = () => {
    if (planningPriority === "store_performance") {
      return { contract_priority: 1 as const, equity_priority: "low" as const };
    }
    if (planningPriority === "strict_contracts") {
      return { contract_priority: 3 as const, equity_priority: "standard" as const };
    }
    return { contract_priority: 2 as const, equity_priority: "high" as const };
  };

  const buildPayload = (): PlanningRequest => {
    const priorities = buildPlanningPriorities();
    return {
      employees: employees.map((employee) => employee.name),
      contracts: employees.map((employee) => employee.weekly_hours),
      roles: employees.map((employee) => employee.role),
      days: buildDays(),
      unavailabilities: [],
      config: {
        coverage_level: coverageLevel,
        optician_requirement: opticianRequirement,
        contract_priority: priorities.contract_priority,
        equity_priority: priorities.equity_priority,
        closed_weekdays: [6],
        start_date: weekStartDate,
        schedule: {
          start_time_minutes: hhmmToMinutes(openingStartTime),
          end_time_minutes: hhmmToMinutes(openingEndTime),
        },
      },
      previous_month_stats: undefined,
    };
  };

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = buildPayload();
      const response = await generatePlanning(payload);
      setPlanningResult(response);
      if (response.error) {
        setError(response.error);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(message);
      setPlanningResult(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="app__header">
        <h1>EasyPlan Cockpit</h1>
      </header>

      <main className="app__content">
        <DecisionPanel
          coverageLevel={coverageLevel}
          planningPriority={planningPriority}
          opticianRequirement={opticianRequirement}
          employees={employees}
          weekStartDate={weekStartDate}
          numberOfDays={numberOfDays}
          openingStartTime={openingStartTime}
          openingEndTime={openingEndTime}
          onCoverageChange={setCoverageLevel}
          onPlanningPriorityChange={setPlanningPriority}
          onOpticianChange={setOpticianRequirement}
          onEmployeesChange={setEmployees}
          onWeekStartDateChange={setWeekStartDate}
          onNumberOfDaysChange={setNumberOfDays}
          onOpeningStartTimeChange={setOpeningStartTime}
          onOpeningEndTimeChange={setOpeningEndTime}
          onGenerate={handleGenerate}
          loading={loading}
        />

        <DiagnosticPanel
          loading={loading}
          error={error}
          onClearError={() => setError(null)}
          onResetResult={() => setPlanningResult(null)}
          onResetLoading={() => setLoading(false)}
        />

        <PlanningView result={planningResult} />
      </main>
    </div>
  );
};

export default App;
