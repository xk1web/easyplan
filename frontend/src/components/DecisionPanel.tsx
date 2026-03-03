type DecisionPanelProps = {
  coverageLevel: "low" | "standard" | "high";
  opticianRequirement: "required" | "recommended" | "none";
  contractPriority: 1 | 2 | 3;
  equityPriority: "low" | "standard" | "high";
  employees: { name: string; weekly_hours: number; role: "opticien" | "vendeur" }[];
  weekStartDate: string;
  numberOfDays: number;
  openingStartMinutes: number;
  openingEndMinutes: number;
  onCoverageChange: (value: "low" | "standard" | "high") => void;
  onOpticianChange: (value: "required" | "recommended" | "none") => void;
  onContractPriorityChange: (value: 1 | 2 | 3) => void;
  onEquityPriorityChange: (value: "low" | "standard" | "high") => void;
  onEmployeesChange: (
    value: { name: string; weekly_hours: number; role: "opticien" | "vendeur" }[],
  ) => void;
  onWeekStartDateChange: (value: string) => void;
  onNumberOfDaysChange: (value: number) => void;
  onOpeningStartMinutesChange: (value: number) => void;
  onOpeningEndMinutesChange: (value: number) => void;
  onGenerate: () => void;
  loading: boolean;
};

const DecisionPanel = ({
  coverageLevel,
  opticianRequirement,
  contractPriority,
  equityPriority,
  employees,
  weekStartDate,
  numberOfDays,
  openingStartMinutes,
  openingEndMinutes,
  onCoverageChange,
  onOpticianChange,
  onContractPriorityChange,
  onEquityPriorityChange,
  onEmployeesChange,
  onWeekStartDateChange,
  onNumberOfDaysChange,
  onOpeningStartMinutesChange,
  onOpeningEndMinutesChange,
  onGenerate,
  loading,
}: DecisionPanelProps) => {
  const handleEmployeeChange = (
    index: number,
    field: "name" | "weekly_hours" | "role",
    value: string | number,
  ) => {
    const next = employees.map((employee, employeeIndex) =>
      employeeIndex === index ? { ...employee, [field]: value } : employee,
    );
    onEmployeesChange(next);
  };

  const handleAddEmployee = () => {
    onEmployeesChange([
      ...employees,
      { name: `Employee ${employees.length + 1}`, weekly_hours: 35, role: "opticien" },
    ]);
  };

  const handleRemoveEmployee = (index: number) => {
    if (employees.length === 1) {
      return;
    }
    onEmployeesChange(employees.filter((_, employeeIndex) => employeeIndex !== index));
  };

  return (
    <section className="panel">
      <h2>Decision Panel</h2>
      <div className="panel__grid">
        <label>
          Coverage level
          <select value={coverageLevel} onChange={(event) => onCoverageChange(event.target.value as DecisionPanelProps["coverageLevel"])}>
            <option value="low">Low</option>
            <option value="standard">Standard</option>
            <option value="high">High</option>
          </select>
        </label>

        <label>
          Optician requirement
          <select
            value={opticianRequirement}
            onChange={(event) =>
              onOpticianChange(event.target.value as DecisionPanelProps["opticianRequirement"])
            }
          >
            <option value="required">Required</option>
            <option value="recommended">Recommended</option>
            <option value="none">None</option>
          </select>
        </label>

        <label>
          Contract priority
          <select
            value={contractPriority}
            onChange={(event) => onContractPriorityChange(Number(event.target.value) as 1 | 2 | 3)}
          >
            <option value={1}>Priority 1</option>
            <option value={2}>Priority 2</option>
            <option value={3}>Priority 3</option>
          </select>
        </label>

        <label>
          Equity priority
          <select
            value={equityPriority}
            onChange={(event) =>
              onEquityPriorityChange(event.target.value as DecisionPanelProps["equityPriority"])
            }
          >
            <option value="low">Low</option>
            <option value="standard">Standard</option>
            <option value="high">High</option>
          </select>
        </label>
      </div>

      <div className="panel__grid">
        {employees.map((employee, index) => (
          <div key={`${employee.name}-${index}`} className="panel__stack">
            <label>
              Employee name
              <input
                type="text"
                value={employee.name}
                onChange={(event) =>
                  handleEmployeeChange(index, "name", event.target.value)
                }
              />
            </label>

            <label>
              Weekly hours
              <input
                type="number"
                value={employee.weekly_hours}
                onChange={(event) =>
                  handleEmployeeChange(index, "weekly_hours", Number(event.target.value))
                }
              />
            </label>

            <label>
              Role
              <select
                value={employee.role}
                onChange={(event) =>
                  handleEmployeeChange(
                    index,
                    "role",
                    event.target.value as "opticien" | "vendeur",
                  )
                }
              >
                <option value="opticien">opticien</option>
                <option value="vendeur">vendeur</option>
              </select>
            </label>

            <button type="button" onClick={() => handleRemoveEmployee(index)}>
              Remove employee
            </button>
          </div>
        ))}
      </div>

      <div className="panel__grid">
        <label>
          Week start date
          <input
            type="date"
            value={weekStartDate}
            onChange={(event) => onWeekStartDateChange(event.target.value)}
          />
        </label>

        <label>
          Number of days
          <input
            type="number"
            min={1}
            value={numberOfDays}
            onChange={(event) => onNumberOfDaysChange(Number(event.target.value))}
          />
        </label>

        <label>
          Opening start (minutes)
          <input
            type="number"
            value={openingStartMinutes}
            onChange={(event) => onOpeningStartMinutesChange(Number(event.target.value))}
          />
        </label>

        <label>
          Opening end (minutes)
          <input
            type="number"
            value={openingEndMinutes}
            onChange={(event) => onOpeningEndMinutesChange(Number(event.target.value))}
          />
        </label>
      </div>
      <div className="panel__actions">
        <button type="button" onClick={handleAddEmployee}>
          Add employee
        </button>
        <button type="button" onClick={onGenerate} disabled={loading}>
          {loading ? "Generating..." : "Generate"}
        </button>
      </div>
    </section>
  );
};

export default DecisionPanel;
