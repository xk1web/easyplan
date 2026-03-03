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
  const [coverageLevel, setCoverageLevel] = useState<"low" | "standard" | "high">("standard");
  const [opticianRequirement, setOpticianRequirement] = useState<
    "required" | "recommended" | "none"
  >("recommended");
  const [contractPriority, setContractPriority] = useState<1 | 2 | 3>(2);
  const [equityPriority, setEquityPriority] = useState<"low" | "standard" | "high">(
    "standard",
  );
  const [employees, setEmployees] = useState<EmployeeInput[]>([
    { name: "Employee 1", weekly_hours: 35, role: "opticien" },
  ]);
  const [weekStartDate, setWeekStartDate] = useState("2026-03-02");
  const [numberOfDays, setNumberOfDays] = useState(6);
  const [openingStartMinutes, setOpeningStartMinutes] = useState(570);
  const [openingEndMinutes, setOpeningEndMinutes] = useState(1215);

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

  const buildPayload = (): PlanningRequest => {
    return {
      employees: employees.map((employee) => employee.name),
      contracts: employees.map((employee) => employee.weekly_hours),
      roles: employees.map((employee) => employee.role),
      days: buildDays(),
      unavailabilities: [],
      config: {
        coverage_level: coverageLevel,
        optician_requirement: opticianRequirement,
        contract_priority: contractPriority,
        equity_priority: equityPriority,
        schedule: {
          start_time_minutes: openingStartMinutes,
          end_time_minutes: openingEndMinutes,
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
          opticianRequirement={opticianRequirement}
          contractPriority={contractPriority}
          equityPriority={equityPriority}
          employees={employees}
          weekStartDate={weekStartDate}
          numberOfDays={numberOfDays}
          openingStartMinutes={openingStartMinutes}
          openingEndMinutes={openingEndMinutes}
          onCoverageChange={setCoverageLevel}
          onOpticianChange={setOpticianRequirement}
          onContractPriorityChange={setContractPriority}
          onEquityPriorityChange={setEquityPriority}
          onEmployeesChange={setEmployees}
          onWeekStartDateChange={setWeekStartDate}
          onNumberOfDaysChange={setNumberOfDays}
          onOpeningStartMinutesChange={setOpeningStartMinutes}
          onOpeningEndMinutesChange={setOpeningEndMinutes}
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
