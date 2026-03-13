type EmployeeLoadTableProps = {
  hoursPerEmployee: Record<string, number>;
};

const EmployeeLoadTable = ({ hoursPerEmployee }: EmployeeLoadTableProps) => {
  const entries = Object.entries(hoursPerEmployee);

  if (entries.length === 0) {
    return <p className="empty-state">Aucune charge employe.</p>;
  }

  return (
    <table className="table">
      <thead>
        <tr>
          <th>Employe</th>
          <th>Heures</th>
        </tr>
      </thead>
      <tbody>
        {entries.map(([employee, hours]) => (
          <tr key={employee}>
            <td>{employee}</td>
            <td>{hours}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};

export default EmployeeLoadTable;
