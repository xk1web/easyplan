type DecisionPanelProps = {
  coverageLevel: "standard" | "high";
  planningPriority: "team_balance" | "store_performance" | "strict_contracts";
  opticianRequirement: "required" | "recommended";
  employees: { name: string; weekly_hours: number; role: "opticien" | "vendeur" }[];
  weekStartDate: string;
  numberOfDays: number;
  openingStartTime: string;
  openingEndTime: string;
  onCoverageChange: (value: "standard" | "high") => void;
  onPlanningPriorityChange: (value: "team_balance" | "store_performance" | "strict_contracts") => void;
  onOpticianChange: (value: "required" | "recommended") => void;
  onEmployeesChange: (
    value: { name: string; weekly_hours: number; role: "opticien" | "vendeur" }[],
  ) => void;
  onWeekStartDateChange: (value: string) => void;
  onNumberOfDaysChange: (value: number) => void;
  onOpeningStartTimeChange: (value: string) => void;
  onOpeningEndTimeChange: (value: string) => void;
  onGenerate: () => void;
  loading: boolean;
};

const DecisionPanel = ({
  coverageLevel,
  planningPriority,
  opticianRequirement,
  employees,
  weekStartDate,
  numberOfDays,
  openingStartTime,
  openingEndTime,
  onCoverageChange,
  onPlanningPriorityChange,
  onOpticianChange,
  onEmployeesChange,
  onWeekStartDateChange,
  onNumberOfDaysChange,
  onOpeningStartTimeChange,
  onOpeningEndTimeChange,
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
      <h2>Pilotage Planning</h2>

      <div className="decision-section">
        <h3>Configuration magasin</h3>
        <div className="panel__grid">
          <label>
            Date de début
            <input
              type="date"
              value={weekStartDate}
              onChange={(event) => onWeekStartDateChange(event.target.value)}
            />
          </label>

          <label>
            Nombre de jours
            <input
              type="number"
              min={1}
              value={numberOfDays}
              onChange={(event) => onNumberOfDaysChange(Number(event.target.value))}
            />
          </label>

          <label>
            Opening start
            <input
              type="time"
              value={openingStartTime}
              onChange={(event) => onOpeningStartTimeChange(event.target.value)}
            />
          </label>

          <label>
            Opening end
            <input
              type="time"
              value={openingEndTime}
              onChange={(event) => onOpeningEndTimeChange(event.target.value)}
            />
          </label>

          <label>
            Niveau de couverture
            <select
              value={coverageLevel}
              onChange={(event) => onCoverageChange(event.target.value as DecisionPanelProps["coverageLevel"])}
            >
              <option value="standard">Standard</option>
              <option value="high">Renforcé</option>
            </select>
          </label>
        </div>
      </div>

      <div className="decision-section">
        <h3>Équipe</h3>
        <div className="panel__grid">
        {employees.map((employee, index) => (
          <div key={`${employee.name}-${index}`} className="card panel__stack">
            <label>
              Nom
              <input
                type="text"
                value={employee.name}
                onChange={(event) =>
                  handleEmployeeChange(index, "name", event.target.value)
                }
              />
            </label>

            <label>
              Contrat (heures semaine)
              <input
                type="number"
                value={employee.weekly_hours}
                onChange={(event) =>
                  handleEmployeeChange(index, "weekly_hours", Number(event.target.value))
                }
              />
            </label>

            <label>
              Rôle
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
              Supprimer employé
            </button>
          </div>
        ))}
        </div>
        <div className="panel__actions">
          <button type="button" onClick={handleAddEmployee}>
            Ajouter un employé
          </button>
        </div>
      </div>

      <div className="decision-section">
        <h3>Stratégie planning</h3>
        <div className="panel__grid">
        <label>
          Priorité planning
          <select
            value={planningPriority}
            onChange={(event) =>
              onPlanningPriorityChange(event.target.value as DecisionPanelProps["planningPriority"])
            }
          >
            <option value="team_balance">Équilibre équipe</option>
            <option value="store_performance">Performance magasin</option>
            <option value="strict_contracts">Respect strict contrats</option>
          </select>
        </label>

        <label>
          Exigence opticien
          <select
            value={opticianRequirement}
            onChange={(event) =>
              onOpticianChange(event.target.value as DecisionPanelProps["opticianRequirement"])
            }
          >
            <option value="required">Obligatoire</option>
            <option value="recommended">Recommandé</option>
          </select>
        </label>
      </div>
      </div>

      <div className="panel__actions">
        <button type="button" className="button--primary" onClick={onGenerate} disabled={loading}>
          {loading ? "Generating..." : "Generate"}
        </button>
      </div>
    </section>
  );
};

export default DecisionPanel;
