import type { RefObject } from "react";
import { useSearchParams } from "react-router-dom";
import { PrototypeSwitcher } from "@/components/ui/PrototypeSwitcher";
import {
  VariantCurrent,
  VariantA,
  VariantB,
  VariantC,
  type LandingHeroProps,
} from "./LandingHero.prototype";

/**
 * PROTOTYPE ONLY — mounts the landing-hero variants on the existing `/`
 * route, gated by `?variant=`. Defaults to `current` (today's shipped
 * design) so an un-parameterized load is unaffected. Delete this file, the
 * variants, and the switcher import in App.tsx once a direction is chosen
 * (see /prototype skill).
 */
const VARIANTS = [
  { key: "current", label: "Today's cards + orbs" },
  { key: "A", label: "Node board (mini live graph)" },
  { key: "B", label: "Node-styled cards + dot-grid" },
  { key: "C", label: "List + decorative sketch" },
];

export function LandingHeroPrototype(
  props: Omit<LandingHeroProps, "fileInputRef"> & { fileInputRef: RefObject<HTMLInputElement | null> }
) {
  const [searchParams] = useSearchParams();
  const variant = searchParams.get("variant") ?? "current";

  return (
    <>
      {variant === "A" && <VariantA {...props} />}
      {variant === "B" && <VariantB {...props} />}
      {variant === "C" && <VariantC {...props} />}
      {variant !== "A" && variant !== "B" && variant !== "C" && <VariantCurrent {...props} />}
      <PrototypeSwitcher variants={VARIANTS} current={variant} />
    </>
  );
}
