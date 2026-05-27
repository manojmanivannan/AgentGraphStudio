import { useState, useCallback, useEffect, useRef } from "react";

interface ResizablePanelProps {
  children: React.ReactNode;
  minWidth?: number;
  maxWidth?: number;
  defaultWidth: number;
  className?: string;
  "data-testid"?: string;
}

export function ResizablePanel({
  children,
  minWidth = 200,
  maxWidth = 600,
  defaultWidth,
  className = "",
  "data-testid": dataTestId,
}: ResizablePanelProps) {
  const [width, setWidth] = useState(defaultWidth);
  const dragging = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(0);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      dragging.current = true;
      startX.current = e.clientX;
      startWidth.current = width;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    },
    [width]
  );

  const onMouseMove = useCallback((e: MouseEvent) => {
    if (!dragging.current) return;
    const delta = startX.current - e.clientX;
    const newWidth = Math.min(maxWidth, Math.max(minWidth, startWidth.current + delta));
    // Use requestAnimationFrame to avoid setting state directly in event handler
    setWidth(newWidth);
  }, [minWidth, maxWidth]);

  const onMouseUp = useCallback(() => {
    dragging.current = false;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }, []);

  useEffect(() => {
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
    return () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
  }, [onMouseMove, onMouseUp]);

  return (
    <div
      className={`relative h-full flex flex-col ${className}`}
      style={{ width }}
      data-testid={dataTestId}
    >
      <div
        className="absolute left-0 top-0 bottom-0 w-1 -ml-0.5 cursor-col-resize hover:bg-indigo-400 hover:w-1 transition-colors z-10"
        onMouseDown={onMouseDown}
        data-testid="resize-handle"
      />
      {children}
    </div>
  );
}
