import type { ComponentType } from "react";
import type { LucideIcon } from "lucide-react";
import { MonitorSmartphone, PlugZap, Palette } from "lucide-react";
import { AccountSection } from "@/components/account/AccountSection";
import { ProviderSection } from "@/components/settings/sections/ProviderSection";
import { AppearanceSection } from "@/components/settings/sections/AppearanceSection";

export type SettingsSectionId = "account" | "providers" | "appearance";

export const DEFAULT_SECTION: SettingsSectionId = "account";

export interface SettingsSection {
  id: SettingsSectionId;
  /** Tab label. */
  label: string;
  /** One-liner shown under the tab's panel title. */
  description: string;
  icon: LucideIcon;
  Component: ComponentType;
}

/**
 * Where to add a new section (e.g. "Model parameters", "Memory"): create the
 * section component, then add exactly one entry here. The SettingsDialog
 * renders whatever the registry defines — no other file changes.
 */
export const SETTINGS_SECTIONS: SettingsSection[] = [
  {
    id: "account",
    label: "Account",
    description: "Your sign-in identity, password and active sessions",
    icon: MonitorSmartphone,
    Component: AccountSection,
  },
  {
    id: "providers",
    label: "Providers",
    description: "Model provider used by every agent in this workspace",
    icon: PlugZap,
    Component: ProviderSection,
  },
  {
    id: "appearance",
    label: "Appearance",
    description: "Theme and display preferences",
    icon: Palette,
    Component: AppearanceSection,
  },
];

/** Tolerant lookup: unknown or missing ids resolve to undefined. */
export function getSettingsSection(id: string | null): SettingsSection | undefined {
  if (!id) return undefined;
  return SETTINGS_SECTIONS.find((s) => s.id === id);
}