import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  ArrowLeft,
  Check,
  Eye,
  EyeOff,
  Loader2,
  Save,
  X,
  Zap,
} from "lucide-react";
import {
  getProviderSettings,
  testProviderSettings,
  updateProviderSettings,
} from "@/lib/api";
import { useThemeStore } from "@/store/themeStore";
import type {
  ProviderCheckResult,
  ProviderProfileId,
  ProviderSettingsForm,
} from "@/types";
import {
  PROVIDER_PROFILES,
  applyProfile,
  profileRequiresApiKey,
} from "./providerProfiles";

type Feedback =
  | { kind: "success"; message: string }
  | { kind: "error"; message: string }
  | null;

const CHECK_LABELS: Record<string, string> = {
  chat: "Chat model",
  embedding: "Embedding model",
};

const inputClass =
  "px-3 py-2 bg-[var(--color-inset)] border border-[var(--color-border-default)] rounded-lg text-sm outline-none focus:border-[var(--color-accent)] transition-colors text-[var(--color-text-primary)] placeholder-[var(--color-text-tertiary)]";

function Field({
  id,
  label,
  hint,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  children: (id: string) => React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={id}
        className="text-xs font-medium text-[var(--color-text-secondary)]"
      >
        {label}
      </label>
      {children(id)}
      {hint && (
        <span className="text-[11px] text-[var(--color-text-tertiary)]">{hint}</span>
      )}
    </div>
  );
}

