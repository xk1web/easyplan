type StatusBadgeProps = {
  status: string;
};

const StatusBadge = ({ status }: StatusBadgeProps) => {
  return <span className="badge">{status}</span>;
};

export default StatusBadge;
