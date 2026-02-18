import React, { useState } from 'react';

const defaultContracts = '35,35,39,39,35,35,39,39,35,35';

function App() {
  const [numEmployees, setNumEmployees] = useState(10);
  const [contracts, setContracts] = useState(defaultContracts);
  const [minStaff, setMinStaff] = useState(1);
  const [slotMinutes, setSlotMinutes] = useState(30);
  const [contiguity, setContiguity] = useState(false);
  const [fastSolve, setFastSolve] = useState(false);
  const [numDays, setNumDays] = useState(30);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleGenerate = async () => {
    setLoading(true);
    setResult(null);
    setError(null);

    const contractList = contracts.split(',').map(c => parseInt(c.trim(), 10));

    const employees = [];
    const roles = [];
    for (let i = 0; i < numEmployees; i++) {
      employees.push(`E${i + 1}`);
      roles.push(i % 2 === 0 ? 'opticien' : 'vendeur');
    }

    const days = [];
    for (let i = 0; i < numDays; i++) {
      days.push(`J${i}`);
    }

    const finalContracts = [];
    for (let i = 0; i < numEmployees; i++) {
      finalContracts.push(contractList[i % contractList.length]);
    }

    const payload = {
      employees,
      contracts: finalContracts,
      roles,
      days,
      unavailabilities: [],
      config: {
        schedule: {
          slot_minutes: slotMinutes,
          min_staff_per_slot: minStaff,
        },
        soft_weights: {
          contiguity: contiguity ? 3 : 0,
        },
        fast_solve: fastSolve,
      },
      previous_month_stats: null,
    };

    try {
      const res = await fetch('/generate-planning', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ fontFamily: 'monospace', padding: '20px', maxWidth: '900px', margin: '0 auto' }}>
      <h1>Planning Test Frontend</h1>

      <fieldset style={{ marginBottom: '20px', padding: '15px' }}>
        <legend><b>Parametres</b></legend>

        <div style={{ marginBottom: '8px' }}>
          <label>Nombre employes: </label>
          <input type="number" value={numEmployees} onChange={e => setNumEmployees(parseInt(e.target.value, 10) || 1)} min={1} max={20} />
        </div>

        <div style={{ marginBottom: '8px' }}>
          <label>Contrats (CSV heures): </label>
          <input type="text" value={contracts} onChange={e => setContracts(e.target.value)} style={{ width: '300px' }} />
        </div>

        <div style={{ marginBottom: '8px' }}>
          <label>Min staff par slot: </label>
          <input type="number" value={minStaff} onChange={e => setMinStaff(parseInt(e.target.value, 10) || 1)} min={1} max={10} />
        </div>

        <div style={{ marginBottom: '8px' }}>
          <label>Slot minutes: </label>
          <input type="number" value={slotMinutes} onChange={e => setSlotMinutes(parseInt(e.target.value, 10) || 15)} min={15} max={60} step={15} />
        </div>

        <div style={{ marginBottom: '8px' }}>
          <label>Nombre de jours: </label>
          <input type="number" value={numDays} onChange={e => setNumDays(parseInt(e.target.value, 10) || 1)} min={1} max={60} />
        </div>

        <div style={{ marginBottom: '8px' }}>
          <label>
            <input type="checkbox" checked={contiguity} onChange={e => setContiguity(e.target.checked)} />
            {' '}Contiguite
          </label>
        </div>

        <div style={{ marginBottom: '8px' }}>
          <label>
            <input type="checkbox" checked={fastSolve} onChange={e => setFastSolve(e.target.checked)} />
            {' '}Fast solve
          </label>
        </div>
      </fieldset>

      <button
        onClick={handleGenerate}
        disabled={loading}
        style={{ padding: '10px 20px', fontSize: '16px', cursor: loading ? 'wait' : 'pointer' }}
      >
        {loading ? 'Generation en cours...' : 'Generer planning'}
      </button>

      {error && (
        <div style={{ marginTop: '20px', padding: '10px', background: '#ffdddd', border: '1px solid red' }}>
          <b>Erreur:</b> {error}
        </div>
      )}

      {result && (
        <div style={{ marginTop: '20px' }}>
          <h2>Resultats</h2>

          <table style={{ borderCollapse: 'collapse', marginBottom: '15px' }}>
            <tbody>
              <tr><td style={cellStyle}><b>Status</b></td><td style={cellStyle}>{result.status}</td></tr>
              <tr><td style={cellStyle}><b>Solve time</b></td><td style={cellStyle}>{result.solver_time}s</td></tr>
              {result.metrics && (
                <>
                  <tr><td style={cellStyle}><b>Variables</b></td><td style={cellStyle}>{result.metrics.num_variables}</td></tr>
                  <tr><td style={cellStyle}><b>Contraintes</b></td><td style={cellStyle}>{result.metrics.num_constraints}</td></tr>
                  <tr><td style={cellStyle}><b>Gap</b></td><td style={cellStyle}>{result.metrics.gap_percent != null ? result.metrics.gap_percent + '%' : 'N/A'}</td></tr>
                  <tr><td style={cellStyle}><b>Solver status</b></td><td style={cellStyle}>{result.metrics.solver_status}</td></tr>
                </>
              )}
            </tbody>
          </table>

          {result.metrics?.warnings && result.metrics.warnings.length > 0 && (
            <div style={{ marginBottom: '15px', padding: '10px', background: '#ffffdd', border: '1px solid orange' }}>
              <b>Warnings:</b>
              <ul>{result.metrics.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
            </div>
          )}

          {result.schedule && <ScheduleView schedule={result.schedule} />}
        </div>
      )}
    </div>
  );
}

const cellStyle = { border: '1px solid #ccc', padding: '5px 10px' };

function ScheduleView({ schedule }) {
  const employeeStats = schedule.employee_stats || {};
  const dailySchedule = schedule.daily_schedule || {};

  const employees = Object.keys(employeeStats);

  return (
    <>
      <h3>Stats employes</h3>
      <table style={{ borderCollapse: 'collapse', marginBottom: '15px', width: '100%' }}>
        <thead>
          <tr>
            <th style={cellStyle}>Employe</th>
            <th style={cellStyle}>Total heures</th>
            <th style={cellStyle}>Samedis</th>
          </tr>
        </thead>
        <tbody>
          {employees.map(emp => (
            <tr key={emp}>
              <td style={cellStyle}>{emp}</td>
              <td style={cellStyle}>{employeeStats[emp]?.total_hours ?? 'N/A'}</td>
              <td style={cellStyle}>{employeeStats[emp]?.saturdays_worked ?? 'N/A'}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Planning par jour</h3>
      {Object.keys(dailySchedule).length === 0 && <p>Aucune donnee de planning.</p>}
      {Object.entries(dailySchedule).map(([day, data]) => (
        <div key={day} style={{ marginBottom: '10px' }}>
          <b>{day}</b>: {' '}
          {data.employees_present
            ? data.employees_present.join(', ')
            : (data.assignments
              ? Object.keys(data.assignments).join(', ')
              : JSON.stringify(data)
            )
          }
        </div>
      ))}
    </>
  );
}

export default App;
