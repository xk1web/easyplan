import SimulatorPanel from "./components/SimulatorPanel";

const App = () => {
  return (
    <div className="app">
      <header className="app__header">
        <div className="app__header-content">
          <p className="app__eyebrow">EasyPlan Cockpit</p>
          <h1>Générateur de planning opticiens</h1>
          <p className="app__subtitle">
            Simulez vos contraintes, validez vos KPI et générez un planning hebdomadaire exploitable.
          </p>
        </div>
      </header>

      <main className="app__content">
        <SimulatorPanel />
      </main>
    </div>
  );
};

export default App;
