import { useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";

/**
 * PROTOTYPE ONLY — floating bottom bar for cycling `?variant=` options while
 * evaluating a UI prototype. Hidden in production builds. Delete alongside
 * the prototype once a variant is chosen (see /prototype skill, UI.md).
 */
export function PrototypeSwitcher({
  variants,
  current,
  paramName = "variant",
}: {
  variants: { key: string; label: string }[];
  current: string;
  paramName?: string;
}) {
  const navigate = useNavigate();
  const location = useLocation();

  const currentIndex = Math.max(
    0,
    variants.findIndex((v) => v.key === current)
  );

  const go = (delta: number) => {
    const nextIndex = (currentIndex + delta + variants.length) % variants.length;
    const params = new URLSearchParams(location.search);
    params.set(paramName, variants[nextIndex].key);
    navigate(`${location.pathname}?${params.toString()}`, { replace: true });
  };

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) return;
      if (e.key === "ArrowLeft") go(-1);
      if (e.key === "ArrowRight") go(1);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentIndex, location.pathname, location.search]);

  if (import.meta.env.PROD) return null;

  const activeLabel = variants[currentIndex]?.label ?? current;

  return (
    <div
      data-testid="prototype-switcher"
      className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[100] flex items-center gap-1 px-2 py-1.5 rounded-full bg-black/85 text-white text-xs shadow-[0_8px_30px_rgba(0,0,0,0.5)] border border-white/10 backdrop-blur-sm"
    >
      <button
        onClick={() => go(-1)}
        className="p-1 rounded-full hover:bg-white/15"
        aria-label="Previous variant"
      >
        <ChevronLeft className="w-4 h-4" />
      </button>
      <span className="px-2 font-mono font-semibold whitespace-nowrap">
        {current} — {activeLabel}
      </span>
      <button
        onClick={() => go(1)}
        className="p-1 rounded-full hover:bg-white/15"
        aria-label="Next variant"
      >
        <ChevronRight className="w-4 h-4" />
      </button>
    </div>
  );
}
