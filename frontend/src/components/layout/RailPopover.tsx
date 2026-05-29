import { useEffect, useRef, type ReactNode } from "react";

interface RailPopoverProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  anchorRef: React.RefObject<HTMLButtonElement | null>;
}

export function RailPopover({
  open,
  onClose,
  children,
  anchorRef,
}: RailPopoverProps) {
  const popoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        popoverRef.current &&
        !popoverRef.current.contains(target) &&
        anchorRef.current &&
        !anchorRef.current.contains(target)
      ) {
        onClose();
      }
    };

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [open, onClose, anchorRef]);

  if (!open) return null;

  return (
    <div ref={popoverRef} className="rail-popover" data-testid="rail-popover">
      {children}
    </div>
  );
}