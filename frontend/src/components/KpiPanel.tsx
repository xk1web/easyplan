type KpiSummary = Record<string, unknown> | null | undefined;

type KpiPanelProps = {
  kpiSummary?: KpiSummary;
};

const getNumber = (source: KpiSummary, keys: string[]) => {
  if (!source) {
    return 0;
  }
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
  }
  return 0;
};

const tensionStyle = (tensionRate: number) => {
  if (tensionRate > 1.05) {
    return { color: "#b42318" };
  }
  if (tensionRate < 0.95) {
    return { color: "#b54708" };
  }
  return { color: "#027a48" };
};

const tensionDiagnostic = (tensionRate: number) => {
  if (tensionRate > 1.05) {
    return "Sous-effectif structurel";
  }
  if (tensionRate < 0.95) {
    return "Surstaffing structurel";
  }
  return "Planning equilibre";
};

const KpiPanel = ({ kpiSummary }: KpiPanelProps) => {
  const totalContractHours = getNumber(kpiSummary, ["total_contract_hours", "total_heures_contractuelles"]);
  const totalRequiredHours = getNumber(kpiSummary, ["total_required_hours", "total_heures_requises_couverture"]);
  const totalPlannedHours = getNumber(kpiSummary, ["total_planned_hours", "total_heures_planifiees"]);
  const surstaffingHours = getNumber(kpiSummary, ["surstaffing_hours", "surstaffing_net"]);
  const undercoverageHours = getNumber(kpiSummary, ["undercoverage_hours", "sous_couverture_nette"]);
  const tensionRate = getNumber(kpiSummary, ["tension_rate", "taux_tension_percent"]);
  const coverageGap = Math.max(0, totalRequiredHours - totalPlannedHours);
  const fillRate = totalRequiredHours > 0 ? (totalPlannedHours / totalRequiredHours) * 100 : 0;

  return (
    <div className="kpi-panel">
      <div className="kpi-card">
        <p>Heures contractuelles</p>
        <strong>{totalContractHours.toFixed(1)}h</strong>
      </div>
      <div className="kpi-card">
        <p>Heures requises</p>
        <strong>{totalRequiredHours.toFixed(1)}h</strong>
      </div>
      <div className="kpi-card">
        <p>Heures planifiées</p>
        <strong>{totalPlannedHours.toFixed(1)}h</strong>
      </div>
      <div className="kpi-card">
        <p>Taux de couverture</p>
        <strong>{fillRate.toFixed(1)}%</strong>
      </div>
      <div className="kpi-card">
        <p>Sous-couverture</p>
        <strong>{Math.max(undercoverageHours, coverageGap).toFixed(1)}h</strong>
      </div>
      <div className="kpi-card">
        <p>Surstaffing</p>
        <strong>{surstaffingHours.toFixed(1)}h</strong>
      </div>
      <div className="kpi-card kpi-card--wide">
        <p>Tension</p>
        <strong style={tensionStyle(tensionRate)}>{tensionRate.toFixed(2)}</strong>
        <span style={tensionStyle(tensionRate)}>{tensionDiagnostic(tensionRate)}</span>
      </div>
    </div>
  );
};

export default KpiPanel;
