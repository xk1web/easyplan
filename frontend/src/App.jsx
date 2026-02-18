import React, { useState, useCallback } from 'react';

function createDefaultEmployees(count) {
  const emps = [];
  for (let i = 0; i < count; i++) {
    emps.push({
      name: `E${i + 1}`,
      contract: i % 2 === 0 ? 35 : 39,
      role: i % 2 === 0 ? 'opticien' : 'vendeur',
    });
  }
  return emps;
}

function App() {
  const [employees, setEmployees] = useState(createDefaultEmployees(6));
  const [numDays, setNumDays] = useState(30);
  const [minStaff, setMinStaff] = useState(2);
  const [slotMinutes, setSlotMinutes] = useState(30);
  const [startHour, setStartHour] = useState(9);
  const [startMin, setStartMin] = useState(30);
  const [endHour, setEndHour] = useState(20);
  const [endMin, setEndMin] = useState(15);
  const [maxDailyHours, setMaxDailyHours] = useState(10);
  const [maxDaysPerWeek, setMaxDaysPerWeek] = useState(6);
  const [solverTimeout, setSolverTimeout] = useState(30);
  const [contiguity, setContiguity] = useState(false);
  const [fastSolve, setFastSolve] = useState(false);
  const [hoursBalancing, setHoursBalancing] = useState(10);
  const [saturdayFairness, setSaturdayFairness] = useState(5);
  const [contiguityWeight, setContiguityWeight] = useState(3);
  const [longTermEquity, setLongTermEquity] = useState(0.3);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const addEmployee = () => {
    const n = employees.length + 1;
    setEmployees([...employees, {
      name: `E${n}`,
      contract: 35,
      role: 'vendeur',
    }]);
  };

  const removeEmployee = (idx) => {
    if (employees.length <= 1) return;
    setEmployees(employees.filter((_, i) => i !== idx));
  };

  const updateEmployee = (idx, field, value) => {
    const updated = [...employees];
    updated[idx] = { ...updated[idx], [field]: value };
    setEmployees(updated);
  };

  const handleGenerate = async () => {
    setLoading(true);
    setResult(null);
    setError(null);

    const empNames = employees.map(e => e.name);
    const contracts = employees.map(e => e.contract);
    const roles = employees.map(e => e.role);

    const days = [];
    for (let i = 0; i < numDays; i++) {
      days.push(`J${i}`);
    }

    const payload = {
      employees: empNames,
      contracts,
      roles,
      days,
      unavailabilities: [],
      config: {
        schedule: {
          start_time_minutes: startHour * 60 + startMin,
          end_time_minutes: endHour * 60 + endMin,
          slot_minutes: slotMinutes,
          min_staff_per_slot: minStaff,
        },
        hard_constraints: {
          max_daily_minutes: maxDailyHours * 60,
          max_days_per_week: maxDaysPerWeek,
        },
        soft_weights: {
          hours_balancing: hoursBalancing,
          saturday_fairness: saturdayFairness,
          contiguity: contiguity ? contiguityWeight : 0,
        },
        solver: {
          max_time_seconds: solverTimeout,
        },
        fast_solve: fastSolve,
        long_term_equity_weight: longTermEquity,
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
    <div style={{ fontFamily: 'monospace', padding: '20px', maxWidth: '1000px', margin: '0 auto' }}>
      <h1>Planning Test Frontend</h1>

      <fieldset style={{ marginBottom: '15px', padding: '15px' }}>
        <legend><b>Employes</b></legend>

        <table style={{ borderCollapse: 'collapse', marginBottom: '10px', width: '100%' }}>
          <thead>
            <tr>
              <th style={cellStyle}>Nom</th>
              <th style={cellStyle}>Heures/semaine</th>
              <th style={cellStyle}>Role</th>
              <th style={cellStyle}></th>
            </tr>
          </thead>
          <tbody>
            {employees.map((emp, idx) => (
              <tr key={idx}>
                <td style={cellStyle}>
                  <input
                    type="text"
                    value={emp.name}
                    onChange={e => updateEmployee(idx, 'name', e.target.value)}
                    style={{ width: '80px' }}
                  />
                </td>
                <td style={cellStyle}>
                  <input
                    type="number"
                    value={emp.contract}
                    onChange={e => updateEmployee(idx, 'contract', parseInt(e.target.value, 10) || 35)}
                    min={10}
                    max={48}
                    style={{ width: '60px' }}
                  />
                </td>
                <td style={cellStyle}>
                  <select
                    value={emp.role}
                    onChange={e => updateEmployee(idx, 'role', e.target.value)}
                  >
                    <option value="opticien">Opticien</option>
                    <option value="vendeur">Vendeur</option>
                  </select>
                </td>
                <td style={cellStyle}>
                  <button onClick={() => removeEmployee(idx)} disabled={employees.length <= 1}>X</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button onClick={addEmployee}>+ Ajouter employe</button>
      </fieldset>

      <fieldset style={{ marginBottom: '15px', padding: '15px' }}>
        <legend><b>Horaires magasin</b></legend>

        <div style={{ marginBottom: '8px' }}>
          <label>Ouverture: </label>
          <input type="number" value={startHour} onChange={e => setStartHour(parseInt(e.target.value, 10) || 0)} min={0} max={23} style={{ width: '40px' }} />
          <span> h </span>
          <input type="number" value={startMin} onChange={e => setStartMin(parseInt(e.target.value, 10) || 0)} min={0} max={59} step={15} style={{ width: '40px' }} />
          <span> min</span>
        </div>

        <div style={{ marginBottom: '8px' }}>
          <label>Fermeture: </label>
          <input type="number" value={endHour} onChange={e => setEndHour(parseInt(e.target.value, 10) || 0)} min={0} max={23} style={{ width: '40px' }} />
          <span> h </span>
          <input type="number" value={endMin} onChange={e => setEndMin(parseInt(e.target.value, 10) || 0)} min={0} max={59} step={15} style={{ width: '40px' }} />
          <span> min</span>
        </div>

        <div style={{ marginBottom: '8px' }}>
          <label>Nombre de jours: </label>
          <input type="number" value={numDays} onChange={e => setNumDays(parseInt(e.target.value, 10) || 1)} min={1} max={60} style={{ width: '60px' }} />
        </div>
      </fieldset>

      <fieldset style={{ marginBottom: '15px', padding: '15px' }}>
        <legend><b>Contraintes</b></legend>

        <div style={{ marginBottom: '8px' }}>
          <label>Min staff par creneau: </label>
          <input type="number" value={minStaff} onChange={e => setMinStaff(parseInt(e.target.value, 10) || 1)} min={1} max={10} style={{ width: '50px' }} />
        </div>

        <div style={{ marginBottom: '8px' }}>
          <label>Slot (minutes): </label>
          <select value={slotMinutes} onChange={e => setSlotMinutes(parseInt(e.target.value, 10))}>
            <option value={15}>15</option>
            <option value={30}>30</option>
            <option value={60}>60</option>
          </select>
        </div>

        <div style={{ marginBottom: '8px' }}>
          <label>Max heures/jour: </label>
          <input type="number" value={maxDailyHours} onChange={e => setMaxDailyHours(parseInt(e.target.value, 10) || 8)} min={4} max={12} style={{ width: '50px' }} />
        </div>

        <div style={{ marginBottom: '8px' }}>
          <label>Max jours/semaine: </label>
          <input type="number" value={maxDaysPerWeek} onChange={e => setMaxDaysPerWeek(parseInt(e.target.value, 10) || 5)} min={3} max={7} style={{ width: '50px' }} />
        </div>
      </fieldset>

      <fieldset style={{ marginBottom: '15px', padding: '15px' }}>
        <legend><b>Poids soft constraints</b></legend>

        <div style={{ marginBottom: '8px' }}>
          <label>Equilibrage heures: </label>
          <input type="number" value={hoursBalancing} onChange={e => setHoursBalancing(parseInt(e.target.value, 10) || 0)} min={0} max={100} style={{ width: '50px' }} />
        </div>

        <div style={{ marginBottom: '8px' }}>
          <label>Equite samedis: </label>
          <input type="number" value={saturdayFairness} onChange={e => setSaturdayFairness(parseInt(e.target.value, 10) || 0)} min={0} max={100} style={{ width: '50px' }} />
        </div>

        <div style={{ marginBottom: '8px' }}>
          <label>Poids contiguite: </label>
          <input type="number" value={contiguityWeight} onChange={e => setContiguityWeight(parseInt(e.target.value, 10) || 0)} min={0} max={100} style={{ width: '50px' }} />
        </div>

        <div style={{ marginBottom: '8px' }}>
          <label>Equite long terme: </label>
          <input type="number" value={longTermEquity} onChange={e => setLongTermEquity(parseFloat(e.target.value) || 0)} min={0} max={1} step={0.1} style={{ width: '60px' }} />
        </div>
      </fieldset>

      <fieldset style={{ marginBottom: '15px', padding: '15px' }}>
        <legend><b>Solveur</b></legend>

        <div style={{ marginBottom: '8px' }}>
          <label>Timeout (secondes): </label>
          <input type="number" value={solverTimeout} onChange={e => setSolverTimeout(parseInt(e.target.value, 10) || 10)} min={5} max={300} style={{ width: '60px' }} />
        </div>

        <div style={{ marginBottom: '8px' }}>
          <label>
            <input type="checkbox" checked={contiguity} onChange={e => setContiguity(e.target.checked)} />
            {' '}Contiguite activee
          </label>
        </div>

        <div style={{ marginBottom: '8px' }}>
          <label>
            <input type="checkbox" checked={fastSolve} onChange={e => setFastSolve(e.target.checked)} />
            {' '}Fast solve (desactive contiguite + equite samedi)
          </label>
        </div>
      </fieldset>

      <button
        onClick={handleGenerate}
        disabled={loading}
        style={{ padding: '10px 20px', fontSize: '16px', cursor: loading ? 'wait' : 'pointer', marginBottom: '20px' }}
      >
        {loading ? 'Generation en cours...' : 'Generer planning'}
      </button>

      {error && (
        <div style={{ marginTop: '10px', padding: '10px', background: '#ffdddd', border: '1px solid red' }}>
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

          {result.error && (
            <div style={{ marginBottom: '15px', padding: '10px', background: '#ffdddd', border: '1px solid red' }}>
              <b>Erreur solveur:</b> {result.error}
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
  const employees = Object.keys(schedule);

  const allDays = new Set();
  employees.forEach(emp => {
    Object.keys(schedule[emp].days).forEach(d => allDays.add(d));
  });
  const sortedDays = [...allDays].sort((a, b) => {
    const numA = parseInt(a.replace(/\D/g, ''), 10);
    const numB = parseInt(b.replace(/\D/g, ''), 10);
    return numA - numB;
  });

  const countSaturdays = (emp) => {
    let count = 0;
    Object.keys(schedule[emp].days).forEach(d => {
      const idx = parseInt(d.replace(/\D/g, ''), 10);
      if (idx % 7 === 5) count++;
    });
    return count;
  };

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
              <td style={cellStyle}>{schedule[emp].total_hours.toFixed(1)}</td>
              <td style={cellStyle}>{countSaturdays(emp)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Planning par jour</h3>
      {sortedDays.map(day => {
        const present = employees.filter(emp => schedule[emp].days[day]);
        return (
          <div key={day} style={{ marginBottom: '5px' }}>
            <b>{day}</b>: {present.join(', ') || 'Aucun'}
          </div>
        );
      })}
    </>
  );
}

export default App;
