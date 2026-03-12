type FeasibilityIndicatorProps = {
  total_contract_hours: number;
  total_required_hours: number;
  tension_rate: number;
};

const getScenarioStatus = (
  totalContractHours: number,
  totalRequiredHours: number,
  tensionRate: number,
): { label: string; color: string } => {
  if (tensionRate > 1.05 || totalRequiredHours > totalContractHours) {
    return { label: "Sous-effectif", color: "#b42318" };
  }
  if (tensionRate < 0.95 || totalRequiredHours < totalContractHours) {
    return { label: "Surstaffing", color: "#b54708" };
  }
  return { label: "Faisable", color: "#027a48" };
};

const FeasibilityIndicator = ({
  total_contract_hours,
  total_required_hours,
  tension_rate,
}: FeasibilityIndicatorProps) => {
  const scenario = getScenarioStatus(total_contract_hours, total_required_hours, tension_rate);

  return (
    <div className="card" style={{ borderColor: scenario.color }}>
      <div style={{ color: scenario.color, fontWeight: 600 }}>Statut: {scenario.label}</div>
      <div>Contract hours: {total_contract_hours.toFixed(2)}</div>
      <div>Required hours: {total_required_hours.toFixed(2)}</div>
      <div>Tension rate: {tension_rate.toFixed(2)}</div>
    </div>
  );
};

export default FeasibilityIndicator;
