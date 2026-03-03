type DiagnosticPanelProps = {
  loading: boolean;
  error: string | null;
  onClearError: () => void;
  onResetResult: () => void;
  onResetLoading: () => void;
};

const DiagnosticPanel = ({
  loading,
  error,
  onClearError,
  onResetResult,
  onResetLoading,
}: DiagnosticPanelProps) => {
  return (
    <section className="panel">
      <h2>Diagnostics</h2>
      <div className="panel__stack">
        <div>Status: {loading ? "Loading" : "Idle"}</div>
        <div>Error: {error ?? "None"}</div>
        <div className="panel__actions">
          <button type="button" onClick={onResetLoading}>
            Reset Loading
          </button>
          <button type="button" onClick={onResetResult}>
            Clear Result
          </button>
          <button type="button" onClick={onClearError}>
            Clear Error
          </button>
        </div>
      </div>
    </section>
  );
};

export default DiagnosticPanel;
