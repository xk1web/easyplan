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

  return (
    <div className="card panel__stack">
      <div>Total contract hours: {totalContractHours.toFixed(2)}</div>
      <div>Total required hours: {totalRequiredHours.toFixed(2)}</div>
      <div>Total planned hours: {totalPlannedHours.toFixed(2)}</div>
      <div>Surstaffing hours: {surstaffingHours.toFixed(2)}</div>
      <div>Undercoverage hours: {undercoverageHours.toFixed(2)}</div>
      <div style={tensionStyle(tensionRate)}>Tension rate: {tensionRate.toFixed(2)}</div>
      <div style={tensionStyle(tensionRate)}>{tensionDiagnostic(tensionRate)}</div>
    </div>
  );
};

export default KpiPanel;
