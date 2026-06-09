import { useEffect, useRef, useState, type ReactNode } from "react";
import { useCanvasStore } from "@/store/canvasStore";

interface OverlayPanelProps {
  open: boolean;
  width: number;
  offsetRight?: number;
  children: ReactNode;
  onClose: () => void;
  "data-testid"?: string;
  resizable?: boolean;
  onWidthChange?: (width: number) => void;
  minWidth?: number;
  maxWidth?: number;
}

export function OverlayPanel({
  open,
  width,
  offsetRight = 0,
  children,
  onClose,
  "data-testid": dataTestId,
  resizable = false,
  onWidthChange,
  minWidth,
  maxWidth,
}: OverlayPanelProps) {
  const [visible, setVisible] = useState(false);
  const [exiting, setExiting] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const setIsDraggingPanel = useCanvasStore((s) => s.setIsDraggingPanel);
  const prevOpenRef = useRef(open);

  useEffect(() => {
    // Always snapshot and update prevOpenRef before any early return
    const prevOpen = prevOpenRef.current;
    prevOpenRef.current = open;

    if (open && !prevOpen) {
      // Opening
      setVisible(true);
      setExiting(false);
    } else if (!open && prevOpen) {
      // Closing — play exit animation then unmount
      setExiting(true);
      const timeout = setTimeout(() => {
        setVisible(false);
        setExiting(false);
      }, 200);
      return () => clearTimeout(timeout);
    }
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

  const handleMouseDown = (e: React.MouseEvent) => {
    if (!resizable || !onWidthChange) return;
    e.preventDefault();
    setIsDragging(true);
    setIsDraggingPanel(true);

    const startX = e.clientX;
    const startWidth = width;

    // Prevent text selection and cursor glitches during drag
    const prevUserSelect = document.body.style.userSelect;
    const prevCursor = document.body.style.cursor;
    document.body.style.userSelect = "none";
    document.body.style.cursor = "ew-resize";

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX;
      let newWidth = startWidth - deltaX;

      if (minWidth !== undefined && newWidth < minWidth) {
        newWidth = minWidth;
      }
      if (maxWidth !== undefined && newWidth > maxWidth) {
        newWidth = maxWidth;
      }

      onWidthChange(newWidth);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      setIsDraggingPanel(false);
      document.body.style.userSelect = prevUserSelect;
      document.body.style.cursor = prevCursor;

      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
  };

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
      {resizable && (
        <div
          className={`resize-handle ${isDragging ? "active" : ""}`}
          onMouseDown={handleMouseDown}
        />
      )}
      {children}
    </div>
  );
}