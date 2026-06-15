import { CanvasView } from "@/components/canvas/CanvasView";
import { SidebarRail } from "@/components/layout/SidebarRail";
import { TopBar } from "@/components/layout/TopBar";
import { PropertiesOverlay } from "@/components/PropertiesOverlay";
import { useCanvasStore } from "@/store/canvasStore";

export function AppShell() {
  const selectedNodeId = useCanvasStore((s) => s.selectedNodeId);
  const propertiesWidth = useCanvasStore((s) => s.propertiesWidth);
  const isDraggingPanel = useCanvasStore((s) => s.isDraggingPanel);
  const sidebarCollapsed = useCanvasStore((s) => s.sidebarCollapsed);

  const propertiesOpen = selectedNodeId !== null;
  // Total right-side panel width so the canvas container shrinks and fitView
  // accounts for the area covered by overlay panels.
  const canvasRightOffset = propertiesOpen ? propertiesWidth : 0;
  const canvasLeftOffset = sidebarCollapsed ? 64 : 256;

  return (
    <div className="h-screen w-screen relative overflow-hidden bg-[var(--color-base)]">
      <div
        className={`absolute bottom-0 z-0 ${
          isDraggingPanel ? "" : "transition-all duration-300 ease-out"
        }`}
        style={{ top: 40, left: canvasLeftOffset, right: canvasRightOffset }}
      >
        <CanvasView />
      </div>
      <SidebarRail />
      <PropertiesOverlay />
      {/* Shared across both modes — persists across mode switches */}
      <TopBar />
    </div>
  );
}