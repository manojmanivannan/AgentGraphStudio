import { useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Info } from "lucide-react";

type InfoTooltipProps = {
  content: string;
  ariaLabel: string;
  testId?: string;
};

export function InfoTooltip({ content, ariaLabel, testId }: InfoTooltipProps) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{ left: number; top: number; placeAbove: boolean } | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const tooltipId = useId();

  useLayoutEffect(() => {
    if (!open) return;

    const updatePosition = () => {
      const button = buttonRef.current;
      if (!button) return;

      const rect = button.getBoundingClientRect();
      const tooltipWidth = 280;
      const edgePadding = 8;
      const gap = 6;
      const estimatedTooltipHeight = 72;

      let left = rect.left;
      if (left + tooltipWidth + edgePadding > window.innerWidth) {
        left = Math.max(edgePadding, rect.right - tooltipWidth);
      }

      const canPlaceAbove = rect.top - gap - estimatedTooltipHeight > edgePadding;
      const placeAbove = rect.bottom + gap + estimatedTooltipHeight > window.innerHeight && canPlaceAbove;
      const top = placeAbove ? rect.top - gap : rect.bottom + gap;

      setPosition({ left, top, placeAbove });
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  return (
    <span className="inline-flex items-center">
      <button
        ref={buttonRef}
        type="button"
        aria-label={ariaLabel}
        aria-describedby={open ? tooltipId : undefined}
        data-testid={testId}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="inline-flex items-center justify-center w-4 h-4 rounded-full border border-[var(--color-border-default)] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] hover:border-[var(--color-border-strong)] transition-colors"
      >
        <Info className="w-2.5 h-2.5" />
      </button>

      {open && position && typeof document !== "undefined" && createPortal(
        <span
          id={tooltipId}
          role="tooltip"
          className="fixed z-[80] rounded-md border border-[var(--color-border-default)] bg-[var(--color-surface)] px-2.5 py-2 text-[10px] leading-relaxed text-[var(--color-text-secondary)] shadow-lg"
          style={{
            width: 280,
            left: position.left,
            top: position.top,
            transform: position.placeAbove ? "translateY(-100%)" : undefined,
          }}
        >
          {content}
        </span>,
        document.body
      )}
    </span>
  );
}