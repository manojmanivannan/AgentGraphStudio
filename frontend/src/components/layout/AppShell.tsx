import { CanvasView } from "@/components/canvas/CanvasView";
import { SidebarRail } from "@/components/layout/SidebarRail";
import { TopBar } from "@/components/layout/TopBar";
import { PropertiesOverlay } from "@/components/PropertiesOverlay";
import { ChatOverlay } from "@/components/chat/ChatOverlay";
import { ObservabilityView } from "@/components/observability/ObservabilityView";
import { useCanvasStore } from "@/store/canvasStore";

export function AppShell() {
  const observabilityOpen = useCanvasStore((s) => s.observabilityOpen);

  return (
    <div className="h-screen w-screen relative overflow-hidden bg-[var(--color-base)]">
      {observabilityOpen ? (
        /* Observability mode: iframe fills viewport, no sidebar rail */
        <>
          <ObservabilityView />
          <TopBar />
          <ChatOverlay />
        </>
      ) : (
        /* Canvas mode: full canvas + rail + overlays */
        <>
          <div className="absolute inset-0 z-0">
            <CanvasView />
          </div>
          <TopBar />
          <SidebarRail />
          <PropertiesOverlay />
          <ChatOverlay />
        </>
      )}
    </div>
  );
}