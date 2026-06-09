import { useEffect } from "react";

export default function ObservabilityPage() {
  useEffect(() => {
    window.location.href = "/mlflow/";
  }, []);

  return (
    <div className="min-h-screen w-full bg-[var(--color-base)] flex items-center justify-center">
      <div className="flex gap-1.5 items-center text-xs text-[var(--color-text-secondary)] font-medium">
        <span>Redirecting to MLflow…</span>
      </div>
    </div>
  );
}
