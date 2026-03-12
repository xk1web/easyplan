import SimulatorPanel from "./components/SimulatorPanel";

const App = () => {
  return (
    <div className="app">
      <header className="app__header">
        <h1>EasyPlan Cockpit</h1>
      </header>

      <main className="app__content">
        <SimulatorPanel />
      </main>
    </div>
  );
};

export default App;
