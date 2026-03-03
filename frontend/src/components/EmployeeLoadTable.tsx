type EmployeeLoadTableProps = {
  hoursPerEmployee: Record<string, number>;
};

const EmployeeLoadTable = ({ hoursPerEmployee }: EmployeeLoadTableProps) => {
  const entries = Object.entries(hoursPerEmployee);

  if (entries.length === 0) {
    return <p>No employee load data.</p>;
  }

  return (
    <table className="table">
      <thead>
        <tr>
          <th>Employee</th>
          <th>Hours</th>
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
