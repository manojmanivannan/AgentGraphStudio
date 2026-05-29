import { useEffect, useRef, useState, type ReactNode } from "react";

interface OverlayPanelProps {
  open: boolean;
  width: number;
  offsetRight?: number;
  children: ReactNode;
  onClose: () => void;
  "data-testid"?: string;
}

export function OverlayPanel({
  open,
  width,
  offsetRight = 0,
  children,
  onClose,
  "data-testid": dataTestId,
}: OverlayPanelProps) {
  const [visible, setVisible] = useState(false);
  const [exiting, setExiting] = useState(false);
  const prevOpenRef = useRef(open);

  useEffect(() => {
    if (open && !prevOpenRef.current) {
      // Opening
      setVisible(true);
      setExiting(false);
    } else if (!open && prevOpenRef.current) {
      // Closing — play exit animation then unmount
      setExiting(true);
      const timeout = setTimeout(() => {
        setVisible(false);
        setExiting(false);
      }, 200);
      return () => clearTimeout(timeout);
    }
    prevOpenRef.current = open;
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [open, onClose]);

  if (!visible) return null;

  return (
    <div
      data-testid={dataTestId}
      className={`absolute top-0 bottom-0 h-full bg-[var(--color-surface)] border-l border-[var(--color-border-subtle)] z-40 flex flex-col ${
        exiting ? "overlay-panel-exit" : "overlay-panel"
      }`}
      style={{
        width,
        right: offsetRight,
      }}
    >
      {children}
    </div>
  );
}