export default function SettingsPage() {
  const theme = useThemeStore((s) => s.theme);

  const [form, setForm] = useState<ProviderSettingsForm | null>(null);
  const [savedDimensions, setSavedDimensions] = useState<number | null>(null);
  const [keyStored, setKeyStored] = useState(false);
  const [source, setSource] = useState<"env" | "database">("env");

  const [apiKey, setApiKey] = useState("");
  const [apiKeyDirty, setApiKeyDirty] = useState(false);
  const [showKey, setShowKey] = useState(false);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [checks, setChecks] = useState<ProviderCheckResult[] | null>(null);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [confirmingReindex, setConfirmingReindex] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const settings = await getProviderSettings();
        if (cancelled) return;
        const { api_key_set, source: loadedSource, ...rest } = settings;
        setForm(rest);
        setSavedDimensions(rest.mem0_embedder_dimensions);
        setKeyStored(api_key_set);
        setSource(loadedSource);
      } catch (err: any) {
        if (!cancelled) {
          setFeedback({
            kind: "error",
            message: err?.message || "Failed to load provider settings.",
          });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Editing any field means the values no longer match the chosen preset.
  const update = useCallback(
    (patch: Partial<ProviderSettingsForm>) => {
      setChecks(null);
      setFeedback(null);
      setForm((prev) => (prev ? { ...prev, ...patch, profile: "custom" } : prev));
    },
    []
  );

  const selectProfile = (profile: ProviderProfileId) => {
    setChecks(null);
    setFeedback(null);
    setForm((prev) => (prev ? applyProfile(profile, prev) : prev));
  };

  const handleTest = async () => {
    if (!form) return;
    setTesting(true);
    setChecks(null);
    setFeedback(null);
    try {
      const result = await testProviderSettings(
        form,
        apiKeyDirty ? apiKey : undefined
      );
      setChecks(result.checks);
    } catch (err: any) {
      setFeedback({
        kind: "error",
        message: err?.message || "Could not run the connection test.",
      });
    } finally {
      setTesting(false);
    }
  };

  const persist = async (confirmReindex: boolean) => {
    if (!form) return;
    setSaving(true);
    setFeedback(null);
    try {
      const saved = await updateProviderSettings(form, {
        apiKey: apiKeyDirty ? apiKey : undefined,
        confirmReindex,
      });
      const { api_key_set, source: savedSource, ...rest } = saved;
      setForm(rest);
      setSavedDimensions(rest.mem0_embedder_dimensions);
      setKeyStored(api_key_set);
      setSource(savedSource);
      setApiKey("");
      setApiKeyDirty(false);
      setConfirmingReindex(false);
      setFeedback({ kind: "success", message: "Provider settings saved." });
    } catch (err: any) {
      setConfirmingReindex(false);
      setFeedback({
        kind: "error",
        message: err?.message || "Failed to save provider settings.",
      });
    } finally {
      setSaving(false);
    }
  };

  const handleSave = async () => {
    if (!form) return;
    if (
      savedDimensions !== null &&
      form.mem0_embedder_dimensions !== savedDimensions
    ) {
      setConfirmingReindex(true);
      return;
    }
    await persist(false);
  };

  return (
    <div className="min-h-screen w-full bg-gradient-to-b from-[var(--color-base)] to-[var(--color-inset)] noise-bg px-4 py-10">
      <div className="mx-auto w-full max-w-3xl">
        <header className="flex items-center gap-3 mb-8">
          <img
            src={
              theme === "dark"
                ? "/agent_graph_studio_logo_white.png"
                : "/agent_graph_studio_logo_dark.png"
            }
            alt="Logo"
            className="h-8 w-auto object-contain"
          />
          <div className="flex-1">
            <h1 className="text-xl font-bold tracking-tight text-[var(--color-text-primary)]">
              Settings
            </h1>
            <p className="text-xs text-[var(--color-text-tertiary)] font-light">
              Model provider used by every agent in this workspace
            </p>
          </div>
          <Link
            to="/"
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-[var(--color-border-default)] text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-elevated)] hover:text-[var(--color-text-primary)] transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back
          </Link>
        </header>

        {loading ? (
          <p className="text-sm text-[var(--color-text-tertiary)]">
            Loading provider settings…
          </p>
        ) : !form ? (
          <p role="alert" className="text-sm text-[var(--color-danger)]">
            {feedback?.message ?? "Provider settings are unavailable."}
          </p>
        ) : (
          <div className="flex flex-col gap-6">
            {source === "env" && (
              <p className="text-xs text-[var(--color-text-tertiary)]">
                Showing the values from the server environment. Saving stores them
                in the database, which then takes precedence.
              </p>
            )}

            {feedback && (
              <div
                role="alert"
                className={`flex items-start gap-2 p-3 rounded-lg border text-xs ${
                  feedback.kind === "success"
                    ? "bg-[var(--color-success-subtle)] border-[var(--color-success)]/30 text-[var(--color-success)]"
                    : "bg-[var(--color-danger-subtle)] border-[var(--color-danger)]/30 text-[var(--color-danger)]"
                }`}
              >
                {feedback.kind === "success" ? (
                  <Check className="w-4 h-4 shrink-0 mt-0.5" />
                ) : (
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                )}
                <p>{feedback.message}</p>
              </div>
            )}

            {/* Profiles */}
            <section className="flex flex-col gap-3">
              <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">
                Provider profile
              </h2>
              <div
                role="radiogroup"
                aria-label="Provider profile"
                className="grid grid-cols-1 sm:grid-cols-2 gap-2"
              >
                {PROVIDER_PROFILES.map((profile) => (
                  <button
                    key={profile.id}
                    type="button"
                    role="radio"
                    aria-label={profile.label}
                    aria-checked={form.profile === profile.id}
                    onClick={() => selectProfile(profile.id)}
                    className={`text-left p-3 rounded-xl border transition-colors ${
                      form.profile === profile.id
                        ? "border-[var(--color-accent)] bg-[var(--color-elevated)]"
                        : "border-[var(--color-border-default)] hover:bg-[var(--color-elevated)]"
                    }`}
                  >
                    <span className="block text-sm font-medium text-[var(--color-text-primary)]">
                      {profile.label}
                    </span>
                    <span className="block text-[11px] text-[var(--color-text-tertiary)] mt-0.5">
                      {profile.description}
                    </span>
                  </button>
                ))}
              </div>
            </section>

            {/* Connection */}
            <section className="flex flex-col gap-4">
              <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">
                Connection
              </h2>

              <Field id="provider-base-url" label="Base URL">
                {(id) => (
                  <input
                    id={id}
                    type="text"
                    value={form.llm_base_url}
                    onChange={(e) => update({ llm_base_url: e.target.value })}
                    className={inputClass}
                    placeholder="http://localhost:11434"
                  />
                )}
              </Field>

              <Field
                id="provider-type"
                label="Provider type"
                hint="ollama for a native Ollama server, openai for any OpenAI-compatible API."
              >
                {(id) => (
                  <select
                    id={id}
                    value={form.llm_provider_type}
                    onChange={(e) => update({ llm_provider_type: e.target.value })}
                    className={inputClass}
                  >
                    <option value="ollama">ollama</option>
                    <option value="openai">openai</option>
                  </select>
                )}
              </Field>

              <Field
                id="provider-api-key"
                label="API key"
                hint={
                  keyStored && !apiKeyDirty
                    ? "A key is stored. Leave blank to keep it."
                    : profileRequiresApiKey(form.profile)
                      ? "Required by this provider."
                      : "Optional for local providers."
                }
              >
                {(id) => (
                  <div className="flex gap-2">
                    <input
                      id={id}
                      type={showKey ? "text" : "password"}
                      value={apiKey}
                      onChange={(e) => {
                        setApiKey(e.target.value);
                        setApiKeyDirty(true);
                        setChecks(null);
                      }}
                      autoComplete="off"
                      className={`${inputClass} flex-1`}
                      placeholder={keyStored ? "••••••••" : "sk-…"}
                    />
                    <button
                      type="button"
                      onClick={() => setShowKey((v) => !v)}
                      aria-label={showKey ? "Hide API key" : "Show API key"}
                      className="px-3 rounded-lg border border-[var(--color-border-default)] text-[var(--color-text-secondary)] hover:bg-[var(--color-elevated)] transition-colors"
                    >
                      {showKey ? (
                        <EyeOff className="w-4 h-4" />
                      ) : (
                        <Eye className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                )}
              </Field>
            </section>

            {/* Models */}
            <section className="flex flex-col gap-4">
              <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">
                Models
              </h2>

              <Field
                id="provider-chat-model"
                label="Chat model"
                hint="Used by every agent on the canvas."
              >
                {(id) => (
                  <input
                    id={id}
                    type="text"
                    value={form.llm_model}
                    onChange={(e) => update({ llm_model: e.target.value })}
                    className={inputClass}
                    placeholder="ollama_chat/llama3.1"
                  />
                )}
              </Field>

              <Field
                id="provider-memory-model"
                label="Memory chat model"
                hint="Used by mem0 to summarise and store memories."
              >
                {(id) => (
                  <input
                    id={id}
                    type="text"
                    value={form.mem0_llm_model}
                    onChange={(e) => update({ mem0_llm_model: e.target.value })}
                    className={inputClass}
                  />
                )}
              </Field>

              <Field
                id="provider-embedding-model"
                label="Embedding model"
                hint="Used for RAG and memory search."
              >
                {(id) => (
                  <input
                    id={id}
                    type="text"
                    value={form.mem0_embedder_model}
                    onChange={(e) => update({ mem0_embedder_model: e.target.value })}
                    className={inputClass}
                  />
                )}
              </Field>

              <Field
                id="provider-embedding-dimensions"
                label="Embedding dimensions"
                hint="Must match the embedding model. Changing it clears stored RAG indexes and memories."
              >
                {(id) => (
                  <input
                    id={id}
                    type="number"
                    min={1}
                    value={form.mem0_embedder_dimensions}
                    onChange={(e) =>
                      update({
                        mem0_embedder_dimensions: Number(e.target.value) || 0,
                      })
                    }
                    className={inputClass}
                  />
                )}
              </Field>
            </section>

            {/* Test results */}
            {checks && (
              <section
                aria-label="Connection test results"
                className="flex flex-col gap-2"
              >
                {checks.map((check) => (
                  <div
                    key={check.name}
                    className={`flex items-start gap-2 p-3 rounded-lg border text-xs ${
                      check.ok
                        ? "bg-[var(--color-success-subtle)] border-[var(--color-success)]/30 text-[var(--color-success)]"
                        : "bg-[var(--color-danger-subtle)] border-[var(--color-danger)]/30 text-[var(--color-danger)]"
                    }`}
                  >
                    {check.ok ? (
                      <Check className="w-4 h-4 shrink-0 mt-0.5" />
                    ) : (
                      <X className="w-4 h-4 shrink-0 mt-0.5" />
                    )}
                    <p>
                      <span className="font-medium">
                        {CHECK_LABELS[check.name] ?? check.name}
                      </span>{" "}
                      — {check.detail} ({check.latency_ms} ms)
                    </p>
                  </div>
                ))}
              </section>
            )}

            {/* Actions */}
            <div className="flex items-center gap-2 pt-2 border-t border-[var(--color-border-subtle)]">
              <button
                type="button"
                onClick={handleTest}
                disabled={testing || saving}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-[var(--color-border-default)] text-sm text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] transition-colors disabled:opacity-50"
              >
                {testing ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Zap className="w-4 h-4" />
                )}
                Test connection
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={saving || testing}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[var(--color-accent)] text-white text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {saving ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Save className="w-4 h-4" />
                )}
                Save changes
              </button>
            </div>
          </div>
        )}
      </div>

      {confirmingReindex && form && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Confirm embedding dimension change"
            className="w-full max-w-md p-5 rounded-2xl bg-[var(--color-surface)] border border-[var(--color-border-default)]"
          >
            <h2 className="text-sm font-semibold text-[var(--color-text-primary)] mb-2">
              Clear stored embeddings?
            </h2>
            <p className="text-xs text-[var(--color-text-secondary)] mb-4">
              Changing the embedding dimension from {savedDimensions} to{" "}
              {form.mem0_embedder_dimensions} makes every stored RAG chunk and
              memory unusable. They will be deleted and re-indexed on next use.
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirmingReindex(false)}
                className="px-3 py-2 rounded-lg border border-[var(--color-border-default)] text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-elevated)] transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => persist(true)}
                disabled={saving}
                className="px-3 py-2 rounded-lg bg-[var(--color-danger)] text-white text-xs font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                Clear and save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
