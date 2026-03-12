type RecommendedStaffProps = {
  total_required_hours: number;
  contracts: number[];
};

const RecommendedStaff = ({ total_required_hours, contracts }: RecommendedStaffProps) => {
  const currentStaff = contracts.length;
  const totalContractHours = contracts.reduce((sum, value) => sum + (Number.isFinite(value) ? value : 0), 0);
  const averageContractHours = currentStaff > 0 ? totalContractHours / currentStaff : 35;
  const recommendedStaff =
    averageContractHours > 0 ? Math.max(1, Math.ceil(total_required_hours / averageContractHours)) : 0;

  return (
    <div className="card panel__stack">
      <div>Personnel actuel: {currentStaff}</div>
      <div>Personnel recommande: {recommendedStaff}</div>
    </div>
  );
};

export default RecommendedStaff;
