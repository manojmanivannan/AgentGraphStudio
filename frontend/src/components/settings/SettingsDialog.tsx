import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Modal } from "@/components/ui/Modal";
import { useSettingsModalStore } from "@/store/settingsModalStore";
import { SETTINGS_SECTIONS, getSettingsSection } from "@/components/settings/registry";

/**
 * The unified Settings dialog: one tabbed modal, mounted once at the app
 * level so it can be opened from any surface (landing, canvas, chat) without
 * navigating away. The store owns open/section state; the `?section=` query
 * param is a write-through mirror so /settings and /account deep links work.
 */
export function SettingsDialog() {
  const open = useSettingsModalStore((s) => s.open);
  const section = useSettingsModalStore((s) => s.section);
  const setSection = useSettingsModalStore((s) => s.setSection);
  const closeSettings = useSettingsModalStore((s) => s.closeSettings);

  const location = useLocation();
  const navigate = useNavigate();

  // Inbound sync: a valid ?section= deep link opens the dialog on that
  // section; an unknown value opens on the default. The store is the source
  // of truth; the URL is mirrored on every change.
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const requested = params.get("section");
    if (!requested && !useSettingsModalStore.getState().open) return;
    const target = getSettingsSection(requested);
    if (target) {
      useSettingsModalStore.getState().openSettings(target.id);
    } else {
      // Unknown (or absent with dialog already open) — keep/restore default.
      useSettingsModalStore.getState().openSettings();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search]);

  // Outbound sync: keep ?section= in the URL while the dialog is open, remove
  // it when closed (replace — closing must not add history entries).
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (open && params.get("section") !== section) {
      params.set("section", section);
      navigate({ search: params.toString() }, { replace: true });
    } else if (!open && params.get("section")) {
      params.delete("section");
      navigate({ search: params.toString() }, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, section]);

  // All sections stay mounted so form state survives tab switches; inactive
  // wrappers are hidden rather than unmounted.
  return (
    <Modal
      open={open}
      onClose={closeSettings}
      title="Settings"
      size="xl"
    >
      <div className="flex flex-col sm:flex-row gap-4 min-h-[320px]">
        <nav
          role="tablist"
          aria-label="Settings"
          className="flex sm:flex-col gap-1 overflow-x-auto sm:overflow-visible shrink-0"
        >
          {SETTINGS_SECTIONS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={section === id}
              aria-controls={`settings-panel-${id}`}
              onClick={() => setSection(id)}
              className={`flex items-center gap-2 px-3 h-9 rounded-lg text-xs font-medium whitespace-nowrap transition-colors cursor-pointer ${
                section === id
                  ? "bg-[var(--color-elevated)] text-[var(--color-text-primary)] border border-[var(--color-border-default)]"
                  : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] border border-transparent"
              }`}
            >
              <Icon className="w-4 h-4 shrink-0" />
              {label}
            </button>
          ))}
        </nav>

        <div className="w-px self-stretch bg-[var(--color-border-subtle)] shrink-0" />

        <div
          data-testid="settings-section-body"
          className="flex-1 min-w-0 overflow-y-auto pr-1"
        >
          {SETTINGS_SECTIONS.map(({ id, label, description, Component }) => {
            const active = section === id;
            return (
              <div
                key={id}
                role="tabpanel"
                id={`settings-panel-${id}`}
                aria-label={`${label} settings`}
                hidden={!active}
              >
                {active && (
                  <div className="mb-4">
                    <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
                      {label}
                    </h3>
                    <p className="text-[11px] text-[var(--color-text-tertiary)]">
                      {description}
                    </p>
                  </div>
                )}
                <div hidden={!active}>
                  <Component />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Modal>
  );
}