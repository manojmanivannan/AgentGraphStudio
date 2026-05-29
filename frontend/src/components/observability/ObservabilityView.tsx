// Proxied through Vite dev server (or Docker nginx) so same-origin iframe works.
// No X-Frame-Options issues since it's served from the same origin.
const MLFLOW_PATH = "/mlflow/";

export function ObservabilityView() {
  return (
    <div className="absolute inset-0 z-0 bg-[var(--color-base)]">
      <iframe
        src={MLFLOW_PATH}
        className="w-full h-full border-none"
        title="MLflow Observability"
      />
    </div>
  );
}